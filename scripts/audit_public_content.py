from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".py", ".ps1", ".sh", ".cmd", ".toml", ".xml", ".ts", ".js"}
PATTERNS = (
    ("EMAIL", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("THREAD_OR_GUID", re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")),
    (
        "WINDOWS_USER_PATH",
        re.compile(
            r"(?i)\b[A-Z]:(?:\\+|/+)Users(?:\\+|/+)(?!<|%)[^\\/\s<>\"]+(?:\\+|/+)"
        ),
    ),
    (
        "UNIX_USER_PATH",
        re.compile(
            r"(?i)(?:\\?/)(?:Users|home)(?:\\?/)(?!<|\$|\{)[^/\\\s<>\"]+(?:\\?/)"
        ),
    ),
    ("CREDENTIAL_URL", re.compile(r"(?i)https?://[^\s/:]+:[^\s/@]+@")),
    (
        "SECRET_LITERAL",
        re.compile(
            r"(?i)(?:api[_-]?key|password|passwd|private[_-]?key|access[_-]?token|client[_-]?secret)"
            r"\s*[:=]\s*['\"](?!<|\$\{|%|\*{3}|REDACTED|YOUR_)[^'\"]{8,}['\"]"
        ),
    ),
    ("BEARER_TOKEN", re.compile(r"(?i)\bBearer\s+(?!<|\$\{|REDACTED)[A-Z0-9._~+/-]{20,}={0,2}\b")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


def _tracked_files(root: Path) -> list[Path]:
    files: set[str] = set()
    for args in (("ls-files", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        files.update(item for item in result.stdout.split("\0") if item)
    return [root / item for item in sorted(files)]


def _scan_text(name: str, text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for code, pattern in PATTERNS:
            if pattern.search(line):
                findings.append({"code": code, "path": name, "line": line_no})
    return findings


def _zip_texts(path: Path) -> Iterable[tuple[str, str]]:
    try:
        with zipfile.ZipFile(path) as bundle:
            for info in bundle.infolist():
                if info.is_dir() or Path(info.filename).suffix.lower() not in TEXT_SUFFIXES or info.file_size > 2_000_000:
                    continue
                yield f"{path.name}!/{info.filename}", bundle.read(info).decode("utf-8", errors="ignore")
    except (OSError, zipfile.BadZipFile):
        return


def audit(root: Path) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    scanned = 0
    for path in _tracked_files(root):
        if path.suffix.lower() == ".zip":
            for name, text in _zip_texts(path):
                scanned += 1
                findings.extend(_scan_text(name, text))
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        relative = path.relative_to(root).as_posix()
        findings.extend(_scan_text(relative, text))
        if path.name == "plugin.json":
            try:
                manifest = json.loads(text)
            except json.JSONDecodeError:
                continue
            author = manifest.get("author") if isinstance(manifest.get("author"), dict) else {}
            identities = [author.get("name"), (manifest.get("interface") or {}).get("developerName")]
            for value in identities:
                if value and value != "Hiker":
                    findings.append({"code": "NON_CANONICAL_AUTHOR", "path": relative, "line": 1})
    return {
        "ok": not findings,
        "allowed_product_identifiers": ["Hiker", "hikerctl", "HIKER_CONTROL_*"],
        "scanned_text_entries": scanned,
        "finding_count": len(findings),
        "findings": findings[:200],
        "truncated": len(findings) > 200,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="审核公开仓库是否包含个人、公司、项目或凭据类敏感信息")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = audit(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
