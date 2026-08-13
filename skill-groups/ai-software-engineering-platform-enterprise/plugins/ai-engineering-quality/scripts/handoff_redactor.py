from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from qualitylib import write_json

PATTERNS = [
    ("PASSWORD", re.compile(r"(?i)(password|passwd|pwd|密码)\s*[:=：]?\s*([^\s,;，；]{4,})"), "BLOCK"),
    ("BEARER_TOKEN", re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._~+/=-]{12,})"), "BLOCK"),
    ("API_KEY", re.compile(r"(?i)(api[_ -]?key|secret[_ -]?key|access[_ -]?token)\s*[:=：]\s*([A-Za-z0-9._~+/=-]{8,})"), "BLOCK"),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "BLOCK"),
    ("URL_CREDENTIAL", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://([^\s/:]+):([^\s/@]+)@"), "BLOCK"),
]
TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".csv", ".log"}


def redact_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    output = text
    for name, pattern, severity in PATTERNS:
        matches = list(pattern.finditer(output))
        for match in matches:
            findings.append({"type": name, "severity": severity, "offset": match.start(), "length": len(match.group(0))})
        if name == "PRIVATE_KEY":
            output = pattern.sub("[REDACTED_PRIVATE_KEY]", output)
        elif name == "URL_CREDENTIAL":
            output = pattern.sub(lambda m: m.group(0).replace(m.group(1), "[REDACTED_USER]").replace(m.group(2), "[REDACTED_SECRET]"), output)
        else:
            output = pattern.sub(lambda m: m.group(1) + "[REDACTED]", output)
    return output, findings


def scan(source: Path, output: Path | None, max_files: int = 500, max_bytes: int = 2_000_000) -> dict[str, Any]:
    files = [source] if source.is_file() else [path for path in sorted(source.rglob("*")) if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES]
    files = files[:max_files]
    findings: list[dict[str, Any]] = []
    written: list[str] = []
    for path in files:
        if path.stat().st_size > max_bytes:
            findings.append({"path": str(path), "type": "FILE_TOO_LARGE", "severity": "WARN"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        redacted, hits = redact_text(text)
        for hit in hits:
            findings.append({"path": str(path), **hit})
        if output is not None:
            target = output if source.is_file() else output / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True); target.write_text(redacted, encoding="utf-8", newline="\n"); written.append(str(target))
    blockers = [item for item in findings if item.get("severity") == "BLOCK"]
    return {
        "schema_version": 1, "result": "BLOCK" if blockers else "PASS", "scanned_files": len(files),
        "findings": findings, "redacted_outputs": written,
        "export_allowed": not blockers or output is not None,
        "rule": "raw handoff export is blocked when secrets are present; only verified redacted output may be packaged",
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--source", required=True); parser.add_argument("--output"); parser.add_argument("--report", required=True)
    args = parser.parse_args(); result = scan(Path(args.source).resolve(), Path(args.output).resolve() if args.output else None)
    write_json(Path(args.report).resolve(), result); print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["export_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
