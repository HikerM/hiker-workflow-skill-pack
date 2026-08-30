from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from corelib import ai_root, atomic_write_json, atomic_write_text, ensure_schema, git_info, read_json, sha256_file, utc_now
from context_memory import bounded_items, crop, enforce_checkpoint_retention, ensure_memory_policy, limit_text, memory_status
from suite_router import PLUGIN_DISPLAY, PLUGIN_FOR, skill_display
from suite_version import inspect_suite
from decision_memory import AUTHORITIES, record as record_decision


def task_path(root: Path) -> Path: return ai_root(root) / "runtime" / "task.json"
def control_path(root: Path) -> Path: return ai_root(root) / "runtime" / "control.json"
def routing_path(root: Path) -> Path: return ai_root(root) / "runtime" / "skill-routing.json"


def load_task(root: Path) -> dict:
    data = read_json(task_path(root), {})
    return data if isinstance(data, dict) else {}


def _next_task_gate(task: dict) -> str | None:
    progress = (task.get("convergence") or {}).get("delivery_progress") or {}
    if str(progress.get("next_business_gate") or "").strip():
        return crop(progress["next_business_gate"], 240)
    gates = (task.get("gate_applicability") or {}).get("gates") or {}
    state = str(task.get("state") or task.get("status") or "")
    order = {
        "Created": ("planning", "development", "architecture", "review", "testing", "documentation", "merge", "release"),
        "Planning": ("development", "architecture", "review", "testing", "documentation", "merge", "release"),
        "Development": ("architecture", "review", "testing", "documentation", "merge", "release"),
        "Review": ("testing", "documentation", "merge", "release"),
        "Testing": ("documentation", "merge", "release"),
        "MergedPendingCleanup": ("merge", "release"),
        "Merged": ("release",),
        "Released": (),
    }
    for gate in order.get(state, ("planning", "development", "review", "testing")):
        if not gates or (gates.get(gate) or {}).get("status") != "NOT_APPLICABLE":
            return gate
    return None


def direct_progress(root: Path) -> dict:
    ai = ai_root(root)
    reads = [
        "governance/goal-contract.json",
        "governance/task-index.json",
        "runtime/task.json",
        "runtime/checkpoint-ledger.json",
    ]
    goal = read_json(ai / reads[0], {}) or {}
    index = read_json(ai / reads[1], {}) or {}
    legacy_task = read_json(ai / reads[2], {}) or {}
    ledger = read_json(ai / reads[3], {}) or {}
    summaries = [
        item for item in (index.get("tasks") or [])
        if isinstance(item, dict) and item.get("task_id") and item.get("state") not in {"Merged", "Released"}
    ][:8]
    preferred_id = str(legacy_task.get("id") or legacy_task.get("task_id") or "")
    candidates = [str(item["task_id"]) for item in summaries]
    selected_id = preferred_id if preferred_id in candidates else candidates[0] if len(candidates) == 1 else ""
    ambiguity = None
    task: dict = {}
    if selected_id:
        relative = f"tasks/{re.sub(r'[^A-Za-z0-9._-]+', '-', selected_id).strip('._-')}.json"
        reads.append(relative)
        task = read_json(ai / relative, {}) or {}
    elif len(candidates) > 1:
        ambiguity = {"code": "AMBIGUOUS_CURRENT_TASK", "candidate_task_ids": candidates}
    elif isinstance(legacy_task, dict):
        task = legacy_task
    goal_binding = task.get("goal_binding") if isinstance(task.get("goal_binding"), dict) else {}
    current_goal = {
        "goal_id": goal.get("goal_id") or goal_binding.get("goal_id"),
        "revision": goal.get("revision") or goal_binding.get("revision"),
        "status": goal.get("status"),
        "outcome": crop(goal.get("outcome") or task.get("goal") or "", 400),
        "fingerprint": goal.get("fingerprint") or goal_binding.get("fingerprint"),
    }
    delivery = (task.get("convergence") or {}).get("delivery_progress") or {}
    completed = [crop(item, 240) for item in (task.get("completed_changes") or task.get("completed") or [])[-8:]]
    pending = [crop(item, 240) for item in (task.get("pending_items") or task.get("pending") or [])[:8]]
    blockers = [crop(item, 240) for item in (task.get("risks") or [])[:8]]
    if task.get("control_status") == "PAUSED" or task.get("status") == "PAUSED":
        blockers.insert(0, "TASK_PAUSED")
    adjustment = task.get("goal_adjustment") or {}
    if adjustment.get("status") not in {None, "CURRENT"}:
        blockers.insert(0, f"GOAL_ADJUSTMENT_{adjustment.get('status')}")
    convergence = task.get("convergence") or {}
    if convergence.get("status") in {"PIVOT_REQUIRED", "DIAGNOSIS_REQUIRED", "BUSINESS_REQUIRED"}:
        blockers.insert(0, str(convergence["status"]))
    retained = ledger.get("retained") if isinstance(ledger.get("retained"), list) else []
    checkpoint_value = retained[0] if retained and isinstance(retained[0], dict) else None
    return {
        "schema_version": "hiker-direct-progress/v1",
        "status": "AMBIGUOUS" if ambiguity else "READY" if task else "NO_ACTIVE_TASK",
        "current_goal": current_goal,
        "current_task": {
            "task_id": task.get("task_id") or task.get("id"),
            "state": task.get("state") or task.get("status"),
            "control_status": task.get("control_status"),
            "updated_at": task.get("updated_at"),
        } if task else None,
        "business_progress": {
            "last_summary": crop(delivery.get("last_summary") or "", 240),
            "business_events": int(delivery.get("business_events") or 0),
            "completed": completed,
            "pending": pending,
        },
        "checkpoint": checkpoint_value,
        "blockers": list(dict.fromkeys(blockers))[:8],
        "next_gate": _next_task_gate(task) if task else None,
        "ambiguity": ambiguity,
        "reads": reads,
        "cold_history_scanned": False,
        "git_scanned": False,
        "chat_history_used": False,
        "writes": 0,
    }


def save_task(root: Path, task: dict) -> None:
    task["updated_at"] = utc_now(); atomic_write_json(task_path(root), task)


def _application_receipt(loaded_skills: list[str]) -> str:
    reverse = {skill_display(internal): internal for internal in PLUGIN_FOR}
    items = []
    for display_name in loaded_skills:
        internal = reverse.get(display_name)
        if not internal:
            raise ValueError(f"unknown loaded skill display name: {display_name}")
        items.append(f"{PLUGIN_DISPLAY[PLUGIN_FOR[internal]]}｜{display_name}")
    return "已应用：" + "；".join(items) if items else ""


def record_routing(root: Path, stage: str, active_skills: list[str], deferred_skills: list[str], route_fingerprint: str = "", loaded_skills: list[str] | None = None) -> dict:
    active = list(dict.fromkeys(item.strip() for item in active_skills if item.strip()))
    deferred = [item for item in dict.fromkeys(item.strip() for item in deferred_skills if item.strip()) if item not in active]
    loaded = list(dict.fromkeys(item.strip() for item in (loaded_skills or []) if item.strip()))
    if len(active) > 2:
        raise ValueError("active atomic skills cannot exceed 2; router is excluded from this limit")
    if loaded and loaded != active:
        raise ValueError("loader telemetry must exactly match active atomic skills and preserve order")
    previous = read_json(routing_path(root), {})
    basis = {"stage": stage or "unknown", "active_atomic_skills": active, "deferred_atomic_skills": deferred}
    fingerprint = route_fingerprint or __import__("hashlib").sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    changed = fingerprint != previous.get("route_fingerprint")
    suite = inspect_suite()
    if not suite["consistent"]:
        raise ValueError("plugin suite version is inconsistent")
    data = {
        "schema_version": "1.0.0", "route_revision": int(previous.get("route_revision", 0)) + (1 if changed else 0),
        **basis, "loaded_atomic_skills": loaded, "router_counts_toward_limit": False, "max_loaded_atomic_skills": 2,
        "phase_transition": bool(previous and previous.get("stage") != basis["stage"]),
        "previous_stage": previous.get("stage") if previous else None,
        "application_receipt": _application_receipt(loaded),
        "receipt_source": "skill-loader-telemetry" if loaded else "route-declaration-only",
        "route_fingerprint": fingerprint, "updated_at": utc_now(),
        "suite_version": suite["version"], "suite_fingerprint": suite["fingerprint"],
    }
    atomic_write_json(routing_path(root), data)
    return data


def active_governance_task_files(root: Path, limit: int = 5) -> list[Path]:
    ai = ai_root(root)
    index = read_json(ai / "governance" / "task-index.json", {}) or {}
    summaries = index.get("tasks") if isinstance(index, dict) else []
    if isinstance(summaries, list):
        active_ids = [str(item.get("task_id") or "") for item in summaries if isinstance(item, dict) and item.get("state") not in {"Merged", "Released"}]
        paths = [ai / "tasks" / f"{re.sub(r'[^A-Za-z0-9._-]+', '-', task_id).strip('._-')}.json" for task_id in active_ids[:limit] if task_id]
        existing = [path for path in paths if path.is_file()]
        if existing or index:
            return existing
    folder = ai / "tasks"
    if not folder.is_dir():
        return []
    # Legacy fallback only. Once task-index.json exists, normal paths never enumerate all historical tasks.
    return sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)[:limit]


def update_active(root: Path, task: dict) -> None:
    policy = ensure_memory_policy(root); limit = policy["max_items_per_section"]
    source = ".ai/runtime/task.json"
    lines = ["# 当前有效上下文", "", f"- 任务：{crop(task.get('id') or '无', 120)}", f"- 目标：{crop(task.get('goal') or '无')}", f"- 状态：{task.get('status')}", f"- 计划版本：{task.get('plan_version', 0)}", f"- 允许范围：{crop(task.get('scope') or '未定义')}", "", "## 已完成"]
    lines += bounded_items(task.get("completed"), limit, source)
    lines += ["", "## 正在进行"] + bounded_items(task.get("working"), limit, source)
    lines += ["", "## 待处理"] + bounded_items(task.get("pending"), limit, source)
    lines += ["", "## 风险"] + bounded_items(task.get("risks"), limit, source)
    routing = read_json(routing_path(root), {})
    if routing:
        lines += ["", "## 当前 Skill 路由", "- 路由入口：智能工程轻量路由（不计入原子 Skill 上限）", f"- 当前阶段：{crop(routing.get('stage') or 'unknown', 120)}"]
        lines += [f"- 活跃原子 Skill：{crop('、'.join(routing.get('active_atomic_skills') or []) or '无')}" ]
        lines += [f"- 待执行原子 Skill：{crop('、'.join(routing.get('deferred_atomic_skills') or []) or '无')}" ]
    lines += ["", "## 恢复规则", "- 本文件是有界工作集，不是完整历史。", "- 事实恢复顺序：项目身份 → Task/决定 → Git → 文档 → 检查点 → 聊天摘要。"]
    text = limit_text("\n".join(lines), policy["active_context_max_chars"], source)
    atomic_write_text(ai_root(root) / "runtime" / "active-context.md", text)


def checkpoint(root: Path, label: str, event: str = "manual") -> Path:
    ai = ai_root(root); cp_dir = ai / "runtime" / "checkpoints"; cp_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "-")
    key_files = ["schema.json", "context/project.json", "context/tech-stack.json", "context/architecture.json", "context/standards.json", "runtime/task.json", "runtime/control.json", "runtime/active-context.md", "runtime/skill-routing.json", "governance/locked-decisions.json", "governance/ownership.json", "governance/project-state.json", "governance/task-index.json", "architecture/module-registry.json", "architecture/dependency-rules.json", "architecture/public-surface.json", "workspace/task-map.json", "quality/policy.json", "knowledge/metadata.json", "evidence/index.json"]
    for candidate in active_governance_task_files(root):
        key_files.append(candidate.relative_to(ai).as_posix())
    key_files = list(dict.fromkeys(key_files))
    root_files = ["PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md"]
    snapshot = {"schema_version": "1.0.0", "created_at": utc_now(), "label": label, "event": event, "git": git_info(root), "files": {}}
    for rel in key_files:
        p = ai / rel
        snapshot["files"][rel] = {"exists": p.exists(), "sha256": sha256_file(p)}
    for rel in root_files:
        p = root / rel
        snapshot["files"][f"root/{rel}"] = {"exists": p.exists(), "sha256": sha256_file(p)}
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("._-")[:80] or "checkpoint"
    path = cp_dir / f"{stamp}-{safe_label}.json"
    atomic_write_json(path, snapshot)
    # Keep a copy of mutable state for recovery without copying source code.
    state_dir = cp_dir / (path.stem + "-state")
    state_dir.mkdir(parents=True, exist_ok=True)
    for rel in key_files:
        src = ai / rel
        if src.exists():
            dst = state_dir / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    for rel in root_files:
        src = root / rel
        if src.exists():
            dst = state_dir / "root" / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    enforce_checkpoint_retention(root)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("task-start"); p.add_argument("--id", required=True); p.add_argument("--goal", required=True); p.add_argument("--scope", default="current task module")
    sub.add_parser("status")
    sub.add_parser("progress")
    p = sub.add_parser("pause"); p.add_argument("--reason", default="user interruption")
    sub.add_parser("resume")
    p = sub.add_parser("adjust"); p.add_argument("--instruction", required=True)
    p = sub.add_parser("checkpoint"); p.add_argument("--label", required=True)
    sub.add_parser("complete")
    sub.add_parser("validate")
    sub.add_parser("memory-status")
    p = sub.add_parser("route-record"); p.add_argument("--stage", required=True); p.add_argument("--active-skill", action="append", default=[]); p.add_argument("--loaded-skill", action="append", default=[]); p.add_argument("--deferred-skill", action="append", default=[]); p.add_argument("--route-fingerprint", default="")
    p = sub.add_parser("lock-decision"); p.add_argument("--id", required=True); p.add_argument("--content", required=True); p.add_argument("--reason", required=True); p.add_argument("--authority", choices=sorted(AUTHORITIES), default="USER_LOCKED_DECISION"); p.add_argument("--generation", type=int, default=0); p.add_argument("--task-id", action="append", default=[]); p.add_argument("--scope", action="append", default=[]); p.add_argument("--project-global", action="store_true"); p.add_argument("--supersedes")
    args = ap.parse_args(); root = Path(args.root).resolve()
    ok, version = ensure_schema(root)
    if not ok and args.cmd != "validate": raise SystemExit(f"STATE_ERROR: {version}")
    task = load_task(root)
    if args.cmd == "task-start":
        task = {"schema_version": "1.0.0", "id": args.id, "goal": args.goal, "scope": args.scope, "status": "EXECUTING", "plan_version": 1, "completed": [], "working": ["分析并执行当前计划"], "pending": [], "risks": [], "updated_at": utc_now()}; save_task(root, task); update_active(root, task); checkpoint(root, "task-start")
    elif args.cmd == "status":
        print(json.dumps({"schema_ok": ok, "schema": version, "task": task, "git": git_info(root), "control": read_json(control_path(root), {}), "skill_routing": read_json(routing_path(root), {})}, ensure_ascii=False, indent=2)); return 0
    elif args.cmd == "progress":
        print(json.dumps({"schema_ok": ok, "schema": version, "progress": direct_progress(root)}, ensure_ascii=False, indent=2)); return 0
    elif args.cmd == "pause":
        task["status"] = "PAUSED"; task.setdefault("risks", []).append(f"暂停原因：{args.reason}"); save_task(root, task); update_active(root, task); checkpoint(root, "paused")
    elif args.cmd == "resume":
        task["status"] = "EXECUTING"; save_task(root, task); update_active(root, task); atomic_write_json(control_path(root), {"schema_version": "1.0.0", "requested_action": None, "request_text": None, "updated_at": utc_now()})
    elif args.cmd == "adjust":
        task["status"] = "REPLANNING"; task["plan_version"] = int(task.get("plan_version", 0)) + 1; task.setdefault("plan_changes", []).append({"at": utc_now(), "instruction": args.instruction}); save_task(root, task); update_active(root, task); checkpoint(root, f"before-plan-v{task['plan_version']}")
    elif args.cmd == "checkpoint": print(checkpoint(root, args.label)); return 0
    elif args.cmd == "complete": task["status"] = "COMPLETED"; save_task(root, task); update_active(root, task); checkpoint(root, "completed")
    elif args.cmd == "validate":
        required = ["context/project.json", "context/tech-stack.json", "runtime/task.json", "runtime/active-context.md", "governance/locked-decisions.json"]
        missing = [x for x in required if not (ai_root(root) / x).exists()]
        print(json.dumps({"ok": ok and not missing, "schema": version, "missing": missing, "git": git_info(root)}, ensure_ascii=False, indent=2)); return 0 if ok and not missing else 2
    elif args.cmd == "memory-status":
        from session_epoch import assess as assess_epoch
        print(json.dumps({"ok": True, "memory": memory_status(root), "session_epoch": assess_epoch(root)}, ensure_ascii=False, indent=2)); return 0
    elif args.cmd == "route-record":
        try: routing = record_routing(root, args.stage, args.active_skill, args.deferred_skill, args.route_fingerprint, args.loaded_skill)
        except ValueError as exc: raise SystemExit(f"ROUTE_STATE_ERROR: {exc}")
        update_active(root, task); print(json.dumps({"ok": True, "routing": routing}, ensure_ascii=False, indent=2)); return 0
    elif args.cmd == "lock-decision":
        try:
            receipt = record_decision(
                root, decision_id=args.id, content=args.content, reason=args.reason,
                authority=args.authority, generation=args.generation, task_relevance=args.task_id,
                scope=args.scope, bind_current_goal=not args.project_global, supersedes=args.supersedes,
            )
        except ValueError as exc:
            raise SystemExit(f"DECISION_STATE_ERROR: {exc}")
        print(json.dumps({"ok": True, "command": args.cmd, **receipt}, ensure_ascii=False, indent=2)); return 0
    if args.cmd not in {"status", "progress", "validate", "checkpoint", "memory-status"}: print(json.dumps({"ok": True, "command": args.cmd, "task": load_task(root)}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
