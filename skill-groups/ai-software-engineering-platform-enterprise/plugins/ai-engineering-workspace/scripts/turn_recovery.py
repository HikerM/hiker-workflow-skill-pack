from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from turn_lease import inspect_turn_lease
from workspacelib import read_json, safe_id


CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))
from control_kernel import operation_file  # noqa: E402


COMMITTED_OPERATION_STATES = {"DOMAIN_COMMITTED", "TRACE_PENDING", "COMPLETE"}


def _operation_entry(root: Path, operation_id: str) -> dict[str, Any]:
    path = operation_file(root)
    if not path.is_file():
        return {}
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"operation journal cannot be used for turn recovery: {exc}")
    operations = journal.get("operations") if isinstance(journal, dict) else None
    if not isinstance(operations, dict):
        raise RuntimeError("operation journal cannot be used for turn recovery: invalid schema")
    entry = operations.get(operation_id)
    return entry if isinstance(entry, dict) else {}


def _checkpoint_fact(
    root: Path,
    checkpoint_path: str | None,
    task_id: str | None,
    operation_id: str,
) -> dict[str, Any]:
    if not checkpoint_path:
        return {"status": "NOT_PROVIDED", "path": None, "operation_recorded": False}
    candidate = Path(checkpoint_path)
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        if os.path.commonpath([os.path.normcase(str(root.resolve())), os.path.normcase(str(target))]) != os.path.normcase(str(root.resolve())):
            return {"status": "OUTSIDE_REPOSITORY", "path": None, "operation_recorded": False}
    except ValueError:
        return {"status": "OUTSIDE_REPOSITORY", "path": None, "operation_recorded": False}
    relative = Path(os.path.relpath(str(target), str(root.resolve()))).as_posix()
    value = read_json(target, {}) or {}
    if not isinstance(value, dict) or not value:
        return {"status": "MISSING_OR_DAMAGED", "path": relative, "operation_recorded": False}
    checkpoint_task = value.get("task") if isinstance(value.get("task"), dict) else {}
    checkpoint_task_id = str(checkpoint_task.get("task_id") or "").upper()
    expected_task_id = str(task_id or "").upper()
    operation_recorded = value.get("operation_id") == safe_id(operation_id)
    if expected_task_id and checkpoint_task_id and checkpoint_task_id != expected_task_id:
        status = "TASK_MISMATCH"
    else:
        status = "VALID"
    return {
        "status": status,
        "path": relative,
        "operation_recorded": operation_recorded,
        "task_id": checkpoint_task_id or None,
    }


def _task_fact(root: Path, task_id: str | None, operation_id: str) -> dict[str, Any]:
    if not task_id:
        return {"status": "NOT_BOUND", "operation_recorded": False}
    task = read_json(root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json", {}) or {}
    if not isinstance(task, dict) or not task:
        return {"status": "NOT_FOUND", "operation_recorded": False}
    operation_recorded = any(
        isinstance(item, dict) and item.get("operation_id") == operation_id
        for item in task.get("history", [])
    )
    return {
        "status": str(task.get("state") or "UNKNOWN"),
        "control_status": str(task.get("control_status") or "UNKNOWN"),
        "operation_recorded": operation_recorded,
    }


def probe_turn_recovery(
    root: Path,
    turn: dict[str, Any],
    current_domain_fingerprint: str | None = None,
    checkpoint_path: str | None = None,
) -> dict[str, Any]:
    operation_id = str(turn.get("operation_id") or "")
    task_id = str(turn.get("task_id") or "") or None
    if not operation_id:
        raise RuntimeError("interrupted turn has no operation id")
    operation = _operation_entry(root, operation_id)
    operation_status = str(operation.get("status") or "ABSENT")
    checkpoint = _checkpoint_fact(root, checkpoint_path, task_id, operation_id)
    task = _task_fact(root, task_id, operation_id)
    lease = inspect_turn_lease(root, str(turn.get("thread_key") or ""))

    reason = "operation outcome cannot be proven"
    operation_task_id = str(operation.get("task_id") or "").upper()
    if task_id and operation_task_id and operation_task_id != task_id.upper():
        result, reason = "REVIEW_REQUIRED", "operation journal task identity does not match the Turn"
    elif operation_status in COMMITTED_OPERATION_STATES or task.get("operation_recorded"):
        result, reason = "RECOVERED", "domain commit is proven by the operation journal or Task history"
    elif operation_status == "FAILED_BEFORE_COMMIT":
        result, reason = "RETRYABLE", "operation journal proves failure before domain commit"
    elif operation_status == "PREPARED":
        before = operation.get("before_fingerprint")
        if before and current_domain_fingerprint and before == current_domain_fingerprint:
            result, reason = "RETRYABLE", "current domain fingerprint still matches PREPARED before-state"
        else:
            result = "REVIEW_REQUIRED"
            reason = "PREPARED operation has no matching current domain fingerprint"
    else:
        result = "REVIEW_REQUIRED"
    if checkpoint.get("status") in {"OUTSIDE_REPOSITORY", "TASK_MISMATCH"}:
        result, reason = "REVIEW_REQUIRED", "checkpoint identity is invalid"
    return {
        "result": result,
        "reason": reason,
        "task_id": task_id,
        "turn_attempt_id": turn.get("turn_attempt_id"),
        "dispatch_id": turn.get("dispatch_id"),
        "operation_id": operation_id,
        "operation": {
            "status": operation_status,
            "before_fingerprint": operation.get("before_fingerprint"),
            "committed_after_fingerprint": operation.get("committed_after_fingerprint"),
        },
        "task": task,
        "checkpoint": checkpoint,
        "lease": {
            "lease_state": lease.get("lease_state"),
            "owner_status": lease.get("owner_status"),
            "expired_hint": lease.get("expired_hint"),
        },
        "automatic_resend": False,
        "new_turn_allowed": result == "RETRYABLE",
    }
