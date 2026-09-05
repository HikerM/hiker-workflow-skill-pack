from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from source_surface import TraversalBudget,read_bounded_text,walk_source_files


SKIP = {".git", ".ai", "build", "bin", "obj", "dist", ".venv", "venv", "node_modules"}
SUFFIXES = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".qml", ".ui", ".qrc", ".pro", ".pri", ".cmake", ".py"}


def bounded_files(root: Path, max_depth: int = 7, max_files: int = 4000) -> tuple[list[Path], bool]:
    root=root.resolve();paths,_=walk_source_files(root,TraversalBudget(max_depth=max_depth,max_directories=4096,max_entries=50000,max_files=max(20000,max_files*10),max_observed_bytes=2*1024*1024*1024,max_elapsed_ms=10000),ignored_directories=frozenset(name.casefold() for name in SKIP),include=lambda path:path.stat().st_size<=8*1024*1024 and (path.suffix.lower() in SUFFIXES or path.name in {"CMakeLists.txt","qt.conf"}))
    return paths[:max_files],len(paths)>max_files


def text(path: Path) -> str:
    try:
        value,truncated=read_bounded_text(path,8*1024*1024);return "" if truncated else value
    except OSError:
        return ""


def relative(paths: Iterable[Path], root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in list(paths)[:80]]


def item(paths: list[Path], root: Path, findings: list[dict[str, str]] | None = None, required: bool = False, note: str | None = None) -> dict[str, Any]:
    issues = findings or []
    status = "FAIL" if any(value.get("severity") == "HIGH" for value in issues) else "PASS" if paths and not issues else "GAP"
    if required and not paths:
        status = "BLOCKED"
    result: dict[str, Any] = {"status": status, "evidence": relative(paths, root), "findings": issues}
    if note:
        result["note"] = note
    return result


def issue(rule: str, path: Path, root: Path, severity: str = "MEDIUM") -> dict[str, str]:
    return {"severity": severity, "rule": rule, "path": path.relative_to(root).as_posix()}


def audit(root: Path) -> dict[str, Any]:
    root = root.resolve(); files, truncated = bounded_files(root)
    cmake = [path for path in files if path.name == "CMakeLists.txt" or path.suffix.lower() == ".cmake"]
    qmake = [path for path in files if path.suffix.lower() in {".pro", ".pri"}]
    build_files = cmake + qmake
    build_text = "\n".join(text(path) for path in build_files)
    version_match = re.search(r"find_package\s*\(\s*Qt(?P<major>[56])(?:\s+(?P<version>\d+(?:\.\d+){1,3}))?", build_text, re.I)
    qt_major = version_match.group("major") if version_match else "unknown"
    qt_version = version_match.group("version") if version_match and version_match.group("version") else "unknown"
    source = [path for path in files if path.suffix.lower() in {".cpp", ".cc", ".cxx", ".h", ".hpp", ".qml", ".py"}]
    signal_slot = [path for path in source if re.search(r"\b(?:signals|slots)\s*:|\bconnect\s*\(|Signal\s*\(|Slot\s*\(", text(path))]
    ownership = [path for path in source if re.search(r"\b(?:QObject|QPointer|QScopedPointer|std::unique_ptr)\b|deleteLater\s*\(", text(path))]
    ownership_findings = [issue("qobject-without-parent", path, root) for path in source if re.search(r"new\s+Q[A-Za-z0-9_]+\s*\(\s*\)", text(path))]
    thread = [path for path in source if re.search(r"\b(?:QThread|QtConcurrent|moveToThread|QueuedConnection)\b", text(path))]
    thread_findings = []
    for path in source:
        body = text(path)
        if "Qt::DirectConnection" in body and ("QThread" in body or "moveToThread" in body):
            thread_findings.append(issue("cross-thread-direct-connection", path, root, "HIGH"))
        if re.search(r"\b(?:waitForFinished|waitForReadyRead|QThread::sleep|\.wait\s*\()", body) and re.search(r"(?:MainWindow|Widget|QML|View)", path.as_posix(), re.I):
            thread_findings.append(issue("blocking-ui-thread", path, root, "HIGH"))
    resources = [path for path in files if path.suffix.lower() in {".qrc", ".ui"}]
    resource_use = [path for path in source if re.search(r"[\"']:/|qrc:/", text(path))]
    deployment = [path for path in files if re.search(r"(?:windeployqt|macdeployqt|linuxdeployqt|qt_generate_deploy|install\s*\(|CPack)", text(path), re.I)]
    tests = [path for path in source if re.search(r"\bQTEST_(?:MAIN|APPLESS_MAIN)|#include\s*[<\"]QtTest", text(path)) or "tests" in {part.lower() for part in path.relative_to(root).parts}]
    identity_files = build_files if re.search(r"\bQt[56]?\b|QT\s*\+=", build_text, re.I) else []
    dimensions = {
        "identity_and_version": item(identity_files, root, required=True, note=f"qt_major={qt_major}; qt_version={qt_version}"),
        "build_system": item(build_files, root, required=True, note="CMake and qmake are reported separately"),
        "signals_and_slots": item(signal_slot, root, required=True),
        "ownership": item(ownership, root, ownership_findings, required=True),
        "threading": item(thread, root, thread_findings, note="absence means no explicit thread evidence was found"),
        "resources": item(resources + resource_use, root),
        "deployment": item(deployment, root),
        "test_evidence": item(tests, root, required=True),
    }
    if qt_version == "unknown" and dimensions["identity_and_version"]["status"] != "BLOCKED":
        dimensions["identity_and_version"]["status"] = "GAP"
        dimensions["identity_and_version"]["findings"].append({"severity": "MEDIUM", "rule": "missing-exact-qt-version", "path": relative(build_files, root)[0] if build_files else "CMakeLists.txt"})
    statuses = {value["status"] for value in dimensions.values()}
    overall = "BLOCKED" if "BLOCKED" in statuses else "FAIL" if "FAIL" in statuses else "PASS_WITH_GAPS" if "GAP" in statuses else "PASS"
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode("utf-8")); digest.update(path.read_bytes())
    return {
        "schema_version": "1.0.0", "profile": "qt", "result": overall,
        "identity": {"family": "qt", "qt_major": qt_major, "qt_version": qt_version, "build_systems": (["cmake"] if cmake else []) + (["qmake"] if qmake else [])},
        "dimensions": dimensions, "source_fingerprint": digest.hexdigest(),
        "bounded_scan": {"max_depth": 7, "max_files": 4000, "scanned_files": len(files), "truncated": truncated},
        "storage_policy": "paths-versions-status-hashes-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="On-demand Qt specialization evidence audit")
    parser.add_argument("--root", default="."); parser.add_argument("--output")
    args = parser.parse_args(); data = audit(Path(args.root)); rendered = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 2 if data["result"] in {"BLOCKED", "FAIL"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
