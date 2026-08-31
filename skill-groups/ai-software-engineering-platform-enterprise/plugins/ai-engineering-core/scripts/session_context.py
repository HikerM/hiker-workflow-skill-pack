from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from corelib import ai_root, ensure_schema, git_info, read_json
from context_memory import ensure_memory_policy, limit_text, memory_status
from session_epoch import assess as assess_epoch
from decision_memory import load as load_decisions, retrieve as retrieve_decisions


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try: payload = json.load(sys.stdin)
    except Exception: payload = {}
    root = Path(payload.get("cwd") or ".").resolve(); ai = ai_root(root)
    if not ai.exists(): return 0
    ok, version = ensure_schema(root)
    if not ok:
        print(json.dumps({"continue": False, "stopReason": f"AI工程状态不可恢复：{version}", "systemMessage": "请先运行项目智能初始化或迁移 .ai 协议。"}, ensure_ascii=False)); return 0
    policy = ensure_memory_policy(root)
    decision_memory = load_decisions(root); active = ""
    workspace_context = root / "CURRENT_CONTEXT.md"
    task_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(payload.get("task_id") or payload.get("taskId") or "").strip()).strip("._-").upper()
    task_context = ai / "runtime" / "task-contexts" / f"{task_id}.md" if task_id else None
    if task_context and task_context.is_file():
        active_path = task_context
    else:
        active_path = workspace_context if (ai / "governance" / "project-state.json").is_file() and workspace_context.is_file() else ai / "runtime" / "active-context.md"
    try: active = active_path.read_text(encoding="utf-8")
    except OSError: pass
    git = git_info(root)
    status = memory_status(root)
    status["active_context_chars"] = len(active)
    receipt = f"有界记忆：活动上下文 {status['active_context_chars']} 字符；热检查点 {status['retained_checkpoints']} 个、冷归档 {status['cold_archived_checkpoints']} 个"
    epoch = assess_epoch(root)
    goal = read_json(ai / "governance" / "goal-contract.json", {}) or {}
    raw_scope = payload.get("current_changed_scope") or payload.get("changed_scope") or []
    current_scope = [str(item) for item in raw_scope] if isinstance(raw_scope, list) else []
    if task_id and not current_scope:
        task_state = read_json(ai / "tasks" / f"{task_id}.json", {}) or {}
        current_scope = task_state.get("affected_files", []) if isinstance(task_state.get("affected_files"), list) else []
        if not current_scope and isinstance(task_state.get("change_contract"), dict):
            allowed = task_state["change_contract"].get("allowed_files", [])
            current_scope = allowed if isinstance(allowed, list) else []
    raw_generation = payload.get("project_generation", payload.get("state_generation"))
    try: current_generation = int(raw_generation) if raw_generation is not None else None
    except (TypeError, ValueError): current_generation = None
    decision_receipt = retrieve_decisions(
        decision_memory, current_goal=goal, current_task=task_id or None,
        current_generation=current_generation, current_scope=current_scope,
        limit=policy["max_items_per_section"],
    )
    locked = [f"- {item.get('id')}: {item.get('content')}" for item in decision_receipt["selected"]]
    goal_line = "项目目标契约：未设置；当前任务按自己的稳定目标指纹执行。"
    if goal.get("status") == "ACTIVE":
        goal_line = f"项目目标契约：{goal.get('goal_id')} r{goal.get('revision')} / {str(goal.get('fingerprint') or '')[:12]}；结果：{str(goal.get('outcome') or '')[:400]}"
    epoch_line = f"总控纪元：{epoch['epoch']}；轮换={'需要' if epoch['rotation_required'] else '无需'}；原因：{','.join(epoch['reasons']) or '无'}"
    binding_line = f"会话绑定：Task={task_id or 'master'}；Role={payload.get('role_family') or payload.get('roleFamily') or 'unknown'}；Lane={payload.get('ownership_lane') or payload.get('ownershipLane') or 'default'}"
    context = "\n".join([
        f"[智能工程状态协议 {version}]", f"会话来源：{payload.get('source')}", binding_line,
        f"Git分支/提交：{git.get('branch')} / {str(git.get('head'))[:12]}",
        f"恢复来源：{active_path.relative_to(root).as_posix()}", receipt, epoch_line, goal_line,
        "规则：正式状态优先于聊天摘要；只执行绑定Task与Lane；继续前不得覆盖锁定决策；用户中断指令按控制状态处理。",
        f"## 当前适用决定（{decision_receipt['selected_count']}/{decision_receipt['considered_count']}）", *(locked or ["- 无"]),
        *(["- Decision Memory 超出热状态预算；已停止部分召回，需在安全边界压缩后再采用其中决定。"] if decision_receipt["requires_compaction"] else []),
        *(["- 其余决定因 Goal、Task、generation、scope、authority 或 superseded 状态不适用，未注入。"] if decision_receipt["excluded"] else []),
        "## 当前有界工作集", active,
    ])
    context = limit_text(context, policy["session_context_max_chars"], ".ai/ 与四个根状态文档")
    out = {"continue": True, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    print(json.dumps(out, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
