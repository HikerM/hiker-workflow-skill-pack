#!/usr/bin/env python3
"""Calculate risk-based coverage across all reconstruction inventories."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from common import (
    active_waiver_rows, collect_inventory_records, detect_execution_mode,
    format_rate, in_scope, is_core, is_pass, markdown_table, priority_of,
    project_setting, read_csv_rows, referenced_by_waiver, resolve_root,
    split_values, write_csv_rows, write_json,
)


def linked_trace_values(trace_rows: list[dict[str, str]], field: str) -> list[str]:
    result: list[str] = []
    for row in trace_rows:
        result.extend(split_values(row.get(field)))
    return list(dict.fromkeys(result))


def tests_pass(test_ids: list[str], tests: dict[str, dict[str, str]]) -> bool:
    return bool(test_ids) and all(test_id in tests and is_pass(tests[test_id].get("status")) for test_id in test_ids)


def open_defects(defect_ids: list[str], defects: dict[str, dict[str, str]]) -> list[str]:
    closed = {"closed", "fixed", "resolved", "verified", "已关闭", "已修复", "已验证"}
    return [did for did in defect_ids if did in defects and defects[did].get("status", "").strip().lower() not in closed]


def evidence_channel_count(evidence_ids: list[str], evidence: dict[str, dict[str, str]]) -> int:
    channels = set()
    for evidence_id in evidence_ids:
        row = evidence.get(evidence_id)
        if not row:
            continue
        channel = row.get("source_channel") or row.get("evidence_type")
        if channel:
            channels.add(channel.strip().lower())
    return len(channels)


def required_coverage(kind: str, phase: str, item: dict[str, str]) -> list[str]:
    required: list[str] = ["evidence", "test_mapping"]
    if kind not in {"menu_or_shortcut", "permission", "performance", "error"}:
        required.append("spec")
    if kind == "entry": required += ["related_target"]
    if kind in {"page", "control"}:
        required += [f"state:{state}" for state in split_values(item.get("applicable_states"))]
    if kind == "control": required.append("interaction")
    if kind == "menu_or_shortcut": required.append("interaction")
    if kind == "permission": required.append("policy")
    if kind == "external_dependency": required += ["version_or_api", "license", "failure_behavior"]
    if kind == "error": required += ["rollback_or_retry"]
    if kind == "performance": required += ["feature_link", "dataset", "environment", "gate"]
    if phase in {"implementation", "release"}:
        required += ["task", "implementation"]
    if phase == "release":
        required += ["test_pass", "no_open_defect"]
    return list(dict.fromkeys(required))


def covered_items(
    kind: str,
    item: dict[str, str],
    trace_rows: list[dict[str, str]],
    phase: str,
    tests: dict[str, dict[str, str]],
    defects: dict[str, dict[str, str]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    evidence_ids = list(dict.fromkeys(split_values(item.get("evidence_ids")) + linked_trace_values(trace_rows, "evidence_ids")))
    spec_ids = list(dict.fromkeys(split_values(item.get("spec_ids")) + linked_trace_values(trace_rows, "spec_ids")))
    task_ids = list(dict.fromkeys(split_values(item.get("task_ids")) + linked_trace_values(trace_rows, "task_ids")))
    implementation_ids = list(dict.fromkeys(split_values(item.get("implementation_ids")) + linked_trace_values(trace_rows, "implementation_ids")))
    test_ids = list(dict.fromkeys(split_values(item.get("test_case_ids")) + linked_trace_values(trace_rows, "test_case_ids")))
    defect_ids = list(dict.fromkeys(split_values(item.get("defect_ids")) + linked_trace_values(trace_rows, "defect_ids")))

    covered: list[str] = []
    if evidence_ids: covered.append("evidence")
    if spec_ids: covered.append("spec")
    if test_ids: covered.append("test_mapping")
    if task_ids: covered.append("task")
    if implementation_ids: covered.append("implementation")
    if tests_pass(test_ids, tests) or is_pass(item.get("test_result")):
        covered.append("test_pass")
    if not open_defects(defect_ids, defects):
        covered.append("no_open_defect")

    if kind == "entry" and split_values(item.get("related_ids")): covered.append("related_target")
    if kind in {"page", "control"}:
        verified = set(split_values(item.get("verified_states")))
        covered.extend(f"state:{state}" for state in split_values(item.get("applicable_states")) if state in verified)
    if kind == "control" and split_values(item.get("interaction_ids")): covered.append("interaction")
    if kind == "menu_or_shortcut" and (item.get("interaction_id") or split_values(item.get("interaction_ids"))): covered.append("interaction")
    if kind == "permission" and item.get("expected_policy"): covered.append("policy")
    if kind == "external_dependency":
        if item.get("version_or_api"): covered.append("version_or_api")
        if item.get("license_status") and item.get("license_status", "").upper() not in {"UNKNOWN", "UNVERIFIED"}: covered.append("license")
        if item.get("failure_behavior"): covered.append("failure_behavior")
    if kind == "error" and (item.get("rollback_behavior") or item.get("retry_behavior")): covered.append("rollback_or_retry")
    if kind == "performance":
        if split_values(item.get("related_feature_ids")): covered.append("feature_link")
        if item.get("dataset_id"): covered.append("dataset")
        if item.get("environment_id"): covered.append("environment")
        if item.get("target_gate") or item.get("accepted_ratio"): covered.append("gate")
        if is_pass(item.get("status")): covered.append("test_pass")
    return list(dict.fromkeys(covered)), evidence_ids, test_ids, defect_ids


def discovery_status(root: Path) -> dict[str, object]:
    rows = [row for row in read_csv_rows(root / "03_inventory" / "DISCOVERY_ROUNDS.csv") if row.get("round_id")]
    required_rounds = int(project_setting(
        root,
        "discovery_zero_new_core_rounds",
        project_setting(root, "discovery_saturation_rounds", 2),
    ))
    consecutive = 0
    for row in reversed(rows):
        try:
            new_core = int(row.get("new_p0_p1_items", "") or -1)
        except ValueError:
            new_core = -1
        result = row.get("result", "").strip().lower()
        if new_core == 0 and result in {"pass", "saturated_within_scope", "通过", "范围内饱和"} and split_values(row.get("evidence_ids")):
            consecutive += 1
        else:
            break
    return {
        "required_zero_new_core_rounds": required_rounds,
        "recorded_rounds": len(rows),
        "consecutive_zero_new_core_rounds": consecutive,
        "pass": len(rows) >= required_rounds and consecutive >= required_rounds,
    }


def calculate(root: Path, phase: str) -> dict[str, object]:
    mode = detect_execution_mode(root)
    tests = {row.get("test_id", ""): row for row in read_csv_rows(root / "07_tests" / "TEST_CASES.csv") if row.get("test_id")}
    defects = {row.get("defect_id", ""): row for row in read_csv_rows(root / "07_tests" / "DEFECTS.csv") if row.get("defect_id")}
    evidence = {row.get("evidence_id", ""): row for row in read_csv_rows(root / "02_evidence" / "EVIDENCE_INDEX.csv") if row.get("evidence_id")}
    waivers = active_waiver_rows(root)
    traces_by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv_rows(root / "07_tests" / "TRACEABILITY_MATRIX.csv"):
        if row.get("item_id"):
            traces_by_item[row["item_id"]].append(row)

    minimum_channels = int(project_setting(root, "minimum_independent_evidence_channels_p0_p1", 2))
    allow_core_release_waiver = bool(project_setting(root, "allow_core_waiver_at_release", False))
    rows: list[dict[str, object]] = []
    core_waiver_count = 0

    for item in collect_inventory_records(root):
        if not in_scope(item):
            continue
        subject_id = item["record_id"]
        kind = item["record_kind"]
        priority = priority_of(item)
        trace_rows = traces_by_item.get(subject_id, [])
        required = required_coverage(kind, phase, item)
        covered, evidence_ids, test_ids, defect_ids = covered_items(kind, item, trace_rows, phase, tests, defects)
        channel_count = evidence_channel_count(evidence_ids, evidence)
        if priority in {"P0", "P1"}:
            required.append(f"independent_evidence_channels:{minimum_channels}")
            if channel_count >= minimum_channels:
                covered.append(f"independent_evidence_channels:{minimum_channels}")

        required = list(dict.fromkeys(required))
        covered = [value for value in dict.fromkeys(covered) if value in required]
        rate = format_rate(len(covered), len(required)) if required else 1.0
        waiver_id = item.get("waiver_id", "") or next((row.get("waiver_id", "") for row in trace_rows if row.get("waiver_id")), "")
        waiver = waivers.get(waiver_id)
        waiver_ok = bool(waiver and referenced_by_waiver(waiver, subject_id))
        if phase == "release" and priority in {"P0", "P1"} and not allow_core_release_waiver:
            waiver_ok = False
        status = "PASS" if rate >= 1.0 else ("WAIVED" if waiver_ok else "FAIL")
        if status == "WAIVED" and priority in {"P0", "P1"}:
            core_waiver_count += 1
        rows.append({
            "coverage_id": "",
            "dimension": kind,
            "subject_id": subject_id,
            "priority": priority,
            "required_items": ";".join(required),
            "covered_items": ";".join(covered),
            "coverage_rate": f"{rate:.6f}",
            "status": status,
            "waiver_id": waiver_id,
            "evidence_ids": ";".join(evidence_ids),
            "notes": f"test_ids={';'.join(test_ids)};defect_ids={';'.join(defect_ids)};evidence_channels={channel_count}",
        })

    for index, row in enumerate(rows, start=1):
        row["coverage_id"] = f"COV-{index:04d}"

    summary: dict[str, dict[str, object]] = {}
    for priority in ["P0", "P1", "P2", "P3"]:
        subset = [row for row in rows if row["priority"] == priority]
        passed = [row for row in subset if row["status"] == "PASS"]
        accepted = [row for row in subset if row["status"] in {"PASS", "WAIVED"}]
        summary[priority] = {
            "total": len(subset),
            "passed": len(passed),
            "passed_or_waived": len(accepted),
            "pass_rate": format_rate(len(passed), len(subset)),
            "accepted_rate": format_rate(len(accepted), len(subset)),
        }

    discovery = discovery_status(root)
    core_rows = [row for row in rows if row["priority"] in {"P0", "P1"}]
    core_ok = bool(core_rows) and all(row["status"] == "PASS" for row in core_rows)
    core_accepted = bool(core_rows) and all(row["status"] in {"PASS", "WAIVED"} for row in core_rows)
    p2_threshold = float(project_setting(root, "p2_required_rate", 0.98))
    p2_ok = summary["P2"]["total"] == 0 or float(summary["P2"]["accepted_rate"]) >= p2_threshold

    if core_ok and p2_ok and discovery["pass"]:
        gate = "PASS"
    elif core_accepted and p2_ok and discovery["pass"] and core_waiver_count:
        gate = "CONDITIONAL"
    else:
        gate = "FAIL"

    return {
        "schema_version": "1.1",
        "gate_id": "G4-C",
        "project_dir": str(root),
        "execution_mode": mode,
        "phase": phase,
        "calculated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gate": gate,
        "core_subject_count": len(core_rows),
        "core_waiver_count": core_waiver_count,
        "p2_threshold": p2_threshold,
        "discovery": discovery,
        "summary": summary,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="计算桌面软件重建的多维覆盖率")
    parser.add_argument("project_dir")
    parser.add_argument(
        "--phase", "--level", dest="phase",
        choices=["spec", "implementation", "release"], default="spec",
    )
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--allow-conditional", action="store_true")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result = calculate(root, args.phase)
    matrix_path = root / "07_tests" / "COVERAGE_MATRIX.csv"
    fields = ["coverage_id", "dimension", "subject_id", "priority", "required_items", "covered_items", "coverage_rate", "status", "waiver_id", "evidence_ids", "notes"]
    write_csv_rows(matrix_path, fields, result["rows"])
    json_path = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / "coverage-results.json"
    write_json(json_path, result)

    summary_rows = [[p, v["total"], v["passed"], v["passed_or_waived"], f"{v['pass_rate']:.2%}", f"{v['accepted_rate']:.2%}"] for p, v in result["summary"].items()]
    failures = [row for row in result["rows"] if row["status"] == "FAIL"]
    failure_rows = [[row["priority"], row["dimension"], row["subject_id"], row["required_items"], row["covered_items"]] for row in failures[:300]]
    report = (
        "<!-- document_status: " + ("PASS" if result["gate"] == "PASS" else result["gate"]) + " -->\n"
        "# 覆盖完整性报告\n\n"
        f"- 阶段：{result['phase']}\n- 执行模式：{result['execution_mode']}\n- 门禁：**{result['gate']}**\n"
        f"- P0/P1 对象：{result['core_subject_count']}；核心豁免：{result['core_waiver_count']}\n"
        f"- 连续零新增核心发现轮次：{result['discovery']['consecutive_zero_new_core_rounds']}/{result['discovery']['required_zero_new_core_rounds']}\n\n"
        "## 按优先级统计\n\n" + markdown_table(["优先级", "总数", "直接通过", "通过/豁免", "直接通过率", "接受率"], summary_rows) + "\n\n"
        "## 未完整覆盖项\n\n" + (markdown_table(["优先级", "维度", "对象", "必需", "已覆盖"], failure_rows) if failure_rows else "无。") + "\n"
    )
    (root / "09_reports" / "COVERAGE_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    accepted = result["gate"] == "PASS" or (args.allow_conditional and result["gate"] == "CONDITIONAL")
    return 0 if accepted or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
