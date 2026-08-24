from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, locked_state, read_json, repo_root, safe_id, state_lock
from session_pool import bind as bind_slot
from session_pool import complete as complete_slot
from session_pool import plan as plan_slot
from session_pool import release_ack as release_slot
from session_pool import status as pool_status
from goal_contract import verify_binding

SCHEMA = "1.0.0"
ACTIVE_STATES = {"SETUP_PENDING", "BOUND", "READY", "RUNNING", "WAITING_APPROVAL", "UNKNOWN_RUNNING"}
TERMINAL_STATES = {"DELIVERED", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}
RUNTIME_MAP = {
    "ready": "READY", "inprogress": "RUNNING", "running": "RUNNING", "active": "RUNNING",
    "waitingonapproval": "WAITING_APPROVAL", "waitingapproval": "WAITING_APPROVAL",
    "completed": "COMPLETED", "failed": "FAILED", "cancelled": "CANCELLED",
    "interrupted": "INTERRUPTED", "delivered": "DELIVERED",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dispatch_file(root: Path) -> Path:
    return root / ".ai" / "governance" / "dispatch-state.json"


def key_for(task_id: str, role: str, repository: str, base_sha: str, ownership_lane: str = "default") -> str:
    raw = "|".join((safe_id(task_id).upper(), role.strip(), safe_id(ownership_lane).lower(), str(Path(repository).resolve()).lower(), base_sha.strip().lower()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_runtime(value: str | None) -> str | None:
    if not value:
        return None
    token = "".join(ch for ch in value.lower() if ch.isalnum())
    return RUNTIME_MAP.get(token)


def classify_observation(
    api_result: str,
    thread_id: str | None = None,
    client_thread_id: str | None = None,
    runtime_status: str | None = None,
) -> str:
    api = api_result.upper()
    runtime = normalize_runtime(runtime_status)
    if api == "ERROR":
        return "API_ERROR"
    if api == "TIMEOUT":
        return runtime or "QUERY_TIMEOUT"
    if thread_id:
        return runtime or "BOUND"
    if client_thread_id:
        return "SETUP_PENDING"
    if api == "EMPTY":
        return "EMPTY_CONFIRMED"
    if api == "FOUND":
        return runtime or "UNKNOWN_RUNNING"
    raise ValueError(f"unsupported api result: {api_result}")


def load(root: Path) -> dict[str, Any]:
    state = read_json(dispatch_file(root), {}) or {}
    state.setdefault("schema_version", SCHEMA)
    state.setdefault("dispatches", {})
    state.setdefault("notifications", {})
    return state


@locked_state
def observe(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    state = load(root)
    lane = getattr(args, "ownership_lane", None) or "default"
    key = key_for(args.task_id, args.role, args.repository or str(root), args.base_sha, lane)
    previous = state["dispatches"].get(key, {})
    observed = classify_observation(args.api_result, args.thread_id, args.client_thread_id, args.runtime_status)
    entry = {
        "dispatch_key": key,
        "task_id": safe_id(args.task_id).upper(),
        "role": args.role,
        "ownership_lane": lane,
        "repository": str(Path(args.repository or root).resolve()),
        "base_sha": args.base_sha,
        "state": observed,
        "thread_id": args.thread_id or previous.get("thread_id"),
        "client_thread_id": args.client_thread_id or previous.get("client_thread_id"),
        "detail": args.detail,
        "observed_at": now(),
    }
    state["dispatches"][key] = entry
    state["updated_at"] = now()
    atomic_json(dispatch_file(root), state)
    conflicts = [item for item in state["dispatches"].values() if item.get("dispatch_key") != key and item.get("task_id") == entry["task_id"] and item.get("role") == entry["role"] and item.get("ownership_lane", "default") == lane and item.get("state") in ACTIVE_STATES]
    project = read_json(root / ".ai" / "governance" / "project-state.json", {}) or {}
    project_id = args.project_id or str(project.get("project_id") or root.name)
    session = plan_slot(
        root,
        project_id,
        args.task_id,
        args.role,
        args.repository or str(root),
        args.base_sha,
        observed,
        args.thread_id,
        args.client_thread_id,
        lane,
    )
    task = read_json(root / ".ai" / "tasks" / f"{safe_id(args.task_id).upper()}.json", {}) or {}
    goal_check = verify_binding(root, task.get("goal_binding")) if task else {"ok": True, "status": "TASK_NOT_INITIALIZED"}
    if not goal_check["ok"]:
        session = {**session, "action": "BLOCK_GOAL_DRIFT", "reason": "任务绑定的目标修订已过期，禁止按旧目标继续"}
    elif (task.get("goal_adjustment") or {}).get("status") == "REPLAN_REQUIRED":
        session = {**session, "action": "BLOCK_REPLAN_REQUIRED", "reason": "目标已重新绑定但变更契约尚未对账，禁止继续旧实现"}
    task_map = read_json(root / ".ai" / "workspace" / "task-map.json", {}) or {}
    lane_contract = next((item for item in task_map.get("lanes", []) if item.get("ownership_lane") == lane), {})
    serial_with = set(lane_contract.get("serial_with") or [])
    active_conflicts = [
        item for item in pool_status(root, project_id).get("slots", [])
        if item.get("role_family") == "writer"
        and item.get("ownership_lane") in serial_with
        and item.get("state") in ACTIVE_STATES
    ]
    if active_conflicts:
        session = {**session, "action": "BLOCK_SCOPE_CONFLICT", "reason": "写范围与活动所有权通道重叠，必须串行"}
    fallback = {
        "allowed": session.get("action") == "BLOCK_QUERY" and not getattr(args, "require_isolated_runtime", False),
        "mode": "CURRENT_THREAD_BOUNDED" if session.get("action") == "BLOCK_QUERY" and not getattr(args, "require_isolated_runtime", False) else None,
        "rule": "查询失败只禁止新建桌面任务；不需要新隔离运行时的现有工作可在当前有界上下文继续",
    }
    create_allowed = session["action"] == "CREATE_THREAD" and previous.get("state") not in ACTIVE_STATES and not conflicts
    context_packet = root / ".ai" / "runtime" / "task-contexts" / f"{safe_id(args.task_id).upper()}.md"
    return {"observation": entry, "session": session, "create_allowed": create_allowed, "fallback": fallback, "goal_check": goal_check, "lane_contract": lane_contract, "scope_conflicts": active_conflicts, "context_packet": context_packet.relative_to(root).as_posix(), "conflicts": conflicts, "rule": "reuse a project/repository/role/lane slot before creating a thread"}


def environment_plan(requirements: list[str], read_only: bool) -> dict[str, Any]:
    req = {value.lower() for value in requirements}
    repository = "repository" in req or "repo" in req
    docker = "docker" in req
    device = "device" in req or "unity" in req
    browser = "browser-session" in req or "browser" in req
    if repository or docker or device:
        environment = "project-worktree" if not read_only else "project-local-readonly"
    elif browser:
        environment = "current-host-session"
    else:
        environment = "projectless"
    blockers = []
    if docker and environment == "projectless":
        blockers.append("Docker任务禁止使用projectless")
    return {"requirements": sorted(req), "read_only": read_only, "recommended_environment": environment, "blockers": blockers, "ok": not blockers}


def status_fingerprint(task_id: str, status: str, progress: str, blocker: str, evidence_id: str, next_gate: str) -> str:
    payload = json.dumps([task_id, status, progress, blocker, evidence_id, next_gate], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


@locked_state
def notify(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    state = load(root)
    fingerprint = status_fingerprint(args.task_id, args.status, args.progress, args.blocker, args.evidence_id, args.next_gate)
    previous = state["notifications"].get(safe_id(args.task_id).upper())
    should_notify = previous != fingerprint
    if args.ack and should_notify:
        state["notifications"][safe_id(args.task_id).upper()] = fingerprint
        state["updated_at"] = now()
        atomic_json(dispatch_file(root), state)
    return {"fingerprint": fingerprint, "previous": previous, "should_notify": should_notify, "acked": bool(args.ack and should_notify)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("observe")
    p.add_argument("--task-id", required=True); p.add_argument("--role", required=True); p.add_argument("--repository")
    p.add_argument("--base-sha", required=True); p.add_argument("--api-result", choices=["ERROR", "TIMEOUT", "EMPTY", "FOUND"], required=True)
    p.add_argument("--project-id"); p.add_argument("--thread-id"); p.add_argument("--client-thread-id"); p.add_argument("--runtime-status"); p.add_argument("--detail", default="")
    p.add_argument("--ownership-lane", default="default"); p.add_argument("--require-isolated-runtime", action="store_true")
    p = sub.add_parser("bind")
    p.add_argument("--project-id", required=True); p.add_argument("--task-id", required=True); p.add_argument("--role", required=True)
    p.add_argument("--repository"); p.add_argument("--base-sha", required=True); p.add_argument("--thread-id"); p.add_argument("--client-thread-id")
    p.add_argument("--runtime-state", choices=sorted(ACTIVE_STATES | {"IDLE_REUSABLE"}), required=True); p.add_argument("--worktree"); p.add_argument("--ownership-lane", default="default")
    p = sub.add_parser("complete")
    p.add_argument("--project-id", required=True); p.add_argument("--task-id", required=True); p.add_argument("--role", required=True); p.add_argument("--repository")
    p.add_argument("--outcome", choices=["PASS", "FAIL", "CANCELLED", "SUPERSEDED"], required=True); p.add_argument("--checkpoint-id", required=True); p.add_argument("--candidate-id")
    p.add_argument("--locks-released", action="store_true"); p.add_argument("--resources-released", action="store_true")
    p.add_argument("--worktree-state", choices=["CLEAN", "CLOSED", "PAUSED_DIRTY"], required=True); p.add_argument("--project-terminal", action="store_true"); p.add_argument("--ownership-lane", default="default")
    p = sub.add_parser("release-ack")
    p.add_argument("--project-id", required=True); p.add_argument("--role", required=True); p.add_argument("--repository")
    p.add_argument("--thread-archived", action="store_true"); p.add_argument("--runtime-release-verified", action="store_true")
    p.add_argument("--worktree-state", choices=["KEPT", "CLOSED"], required=True); p.add_argument("--ownership-lane", default="default"); p.add_argument("--probe-id")
    p = sub.add_parser("pool-status"); p.add_argument("--project-id")
    p = sub.add_parser("environment")
    p.add_argument("--require", action="append", default=[]); p.add_argument("--read-only", action="store_true")
    p = sub.add_parser("notify")
    p.add_argument("--task-id", required=True); p.add_argument("--status", required=True); p.add_argument("--progress", default="")
    p.add_argument("--blocker", default=""); p.add_argument("--evidence-id", default=""); p.add_argument("--next-gate", default=""); p.add_argument("--ack", action="store_true")
    args = parser.parse_args()
    root = repo_root(Path(args.root).resolve())
    with state_lock(root):
        if args.cmd == "observe":
            result = observe(root, args)
        elif args.cmd == "bind":
            result = bind_slot(root, args.project_id, args.task_id, args.role, args.repository or str(root), args.base_sha, args.thread_id, args.client_thread_id, args.runtime_state, args.worktree, args.ownership_lane)
        elif args.cmd == "complete":
            result = complete_slot(root, args.project_id, args.task_id, args.role, args.repository or str(root), args.outcome, args.checkpoint_id, args.locks_released, args.resources_released, args.worktree_state, args.candidate_id, args.project_terminal, args.ownership_lane)
        elif args.cmd == "release-ack":
            result = release_slot(root, args.project_id, args.role, args.repository or str(root), args.thread_archived, args.runtime_release_verified, args.worktree_state, args.ownership_lane, args.probe_id)
        elif args.cmd == "pool-status":
            result = pool_status(root, args.project_id)
        elif args.cmd == "environment":
            result = environment_plan(args.require, args.read_only)
        else:
            result = notify(root, args)
    print(json.dumps({"ok": result.get("ok", True), "result": result}, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
