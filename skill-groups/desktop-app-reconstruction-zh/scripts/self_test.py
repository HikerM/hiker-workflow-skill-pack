#!/usr/bin/env python3
"""Regression self-test for the desktop-app-reconstruction-zh Skill.

The test uses only temporary directories. It validates initialization, evidence
indexing, discovery/coverage/traceability/orphan gates, exact-version locking,
technology fingerprinting, deliverable validation, and package structure.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from common import read_csv_rows, write_csv_rows, write_json


def run_json(script: Path, args: list[str], output: Path, *, expected_gate: str = "PASS") -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(script), *args, "--json", str(output)]
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False, check=False)
    try:
        data = json.loads(output.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(
            f"{script.name} 未生成有效 JSON：{exc}; rc={proc.returncode}; stderr={proc.stderr[-2000:]}"
        ) from exc
    if not isinstance(data, dict):
        raise AssertionError(f"{script.name} JSON 根不是对象")
    actual_gate = str(data.get("gate", ""))
    if actual_gate != expected_gate:
        raise AssertionError(
            f"{script.name} 预期 gate={expected_gate}，实际={actual_gate}; "
            f"rc={proc.returncode}; stderr={proc.stderr[-2000:]}"
        )
    if expected_gate == "PASS" and proc.returncode != 0:
        raise AssertionError(f"{script.name} gate PASS 但退出码为 {proc.returncode}")
    return {**data, "command": command, "exit_code": proc.returncode}


def run_plain(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"{script.name} 失败：rc={proc.returncode}; stderr={proc.stderr[-2000:]}")
    return proc


def csv_write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        fields = next(csv.reader(handle), [])
    write_csv_rows(path, fields, rows)


def make_spec_fixture(project: Path, scripts: Path, report_dir: Path) -> dict[str, Any]:
    auth = project / "00_control" / "AUTHORIZATION.md"
    auth.write_text(
        auth.read_text(encoding="utf-8-sig").replace("授权状态：UNVERIFIED", "授权状态：VERIFIED"),
        encoding="utf-8",
        newline="\n",
    )

    raw = project / "02_evidence" / "raw"
    (raw / "manual.txt").write_text("self-test manual evidence\n", encoding="utf-8")
    (raw / "screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\nself-test")
    run_plain(scripts / "index_evidence.py", [str(raw)])
    evidence_rows = read_csv_rows(project / "02_evidence" / "EVIDENCE_INDEX.csv")
    if len(evidence_rows) != 2:
        raise AssertionError(f"证据索引数量应为 2，实际 {len(evidence_rows)}")
    if "source_channel" not in evidence_rows[0] or "related_inventory_ids" not in evidence_rows[0]:
        raise AssertionError("证据索引未使用 v1.1 字段契约")
    evidence_ids = [row["evidence_id"] for row in evidence_rows]
    evidence_joined = ";".join(evidence_ids)

    csv_write(project / "00_control" / "SCOPE_MATRIX.csv", [
        {
            "scope_id": "SC-0001", "module": "core", "item_type": "entry", "item_id": "ENTRY-0001",
            "name": "启动入口", "priority": "P1", "in_scope": "true", "source_version": "1.0.0",
            "target_platform": "self-test", "parity_types": "interaction", "acceptance_criteria": "入口可追踪",
            "status": "VERIFIED", "evidence_ids": evidence_joined,
        },
        {
            "scope_id": "SC-0002", "module": "core", "item_type": "feature", "item_id": "FEAT-0001",
            "name": "核心保存功能", "priority": "P1", "in_scope": "true", "source_version": "1.0.0",
            "target_platform": "self-test", "parity_types": "functional;data", "acceptance_criteria": "保存行为等价",
            "status": "VERIFIED", "evidence_ids": evidence_joined,
        },
    ])
    csv_write(project / "03_inventory" / "ENTRY_POINT_INVENTORY.csv", [{
        "entry_id": "ENTRY-0001", "module": "core", "entry_type": "application_start", "name": "启动入口",
        "parent_context": "desktop", "trigger": "launch", "priority": "P1", "in_scope": "true", "roles": "ROLE-USER",
        "related_ids": "FEAT-0001", "evidence_ids": evidence_joined, "spec_ids": "SPEC-ENTRY-0001",
        "test_case_ids": "TC-ENTRY-0001", "status": "VERIFIED",
    }])
    csv_write(project / "03_inventory" / "FEATURE_INVENTORY.csv", [{
        "feature_id": "FEAT-0001", "module": "core", "name": "保存", "priority": "P1", "in_scope": "true",
        "status": "VERIFIED", "entry_points": "ENTRY-0001", "role_ids": "ROLE-USER", "input_types": "text",
        "data_scale_classes": "small", "evidence_ids": evidence_joined, "spec_ids": "SPEC-FEAT-0001",
        "test_case_ids": "TC-FEAT-0001",
    }])
    csv_write(project / "03_inventory" / "DISCOVERY_ROUNDS.csv", [
        {
            "round_id": "DISC-0001", "performed_at": "2026-08-01T10:00:00+08:00", "channel": "ui_walkthrough",
            "roles": "ROLE-USER", "data_sets": "DATA-SELFTEST", "environments": "ENV-SELFTEST",
            "entry_points_checked": "ENTRY-0001", "pages_checked": "", "new_p0_p1_items": "0",
            "new_p2_p3_items": "0", "blockers": "", "evidence_ids": evidence_joined, "result": "PASS",
        },
        {
            "round_id": "DISC-0002", "performed_at": "2026-08-01T11:00:00+08:00", "channel": "manual_document",
            "roles": "ROLE-USER", "data_sets": "DATA-SELFTEST", "environments": "ENV-SELFTEST",
            "entry_points_checked": "ENTRY-0001", "pages_checked": "", "new_p0_p1_items": "0",
            "new_p2_p3_items": "0", "blockers": "", "evidence_ids": evidence_joined, "result": "PASS",
        },
    ])

    (project / "04_specifications" / "features" / "FEAT-0001.yaml").write_text(
        'schema_version: "1.1"\nspec_id: "SPEC-FEAT-0001"\npriority: "P1"\nfeature_id: "FEAT-0001"\nstatus: "VERIFIED"\n',
        encoding="utf-8",
    )
    (project / "04_specifications" / "interactions" / "ENTRY-0001.yaml").write_text(
        'schema_version: "1.1"\nspec_id: "SPEC-ENTRY-0001"\npriority: "P1"\nstatus: "VERIFIED"\n',
        encoding="utf-8",
    )
    csv_write(project / "07_tests" / "TEST_CASES.csv", [
        {
            "test_id": "TC-ENTRY-0001", "module": "core", "related_ids": "ENTRY-0001", "title": "启动入口规格测试",
            "priority": "P1", "test_type": "spec", "scenario_class": "normal", "preconditions": "fixture",
            "steps": "launch", "expected_result": "entry available", "status": "DESIGNED",
        },
        {
            "test_id": "TC-FEAT-0001", "module": "core", "related_ids": "FEAT-0001", "title": "保存功能规格测试",
            "priority": "P1", "test_type": "spec", "scenario_class": "normal", "preconditions": "fixture",
            "steps": "save", "expected_result": "data persisted", "status": "DESIGNED",
        },
    ])
    csv_write(project / "07_tests" / "TRACEABILITY_MATRIX.csv", [
        {
            "trace_id": "TRACE-0001", "scope_id": "SC-0001", "item_type": "entry", "item_id": "ENTRY-0001",
            "priority": "P1", "evidence_ids": evidence_joined, "spec_ids": "SPEC-ENTRY-0001",
            "test_case_ids": "TC-ENTRY-0001", "chain_status": "DESIGNED",
        },
        {
            "trace_id": "TRACE-0002", "scope_id": "SC-0002", "item_type": "feature", "item_id": "FEAT-0001",
            "priority": "P1", "evidence_ids": evidence_joined, "spec_ids": "SPEC-FEAT-0001",
            "test_case_ids": "TC-FEAT-0001", "chain_status": "DESIGNED",
        },
    ])

    results = {}
    results["basic"] = run_json(scripts / "validate_project.py", [str(project), "--profile", "basic"], report_dir / "basic.json")
    results["discovery"] = run_json(scripts / "validate_discovery.py", [str(project)], report_dir / "discovery.json")
    results["coverage"] = run_json(scripts / "calculate_coverage.py", [str(project), "--level", "spec"], report_dir / "coverage.json")
    results["traceability"] = run_json(scripts / "validate_traceability.py", [str(project), "--level", "spec"], report_dir / "traceability.json")
    results["orphans"] = run_json(scripts / "detect_orphan_items.py", [str(project), "--phase", "spec"], report_dir / "orphans.json")
    results["coverage_profile"] = run_json(scripts / "validate_project.py", [str(project), "--profile", "coverage"], report_dir / "coverage-profile.json")
    results["spec_quality_gates"] = run_json(scripts / "run_quality_gates.py", [str(project), "--phase", "spec"], report_dir / "spec-quality-gates.json")
    return {"evidence_ids": evidence_ids, "results": results}


def make_toolchain_fixture(project: Path, scripts: Path, report_dir: Path) -> dict[str, Any]:
    python_version = platform.python_version()
    version_file = project / "05_technical_design" / "self-test-versions.txt"
    version_file.write_text(
        "\n".join([python_version, "1.0.0", "self-test exact version evidence"]) + "\n",
        encoding="utf-8",
    )
    lock_file = project / "06_implementation" / "dependency-locks" / "self-test.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("selftest-dependency==1.0.0\n", encoding="utf-8")

    component_defs = [
        ("programming_language", "Python", python_version),
        ("runtime", "SelfTest Runtime", "1.0.0"),
        ("sdk", "SelfTest SDK", "1.0.0"),
        ("compiler", "SelfTest Compiler", "1.0.0"),
        ("ui_framework", "SelfTest UI", "1.0.0"),
        ("build_tool", "SelfTest Build", "1.0.0"),
        ("package_manager", "SelfTest Package", "1.0.0"),
        ("installer", "SelfTest Installer", "1.0.0"),
    ]
    lines = [
        'schema_version: "1.1"', 'lock_id: "TECH-LOCK-SELFTEST"', 'lock_status: "LOCKED"',
        'decision_id: "ADR-TECH-SELFTEST"', 'locked_at: "2026-08-01T12:00:00+08:00"',
        'locked_by: "self_test.py"', 'license_review_status: "VERIFIED"', 'security_review_status: "VERIFIED"',
        '', 'components:',
    ]
    for component_id, name, version in component_defs:
        lines += [
            f'  {component_id}:', f'    name: "{name}"', f'    exact_version: "{version}"',
            '    required: true', '    verification_source: "05_technical_design/self-test-versions.txt"',
            '    verification_status: "VERIFIED"',
        ]
    lines += [
        '  database_or_storage:', '    name: "NOT_APPLICABLE"', '    exact_version: "NOT_APPLICABLE"',
        '    required: false', '    verification_source: ""', '    verification_status: "NOT_APPLICABLE"',
        '', 'targets:', '  operating_systems: ["SelfTest OS x64"]', '  build_configuration: "Release"',
        '', 'version_policy:', '  floating_versions_forbidden: true', '  exact_versions_required: true',
        '  pre_release_allowed: false', '', 'dependency_policy:', '  lock_files_required: true',
        '  expected_lock_files: ["06_implementation/dependency-locks/self-test.lock"]',
        '  hashes_required_for_offline_packages: true', '  sbom_required: true',
        '', 'official_documentation:', '  index_file: "05_technical_design/OFFICIAL_DOC_INDEX.csv"',
        '  exact_version_match_required: true', '', 'build_reproducibility:', '  clean_machine_required: true',
        '  repeat_build_count: 2', '  build_commands: ["python -m compileall"]',
        '  test_commands: ["python scripts/self_test.py"]', '  output_paths: ["08_build/self-test-artifact.txt"]',
        '  clean_build_verified: true', '  clean_test_verified: true', '  artifact_checksum_verified: true',
        '  verification_status: "VERIFIED"',
    ]
    (project / "05_technical_design" / "TECH_STACK_LOCK.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (project / "05_technical_design" / "TECH_STACK_DECISION.yaml").write_text(
        '\n'.join([
            'schema_version: "1.1"', 'decision_id: "ADR-TECH-SELFTEST"', 'status: "ACCEPTED"',
            'selected_candidate_id: "TECH-CANDIDATE-SELFTEST"', 'decided_at: "2026-08-01T12:00:00+08:00"',
            'approved_by: "self_test.py"', 'poc:', '  overall_result: "PASS"', '  evidence_ids: []',
        ]) + '\n',
        encoding="utf-8",
    )
    csv_write(project / "05_technical_design" / "TECH_STACK_CANDIDATES.csv", [
        {
            "candidate_id": "TECH-CANDIDATE-SELFTEST", "language": "Python", "language_version": python_version,
            "framework": "SelfTest UI", "framework_version": "1.0.0", "runtime": "Python",
            "runtime_version": python_version, "weighted_total": "1.0", "poc_status": "PASS", "decision": "SELECTED",
        },
        {
            "candidate_id": "TECH-CANDIDATE-ALTERNATE", "language": "Alternate", "language_version": "1.0.0",
            "framework": "Alternate", "framework_version": "1.0.0", "runtime": "Alternate",
            "runtime_version": "1.0.0", "weighted_total": "0.5", "poc_status": "NOT_RUN", "decision": "REJECTED",
        },
    ])
    csv_write(project / "01_environment" / "PLATFORM_COMPATIBILITY_MATRIX.csv", [{
        "platform_id": "PLATFORM-SELFTEST", "os_name": "SelfTest OS", "os_version": "1.0", "architecture": "x64",
        "required": "true", "framework_support_status": "PASS", "runtime_support_status": "PASS",
        "installer_support_status": "PASS", "poc_status": "PASS", "test_environment_id": "ENV-SELFTEST",
        "result": "PASS", "evidence_ids": "", "official_doc_ids": "DOC-SELFTEST-PLATFORM",
    }])
    csv_write(project / "05_technical_design" / "DEPENDENCY_INVENTORY.csv", [{
        "dependency_id": "DEP-SELFTEST", "name": "selftest-dependency", "direct_or_transitive": "direct",
        "category": "test", "exact_version": "1.0.0", "source": "local fixture", "license": "MIT",
        "lock_file": "06_implementation/dependency-locks/self-test.lock", "required": "true",
        "offline_available": "true", "vulnerability_status": "VERIFIED", "status": "VERIFIED",
    }])
    doc_rows = []
    for component_id, name, version in component_defs:
        doc_rows.append({
            "doc_id": f"DOC-{component_id.upper().replace('_', '-')}", "component_id": component_id,
            "component_name": name, "locked_version": version, "source_title": "Self-test official fixture",
            "source_type": "official", "source_locator": "local:self-test", "document_version": version,
            "retrieved_at": "2026-08-01", "supported_platforms": "SelfTest OS", "relevant_sections": "version",
            "content_checksum": "self-test", "verification_status": "VERIFIED",
        })
    csv_write(project / "05_technical_design" / "OFFICIAL_DOC_INDEX.csv", doc_rows)
    (project / "08_build" / "self-test-artifact.txt").write_text("self-test build artifact\n", encoding="utf-8")

    return run_json(scripts / "validate_toolchain.py", [str(project)], report_dir / "technology.json")


def make_detector_fixture(temp_root: Path, scripts: Path, report_dir: Path) -> dict[str, Any]:
    source = temp_root / "source-fixture"
    (source / "resources").mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps({
            "name": "self-test-electron", "version": "1.0.0", "engines": {"node": "22.0.0"},
            "devDependencies": {"electron": "35.0.0", "typescript": "5.8.2"},
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    (source / "resources" / "app.asar").write_bytes(b"self-test")
    out = report_dir / "detected-stack.json"
    proc = run_plain(scripts / "detect_project_stack.py", [str(source), "--json", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    technologies = {str(item.get("technology")) for item in data.get("candidates", [])}
    if "Electron" not in technologies:
        raise AssertionError(f"技术探测未识别 Electron：{sorted(technologies)}; stdout={proc.stdout[-1000:]}")
    if not data.get("lock_files"):
        raise AssertionError("技术探测未记录锁文件")
    return data


def make_deliverable_fixture(temp_root: Path, scripts: Path, report_dir: Path) -> dict[str, Any]:
    root = temp_root / "deliverable-fixture"
    (root / "00_control").mkdir(parents=True)
    (root / "09_reports").mkdir(parents=True)
    (root / "08_build" / "checksums").mkdir(parents=True)
    (root / "00_control" / "PROJECT.yaml").write_text('execution_mode: "analysis"\n', encoding="utf-8")
    artifact = root / "artifact.md"
    artifact.write_text('状态：VERIFIED\ncontent\n', encoding="utf-8")
    fields = [
        "deliverable_id", "path", "kind", "required_for_mode", "stage", "min_size_bytes",
        "min_non_placeholder_items", "placeholder_forbidden", "forbidden_markers", "required_markers",
        "checksum_required", "notes",
    ]
    write_csv_rows(root / "00_control" / "DELIVERABLE_CHECKLIST.csv", fields, [{
        "deliverable_id": "DLV-SELFTEST", "path": "artifact.md", "kind": "file", "required_for_mode": "all",
        "stage": "G9-D", "min_size_bytes": "5", "min_non_placeholder_items": "0",
        "placeholder_forbidden": "true", "forbidden_markers": "UNVERIFIED",
        "required_markers": "状态：VERIFIED", "checksum_required": "true", "notes": "self-test",
    }])
    (root / "00_control" / "DELIVERABLE_MANIFEST.yaml").write_text(
        '\n'.join([
            'schema_version: "1.1"',
            'project_id: "SELFTEST"',
            'execution_mode: "analysis"',
            'manifest_status: "DRAFT"',
            'generated_from: "00_control/DELIVERABLE_CHECKLIST.csv"',
            'items:',
            '  - id: "DLV-SELFTEST"',
            '    path: "artifact.md"',
            '    kind: "file"',
            '    required_modes: ["all"]',
            '    stage: "G9-D"',
            '    status: "READY"',
            '    version: "1.0.0"',
            '    sha256: ""',
            '    checksum_required: true',
            '    related_ids: []',
            '    evidence_ids: []',
            '    waiver_id: ""',
            '    owner: "self_test.py"',
            '    notes: "self-test"',
        ]) + '\n',
        encoding="utf-8",
    )
    passed = run_json(
        scripts / "validate_deliverables.py",
        [str(root), "--write-checksums"], report_dir / "deliverables-pass.json",
    )
    artifact.write_text('状态：UNVERIFIED\n', encoding="utf-8")
    failed = run_json(
        scripts / "validate_deliverables.py",
        [str(root), "--no-fail"], report_dir / "deliverables-fail.json", expected_gate="FAIL",
    )
    return {"pass_case": passed, "negative_case": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 desktop-app-reconstruction-zh 回归自测")
    parser.add_argument("--skill-root", default=None, help="Skill 根目录；默认脚本父目录的父目录")
    parser.add_argument("--json", dest="json_path", default=None, help="写入自测 JSON")
    parser.add_argument("--keep-temp", action="store_true", help="保留临时目录以便排查")
    args = parser.parse_args()

    skill_root = Path(args.skill_root).expanduser().resolve() if args.skill_root else Path(__file__).resolve().parent.parent
    scripts = skill_root / "scripts"
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    checks: dict[str, Any] = {}
    errors: list[str] = []

    temp_manager = None if args.keep_temp else tempfile.TemporaryDirectory(prefix="desktop-recon-selftest-")
    temp_root = Path(temp_manager.name) if temp_manager else Path(tempfile.mkdtemp(prefix="desktop-recon-selftest-"))
    report_dir = temp_root / "reports"
    try:
        projects_parent = temp_root / "projects"
        projects_parent.mkdir(parents=True)

        negative_init = run_plain(scripts / "init_project.py", [
            "--output", str(projects_parent), "--project-name", "negative-empty-project", "--source-app", "empty-source",
            "--execution-mode", "analysis", "--reconstruction-mode", "black_box",
        ])
        negative_project = projects_parent / "negative-empty-project"
        if not negative_project.is_dir():
            raise AssertionError(f"负向初始化目录不存在：{negative_project}; stdout={negative_init.stdout}")
        checks["negative_empty_project"] = {
            "basic_passes_structure": run_json(
                scripts / "validate_project.py", [str(negative_project), "--profile", "basic"],
                report_dir / "negative-basic.json", expected_gate="PASS",
            ),
            "coverage_rejects_missing_evidence": run_json(
                scripts / "validate_project.py", [str(negative_project), "--profile", "coverage"],
                report_dir / "negative-coverage.json", expected_gate="FAIL",
            ),
            "technology_rejects_unlocked_versions": run_json(
                scripts / "validate_project.py", [str(negative_project), "--profile", "technology"],
                report_dir / "negative-technology.json", expected_gate="FAIL",
            ),
            "release_rejects_incomplete_delivery": run_json(
                scripts / "validate_project.py", [str(negative_project), "--profile", "release"],
                report_dir / "negative-release.json", expected_gate="FAIL",
            ),
        }

        init = run_plain(scripts / "init_project.py", [
            "--output", str(projects_parent), "--project-name", "self-test-project", "--source-app", "self-test-source",
            "--execution-mode", "analysis", "--reconstruction-mode", "black_box",
        ])
        project = projects_parent / "self-test-project"
        if not project.is_dir():
            raise AssertionError(f"初始化后项目目录不存在：{project}; stdout={init.stdout}")
        checks["project_spec_gates"] = make_spec_fixture(project, scripts, report_dir)
        checks["technology_gate"] = make_toolchain_fixture(project, scripts, report_dir)
        checks["technology_detector"] = make_detector_fixture(temp_root, scripts, report_dir)
        checks["deliverable_validator"] = make_deliverable_fixture(temp_root, scripts, report_dir)
        checks["package_structure"] = run_json(
            scripts / "validate_skill_package.py", [str(skill_root)], report_dir / "package-structure.json"
        )
    except Exception as exc:  # self-test should preserve a precise failure summary
        errors.append(f"{type(exc).__name__}: {exc}")

    gate = "PASS" if not errors else "FAIL"
    result = {
        "schema_version": "1.1", "gate_id": "SKILL-SELF-TEST", "gate": gate,
        "skill_root": str(skill_root), "started_at": started,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python_version": platform.python_version(), "temporary_directory": str(temp_root) if args.keep_temp else "REMOVED",
        "checks": checks, "errors": errors,
        "boundary": "自测验证脚本接口和最小闭环，不代表某个真实目标软件已经完成反推、实现或验收。",
    }
    if args.json_path:
        write_json(Path(args.json_path).expanduser().resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if temp_manager:
        temp_manager.cleanup()
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
