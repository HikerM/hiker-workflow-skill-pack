from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from qualitylib import git, git_root, posix


TEXT_EXTENSIONS = {
    ".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".css", ".scss", ".less", ".json", ".yaml", ".yml", ".xml", ".xaml",
    ".cs", ".java", ".kt", ".swift", ".dart", ".cpp", ".h", ".qml",
}
EXCLUDED_PARTS = {
    ".git", ".ai", "test", "tests", "__tests__", "fixture", "fixtures",
    "mock", "mocks", "example", "examples", "evals", "docs", "node_modules",
    "dist", "build", "bin", "obj", "library", "temp",
}
PLACEHOLDER_PATTERNS = (
    ("PLACEHOLDER_TEXT", re.compile(r"(?i)\b(lorem ipsum|coming soon|tbd|todo)\b")),
    ("DEMO_TEXT", re.compile(r"(?i)(演示数据|测试数据|占位数据|假数据|示例用户|sample user|demo data|mock data)")),
)
INTERNAL_PATTERNS = (
    ("STACK_TRACE_EXPOSURE", re.compile(r"(?i)(stack trace|traceback \(most recent call last\)|at [\w.$]+\([^)]*:\d+\))")),
    ("DATABASE_ERROR_EXPOSURE", re.compile(r"(?i)(sqlstate|syntax error at or near|database exception|table .* does not exist)")),
    ("INTERNAL_PATH_EXPOSURE", re.compile(
        r"(?i)([A-Z]:\\Users\\[^\\\s]+\\|" + r"/Users/" + r"[^/\s]+/|" + r"/home/" + r"[^/\s]+/)"
    )),
)
UNSAFE_RUNTIME_PATTERNS = (
    ("DEMO_DEFAULT_ENABLED", re.compile(r"(?i)\b(DEMO_MODE|ENABLE_DEMO|USE_DEMO_DATA)\b\s*[:=]\s*(true|1|['\"]true['\"])")),
    ("MOCK_DEFAULT_ENABLED", re.compile(r"(?i)\b(USE_MOCK|ENABLE_MOCK|MOCK_API)\b\s*[:=]\s*(true|1|['\"]true['\"])")),
    ("RUNTIME_FIXTURE_IMPORT", re.compile(r"(?i)(from\s+['\"][^'\"]*(fixture|mock|demo)[^'\"]*['\"]|require\(['\"][^'\"]*(fixture|mock|demo))")),
)


def _is_runtime_file(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    return not bool(parts & EXCLUDED_PARTS) and Path(path).suffix.lower() in TEXT_EXTENSIONS


def _tracked_files(root: Path, mode: str) -> list[str]:
    if mode == "changed":
        names: set[str] = set()
        for args in (("diff", "--name-only", "-z"), ("diff", "--cached", "--name-only", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
            result = git(root, *args, check=False)
            names.update(posix(item) for item in result.stdout.split("\0") if item)
        return sorted(names)
    result = git(root, "ls-files", "-z", check=False)
    return [posix(item) for item in result.stdout.split("\0") if item][:20_000]


def _looks_user_visible(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith(("//", "/*", "*", "#")):
        return False
    return bool(re.search(r"(['\"]).+\1|<[^>]+>|\b(text|label|title|message|description|placeholder)\s*[:=]", line, re.I))


def audit(root: Path, mode: str = "changed", extra_artifacts: list[Path] | None = None) -> dict[str, Any]:
    try:
        root = git_root(root)
    except Exception:
        root = root.resolve()
    files = _tracked_files(root, mode) if (root / ".git").exists() or git(root, "rev-parse", "--git-dir", check=False).returncode == 0 else []
    for artifact in extra_artifacts or []:
        target = artifact.resolve()
        if target.is_file() and root in target.parents:
            files.append(target.relative_to(root).as_posix())
    findings: list[dict[str, Any]] = []
    scanned = 0
    for relative in sorted(set(files)):
        if not _is_runtime_file(relative):
            continue
        path = root / relative
        try:
            if path.stat().st_size > 2_000_000:
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        scanned += 1
        for number, line in enumerate(lines, 1):
            for code, pattern in UNSAFE_RUNTIME_PATTERNS:
                if pattern.search(line):
                    findings.append({"severity": "block", "code": code, "path": relative, "line": number})
            if _looks_user_visible(line):
                for code, pattern in PLACEHOLDER_PATTERNS + INTERNAL_PATTERNS:
                    if pattern.search(line):
                        severity = "block" if mode == "release" else "warn"
                        findings.append({"severity": severity, "code": code, "path": relative, "line": number})
            if len(findings) >= 100:
                break
        if len(findings) >= 100:
            break
    blocked = [item for item in findings if item["severity"] == "block"]
    return {
        "ok": not blocked,
        "status": "BLOCK" if blocked else ("WARN" if findings else "PASS"),
        "mode": mode,
        "scanned_files": scanned,
        "finding_count": len(findings),
        "findings": findings,
        "bounded": True,
        "max_findings": 100,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查正式交付中的占位、演示、Mock和内部诊断残留")
    parser.add_argument("--root", default=".")
    parser.add_argument("--mode", choices=("changed", "release"), default="changed")
    parser.add_argument("--artifact", action="append", default=[])
    args = parser.parse_args()
    result = audit(Path(args.root), args.mode, [Path(item) for item in args.artifact])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
