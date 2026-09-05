from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from corelib import ai_root
from result_fuse import CaptureBudget, CaptureReceipt, read_page, start_capture_thread
from source_surface import is_reparse_or_symlink


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("._-")[:80] or "tool-output"


def _excerpt(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size
    if size <= limit:
        return path.read_text(encoding="utf-8", errors="replace"), False
    head = max(1, limit * 2 // 3)
    tail = max(1, limit - head)
    with path.open("rb") as stream:
        first = stream.read(head)
        stream.seek(max(0, size - tail))
        last = stream.read(tail)
    message = b"\n... output truncated; use bounded evidence paging ...\n"
    return (first + message + last).decode("utf-8", errors="replace"), True


def _combine_and_hash(path: Path, stdout_part: Path, stderr_part: Path) -> str:
    digest = hashlib.sha256()
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as output:
            for heading, source in ((b"# STDOUT\n", stdout_part), (b"\n# STDERR\n", stderr_part)):
                output.write(heading)
                digest.update(heading)
                with source.open("rb") as stream:
                    while chunk := stream.read(64 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return digest.hexdigest()


def run_bounded(
    root: Path,
    evidence_id: str,
    command: list[str],
    max_chars: int = 4000,
    timeout: int = 900,
    max_spool_bytes: int = 8 * 1024 * 1024,
) -> dict[str, object]:
    if not command:
        raise RuntimeError("a command is required after --")
    folder = ai_root(root) / "evidence" / "tool-output"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_id(evidence_id)}.log"
    stdout_part = folder / f".{path.name}.stdout.{os.getpid()}.tmp"
    stderr_part = folder / f".{path.name}.stderr.{os.getpid()}.tmp"
    per_stream = max(64 * 1024, max_spool_bytes // 2)
    budget = CaptureBudget(max_spool_bytes=per_stream, max_inline_chars=max_chars)
    stdout_receipt = CaptureReceipt()
    stderr_receipt = CaptureReceipt()
    process = subprocess.Popen(
        command,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("command output pipes are unavailable")
    try:
        with stdout_part.open("wb") as stdout_file, stderr_part.open("wb") as stderr_file:
            stdout_thread = start_capture_thread(process.stdout, stdout_file, budget, stdout_receipt)
            stderr_thread = start_capture_thread(process.stderr, stderr_file, budget, stderr_receipt)
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                exit_code = 124
            stdout_thread.join(timeout=30)
            stderr_thread.join(timeout=30)
            if stdout_thread.is_alive() or stderr_thread.is_alive():
                process.kill()
                raise RuntimeError("output capture did not converge")
            stdout_file.flush()
            os.fsync(stdout_file.fileno())
            stderr_file.flush()
            os.fsync(stderr_file.fileno())
        digest = _combine_and_hash(path, stdout_part, stderr_part)
        stdout_excerpt, stdout_inline_truncated = _excerpt(stdout_part, max_chars // 2)
        stderr_excerpt, stderr_inline_truncated = _excerpt(stderr_part, max_chars // 2)
        observed = stdout_receipt.observed_bytes + stderr_receipt.observed_bytes
        stored = stdout_receipt.stored_bytes + stderr_receipt.stored_bytes
        return {
            "exit_code": exit_code,
            "command": command[:1] + (["<arguments omitted from conversation>"] if len(command) > 1 else []),
            "stdout_excerpt": stdout_excerpt,
            "stderr_excerpt": stderr_excerpt,
            "truncated": stdout_receipt.truncated or stderr_receipt.truncated or stdout_inline_truncated or stderr_inline_truncated,
            "evidence_path": path.relative_to(root).as_posix(),
            "evidence_sha256": digest,
            "observed_bytes": observed,
            "stored_bytes": stored,
            "discarded_bytes": max(0, observed - stored),
            "returned_count": len(stdout_excerpt) + len(stderr_excerpt),
            "artifact_reference": path.relative_to(root).as_posix(),
        }
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.stderr.close()
        stdout_part.unlink(missing_ok=True)
        stderr_part.unlink(missing_ok=True)


def read_evidence_page(root: Path, relative: str, offset: int, max_bytes: int) -> dict[str, object]:
    base = ai_root(root).resolve()
    candidate = Path(relative)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        lexical = candidate.resolve(strict=True)
    except OSError as exception:
        raise ValueError("evidence page is missing") from exception
    try:
        lexical.relative_to(base)
    except ValueError as exception:
        raise ValueError("evidence page must stay inside .ai") from exception
    if not lexical.is_file() or is_reparse_or_symlink(lexical):
        raise ValueError("evidence page is missing or is a reparse point")
    return read_page(lexical, offset, max_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行命令并只向会话返回有界摘要")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-id")
    parser.add_argument("--max-output-chars", type=int, default=4000)
    parser.add_argument("--max-spool-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--read-page")
    parser.add_argument("--page-offset", type=int, default=0)
    parser.add_argument("--page-bytes", type=int, default=64 * 1024)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.read_page:
        print(json.dumps({"ok": True, "result": read_evidence_page(root, args.read_page, args.page_offset, args.page_bytes)}, ensure_ascii=False, indent=2))
        return 0
    if not args.evidence_id:
        parser.error("--evidence-id is required when running a command")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = run_bounded(root, args.evidence_id, command, max(500, args.max_output_chars), args.timeout, max(128 * 1024, args.max_spool_bytes))
    print(json.dumps({"ok": result["exit_code"] == 0, "result": result}, ensure_ascii=False, indent=2))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
