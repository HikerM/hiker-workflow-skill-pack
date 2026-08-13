from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, read_json, repo_root, safe_id, state_lock

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


def key_for(task_id: str, role: str, repository: str, base_sha: str) -> str:
    raw = "|".join((safe_id(task_id).upper(), role.strip(), str(Path(repository).resolve()).lower(), base_sha.strip().lower()))
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
    return read_json(dispatch_file(root), {}) or {"schema_version": SCHEMA, "dispatches": {}, "notifications": {}}


def observe(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    state = load(root)
    key = key_for(args.task_id, args.role, args.repository or str(root), args.base_sha)
    previous = state["dispatches"].get(key, {})
    observed = classify_observation(args.api_result, args.thread_id, args.client_thread_id, args.runtime_status)
    entry = {
        "dispatch_key": key,
        "task_id": safe_id(args.task_id).upper(),
        "role": args.role,
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
    conflicts = [item for item in state["dispatches"].values() if item.get("dispatch_key") != key and item.get("task_id") == entry["task_id"] and item.get("role") == entry["role"] and item.get("state") in ACTIVE_STATES]
    create_allowed = observed == "EMPTY_CONFIRMED" and previous.get("state") not in ACTIVE_STATES and not conflicts
    return {"observation": entry, "create_allowed": create_allowed, "conflicts": conflicts, "rule": "only EMPTY_CONFIRMED may create"}


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
    p.add_argument("--thread-id"); p.add_argument("--client-thread-id"); p.add_argument("--runtime-status"); p.add_argument("--detail", default="")
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
        elif args.cmd == "environment":
            result = environment_plan(args.require, args.read_only)
        else:
            result = notify(root, args)
    print(json.dumps({"ok": result.get("ok", True), "result": result}, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
