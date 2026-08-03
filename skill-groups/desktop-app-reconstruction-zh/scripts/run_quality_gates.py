#!/usr/bin/env python3
"""Run the aggregated quality-gate profile and write a concise summary."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from common import markdown_table, resolve_root, write_json

PROFILE_MAP = {
    "spec": "coverage",
    "technology": "technology",
    "implementation": "implementation",
    "release": "release",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="执行桌面软件重建的聚合质量门禁")
    parser.add_argument("project_dir")
    parser.add_argument("--phase", choices=list(PROFILE_MAP), default="spec")
    parser.add_argument("--write-checksums", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr); return 2

    script = Path(__file__).resolve().parent / "validate_project.py"
    machine_json = root / "09_reports" / ".validation" / f"quality-{args.phase}.json"
    cmd = [sys.executable, str(script), str(root), "--profile", PROFILE_MAP[args.phase], "--json", str(machine_json)]
    if args.write_checksums: cmd.append("--write-checksums")
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, check=False, timeout=300)
    try:
        result = json.loads(machine_json.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        result = {"gate": "FAIL", "checks": {}, "error": f"无法读取聚合门禁结果：{exc}"}

    check_rows = []
    for name, value in result.get("checks", {}).items():
        if isinstance(value, dict):
            detail = value.get("error") or value.get("message") or f"issues={len(value.get('issues', [])) if isinstance(value.get('issues'), list) else ''}"
            check_rows.append([name, value.get("gate", "UNKNOWN"), detail])
    gate = result.get("gate", "FAIL")
    summary = {
        "schema_version": "1.1", "project_dir": str(root), "phase": args.phase,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gate": gate, "validate_project_exit_code": completed.returncode,
        "checks": result.get("checks", {}),
        "stderr": completed.stderr.strip()[-4000:] if completed.stderr.strip() else "",
    }
    output = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / "QUALITY_GATES_SUMMARY.json"
    write_json(output, summary)
    report = (
        "<!-- document_status: " + str(gate) + " -->\n"
        "# 质量门禁总览\n\n"
        f"- 阶段：{args.phase}\n- 门禁：**{gate}**\n- 时间：{summary['checked_at']}\n\n"
        "## 子门禁\n\n" + (markdown_table(["检查", "结果", "摘要"], check_rows) if check_rows else "无可用结果。") + "\n\n"
        "## 边界\n\n机器门禁不替代授权、人工视觉复核和真实目标环境测试。\n"
    )
    (root / "09_reports" / "QUALITY_GATES_SUMMARY.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
