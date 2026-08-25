from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from desktop_pressure import active_lease_count, apply_pressure, current_pressure, evaluate_local_pressure
from dispatch_state import (
    OUTSTANDING_TURN_LEASES,
    TURN_ACTIVE_STATES,
    TURN_IN_FLIGHT_STATES,
    TURN_RESOLVED_STATES,
    TURN_TERMINAL_STATES,
    dispatch_file,
    load_dispatch,
    now,
    status_token,
    turn_pair,
)
from session_pool import project_policy
from turn_lease import (
    active_lease_count as active_runtime_lease_count,
    close_turn_lease,
    inspect_turn_lease,
    open_turn_lease,
    refresh_turn_lease,
)
from turn_recovery import probe_turn_recovery
from turn_summary import write_turn_summary
from workspacelib import atomic_json, locked_state, read_json, safe_id


def _thread_key(thread_id: str) -> str:
    if not str(thread_id or "").strip():
        raise ValueError("thread id is required")
    return hashlib.sha256(str(thread_id).encode("utf-8")).hexdigest()[:24]


def _turn_attempt_id(task_id: str | None, dispatch_id: str, message_digest: str) -> str:
    raw = "|".join((safe_id(task_id).upper() if task_id else "UNBOUND", dispatch_id, message_digest))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _validated_digest(value: str | None) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("message digest must be a SHA-256 hex value; raw message content is forbidden")
    return digest


def _task_dispatch_allowed(root: Path, task_id: str | None) -> tuple[bool, str]:
    if not task_id:
        return True, "TASK_NOT_BOUND"
    task = read_json(root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json", {}) or {}
    if not task:
        return True, "TASK_NOT_INITIALIZED"
    status = str(task.get("control_status") or "ACTIVE").upper()
    return status == "ACTIVE", status


def _archive_resolved(
    root: Path,
    state: dict[str, Any],
    turn: dict[str, Any],
    checkpoint_id: str | None = None,
    changed_surfaces: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any] | None:
    if turn.get("status") not in TURN_RESOLVED_STATES:
        return None
    summary = write_turn_summary(
        root, turn, checkpoint_id=checkpoint_id,
        changed_surfaces=changed_surfaces, evidence_refs=evidence_refs,
    )
    archive = state.setdefault("turn_archive", [])
    archive.append({
        "turn_attempt_id": turn.get("turn_attempt_id"),
        "task_id": turn.get("task_id"),
        "dispatch_id": turn.get("dispatch_id"),
        "operation_id": turn.get("operation_id"),
        "message_digest": turn.get("message_digest"),
        "status": turn.get("status"),
        "summary_ref": f"turn-summaries/{summary['turn_id']}.json",
        "summary_hash": summary["summary_hash"],
        "ended_at": summary["end"],
    })
    del archive[:-64]
    return summary


def _archive_and_remove(
    root: Path,
    state: dict[str, Any],
    key: str,
    turn: dict[str, Any],
    checkpoint_id: str | None = None,
    changed_surfaces: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any] | None:
    summary = _archive_resolved(root, state, turn, checkpoint_id, changed_surfaces, evidence_refs)
    state["turn_leases"].pop(key, None)
    return summary


@locked_state
def guard_turn_dispatch(
    root: Path,
    thread_id: str,
    host_status: str,
    turn_status: str,
    turn_id: str | None = None,
    operation_id: str | None = None,
    message_digest: str | None = None,
    reserve: bool = False,
    task_id: str | None = None,
    dispatch_id: str | None = None,
    host_pid: int | None = None,
    lease_seconds: int = 180,
) -> dict[str, Any]:
    """Fail closed before sending; persist only lifecycle changes, not ordinary observations."""
    state = load_dispatch(root)
    turns = state["turn_leases"]
    key = _thread_key(thread_id)
    turn = dict(turns.get(key) or {})
    previous = dict(turn)
    pair = turn_pair(host_status, turn_status)
    current_turn = str(turn_id or "").strip() or None
    lifecycle_changed = False

    if turn.get("status") in {"RESERVED", "STARTED"} and current_turn and status_token(turn_status) in TURN_ACTIVE_STATES:
        turn.update({"status": "ACTIVE", "started_turn_id": current_turn, "active_at": now()})
        turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
        lifecycle_changed = True
    if turn.get("status") in {"STARTED", "ACTIVE"} and current_turn == turn.get("started_turn_id") and status_token(turn_status) in TURN_TERMINAL_STATES:
        turn.update({"status": "COMPLETING", "host_terminal_at": now(), "host_outcome": status_token(turn_status)})
        turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
        lifecycle_changed = True
        if not turn.get("task_id"):
            turn.update({"status": "CONFIRMED", "confirmed_at": now(), "confirmation": "LEGACY_HOST_TERMINAL"})
            close_turn_lease(root, key, "CONFIRMED")

    requested_dispatch = str(dispatch_id or operation_id or "").strip() or None
    normalized_task = safe_id(task_id).upper() if task_id else None
    duplicate = None
    if requested_dispatch:
        candidates = [
            item for other_key, item in turns.items()
            if other_key != key and isinstance(item, dict)
        ] + [item for item in state.get("turn_archive", []) if isinstance(item, dict)]
        duplicate = next((
            item for item in candidates
            if item.get("dispatch_id") == requested_dispatch
            and item.get("task_id") == normalized_task
            and item.get("message_digest") == message_digest
            and item.get("status") in OUTSTANDING_TURN_LEASES | TURN_RESOLVED_STATES
        ), None)

    outstanding = turn.get("status") in OUTSTANDING_TURN_LEASES
    pressure = current_pressure(state)
    active_turns = active_lease_count(state)
    max_active_turns = min(
        max(1, project_policy(root)["max_active_turns"]),
        max(0, int(pressure.get("max_active_turns", 2))),
    )
    task_allowed, task_control_status = _task_dispatch_allowed(root, task_id)
    if turn.get("status") in {"INTERRUPTED_UNKNOWN", "RECOVERY_PROBE", "REVIEW_REQUIRED"}:
        action, reason, send_allowed = "RECOVERY_PROBE_REQUIRED", "旧Turn结果未确定；禁止自动重发或创建替代Turn", False
    elif duplicate:
        action, reason, send_allowed = "BLOCK_DUPLICATE_DISPATCH", "同一Task、Turn意图和dispatch identity已有记录", False
    elif outstanding:
        same = requested_dispatch and requested_dispatch == turn.get("dispatch_id") and message_digest == turn.get("message_digest")
        action = "ALREADY_RESERVED" if same and turn.get("status") == "RESERVED" else "WAIT_ACTIVE"
        reason, send_allowed = "目标任务已有未终态Turn，禁止发送第二次", False
    elif pair == "ACTIVE":
        action, reason, send_allowed = "WAIT_ACTIVE", "宿主仍报告活动Turn，禁止发送或重发", False
    elif not task_allowed:
        action, reason, send_allowed = "BLOCK_TASK_CONTROL", f"Task control_status={task_control_status}，禁止继续派发", False
    elif pressure.get("blocks_new_dispatch"):
        action, reason, send_allowed = "DRAIN_DESKTOP_PRESSURE", "桌面压力熔断中，只允许收敛和恢复", False
    elif active_turns >= max_active_turns:
        action, reason, send_allowed = "QUEUE_ACTIVE_TURN_BUDGET", "活动Turn达到安全预算", False
    elif pair == "UNKNOWN":
        action, reason, send_allowed = "CHECKPOINT_AND_PAUSE", "宿主状态不可确认，禁止轮询恢复风暴", False
    elif pair == "INCONSISTENT":
        fingerprint = hashlib.sha256(f"{status_token(host_status)}|{status_token(turn_status)}|{current_turn or ''}".encode()).hexdigest()[:20]
        attempts = int(turn.get("mismatch_attempts") or 0) + 1 if turn.get("mismatch_fingerprint") == fingerprint else 1
        turn.update({"mismatch_fingerprint": fingerprint, "mismatch_attempts": attempts, "mismatch_at": now()})
        lifecycle_changed = True
        action = "WAIT_ONCE" if attempts == 1 else "CHECKPOINT_AND_PAUSE"
        reason, send_allowed = "宿主与Turn状态不一致，只允许一次有界复查", False
    else:
        action, reason, send_allowed = "SEND_ALLOWED", "宿主可复用且没有未终态Turn", True

    runtime_lease = None
    if reserve and send_allowed:
        if not operation_id or not requested_dispatch or not message_digest:
            raise ValueError("operation id, dispatch id and message digest are required to reserve a dispatch")
        message_digest = _validated_digest(message_digest)
        attempt_id = _turn_attempt_id(normalized_task, requested_dispatch, message_digest)
        _archive_resolved(root, state, turn)
        turn = {
            "thread_key": key,
            "turn_attempt_id": attempt_id,
            "task_id": normalized_task,
            "dispatch_id": requested_dispatch,
            "operation_id": operation_id,
            "message_digest": message_digest,
            "status": "RESERVED",
            "observed_turn_id": current_turn,
            "reserved_at": now(),
            "lifecycle_event_count": 1,
            "automatic_resend": False,
        }
        turns[key] = turn
        state["updated_at"] = now()
        atomic_json(dispatch_file(root), state)
        runtime_lease = open_turn_lease(root, key, attempt_id, normalized_task, requested_dispatch, operation_id, host_pid, lease_seconds)
        action, reason, lifecycle_changed = "DISPATCH_RESERVED", "唯一Turn已预留，宿主发送后必须ACK", False
    elif lifecycle_changed or turn != previous:
        turn["thread_key"] = key
        turns[key] = turn
        state["updated_at"] = now()
        atomic_json(dispatch_file(root), state)

    return {
        "thread_key": key,
        "turn_attempt_id": turn.get("turn_attempt_id"),
        "pair": pair,
        "action": action,
        "reason": reason,
        "send_allowed": send_allowed,
        "turn_state": turn.get("status"),
        "lease_status": turn.get("status"),
        "mismatch_attempts": int(turn.get("mismatch_attempts") or 0),
        "active_turns": active_turns,
        "active_leases": active_runtime_lease_count(root),
        "max_active_turns": max_active_turns,
        "lifecycle_write": bool(reserve or lifecycle_changed),
        "lease_write": bool(runtime_lease and runtime_lease.get("write_performed")),
    }


@locked_state
def acknowledge_turn_dispatch(root: Path, thread_id: str, operation_id: str, accepted: bool) -> dict[str, Any]:
    state = load_dispatch(root)
    key = _thread_key(thread_id)
    turn = state["turn_leases"].get(key)
    if not isinstance(turn, dict) or turn.get("status") != "RESERVED":
        raise RuntimeError("no reserved Turn exists for this desktop task")
    if operation_id != turn.get("operation_id"):
        raise RuntimeError("operation id does not match the Turn reservation")
    turn["status"] = "STARTED" if accepted else "RETRYABLE"
    turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
    turn["acknowledged_at"] = now()
    turn["automatic_resend"] = False
    if not accepted:
        _archive_and_remove(root, state, key, turn)
    state["updated_at"] = now()
    atomic_json(dispatch_file(root), state)
    if accepted:
        refresh_turn_lease(root, key, force=True)
    else:
        close_turn_lease(root, key, "RETRYABLE")
    return {"thread_key": key, "turn_state": turn["status"], "status": turn["status"], "send_allowed": False}


def _interrupt_locked(root: Path, key: str, reason: str) -> dict[str, Any]:
    state = load_dispatch(root)
    turn = state["turn_leases"].get(key)
    if not isinstance(turn, dict):
        raise RuntimeError("Turn not found")
    if turn.get("status") in TURN_IN_FLIGHT_STATES:
        turn.update({"status": "INTERRUPTED_UNKNOWN", "interrupted_at": now(), "interruption_reason": reason, "automatic_resend": False})
        turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
        state["updated_at"] = now()
        atomic_json(dispatch_file(root), state)
    close_turn_lease(root, key, "INTERRUPTED_UNKNOWN")
    return {"thread_key": key, "turn_state": turn.get("status"), "automatic_resend": False, "reason": reason}


def heartbeat_turn(root: Path, thread_id: str, host_pid: int | None = None, force: bool = False) -> dict[str, Any]:
    key = _thread_key(thread_id)
    refreshed = refresh_turn_lease(root, key, host_pid, force)
    if refreshed.get("owner_status") in {"DEAD", "IDENTITY_CHANGED"}:
        return _interrupt_turn(root, key, f"owner:{str(refreshed['owner_status']).lower()}")
    return {
        "thread_key": key,
        "turn_state": (load_dispatch(root).get("turn_leases", {}).get(key) or {}).get("status"),
        "owner_status": refreshed.get("owner_status"),
        "expired_hint": refreshed.get("expired_hint"),
        "write_performed": refreshed.get("write_performed", False),
        "refresh_allowed": refreshed.get("refresh_allowed", True),
    }


@locked_state
def _interrupt_turn(root: Path, key: str, reason: str) -> dict[str, Any]:
    return _interrupt_locked(root, key, reason)


@locked_state
def probe_turn_host(root: Path, thread_id: str) -> dict[str, Any]:
    key = _thread_key(thread_id)
    lease = inspect_turn_lease(root, key)
    if lease.get("owner_status") in {"DEAD", "IDENTITY_CHANGED"}:
        return {**_interrupt_locked(root, key, f"owner:{str(lease['owner_status']).lower()}"), "lease": lease}
    turn = (load_dispatch(root).get("turn_leases", {}).get(key) or {})
    return {
        "thread_key": key,
        "turn_state": turn.get("status"),
        "owner_status": lease.get("owner_status"),
        "expired_hint": lease.get("expired_hint"),
        "automatic_resend": False,
    }


@locked_state
def observe_desktop_pressure(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    state = load_dispatch(root)
    report = evaluate_local_pressure(
        root, state, task_id=getattr(args, "task_id", None),
        backend_status=args.backend_status, observation_id=args.observation_id,
    )
    report = apply_pressure(state, report)
    state["updated_at"] = now()
    atomic_json(dispatch_file(root), state)
    for key in report["interrupted_dispatches"]:
        close_turn_lease(root, key, "INTERRUPTED_UNKNOWN")
    legacy_fields = (
        "active_tasks", "streaming_tasks", "active_turns", "loaded_projects",
        "incremental_events", "largest_task_bytes",
    )
    return {
        **report,
        "new_threads_allowed": not report["blocks_new_dispatch"],
        "automatic_resend_allowed": False,
        "legacy_host_counters_ignored": any(getattr(args, field, None) is not None for field in legacy_fields),
    }


@locked_state
def probe_interrupted_dispatch(
    root: Path,
    thread_id: str,
    operation_id: str,
    current_domain_fingerprint: str | None = None,
    checkpoint_path: str | None = None,
) -> dict[str, Any]:
    state = load_dispatch(root)
    key = _thread_key(thread_id)
    turn = state["turn_leases"].get(key)
    if not isinstance(turn, dict) or turn.get("status") not in {"INTERRUPTED_UNKNOWN", "RECOVERY_PROBE", "REVIEW_REQUIRED"}:
        raise RuntimeError("desktop task has no interrupted unknown Turn")
    if operation_id != turn.get("operation_id"):
        raise RuntimeError("operation id does not match interrupted Turn")
    turn["status"] = "RECOVERY_PROBE"
    turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
    turn["recovery_started_at"] = now()
    state["updated_at"] = now()
    atomic_json(dispatch_file(root), state)
    result = probe_turn_recovery(root, turn, current_domain_fingerprint, checkpoint_path)
    turn.update({
        "status": result["result"],
        "recovery_completed_at": now(),
        "recovery_reason": result["reason"],
        "automatic_resend": False,
        "new_turn_allowed": result["new_turn_allowed"],
    })
    turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
    if result["result"] in TURN_RESOLVED_STATES:
        _archive_and_remove(
            root, state, key, turn,
            Path(checkpoint_path).name if checkpoint_path else None,
        )
    state["updated_at"] = now()
    atomic_json(dispatch_file(root), state)
    close_turn_lease(root, key, result["result"])
    return {**result, "thread_key": key, "turn_state": result["result"]}


@locked_state
def confirm_turn(
    root: Path,
    thread_id: str,
    operation_id: str,
    checkpoint_id: str,
    checkpoint_path: str | None = None,
    changed_surfaces: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if not str(checkpoint_id or "").strip():
        raise ValueError("Turn confirmation requires a checkpoint id")
    state = load_dispatch(root)
    key = _thread_key(thread_id)
    turn = state["turn_leases"].get(key)
    if not isinstance(turn, dict) or turn.get("status") != "COMPLETING":
        raise RuntimeError("Turn is not ready for confirmation")
    if operation_id != turn.get("operation_id"):
        raise RuntimeError("operation id does not match completing Turn")
    proof = probe_turn_recovery(root, turn, checkpoint_path=checkpoint_path)
    if turn.get("task_id") and proof["result"] != "RECOVERED":
        raise RuntimeError("Domain commit is not proven; Turn cannot be confirmed")
    turn.update({"status": "CONFIRMED", "confirmed_at": now(), "checkpoint_id": safe_id(checkpoint_id), "automatic_resend": False})
    turn["lifecycle_event_count"] = int(turn.get("lifecycle_event_count") or 0) + 1
    summary = _archive_and_remove(root, state, key, turn, checkpoint_id, changed_surfaces, evidence_refs)
    state["updated_at"] = now()
    atomic_json(dispatch_file(root), state)
    close_turn_lease(root, key, "CONFIRMED")
    return {
        "thread_key": key, "turn_state": "CONFIRMED", "operation": proof["operation"],
        "active_leases": active_runtime_lease_count(root),
        "summary_ref": f"turn-summaries/{summary['turn_id']}.json" if summary else None,
        "summary_hash": summary.get("summary_hash") if summary else None,
    }


def reconcile_interrupted_dispatch(
    root: Path,
    thread_id: str,
    operation_id: str,
    outcome: str | None,
    checkpoint_id: str,
) -> dict[str, Any]:
    """Deprecated compatibility entry; caller-supplied outcome is never recovery authority."""
    if not str(checkpoint_id or "").strip():
        raise ValueError("interrupted Turn recovery requires a checkpoint id")
    checkpoint_path = checkpoint_id if (root / checkpoint_id).is_file() else None
    result = probe_interrupted_dispatch(root, thread_id, operation_id, checkpoint_path=checkpoint_path)
    return {**result, "caller_outcome_ignored": status_token(outcome) if outcome else None, "automatic_resend": False}
