from __future__ import annotations

import json
import sys
from pathlib import Path

from corelib import ai_root, ensure_schema, git_info, read_json
from context_memory import ensure_memory_policy, limit_text, memory_status


def main() -> int:
    try: payload = json.load(sys.stdin)
    except Exception: payload = {}
    root = Path(payload.get("cwd") or ".").resolve(); ai = ai_root(root)
    if not ai.exists(): return 0
    ok, version = ensure_schema(root)
    if not ok:
        print(json.dumps({"continue": False, "stopReason": f"AI工程状态不可恢复：{version}", "systemMessage": "请先运行项目智能初始化或迁移 .ai 协议。"}, ensure_ascii=False)); return 0
    policy = ensure_memory_policy(root)
    task = read_json(ai / "runtime" / "task.json", {}); decisions = read_json(ai / "governance" / "locked-decisions.json", {}).get("decisions", []); active = ""
    try: active = (ai / "runtime" / "active-context.md").read_text(encoding="utf-8")
    except OSError: pass
    all_locked = [f"- {d.get('id')}: {d.get('content')}" for d in decisions if d.get("status") == "LOCKED"]; locked = all_locked[-policy["max_items_per_section"]:]
    git = git_info(root)
    status = memory_status(root)
    receipt = f"Bounded memory: active={status['active_context_chars']} chars; checkpoints={status['retained_checkpoints']} retained/{status['pruned_checkpoints']} compacted"
    context = "\n".join([f"[AI工程状态协议 {version}]", f"Session source: {payload.get('source')}", f"Git branch/head: {git.get('branch')} / {str(git.get('head'))[:12]}", receipt, active, f"## 锁定决策（共 {len(all_locked)} 项）", *(locked or ["- 无"]), *( ["- 列表已截断；修改前按需读取 .ai/governance/locked-decisions.json。"] if len(all_locked)>len(locked) else [] ), "规则：正式状态优先于聊天摘要；继续前不得覆盖锁定决策；用户中断指令按 control.json 处理。"])
    context = limit_text(context, policy["session_context_max_chars"], ".ai/ 与四个根状态文档")
    out = {"continue": True, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    print(json.dumps(out, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
