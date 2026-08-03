#!/usr/bin/env python3
"""Detect unlinked scope, inventory, specification, task, test, evidence and code artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from common import (
    collect_inventory_records, collect_spec_records, in_scope, is_core, is_pass,
    markdown_table, priority_of, read_csv_rows, resolve_root, split_values, write_json,
)


def add(issues: list[dict[str, str]], kind: str, record_id: str, priority: str, severity: str, message: str) -> None:
    issues.append({"kind": kind, "id": record_id, "priority": priority, "severity": severity, "issue": message})


def detect(root: Path, phase: str) -> dict[str, object]:
    scopes = [row for row in read_csv_rows(root / "00_control" / "SCOPE_MATRIX.csv") if in_scope(row) and row.get("scope_id")]
    inventory = [row for row in collect_inventory_records(root) if in_scope(row)]
    specs = collect_spec_records(root)
    tasks = {row.get("task_id", ""): row for row in read_csv_rows(root / "05_technical_design" / "IMPLEMENTATION_TASKS.csv") if row.get("task_id")}
    tests = {row.get("test_id", ""): row for row in read_csv_rows(root / "07_tests" / "TEST_CASES.csv") if row.get("test_id")}
    defects = {row.get("defect_id", ""): row for row in read_csv_rows(root / "07_tests" / "DEFECTS.csv") if row.get("defect_id")}
    evidence = {row.get("evidence_id", ""): row for row in read_csv_rows(root / "02_evidence" / "EVIDENCE_INDEX.csv") if row.get("evidence_id")}
    traces = [row for row in read_csv_rows(root / "07_tests" / "TRACEABILITY_MATRIX.csv") if row.get("trace_id")]

    trace_scope_ids = {row.get("scope_id", "") for row in traces if row.get("scope_id")}
    trace_item_ids = {row.get("item_id", "") for row in traces if row.get("item_id")}
    trace_evidence_ids = {value for row in traces for value in split_values(row.get("evidence_ids"))}
    trace_spec_ids = {value for row in traces for value in split_values(row.get("spec_ids"))}
    trace_task_ids = {value for row in traces for value in split_values(row.get("task_ids"))}
    trace_test_ids = {value for row in traces for value in split_values(row.get("test_case_ids"))}
    trace_defect_ids = {value for row in traces for value in split_values(row.get("defect_ids"))}
    trace_implementation = {value.split("#", 1)[0] for row in traces for value in split_values(row.get("implementation_ids"))}

    # Inventory objects such as entry points, controls, roles and performance scenarios
    # can be linked by another inventory record even when they do not own a dedicated
    # trace row. This avoids treating a valid cross-reference as an orphan while core
    # feature/page chains are still required below.
    inventory_cross_refs: set[str] = set()
    cross_ref_fields = {
        "entry": ("related_ids",),
        "page": ("entry_points", "role_ids"),
        "control": ("page_id", "interaction_ids", "visible_roles"),
        "interaction": ("page_id", "control_ids"),
        "menu_or_shortcut": ("parent_id", "page_id", "interaction_id", "visible_roles"),
        "feature": ("entry_points", "role_ids", "error_scenario_ids", "performance_scenario_ids"),
        "data": ("producers", "consumers"),
        "permission": ("role_id", "resource_id"),
        "external_dependency": (),
        "performance": ("related_feature_ids",),
        "error": (),
    }
    for record in inventory:
        for field in cross_ref_fields.get(record["record_kind"], ()):
            inventory_cross_refs.update(split_values(record.get(field)))

    issues: list[dict[str, str]] = []
    for row in scopes:
        if row["scope_id"] not in trace_scope_ids:
            add(issues, "scope", row["scope_id"], priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "范围项没有追踪行")

    for row in inventory:
        record_id = row["record_id"]
        if record_id not in trace_item_ids and record_id not in inventory_cross_refs:
            add(issues, row["record_kind"], record_id, priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "库存项既没有追踪行，也未被其他库存对象关联")
        if row["record_kind"] == "control" and not split_values(row.get("interaction_ids")):
            add(issues, "control", record_id, priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "可交互控件没有 interaction_ids")
        if row["record_kind"] == "performance" and not split_values(row.get("related_feature_ids")):
            add(issues, "performance", record_id, priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "性能场景没有关联功能")

    for spec_id, row in specs.items():
        if spec_id not in trace_spec_ids:
            core = row.get("priority") in {"P0", "P1"}
            add(issues, "spec", spec_id, row.get("priority", "P3"), "BLOCKER" if core else "WARNING", "规格未被追踪矩阵引用")

    for task_id, row in tasks.items():
        if task_id not in trace_task_ids:
            add(issues, "task", task_id, priority_of(row), "BLOCKER" if is_core(row) and phase in {"implementation", "release"} else "WARNING", "实施任务未被追踪矩阵引用")

    for test_id, row in tests.items():
        if test_id not in trace_test_ids:
            add(issues, "test", test_id, priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "测试用例未被追踪矩阵引用")
        if row.get("status", "").strip().upper() == "FAIL" and not split_values(row.get("defect_ids")):
            add(issues, "test", test_id, priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "失败测试没有缺陷 ID")

    for defect_id, row in defects.items():
        status = row.get("status", "").strip().lower()
        closed = status in {"closed", "fixed", "resolved", "verified", "已关闭", "已修复", "已验证"}
        if closed:
            regression = split_values(row.get("regression_test_ids"))
            if not regression or not is_pass(row.get("retest_status")):
                add(issues, "defect", defect_id, priority_of(row), "BLOCKER" if is_core(row) else "WARNING", "已关闭缺陷没有通过的回归测试")
        elif phase == "release" and is_core(row):
            add(issues, "defect", defect_id, priority_of(row), "BLOCKER", "发布阶段存在未关闭 P0/P1 缺陷")
        if defect_id not in trace_defect_ids and status not in {"superseded", "duplicate"}:
            add(issues, "defect", defect_id, priority_of(row), "WARNING", "缺陷未被追踪矩阵引用")

    for evidence_id, row in evidence.items():
        direct = split_values(row.get("related_scope_ids")) + split_values(row.get("related_inventory_ids")) + split_values(row.get("related_spec_ids"))
        if evidence_id not in trace_evidence_ids and not direct:
            add(issues, "evidence", evidence_id, "P3", "WARNING", "证据未关联范围、库存、规格或追踪行")

    if phase in {"implementation", "release"}:
        src = root / "06_implementation" / "src"
        if src.is_dir():
            for path in src.rglob("*"):
                if not path.is_file() or path.name in {".gitkeep", ".keep"}:
                    continue
                rel = path.relative_to(root).as_posix()
                if rel not in trace_implementation:
                    add(issues, "implementation", rel, "P3", "WARNING", "源码文件未被 implementation_ids 直接引用")

    blockers = [row for row in issues if row["severity"] == "BLOCKER"]
    core_inventory = [row for row in inventory if is_core(row)]
    gate = "PASS" if scopes and core_inventory and not blockers else "FAIL"
    return {
        "schema_version": "1.1", "project_dir": str(root), "phase": phase,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gate": gate, "scope_count": len(scopes), "core_inventory_count": len(core_inventory),
        "blocker_count": len(blockers), "issue_count": len(issues), "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查重建项目的孤立范围、库存、规格、任务、测试和缺陷")
    parser.add_argument("project_dir")
    parser.add_argument("--phase", choices=["spec", "implementation", "release"], default="spec")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr); return 2
    result = detect(root, args.phase)
    json_path = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / "orphan-results.json"
    write_json(json_path, result)
    rows = [[item["severity"], item["priority"], item["kind"], item["id"], item["issue"]] for item in result["issues"][:600]]
    report = (
        "<!-- document_status: " + result["gate"] + " -->\n"
        "# 孤立项检查报告\n\n"
        f"- 阶段：{result['phase']}\n- 门禁：**{result['gate']}**\n"
        f"- 阻断：{result['blocker_count']}；总问题：{result['issue_count']}\n\n"
        "## 明细\n\n" + (markdown_table(["级别", "优先级", "类型", "ID", "问题"], rows) if rows else "无。") + "\n"
    )
    (root / "09_reports" / "ORPHAN_CHECK_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "PASS" or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
