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


SKIP = {"Library", "Temp", "Logs", "obj", "bin", "Build", "Builds", ".git", ".ai", "UserSettings"}
SUFFIXES = {".cs", ".asmdef", ".json", ".prefab", ".unity", ".asset", ".meta", ".uxml", ".uss"}


def bounded_files(root: Path, max_depth: int = 9, max_files: int = 6000) -> tuple[list[Path], bool]:
    root=root.resolve();paths,_=walk_source_files(root,TraversalBudget(max_depth=max_depth,max_directories=4096,max_entries=50000,max_files=max(20000,max_files*10),max_observed_bytes=4*1024*1024*1024,max_elapsed_ms=10000),ignored_directories=frozenset(name.casefold() for name in SKIP),include=lambda path:path.stat().st_size<=16*1024*1024 and (path.suffix.lower() in SUFFIXES or path.name in {"ProjectVersion.txt","ProjectSettings.asset","EditorBuildSettings.asset"}))
    return paths[:max_files],len(paths)>max_files


def text(path: Path) -> str:
    try:
        value,truncated=read_bounded_text(path,16*1024*1024);return "" if truncated else value
    except OSError:
        return ""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(text(path))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def relative(paths: Iterable[Path], root: Path, limit: int = 100) -> list[str]:
    return [path.relative_to(root).as_posix() for path in list(paths)[:limit]]


def issue(rule: str, path: Path, root: Path, severity: str = "MEDIUM") -> dict[str, str]:
    return {"severity": severity, "rule": rule, "path": path.relative_to(root).as_posix()}


def dimension(paths: list[Path], root: Path, findings: list[dict[str, str]] | None = None, required: bool = False, note: str | None = None) -> dict[str, Any]:
    problems = findings or []
    status = "FAIL" if any(item.get("severity") == "HIGH" for item in problems) else "PASS" if paths and not problems else "GAP"
    if required and not paths:
        status = "BLOCKED"
    result: dict[str, Any] = {"status": status, "evidence": relative(paths, root), "findings": problems}
    if note:
        result["note"] = note
    return result


def project_version(path: Path) -> str:
    match = re.search(r"m_EditorVersion:\s*([^\r\n]+)", text(path))
    return match.group(1).strip() if match else "unknown"


def method_body(source: str, name: str) -> str:
    match = re.search(rf"\b(?:void|IEnumerator|UniTask|Task)\s+{re.escape(name)}\s*\([^)]*\)\s*\{{(?P<body>.{{0,3000}}?)\n?\}}", source, re.S)
    return match.group("body") if match else ""


def audit(root: Path) -> dict[str, Any]:
    root = root.resolve(); files, truncated = bounded_files(root)
    version_file = root / "ProjectSettings" / "ProjectVersion.txt"
    manifest_file = root / "Packages" / "manifest.json"
    lock_file = root / "Packages" / "packages-lock.json"
    manifest = load_json(manifest_file); package_lock = load_json(lock_file)
    dependencies = manifest.get("dependencies") or {}
    unity_version = project_version(version_file)
    identity_files = [path for path in (version_file, manifest_file, lock_file) if path.is_file()]
    identity_findings = []
    if not lock_file.is_file():
        identity_findings.append({"severity": "MEDIUM", "rule": "missing-packages-lock", "path": "Packages/packages-lock.json"})
    asmdefs = [path for path in files if path.suffix.lower() == ".asmdef"]
    scripts = [path for path in files if path.suffix.lower() == ".cs"]
    behaviours = [path for path in scripts if re.search(r":\s*(?:MonoBehaviour|ScriptableObject)\b", text(path))]
    lifecycle = [path for path in behaviours if re.search(r"\b(?:Awake|OnEnable|Start|OnDisable|OnDestroy|Update|LateUpdate|FixedUpdate)\s*\(", text(path))]
    lifecycle_findings = []
    for path in behaviours:
        body = text(path)
        if "OnEnable" in body and "+=" in method_body(body, "OnEnable") and "-=" not in method_body(body, "OnDisable"):
            lifecycle_findings.append(issue("subscription-without-unsubscribe", path, root, "HIGH"))
        if re.search(r"\basync\s+void\s+(?!OnClick|OnSubmit|OnValueChanged)[A-Za-z_]", body):
            lifecycle_findings.append(issue("unsafe-async-void", path, root))
    ui_assets = [path for path in files if path.suffix.lower() in {".uxml", ".uss"}]
    ui_scripts = [path for path in scripts if re.search(r"\b(?:UnityEngine\.UI|VisualElement|UIDocument|Button|Canvas)\b", text(path))]
    ui_systems = []
    if "com.unity.ugui" in dependencies or any("UnityEngine.UI" in text(path) for path in ui_scripts):
        ui_systems.append("uGUI")
    if ui_assets or any(re.search(r"\b(?:VisualElement|UIDocument)\b", text(path)) for path in ui_scripts):
        ui_systems.append("UI Toolkit")
    gc_findings = []
    gc_evidence = []
    for path in scripts:
        body = text(path)
        hot = "\n".join(value for name in ("Update", "LateUpdate", "FixedUpdate") if (value := method_body(body, name)))
        if hot:
            gc_evidence.append(path)
        if hot and re.search(r"\bnew\s+[A-Za-z_]|\.(?:Select|Where|ToList|ToArray)\s*\(|\$\"", hot):
            gc_findings.append(issue("hot-loop-allocation", path, root, "HIGH"))
        if hot and re.search(r"\b(?:GetComponent|GameObject\.Find|FindObjectOfType)\s*[<(]", hot):
            gc_findings.append(issue("hot-loop-scene-lookup", path, root, "HIGH"))
    serialized = [path for path in files if path.suffix.lower() in {".prefab", ".unity", ".asset"} and path.relative_to(root).parts[0] == "Assets"]
    asset_findings = []
    for path in serialized:
        body = text(path)
        if "m_Script: {fileID: 0}" in body:
            asset_findings.append(issue("missing-script-reference", path, root, "HIGH"))
        if not Path(str(path) + ".meta").is_file():
            asset_findings.append(issue("missing-meta", path, root, "HIGH"))
    guid_map: dict[str, list[Path]] = {}
    for path in (value for value in files if value.suffix.lower() == ".meta"):
        match = re.search(r"^guid:\s*([0-9a-fA-F]+)", text(path), re.M)
        if match:
            guid_map.setdefault(match.group(1), []).append(path)
    for guid_paths in guid_map.values():
        if len(guid_paths) > 1:
            for path in guid_paths:
                asset_findings.append(issue("duplicate-guid", path, root, "HIGH"))
    project_settings = [path for path in files if path.name in {"ProjectSettings.asset", "EditorBuildSettings.asset"}]
    build_scripts = [path for path in scripts if re.search(r"\bBuildPipeline\.BuildPlayer\b|\bBuildTarget\.", text(path))]
    platform_constraints = [path for path in scripts + asmdefs if re.search(r"#if\s+UNITY_|includePlatforms|excludePlatforms", text(path))]
    test_files = [path for path in scripts if "tests" in {part.lower() for part in path.relative_to(root).parts} or re.search(r"\[(?:Test|UnityTest)\]", text(path))]
    test_asmdefs = [path for path in asmdefs if "test" in path.name.lower() or "optionalUnityReferences" in text(path)]
    dimensions = {
        "identity_and_packages": dimension(identity_files, root, identity_findings, required=True, note=f"unity_version={unity_version}; declared_packages={len(dependencies)}; locked_packages={len(package_lock.get('dependencies') or {})}"),
        "assembly_boundaries": dimension(asmdefs, root, note="asmdef absence is an explicit maturity gap"),
        "lifecycle": dimension(lifecycle, root, lifecycle_findings, required=True),
        "ui_system": dimension(ui_assets + ui_scripts, root, required=True, note=f"detected={ui_systems or ['unknown']}"),
        "gc_allocation": dimension(gc_evidence, root, gc_findings, note="no hot-loop method means no allocation surface was observed"),
        "asset_references": dimension(serialized, root, asset_findings, required=True),
        "build_target_and_platform": dimension(project_settings + build_scripts + platform_constraints, root, required=True),
        "test_evidence": dimension(test_files + test_asmdefs, root, required=True, note=f"test_framework={'com.unity.test-framework' in dependencies}"),
    }
    if not project_settings or not build_scripts or not platform_constraints:
        dimensions["build_target_and_platform"]["status"] = "GAP" if dimensions["build_target_and_platform"]["status"] != "BLOCKED" else "BLOCKED"
        dimensions["build_target_and_platform"]["note"] = f"project_settings={len(project_settings)}, build_scripts={len(build_scripts)}, platform_constraints={len(platform_constraints)}"
    if unity_version == "unknown" or not manifest_file.is_file():
        dimensions["identity_and_packages"]["status"] = "BLOCKED"
    elif identity_findings:
        dimensions["identity_and_packages"]["status"] = "GAP"
    if truncated:
        dimensions["asset_references"]["status"] = "BLOCKED"
        dimensions["asset_references"]["findings"].append({"severity": "HIGH", "rule": "bounded-scan-truncated", "path": "Assets"})
    statuses = {value["status"] for value in dimensions.values()}
    overall = "BLOCKED" if "BLOCKED" in statuses else "FAIL" if "FAIL" in statuses else "PASS_WITH_GAPS" if "GAP" in statuses else "PASS"
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode("utf-8")); digest.update(path.read_bytes())
    return {
        "schema_version": "1.0.0", "profile": "unity", "result": overall,
        "identity": {"family": "unity", "unity_version": unity_version, "ui_systems": ui_systems, "package_count": len(dependencies)},
        "dimensions": dimensions, "source_fingerprint": digest.hexdigest(),
        "bounded_scan": {"max_depth": 9, "max_files": 6000, "scanned_files": len(files), "truncated": truncated},
        "storage_policy": "paths-versions-status-hashes-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="On-demand Unity specialization evidence audit")
    parser.add_argument("--root", default="."); parser.add_argument("--output")
    args = parser.parse_args(); data = audit(Path(args.root)); rendered = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 2 if data["result"] in {"BLOCKED", "FAIL"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
