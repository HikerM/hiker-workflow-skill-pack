from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from goal_change_model import (
    project_task,
    stable_hash,
    task_fingerprint,
    validate_plan,
)
from goal_contract import activate_staged_contract, contract_file, ensure_contract
from workspacelib import atomic_json, read_json, safe_id, state_lock


SCHEMA_VERSION = "1.0.0"
OPEN_STATUSES = {"PREPARED", "APPLYING", "PROJECTED"}
PROGRESS_BATCH_SIZE = 8
FaultInjector = Callable[[str], None]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def active_file(root: Path) -> Path:
    return root / ".ai" / "governance" / "goal-change-active.json"


def transaction_file(root: Path, operation_id: str) -> Path:
    return root / ".ai" / "runtime" / "goal-changes" / f"{safe_id(operation_id)}.json"


def archive_file(root: Path, operation_id: str) -> Path:
    return root / ".ai" / "archive" / "goal-changes" / f"{safe_id(operation_id)}.json"


def load_plan(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read structured goal change plan: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("goal change plan must be a JSON object")
    return data


def _load_transaction(root: Path, operation_id: str) -> tuple[Path, dict[str, Any]]:
    hot = transaction_file(root, operation_id)
    archived = archive_file(root, operation_id)
    for path in (hot, archived):
        data = read_json(path, {}) or {}
        if data:
            return path, data
    return hot, {}


def _write_marker(root: Path, transaction: dict[str, Any], status: str) -> None:
    entries = transaction.get("task_progress") or []
    applied = sum(1 for item in entries if item.get("status") == "APPLIED")
    marker = {
        "schema_version": SCHEMA_VERSION,
        "operation_id": transaction["operation_id"],
        "status": status,
        "base_goal_revision": transaction["plan"]["base_goal"]["revision"],
        "new_goal_revision": transaction["plan"]["new_goal"]["revision"],
        "new_goal_fingerprint": transaction["plan"]["new_goal"]["fingerprint"],
        "task_count": len(entries),
        "applied_task_count": applied,
        "pending_task_count": len(entries) - applied,
        "transaction_path": str(
            archive_file(root, transaction["operation_id"])
            if status == "COMPLETE"
            else transaction_file(root, transaction["operation_id"])
        ),
        "updated_at": utc_now(),
    }
    atomic_json(active_file(root), marker)


def _task_path(root: Path, task_id: str) -> Path:
    return root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json"


def _update_task_index(root: Path, tasks: dict[str, dict[str, Any]]) -> None:
    path = root / ".ai" / "governance" / "task-index.json"
    index = read_json(path, {}) or {}
    summaries = []
    for item in index.get("tasks", []):
        if not isinstance(item, dict):
            continue
        task_id = safe_id(str(item.get("task_id") or "")).upper()
        task = tasks.get(task_id)
        if not task:
            summaries.append(item)
            continue
        summaries.append({
            "task_id": task.get("task_id"),
            "goal": str(task.get("goal") or "")[:240],
            "state": task.get("state"),
            "control_status": task.get("control_status"),
            "owner_agent": task.get("owner_agent"),
            "branch": task.get("branch"),
            "ownership_lane": task.get("ownership_lane", "default"),
            "goal_revision": (task.get("goal_binding") or {}).get("revision"),
            "updated_at": task.get("updated_at"),
        })
    summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    active = [item for item in summaries if item.get("state") not in {"Merged", "Released"}]
    closed = [item for item in summaries if item.get("state") in {"Merged", "Released"}]
    updated = {
        **index,
        "schema_version": index.get("schema_version") or "2.0.0",
        "tasks": active + closed,
        "active_count": len(active),
        "retained_closed_count": len(closed),
        "facts_source": ".ai/tasks/*.json",
        "updated_at": utc_now(),
    }
    atomic_json(path, updated)


def _prepare_transaction(
    root: Path,
    raw_plan: dict[str, Any],
    operation_id: str,
) -> dict[str, Any]:
    operation = safe_id(operation_id)
    _, existing = _load_transaction(root, operation)
    if existing:
        source_matches = existing.get("source_plan_hash") == stable_hash(raw_plan)
        normalized_matches = raw_plan.get("plan_fingerprint") == existing.get("plan_fingerprint")
        if not (source_matches or normalized_matches):
            raise RuntimeError("operation id was already used with a different goal change plan")
        return existing
    current_goal = ensure_contract(root)
    normalized, tasks = validate_plan(root, raw_plan, current_goal)
    existing_marker = read_json(active_file(root), {}) or {}
    if (
        existing_marker.get("status") in OPEN_STATUSES
        and existing_marker.get("operation_id") != operation
    ):
        raise RuntimeError("another goal revision transaction is incomplete")
    timestamp = utc_now()
    progress = []
    entries = {item["task_id"]: item for item in normalized["tasks"]}
    for task_id in sorted(tasks):
        before = tasks[task_id]
        projected = project_task(
            before, entries[task_id], normalized["new_goal"], operation, timestamp
        )
        progress.append({
            "task_id": task_id,
            "classification": entries[task_id]["classification"],
            "status": "PENDING",
            "before_fingerprint": task_fingerprint(before),
            "intended_after_fingerprint": task_fingerprint(projected),
            "committed_after_fingerprint": None,
        })
    transaction = {
        "schema_version": SCHEMA_VERSION,
        "operation_id": operation,
        "status": "PREPARED",
        "source_plan_hash": stable_hash(raw_plan),
        "plan_fingerprint": normalized["plan_fingerprint"],
        "plan": normalized,
        "projection_timestamp": timestamp,
        "task_progress": progress,
        "prepared_at": timestamp,
        "domain_commit_timestamp": None,
    }
    atomic_json(transaction_file(root, operation), transaction)
    _write_marker(root, transaction, "PREPARED")
    return transaction


def prepare_goal_change(
    root: Path,
    raw_plan: dict[str, Any],
    operation_id: str,
) -> dict[str, Any]:
    with state_lock(root):
        transaction = _prepare_transaction(root.resolve(), raw_plan, operation_id)
        return {
            "operation_id": transaction["operation_id"],
            "plan_fingerprint": transaction["plan_fingerprint"],
            "status": transaction["status"],
            "task_count": len(transaction["task_progress"]),
            "base_goal": transaction["plan"]["base_goal"],
            "new_goal": transaction["plan"]["new_goal"],
        }


def inspect_goal_change(
    root: Path,
    raw_plan: dict[str, Any],
    operation_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    operation = safe_id(operation_id)
    _, transaction = _load_transaction(root, operation)
    if transaction:
        source_matches = transaction.get("source_plan_hash") == stable_hash(raw_plan)
        normalized_matches = raw_plan.get("plan_fingerprint") == transaction.get("plan_fingerprint")
        if not (source_matches or normalized_matches):
            raise RuntimeError("operation id was already used with a different goal change plan")
        return transaction["plan"]
    normalized, _ = validate_plan(root, raw_plan, ensure_contract(root))
    return normalized


def goal_change_status(root: Path, operation_id: str) -> dict[str, Any]:
    root = root.resolve()
    operation = safe_id(operation_id)
    _, transaction = _load_transaction(root, operation)
    if not transaction:
        return {"operation_id": operation, "status": "NOT_FOUND", "projected": [], "pending": []}
    projected: list[str] = []
    pending: list[str] = []
    inconsistent: list[str] = []
    for progress in transaction.get("task_progress") or []:
        task_id = progress["task_id"]
        task = read_json(_task_path(root, task_id), {}) or {}
        marker = task.get("goal_adjustment") or {}
        if (
            marker.get("operation_id") == operation
            and task_fingerprint(task) == progress.get("intended_after_fingerprint")
        ):
            projected.append(task_id)
        elif task_fingerprint(task) == progress.get("before_fingerprint"):
            pending.append(task_id)
        else:
            inconsistent.append(task_id)
    return {
        "operation_id": operation,
        "status": transaction.get("status"),
        "base_goal_revision": transaction["plan"]["base_goal"]["revision"],
        "new_goal_revision": transaction["plan"]["new_goal"]["revision"],
        "projected": projected,
        "pending": pending,
        "inconsistent": inconsistent,
        "safe_to_resume": not inconsistent,
    }


def _transaction_result(root: Path, transaction: dict[str, Any], *, recovered: bool) -> dict[str, Any]:
    classifications = {
        name: sum(1 for item in transaction["task_progress"] if item["classification"] == name)
        for name in ("AFFECTED", "UNAFFECTED", "SUPERSEDED", "REQUIRES_REVIEW")
    }
    domain_fingerprint = stable_hash({
        "goal": ensure_contract(root).get("fingerprint"),
        "tasks": {
            item["task_id"]: item.get("committed_after_fingerprint")
            for item in transaction["task_progress"]
        },
        "operation_id": transaction["operation_id"],
    })
    return {
        "operation_id": transaction["operation_id"],
        "goal_id": transaction["plan"]["new_goal"]["goal_id"],
        "goal_revision": transaction["plan"]["new_goal"]["revision"],
        "goal_fingerprint": transaction["plan"]["new_goal"]["fingerprint"],
        "classifications": classifications,
        "task_count": len(transaction["task_progress"]),
        "transaction_status": transaction["status"],
        "recovered_after_interruption": recovered,
        "domain_fingerprint": domain_fingerprint,
    }


def _finish_transaction(root: Path, transaction: dict[str, Any]) -> dict[str, Any]:
    transaction["status"] = "COMPLETE"
    transaction["domain_commit_timestamp"] = transaction.get("domain_commit_timestamp") or utc_now()
    transaction["completed_at"] = utc_now()
    archived = archive_file(root, transaction["operation_id"])
    atomic_json(archived, transaction)
    _write_marker(root, transaction, "COMPLETE")
    hot = transaction_file(root, transaction["operation_id"])
    try:
        hot.unlink()
    except FileNotFoundError:
        pass
    return transaction


def apply_goal_change(
    root: Path,
    raw_plan: dict[str, Any],
    operation_id: str,
    *,
    fault_injector: FaultInjector | None = None,
    recovered: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    operation = safe_id(operation_id)
    with state_lock(root):
        transaction = _prepare_transaction(root, raw_plan, operation)
        if transaction.get("status") == "COMPLETE":
            return _transaction_result(root, transaction, recovered=True)
        if fault_injector:
            fault_injector("after_prepare")
        transaction["status"] = "APPLYING"
        transaction["applying_at"] = transaction.get("applying_at") or utc_now()
        atomic_json(transaction_file(root, operation), transaction)
        _write_marker(root, transaction, "APPLYING")
        entries = {item["task_id"]: item for item in transaction["plan"]["tasks"]}
        projected_tasks: dict[str, dict[str, Any]] = {}
        total_tasks = len(transaction["task_progress"])
        for position, progress in enumerate(transaction["task_progress"], start=1):
            task_id = progress["task_id"]
            current = read_json(_task_path(root, task_id), {}) or {}
            if not current:
                raise RuntimeError(f"goal change task disappeared: {task_id}")
            marker = current.get("goal_adjustment") or {}
            already_projected = (
                marker.get("operation_id") == operation
                and marker.get("classification") == progress["classification"]
                and (marker.get("target_binding") or {}).get("fingerprint")
                == transaction["plan"]["new_goal"]["fingerprint"]
            )
            current_fingerprint = task_fingerprint(current)
            if progress.get("status") == "APPLIED" or already_projected:
                if current_fingerprint != progress["intended_after_fingerprint"]:
                    raise RuntimeError(f"{task_id} changed after goal projection; recovery review is required")
                progress["status"] = "APPLIED"
                progress["committed_after_fingerprint"] = current_fingerprint
                projected_tasks[task_id] = current
                continue
            if current_fingerprint != progress["before_fingerprint"]:
                raise RuntimeError(f"{task_id} changed during goal revision; recovery review is required")
            projected = project_task(
                current,
                entries[task_id],
                transaction["plan"]["new_goal"],
                operation,
                transaction["projection_timestamp"],
            )
            atomic_json(_task_path(root, task_id), projected)
            if fault_injector:
                fault_injector(f"after_task:{task_id}")
            progress["status"] = "APPLIED"
            progress["committed_after_fingerprint"] = task_fingerprint(projected)
            progress["applied_at"] = utc_now()
            projected_tasks[task_id] = projected
            if position % PROGRESS_BATCH_SIZE == 0 or position == total_tasks:
                atomic_json(transaction_file(root, operation), transaction)
        _update_task_index(root, projected_tasks)
        transaction["status"] = "PROJECTED"
        transaction["projected_at"] = utc_now()
        atomic_json(transaction_file(root, operation), transaction)
        _write_marker(root, transaction, "PROJECTED")
        activate_staged_contract(
            root, transaction["plan"]["new_goal"], transaction["operation_id"]
        )
        if fault_injector:
            fault_injector("after_contract")
        transaction = _finish_transaction(root, transaction)
        return _transaction_result(root, transaction, recovered=recovered)


def recover_goal_change(
    root: Path,
    raw_plan: dict[str, Any],
    operation_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    operation = safe_id(operation_id)
    with state_lock(root):
        _, transaction = _load_transaction(root, operation)
        if not transaction:
            current = ensure_contract(root)
            normalized, _ = validate_plan(root, raw_plan, current)
            return {
                "status": "NOT_COMMITTED",
                "current_fingerprint": stable_hash({
                    "goal": current.get("fingerprint"),
                    "plan": normalized["plan_fingerprint"],
                }),
            }
        source_matches = transaction.get("source_plan_hash") == stable_hash(raw_plan)
        normalized_matches = raw_plan.get("plan_fingerprint") == transaction.get("plan_fingerprint")
        if not (source_matches or normalized_matches):
            return {"status": "UNKNOWN", "current_fingerprint": None}
        current_goal = ensure_contract(root)
        target = transaction["plan"]["new_goal"]
        if transaction.get("status") == "COMPLETE":
            if current_goal.get("fingerprint") != target.get("fingerprint"):
                return {"status": "UNKNOWN", "current_fingerprint": current_goal.get("fingerprint")}
            result = _transaction_result(root, transaction, recovered=True)
            return {
                "status": "COMMITTED",
                "domain_result": result,
                "committed_after_fingerprint": result["domain_fingerprint"],
            }
    result = apply_goal_change(root, transaction["plan"], operation, recovered=True)
    return {
        "status": "COMMITTED",
        "domain_result": result,
        "committed_after_fingerprint": result["domain_fingerprint"],
    }


def transaction_paths(root: Path, operation_id: str, task_ids: list[str]) -> list[Path]:
    paths = [
        active_file(root),
        contract_file(root),
        root / ".ai" / "governance" / "task-index.json",
        transaction_file(root, operation_id),
        archive_file(root, operation_id),
    ]
    paths.extend(_task_path(root, task_id) for task_id in task_ids)
    return paths
