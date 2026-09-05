from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from corelib import ai_root, atomic_write_bytes, atomic_write_text
from resource_budget import effective_value


SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:password|passwd|token|api[_-]?key|secret)\s*[=:]\s*)[^\s,;]+"),
)
ARTIFACT_SCHEMA = "hiker-bounded-artifact/v1"
ARTIFACT_PREFIX = "artifact://tool-output/"
ARTIFACT_PAGE_CHARS = 1024 * 1024
REDACTION_OVERLAP_CHARS = 4096


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("._-")[:80] or "tool-output"


def _excerpt(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size
    if size <= limit:
        return path.read_text(encoding="utf-8", errors="replace"), False
    head = max(1, limit * 2 // 3)
    tail = max(1, limit - head)
    return text[:head].rstrip() + "\n... 已截断，完整脱敏输出见 artifact_reference ...\n" + text[-tail:].lstrip(), True


class _Excerpt:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self.head_limit = max(1, self.limit * 2 // 3)
        self.tail_limit = max(1, self.limit - self.head_limit)
        self.head = ""
        self.tail = ""
        self.small: str | None = ""
        self.total = 0

    def add(self, text: str) -> None:
        self.total += len(text)
        if self.small is not None:
            combined = self.small + text
            self.small = combined if len(combined) <= self.limit else None
        if len(self.head) < self.head_limit:
            self.head += text[:self.head_limit - len(self.head)]
        self.tail = (self.tail + text)[-self.tail_limit:]

    def result(self) -> tuple[str, bool]:
        if self.small is not None:
            return self.small, False
        value = self.head.rstrip() + "\n... 已截断，完整脱敏输出见 artifact_reference ...\n" + self.tail.lstrip()
        return value, True


class _SpoolBudget:
    def __init__(self, maximum: int) -> None:
        self.remaining = maximum
        self.captured = 0
        self.discarded = 0
        self.lock = threading.Lock()

    def take(self, size: int) -> int:
        with self.lock:
            allowed = min(size, self.remaining)
            self.remaining -= allowed
            self.captured += allowed
            self.discarded += size - allowed
            return allowed


def _capture_process(root: Path, command: list[str], raw_stdout: Path, raw_stderr: Path, timeout: int, maximum: int) -> tuple[int, dict]:
    budget = _SpoolBudget(maximum)
    process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def drain(source: object, target: Path) -> None:
        try:
            with target.open("wb") as stream:
                while True:
                    chunk = source.read(65_536)
                    if not chunk:
                        break
                    allowed = budget.take(len(chunk))
                    if allowed:
                        stream.write(chunk[:allowed])
        finally:
            source.close()

    threads = [
        threading.Thread(target=drain, args=(process.stdout, raw_stdout), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, raw_stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for thread in threads:
        thread.join()
    return (124 if timed_out else int(process.returncode or 0)), {
        "maximum_bytes": maximum,
        "captured_bytes": budget.captured,
        "discarded_bytes": budget.discarded,
        "overflow": budget.discarded > 0,
        "timed_out": timed_out,
    }


def _spool_channel(
    raw_path: Path,
    spool_dir: Path,
    channel: str,
    excerpt_limit: int,
    evidence_digest: object,
) -> tuple[dict, str, bool]:
    pages: list[dict] = []
    page_buffer = ""
    carry = ""
    page_number = 0
    total_chars = 0
    summary = _Excerpt(excerpt_limit)

    def write_page(content: str) -> None:
        nonlocal page_number
        page_number += 1
        name = f"{channel}-{page_number:06d}.log"
        (spool_dir / name).write_text(content, encoding="utf-8")
        pages.append({
            "page": page_number,
            "path": name,
            "chars": len(content),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })

    def accept(content: str) -> None:
        nonlocal page_buffer, total_chars
        if not content:
            return
        total_chars += len(content)
        evidence_digest.update(content.encode("utf-8"))
        summary.add(content)
        page_buffer += content
        while len(page_buffer) >= ARTIFACT_PAGE_CHARS:
            write_page(page_buffer[:ARTIFACT_PAGE_CHARS])
            page_buffer = page_buffer[ARTIFACT_PAGE_CHARS:]

    with raw_path.open("r", encoding="utf-8", errors="replace") as stream:
        while True:
            chunk = stream.read(ARTIFACT_PAGE_CHARS)
            if not chunk:
                break
            combined = carry + chunk
            if len(combined) <= REDACTION_OVERLAP_CHARS:
                carry = combined
                continue
            accept(redact(combined[:-REDACTION_OVERLAP_CHARS]))
            carry = combined[-REDACTION_OVERLAP_CHARS:]
    accept(redact(carry))
    if page_buffer:
        write_page(page_buffer)
    excerpt_value, truncated = summary.result()
    return {"chars": total_chars, "pages": pages}, excerpt_value, truncated


def _publish_artifact(root: Path, evidence_id: str, command: list[str], raw_stdout: Path, raw_stderr: Path, max_chars: int, spool: dict) -> tuple[dict, str, str, bool]:
    artifact_id = safe_id(evidence_id)
    artifact_root = ai_root(root) / "evidence" / "tool-output" / artifact_id
    artifact_reference = ARTIFACT_PREFIX + artifact_id
    evidence_digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="hiker-redacted-spool-") as td:
        spool_dir = Path(td)
        evidence_digest.update(b"# STDOUT\n")
        stdout, stdout_excerpt, stdout_truncated = _spool_channel(raw_stdout, spool_dir, "stdout", max_chars // 2, evidence_digest)
        evidence_digest.update(b"\n# STDERR\n")
        stderr, stderr_excerpt, stderr_truncated = _spool_channel(raw_stderr, spool_dir, "stderr", max_chars // 2, evidence_digest)
        digest = evidence_digest.hexdigest()
        generation = digest[:24]
        generation_dir = artifact_root / generation
        generation_dir.mkdir(parents=True, exist_ok=True)
        for page in stdout["pages"] + stderr["pages"]:
            content = (spool_dir / page["path"]).read_text(encoding="utf-8")
            destination = generation_dir / page["path"]
            current = destination.read_bytes() if destination.is_file() else None
            if current is None or hashlib.sha256(current).hexdigest() != page["sha256"]:
                atomic_write_bytes(generation_dir / page["path"], content.encode("utf-8"))
        index = {
            "schema_version": ARTIFACT_SCHEMA,
            "artifact_reference": artifact_reference,
            "artifact_id": artifact_id,
            "generation": generation,
            "evidence_sha256": digest,
            "command": command[:1] + (["<arguments omitted from artifact index>"] if len(command) > 1 else []),
            "channels": {"stdout": stdout, "stderr": stderr},
            "captured_chars": stdout["chars"] + stderr["chars"],
            "page_size_chars": ARTIFACT_PAGE_CHARS,
            "redaction_status": "PASS",
            "spool": spool,
        }
        atomic_write_text(artifact_root / "index.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return index, stdout_excerpt, stderr_excerpt, stdout_truncated or stderr_truncated


def run_bounded(root: Path, evidence_id: str, command: list[str], max_chars: int = 4000, timeout: int = 900, max_artifact_bytes: int | None = None) -> dict:
    max_chars = effective_value("output", "command_output_chars", max_chars)
    max_artifact_bytes = effective_value("output", "artifact_spool_bytes", max_artifact_bytes)
    if not command:
        raise RuntimeError("a command is required after --")
    with tempfile.TemporaryDirectory(prefix="hiker-command-spool-") as td:
        raw_stdout = Path(td) / "stdout.raw"
        raw_stderr = Path(td) / "stderr.raw"
        exit_code, spool = _capture_process(root, command, raw_stdout, raw_stderr, timeout, max_artifact_bytes)
        index, stdout_excerpt, stderr_excerpt, truncated = _publish_artifact(root, evidence_id, command, raw_stdout, raw_stderr, max_chars, spool)
    index_path = ai_root(root) / "evidence" / "tool-output" / safe_id(evidence_id) / "index.json"
    return {
        "exit_code": exit_code,
        "command": command[:1] + (["<arguments omitted from conversation>"] if len(command) > 1 else []),
        "stdout_excerpt": stdout_excerpt,
        "stderr_excerpt": stderr_excerpt,
        "truncated": truncated,
        "artifact_reference": index["artifact_reference"],
        "evidence_path": index_path.relative_to(root).as_posix(),
        "evidence_sha256": index["evidence_sha256"],
        "captured_chars": index["captured_chars"],
        "artifact_pages": sum(len(channel["pages"]) for channel in index["channels"].values()),
        "spool": index["spool"],
    }


def retrieve_artifact(root: Path, artifact_reference: str, channel: str, page: int, offset: int = 0, max_chars: int = 4000) -> dict:
    if not artifact_reference.startswith(ARTIFACT_PREFIX):
        raise ValueError("unsupported artifact reference")
    artifact_id = artifact_reference[len(ARTIFACT_PREFIX):]
    if not artifact_id or safe_id(artifact_id) != artifact_id or channel not in {"stdout", "stderr"} or page < 1 or offset < 0:
        raise ValueError("invalid bounded artifact request")
    index_path = ai_root(root) / "evidence" / "tool-output" / artifact_id / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema_version") != ARTIFACT_SCHEMA or index.get("artifact_reference") != artifact_reference:
        raise ValueError("artifact index is invalid")
    pages = index.get("channels", {}).get(channel, {}).get("pages", [])
    if page > len(pages):
        raise ValueError("artifact page is out of range")
    record = pages[page - 1]
    path = index_path.parent / str(index["generation"]) / str(record["path"])
    content = path.read_text(encoding="utf-8")
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != record.get("sha256"):
        raise ValueError("artifact page integrity check failed")
    max_chars = effective_value("output", "command_output_chars", max_chars)
    chunk = content[offset:offset + max_chars]
    next_offset = offset + len(chunk)
    return {
        "artifact_reference": artifact_reference,
        "channel": channel,
        "page": page,
        "page_count": len(pages),
        "offset": offset,
        "content": chunk,
        "content_sha256": record["sha256"],
        "next_offset": next_offset if next_offset < len(content) else None,
        "next_page": page + 1 if next_offset >= len(content) and page < len(pages) else None,
        "bounded": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行命令并只向会话返回有界摘要")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-id")
    parser.add_argument("--max-output-chars", type=int, default=4000)
    parser.add_argument("--max-spool-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-artifact-bytes", type=int)
    parser.add_argument("--retrieve-artifact")
    parser.add_argument("--channel", choices=("stdout", "stderr"), default="stdout")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.retrieve_artifact:
        try:
            retrieved = retrieve_artifact(root, args.retrieve_artifact, args.channel, args.page, args.offset, args.max_output_chars)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps({"ok": True, "result": retrieved}, ensure_ascii=False, indent=2))
        return 0
    if not args.evidence_id:
        parser.error("--evidence-id is required when executing a command")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = run_bounded(root, args.evidence_id, command, max(500, args.max_output_chars), args.timeout, args.max_artifact_bytes)
    print(json.dumps({"ok": result["exit_code"] == 0, "result": result}, ensure_ascii=False, indent=2))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
