from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from corelib import ai_root, atomic_write_text


SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:password|passwd|token|api[_-]?key|secret)\s*[=:]\s*)[^\s,;]+"),
)


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("._-")[:80] or "tool-output"


def redact(text: str) -> str:
    output = text
    for pattern in SECRET_PATTERNS:
        output = pattern.sub(r"\1[REDACTED]", output)
    return output


def excerpt(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = max(1, limit * 2 // 3)
    tail = max(1, limit - head)
    return text[:head].rstrip() + "\n... 已截断，完整脱敏输出见证据文件 ...\n" + text[-tail:].lstrip(), True


def run_bounded(root: Path, evidence_id: str, command: list[str], max_chars: int = 4000, timeout: int = 900) -> dict:
    if not command:
        raise RuntimeError("a command is required after --")
    result = subprocess.run(command, cwd=root, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    stdout = redact(result.stdout or "")
    stderr = redact(result.stderr or "")
    evidence = "\n".join(("# STDOUT", stdout, "", "# STDERR", stderr)).rstrip() + "\n"
    path = ai_root(root) / "evidence" / "tool-output" / f"{safe_id(evidence_id)}.log"
    atomic_write_text(path, evidence)
    digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
    stdout_excerpt, stdout_truncated = excerpt(stdout, max_chars // 2)
    stderr_excerpt, stderr_truncated = excerpt(stderr, max_chars // 2)
    return {
        "exit_code": result.returncode,
        "command": command[:1] + (["<arguments omitted from conversation>"] if len(command) > 1 else []),
        "stdout_excerpt": stdout_excerpt,
        "stderr_excerpt": stderr_excerpt,
        "truncated": stdout_truncated or stderr_truncated,
        "evidence_path": path.relative_to(root).as_posix(),
        "evidence_sha256": digest,
        "captured_chars": len(stdout) + len(stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行命令并只向会话返回有界摘要")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--max-output-chars", type=int, default=4000)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = run_bounded(Path(args.root).resolve(), args.evidence_id, command, max(500, args.max_output_chars), args.timeout)
    print(json.dumps({"ok": result["exit_code"] == 0, "result": result}, ensure_ascii=False, indent=2))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
