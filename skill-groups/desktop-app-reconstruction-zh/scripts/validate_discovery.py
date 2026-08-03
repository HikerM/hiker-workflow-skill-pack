#!/usr/bin/env python3
"""Validate discovery-channel diversity and consecutive P0/P1 saturation rounds."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from common import markdown_table, read_csv_rows, resolve_root, split_values, write_json

PASS_RESULTS = {"pass", "complete", "completed", "saturated", "saturated_within_scope", "通过", "完成", "范围内饱和"}


def read_int_setting(root: Path, key: str, default: int) -> int:
    path = root / "00_control" / "PROJECT.yaml"
    if not path.is_file():
        return default
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(\d+)", text, re.MULTILINE)
    return int(match.group(1)) if match else default


def as_int(value: str) -> int | None:
    try:
        return int((value or "").strip())
    except ValueError:
        return None


def validate(root: Path) -> dict[str, object]:
    required_rounds = max(1, read_int_setting(root, "discovery_saturation_rounds", 2))
    required_channels = max(1, read_int_setting(root, "p0_p1_min_discovery_channels", 2))
    rows = [row for row in read_csv_rows(root / "03_inventory" / "DISCOVERY_ROUNDS.csv") if row.get("round_id")]
    completed = [row for row in rows if row.get("result", "").strip().lower() in PASS_RESULTS]
    channels = sorted({channel for row in completed for channel in split_values(row.get("channel"))})
    issues: list[dict[str, str]] = []

    if len(completed) < required_rounds:
        issues.append({"severity": "BLOCKER", "item": "discovery_rounds", "issue": f"已完成轮次 {len(completed)} < {required_rounds}"})
    if len(channels) < required_channels:
        issues.append({"severity": "BLOCKER", "item": "channels", "issue": f"独立发现渠道 {len(channels)} < {required_channels}"})

    tail = completed[-required_rounds:] if len(completed) >= required_rounds else completed
    for row in tail:
        count = as_int(row.get("new_p0_p1_items", ""))
        if count is None:
            issues.append({"severity": "BLOCKER", "item": row.get("round_id", ""), "issue": "new_p0_p1_items 不是整数"})
        elif count != 0:
            issues.append({"severity": "BLOCKER", "item": row.get("round_id", ""), "issue": f"本轮仍新增 {count} 个 P0/P1 项"})
        if row.get("blockers", "").strip():
            issues.append({"severity": "BLOCKER", "item": row.get("round_id", ""), "issue": "饱和轮次仍有 blockers"})
        if not split_values(row.get("evidence_ids")):
            issues.append({"severity": "BLOCKER", "item": row.get("round_id", ""), "issue": "饱和轮次缺少 evidence_ids"})

    entry_rows = [row for row in read_csv_rows(root / "03_inventory" / "ENTRY_POINT_INVENTORY.csv") if row.get("entry_id") and row.get("in_scope", "true").strip().lower() not in {"false", "0", "no"}]
    if not entry_rows:
        issues.append({"severity": "BLOCKER", "item": "entry_inventory", "issue": "范围内入口库存为空"})

    gate = "PASS" if not any(item["severity"] == "BLOCKER" for item in issues) else "FAIL"
    return {
        "schema_version": "1.1", "gate_id": "G4-C", "gate": gate,
        "project_dir": str(root), "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "required_saturation_rounds": required_rounds, "completed_rounds": len(completed),
        "required_channels": required_channels, "channels": channels,
        "entry_count": len(entry_rows), "issues": issues,
        "boundary": "发现饱和只对冻结范围、已取得角色/数据/环境和已执行渠道有效，不证明不可见隐藏功能不存在。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证发现渠道和连续 P0/P1 饱和轮次")
    parser.add_argument("project_dir")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = validate(root)
    out = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / "discovery-results.json"
    write_json(out, result)
    issue_rows = [[item["severity"], item["item"], item["issue"]] for item in result["issues"]]
    report = (
        "# 发现饱和与遗漏风险报告\n\n"
        f"- 门禁：**{result['gate']}**\n- 完成轮次：{result['completed_rounds']} / {result['required_saturation_rounds']}\n"
        f"- 独立渠道：{len(result['channels'])} / {result['required_channels']}（{';'.join(result['channels'])}）\n"
        f"- 范围内入口：{result['entry_count']}\n\n"
        "## 问题\n\n" + (markdown_table(["级别", "项目", "问题"], issue_rows) if issue_rows else "无。") + "\n\n"
        "## 边界\n\n" + result["boundary"] + "\n"
    )
    (root / "09_reports" / "DISCOVERY_SATURATION_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "PASS" or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
