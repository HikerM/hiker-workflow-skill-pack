from __future__ import annotations

import json
import sys
from pathlib import Path

from corelib import ai_root, ensure_schema, git_info, read_json


def main() -> int:
    try: payload = json.load(sys.stdin)
    except Exception: payload = {}
    root = Path(payload.get("cwd") or ".").resolve(); ai = ai_root(root)
    if not ai.exists(): return 0
    ok, version = ensure_schema(root)
    if not ok:
        print(json.dumps({"continue": False, "stopReason": f"AI工程状态不可恢复：{version}", "systemMessage": "请先运行项目智能初始化或迁移 .ai 协议。"}, ensure_ascii=False)); return 0
    task = read_json(ai / "runtime" / "task.json", {}); decisions = read_json(ai / "governance" / "locked-decisions.json", {}).get("decisions", []); active = ""
    try: active = (ai / "runtime" / "active-context.md").read_text(encoding="utf-8")[:7000]
    except OSError: pass
    all_locked = [f"- {d.get('id')}: {d.get('content')}" for d in decisions if d.get("status") == "LOCKED"]; locked = all_locked[:20]
    git = git_info(root)
    context = "\n".join([f"[AI工程状态协议 {version}]", f"Session source: {payload.get('source')}", f"Git branch/head: {git.get('branch')} / {str(git.get('head'))[:12]}", active, f"## 锁定决策（共 {len(all_locked)} 项）", *(locked or ["- 无"]), *( ["- 列表已截断；任何修改前必须读取 .ai/governance/locked-decisions.json 全文。"] if len(all_locked)>20 else [] ), "规则：正式状态优先于聊天摘要；继续前不得覆盖锁定决策；用户中断指令按 control.json 处理。"])
    out = {"continue": True, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    print(json.dumps(out, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
