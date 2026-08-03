#!/usr/bin/env python3
"""Run staged validation for a desktop-reconstruction project."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from common import csv_fieldnames, detect_execution_mode, find_placeholders, resolve_root, write_json
from lib_recon import parse_simple_yaml

REQUIRED_FILES = [
    "00_control/PROJECT.yaml", "00_control/STATUS.yaml", "00_control/AUTHORIZATION.md",
    "00_control/SCOPE_MATRIX.csv", "00_control/DECISIONS.md", "00_control/CHANGELOG.md",
    "00_control/WORK_UNITS.csv", "00_control/DELIVERABLE_MANIFEST.yaml", "00_control/DELIVERABLE_CHECKLIST.csv",
    "01_environment/SOURCE_APPLICATION_PROFILE.yaml", "01_environment/SOURCE_TECH_FINGERPRINT.yaml",
    "01_environment/TARGET_CONSTRAINTS.yaml", "01_environment/ENVIRONMENT_MATRIX.csv",
    "01_environment/PLATFORM_COMPATIBILITY_MATRIX.csv", "02_evidence/EVIDENCE_INDEX.csv",
    "03_inventory/ENTRY_POINT_INVENTORY.csv", "03_inventory/WINDOW_PAGE_INVENTORY.csv",
    "03_inventory/INTERACTIVE_CONTROL_INVENTORY.csv", "03_inventory/INTERACTION_INVENTORY.csv",
    "03_inventory/FEATURE_INVENTORY.csv", "03_inventory/DATA_CONTRACT_INVENTORY.csv",
    "03_inventory/ROLE_PERMISSION_MATRIX.csv", "03_inventory/EXTERNAL_DEPENDENCY_MATRIX.csv",
    "03_inventory/ERROR_RECOVERY_CATALOG.yaml", "03_inventory/DISCOVERY_ROUNDS.csv",
    "05_technical_design/TECH_STACK_CANDIDATES.csv", "05_technical_design/TECH_STACK_DECISION.yaml",
    "05_technical_design/TECH_STACK_LOCK.yaml", "05_technical_design/OFFICIAL_DOC_INDEX.csv",
    "05_technical_design/DEPENDENCY_INVENTORY.csv", "05_technical_design/IMPLEMENTATION_TASKS.csv",
    "07_tests/TEST_CASES.csv", "07_tests/PERFORMANCE_SCENARIOS.csv",
    "07_tests/COVERAGE_MATRIX.csv", "07_tests/TRACEABILITY_MATRIX.csv",
    "07_tests/DEFECTS.csv", "07_tests/WAIVERS.csv",
    "09_reports/RESIDUAL_UNKNOWN_RISK_REPORT.md",
]
REQUIRED_DIRS = [
    "02_evidence/raw", "02_evidence/processed", "04_specifications/pages",
    "04_specifications/interactions", "04_specifications/features", "04_specifications/data-contracts",
    "04_specifications/errors", "04_specifications/performance", "05_technical_design",
    "06_implementation", "07_tests", "08_build", "09_reports", "10_delivery",
]
REQUIRED_CSV_HEADERS = {
    "00_control/SCOPE_MATRIX.csv": {"scope_id", "item_id", "priority", "in_scope", "evidence_ids", "waiver_id"},
    "02_evidence/EVIDENCE_INDEX.csv": {"evidence_id", "file_path", "source_channel", "sha256", "related_inventory_ids"},
    "03_inventory/INTERACTION_INVENTORY.csv": {"interaction_id", "priority", "in_scope", "evidence_ids", "spec_ids", "test_case_ids"},
    "03_inventory/DATA_CONTRACT_INVENTORY.csv": {"data_id", "priority", "in_scope", "evidence_ids", "spec_ids", "test_case_ids"},
    "05_technical_design/IMPLEMENTATION_TASKS.csv": {"task_id", "priority", "related_inventory_ids", "status"},
    "07_tests/TRACEABILITY_MATRIX.csv": {"trace_id", "scope_id", "item_type", "item_id", "evidence_ids", "spec_ids", "task_ids", "implementation_ids", "test_case_ids", "deliverable_ids", "chain_status"},
}


def basic(root: Path) -> dict[str, object]:
    missing_files = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    missing_dirs = [rel for rel in REQUIRED_DIRS if not (root / rel).is_dir()]
    placeholders = find_placeholders(root)
    header_issues: list[str] = []
    for rel, required in REQUIRED_CSV_HEADERS.items():
        headers = set(csv_fieldnames(root / rel))
        missing = sorted(required - headers)
        if missing: header_issues.append(f"{rel} 缺少列：{';'.join(missing)}")
    manifest_error = ""
    manifest = root / "00_control" / "DELIVERABLE_MANIFEST.yaml"
    if manifest.is_file():
        try:
            data = parse_simple_yaml(manifest)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data.get("items"):
                manifest_error = "DELIVERABLE_MANIFEST.items 为空或无效"
        except Exception as exc:
            manifest_error = f"DELIVERABLE_MANIFEST 解析失败：{exc}"
    issues = missing_files + missing_dirs + header_issues + ([manifest_error] if manifest_error else [])
    return {
        "gate": "PASS" if not issues and not placeholders else "FAIL",
        "missing_files": missing_files, "missing_directories": missing_dirs,
        "header_issues": header_issues, "manifest_error": manifest_error,
        "unreplaced_placeholders": placeholders,
    }


def read_subresult(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"gate": "FAIL", "error": f"无法读取 {path}"}


def run_script(script: Path, args: list[str], json_path: Path) -> dict[str, object]:
    cmd = [sys.executable, str(script), *args, "--json", str(json_path), "--no-fail"]
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, check=False, timeout=180)
    result = read_subresult(json_path)
    result["exit_code"] = completed.returncode
    if completed.stderr.strip(): result["stderr"] = completed.stderr.strip()[-4000:]
    return result


def status_gates(root: Path, required: list[str]) -> dict[str, object]:
    path = root / "00_control" / "STATUS.yaml"
    if not path.is_file(): return {"gate": "FAIL", "issues": ["STATUS.yaml 不存在"]}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    issues = []
    for key in required:
        match = re.search(rf"^[ \t]*[\"']?{re.escape(key)}[\"']?\s*:\s*[\"']?([A-Z_]+)", text, re.MULTILINE)
        if not match or match.group(1) != "PASS": issues.append(f"{key} 未通过")
    return {"gate": "PASS" if not issues else "FAIL", "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description="按门禁档位校验桌面软件重建项目")
    parser.add_argument("project_dir")
    parser.add_argument("--profile", choices=["basic", "technology", "coverage", "implementation", "release"], default="basic")
    parser.add_argument("--write-checksums", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr); return 2

    scripts = Path(__file__).resolve().parent
    temp = root / "09_reports" / ".validation"
    temp.mkdir(parents=True, exist_ok=True)
    checks: dict[str, object] = {"basic": basic(root)}

    if args.profile in {"technology", "implementation", "release"}:
        checks["toolchain"] = run_script(scripts / "validate_toolchain.py", [str(root)], temp / "toolchain.json")

    if args.profile in {"coverage", "implementation", "release"}:
        phase = "spec" if args.profile == "coverage" else ("implementation" if args.profile == "implementation" else "release")
        checks["discovery"] = run_script(scripts / "validate_discovery.py", [str(root)], temp / "discovery.json")
        checks["coverage"] = run_script(scripts / "calculate_coverage.py", [str(root), "--phase", phase], temp / "coverage.json")
        checks["traceability"] = run_script(scripts / "validate_traceability.py", [str(root), "--phase", phase], temp / "traceability.json")
        checks["orphans"] = run_script(scripts / "detect_orphan_items.py", [str(root), "--phase", phase], temp / "orphans.json")

    if args.profile == "release":
        delivery_args = [str(root), "--phase", "release"]
        if args.write_checksums: delivery_args.append("--write-checksums")
        checks["deliverables"] = run_script(scripts / "validate_deliverables.py", delivery_args, temp / "deliverables.json")
        checks["status_gates"] = status_gates(root, ["G0", "G1", "G1-T", "G2", "G3", "G4-C", "G5-T", "G6", "G7", "G8", "G9-D"])
    elif args.profile == "implementation":
        checks["status_gates"] = status_gates(root, ["G0", "G1", "G1-T", "G2", "G3", "G4-C", "G5-T"])

    gate = "PASS" if all(isinstance(value, dict) and value.get("gate") == "PASS" for value in checks.values()) else "FAIL"
    result = {
        "schema_version": "1.1", "project_dir": str(root), "profile": args.profile,
        "execution_mode": detect_execution_mode(root),
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gate": gate, "checks": checks,
        "warning": "机器检查不替代授权、业务正确性、人工视觉审查和真实目标环境测试。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    output = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / f"project-validation-{args.profile}.json"
    write_json(output, result)
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
