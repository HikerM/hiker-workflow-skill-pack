from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from corelib import ai_root, atomic_write_json, read_json, utc_now

RULES = [
    ("PAUSE", [r"暂停(?:当前)?任务", r"先停一下", r"停止当前执行", r"pause(?: current)? task"]),
    ("RESUME", [r"继续执行", r"恢复执行", r"接着做", r"resume(?: task)?"]),
    ("STATUS", [r"查看(?:当前)?状态", r"做到哪", r"当前进度", r"task status"]),
    ("ROLLBACK_REQUEST", [r"回滚到", r"恢复到.*检查点", r"rollback to"]),
    ("ADJUST", [r"调整方向", r"改成", r"不要.*方案", r"重新规划", r"change direction", r"revise (?:the )?plan"]),
]


def classify(prompt: str) -> str | None:
    for action, patterns in RULES:
        if any(re.search(p, prompt, re.I) for p in patterns): return action
    return None


def main() -> int:
    try: payload = json.load(sys.stdin)
    except Exception: return 0
    root = Path(payload.get("cwd") or ".").resolve(); prompt = str(payload.get("prompt") or ""); action = classify(prompt)
    if not action or not (ai_root(root) / "schema.json").exists(): return 0
    current = read_json(ai_root(root) / "runtime" / "control.json", {})
    record = {"schema_version": "1.0.0", "requested_action": action, "request_text": prompt[:4000], "session_id": payload.get("session_id"), "turn_id": payload.get("turn_id"), "previous_action": current.get("requested_action") if isinstance(current, dict) else None, "updated_at": utc_now()}
    atomic_write_json(ai_root(root) / "runtime" / "control.json", record)
    guidance = {
        "PAUSE": "用户要求软暂停。立即停止新增修改，保存当前状态和检查点；不要把任务标记失败。",
        "RESUME": "用户要求恢复。先验证 .ai 状态、当前分支和最新检查点，再从 pending/working 继续，不重复已完成工作。",
        "STATUS": "用户只要求状态。读取 task.json、active-context.md、Git状态后简洁报告，不开始新修改。",
        "ROLLBACK_REQUEST": "用户请求回滚。先生成影响和恢复计划；默认不得执行破坏性 reset/restore，除非用户明确批准具体动作。",
        "ADJUST": "用户中途调整方向。保留无关已完成成果，分析受影响范围，增加计划版本，废弃旧方案仅限受影响部分，然后继续。",
    }[action]
    out = {"continue": True, "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": f"[AI工程运行时控制] {guidance} 控制记录已写入 .ai/runtime/control.json。"}}
    print(json.dumps(out, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
