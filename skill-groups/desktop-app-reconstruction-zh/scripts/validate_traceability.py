#!/usr/bin/env python3
"""Validate scope-to-deliverable traceability with referential integrity."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from common import (
    active_waiver_rows, collect_inventory_records, collect_spec_records,
    in_scope, is_core, is_pass, markdown_table, priority_of, project_setting,
    read_csv_rows, referenced_by_waiver, resolve_root, safe_relative_path,
    split_values, write_json,
)
from lib_recon import parse_simple_yaml


def duplicate_ids(rows: list[dict[str, str]], field: str) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        value = row.get(field, "")
        if value: counts[value] += 1
    return sorted(value for value, count in counts.items() if count > 1)


def manifest_ids(root: Path) -> set[str]:
    path = root / "00_control" / "DELIVERABLE_MANIFEST.yaml"
    if not path.is_file(): return set()
    try:
        data = parse_simple_yaml(path)
    except Exception:
        return set()
    items = data.get("items", []) if isinstance(data, dict) else []
    return {str(item.get("id", "")) for item in items if isinstance(item, dict) and item.get("id")}


def issue(issues: list[dict[str, str]], severity: str, priority: str, scope_id: str, item_id: str, message: str) -> None:
    issues.append({"severity": severity, "priority": priority, "scope_id": scope_id, "item_id": item_id, "issue": message})


def validate(root: Path, phase: str) -> dict[str, object]:
    scope_rows = [row for row in read_csv_rows(root / "00_control" / "SCOPE_MATRIX.csv") if in_scope(row) and row.get("scope_id")]
    scope_map = {row["scope_id"]: row for row in scope_rows}
    inventory_rows = [row for row in collect_inventory_records(root) if in_scope(row)]
    item_map = {row["record_id"]: row for row in inventory_rows}
    evidence_rows = read_csv_rows(root / "02_evidence" / "EVIDENCE_INDEX.csv")
    evidence = {row.get("evidence_id", ""): row for row in evidence_rows if row.get("evidence_id")}
    specs = collect_spec_records(root)
    task_rows = read_csv_rows(root / "05_technical_design" / "IMPLEMENTATION_TASKS.csv")
    tasks = {row.get("task_id", ""): row for row in task_rows if row.get("task_id")}
    test_rows = read_csv_rows(root / "07_tests" / "TEST_CASES.csv")
    tests = {row.get("test_id", ""): row for row in test_rows if row.get("test_id")}
    defect_rows = read_csv_rows(root / "07_tests" / "DEFECTS.csv")
    defects = {row.get("defect_id", ""): row for row in defect_rows if row.get("defect_id")}
    waivers = active_waiver_rows(root)
    deliverables = manifest_ids(root)
    traces = [row for row in read_csv_rows(root / "07_tests" / "TRACEABILITY_MATRIX.csv") if row.get("trace_id")]

    issues: list[dict[str, str]] = []
    # Duplicate IDs are always blockers because references become ambiguous.
    registries = [
        (scope_rows, "scope_id", "范围"), (evidence_rows, "evidence_id", "证据"),
        (task_rows, "task_id", "任务"), (test_rows, "test_id", "测试"),
        (defect_rows, "defect_id", "缺陷"), (traces, "trace_id", "追踪"),
    ]
    for rows, field, label in registries:
        for value in duplicate_ids(rows, field):
            issue(issues, "BLOCKER", "P0", "", value, f"{label} ID 重复：{value}")
    item_counts: dict[str, int] = defaultdict(int)
    for row in inventory_rows: item_counts[row["record_id"]] += 1
    for value, count in item_counts.items():
        if count > 1: issue(issues, "BLOCKER", "P0", "", value, f"库存 ID 跨文件重复：{value}")

    traces_by_scope: dict[str, list[dict[str, str]]] = defaultdict(list)
    traces_by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in traces:
        traces_by_scope[row.get("scope_id", "")].append(row)
        traces_by_item[row.get("item_id", "")].append(row)

    allow_core_release_waiver = bool(project_setting(root, "allow_core_waiver_at_release", False))

    for row in traces:
        scope_id = row.get("scope_id", "")
        item_id = row.get("item_id", "")
        source = scope_map.get(scope_id) or item_map.get(item_id) or row
        priority = priority_of(source)
        core = priority in {"P0", "P1"}
        severity = "BLOCKER" if core else "WARNING"
        waiver_id = row.get("waiver_id", "")
        waiver = waivers.get(waiver_id)
        waiver_ok = bool(waiver and (referenced_by_waiver(waiver, scope_id) or referenced_by_waiver(waiver, item_id)))
        if phase == "release" and core and not allow_core_release_waiver:
            waiver_ok = False

        if not scope_id or scope_id not in scope_map:
            issue(issues, severity, priority, scope_id, item_id, "scope_id 为空或不存在")
        if not item_id or item_id not in item_map:
            issue(issues, severity, priority, scope_id, item_id, "item_id 为空或未在库存登记")

        required_fields = ["evidence_ids", "spec_ids", "test_case_ids"]
        if phase in {"implementation", "release"}: required_fields += ["task_ids", "implementation_ids"]
        if phase == "release": required_fields += ["deliverable_ids"]
        for field in required_fields:
            if not split_values(row.get(field)) and not waiver_ok:
                issue(issues, severity, priority, scope_id, item_id, f"{field} 为空")

        for value in split_values(row.get("evidence_ids")):
            if value not in evidence: issue(issues, severity, priority, scope_id, item_id, f"证据 ID 不存在：{value}")
        for value in split_values(row.get("spec_ids")):
            if value not in specs: issue(issues, severity, priority, scope_id, item_id, f"规格 ID 不存在：{value}")
        for value in split_values(row.get("task_ids")):
            if value not in tasks: issue(issues, severity, priority, scope_id, item_id, f"任务 ID 不存在：{value}")
        for value in split_values(row.get("test_case_ids")):
            if value not in tests: issue(issues, severity, priority, scope_id, item_id, f"测试 ID 不存在：{value}")
        for value in split_values(row.get("defect_ids")):
            if value not in defects: issue(issues, severity, priority, scope_id, item_id, f"缺陷 ID 不存在：{value}")
        for value in split_values(row.get("deliverable_ids")):
            if value not in deliverables: issue(issues, severity, priority, scope_id, item_id, f"交付物 ID 不存在：{value}")

        if phase in {"implementation", "release"}:
            for value in split_values(row.get("implementation_ids")):
                rel = value.split("#", 1)[0].strip()
                ok, candidate = safe_relative_path(root, rel)
                if not ok:
                    issue(issues, severity, priority, scope_id, item_id, f"实现路径越出项目：{value}")
                elif not candidate.exists():
                    issue(issues, severity, priority, scope_id, item_id, f"实现路径不存在：{value}")

        test_ids = split_values(row.get("test_case_ids"))
        failed_tests = [test_id for test_id in test_ids if test_id in tests and tests[test_id].get("status", "").strip().upper() == "FAIL"]
        if failed_tests and not split_values(row.get("defect_ids")):
            issue(issues, severity, priority, scope_id, item_id, "失败测试没有缺陷 ID：" + ";".join(failed_tests))
        if phase == "release" and not waiver_ok:
            if not test_ids or not all(test_id in tests and is_pass(tests[test_id].get("status")) for test_id in test_ids):
                issue(issues, severity, priority, scope_id, item_id, "发布级测试未全部实际执行并通过")
            open_ids = []
            for defect_id in split_values(row.get("defect_ids")):
                defect = defects.get(defect_id)
                if defect and defect.get("status", "").strip().lower() not in {"closed", "fixed", "resolved", "verified", "已关闭", "已修复", "已验证"}:
                    open_ids.append(defect_id)
            if open_ids: issue(issues, severity, priority, scope_id, item_id, "存在未关闭缺陷：" + ";".join(open_ids))
            if row.get("chain_status", "").strip().upper() != "PASS":
                issue(issues, severity, priority, scope_id, item_id, "chain_status 不是 PASS")

        if waiver_id and not waiver_ok:
            issue(issues, severity, priority, scope_id, item_id, f"豁免不存在、过期、未批准或未关联主体：{waiver_id}")

    # Every in-scope scope and every core inventory subject must have a chain.
    for scope in scope_rows:
        sid = scope["scope_id"]
        linked = traces_by_scope.get(sid, [])
        if not linked:
            issue(issues, "BLOCKER" if is_core(scope) else "WARNING", priority_of(scope), sid, scope.get("item_id", ""), "范围项没有追踪行")
        elif scope.get("item_id") and not any(row.get("item_id") == scope["item_id"] for row in linked):
            issue(issues, "BLOCKER" if is_core(scope) else "WARNING", priority_of(scope), sid, scope["item_id"], "范围项指定的 item_id 没有对应追踪行")

    for item in inventory_rows:
        item_id = item["record_id"]
        if not traces_by_item.get(item_id):
            issue(issues, "BLOCKER" if is_core(item) else "WARNING", priority_of(item), "", item_id, "库存项没有追踪行")

    # Closed defects require explicit regression evidence.
    for defect_id, defect in defects.items():
        if defect.get("status", "").strip().lower() in {"closed", "fixed", "resolved", "verified", "已关闭", "已修复", "已验证"}:
            regression = split_values(defect.get("regression_test_ids"))
            if not regression or not is_pass(defect.get("retest_status")):
                issue(issues, "BLOCKER" if is_core(defect) else "WARNING", priority_of(defect), "", defect_id, "已关闭缺陷缺少通过的回归测试")
            for test_id in regression:
                if test_id not in tests or not is_pass(tests[test_id].get("status")):
                    issue(issues, "BLOCKER" if is_core(defect) else "WARNING", priority_of(defect), "", defect_id, f"回归测试不存在或未通过：{test_id}")

    blockers = [item for item in issues if item["severity"] == "BLOCKER"]
    core_subject_count = sum(1 for row in scope_rows if is_core(row)) + sum(1 for row in inventory_rows if is_core(row))
    gate = "PASS" if scope_rows and core_subject_count > 0 and not blockers else "FAIL"
    return {
        "schema_version": "1.1", "project_dir": str(root), "phase": phase,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gate": gate, "scope_count": len(scope_rows), "inventory_count": len(inventory_rows),
        "trace_count": len(traces), "core_subject_count": core_subject_count,
        "blocker_count": len(blockers), "issue_count": len(issues), "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查范围到证据、规格、实现、测试和交付物的追踪链")
    parser.add_argument("project_dir")
    parser.add_argument("--phase", "--level", dest="phase", choices=["spec", "implementation", "release"], default="spec")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr); return 2

    result = validate(root, args.phase)
    json_path = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / "traceability-results.json"
    write_json(json_path, result)
    rows = [[item["severity"], item["priority"], item["scope_id"], item["item_id"], item["issue"]] for item in result["issues"][:500]]
    report = (
        "<!-- document_status: " + result["gate"] + " -->\n"
        "# 全链路追踪验证报告\n\n"
        f"- 阶段：{result['phase']}\n- 门禁：**{result['gate']}**\n"
        f"- 范围：{result['scope_count']}；库存：{result['inventory_count']}；追踪行：{result['trace_count']}\n"
        f"- 阻断：{result['blocker_count']}；总问题：{result['issue_count']}\n\n"
        "## 问题\n\n" + (markdown_table(["级别", "优先级", "范围", "对象", "问题"], rows) if rows else "无。") + "\n"
    )
    (root / "09_reports" / "TRACEABILITY_VALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "PASS" or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
