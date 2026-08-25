from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from goal_contract import build_contract
from workspacelib import read_json, safe_id


SCHEMA_VERSION = "1.0.0"
CLASSIFICATIONS = {"AFFECTED", "UNAFFECTED", "SUPERSEDED", "REQUIRES_REVIEW"}
CHANGE_KINDS = {"ADD", "REMOVE", "MODIFY", "ARCHITECTURE", "STACK_MIGRATION", "UNDO"}
INVALIDATION_FIELDS = {
    "implementation_route_ids",
    "review_record_ids",
    "test_record_ids",
    "checkpoint_ids",
    "acceptance_ids",
}
SURFACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def task_fingerprint(task: dict[str, Any]) -> str:
    return stable_hash(task)


def _unique_strings(values: Any, field: str, *, limit: int = 200) -> list[str]:
    if not isinstance(values, list):
        raise RuntimeError(f"{field} must be an array")
    result: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if not token:
            raise RuntimeError(f"{field} contains an empty value")
        if token not in result:
            result.append(token)
    if len(result) > limit:
        raise RuntimeError(f"{field} exceeds the bounded item limit")
    return result


def _surface_ids(values: Any, field: str) -> list[str]:
    result = _unique_strings(values, field)
    if any(not SURFACE_ID.fullmatch(value) for value in result):
        raise RuntimeError(f"{field} contains an invalid stable surface id")
    return result


def _record_ids(container: dict[str, Any], key: str) -> set[str]:
    records = (container.get(key) or {}).get("records") or []
    return {
        str(item.get("id"))
        for item in records
        if isinstance(item, dict) and item.get("id")
    }


def _route_ids(task: dict[str, Any]) -> set[str]:
    return {
        str(item.get("route_id"))
        for item in (task.get("convergence") or {}).get("implementation_routes") or []
        if isinstance(item, dict) and item.get("route_id")
    }


def _checkpoint_ids(task: dict[str, Any]) -> set[str]:
    return {
        str(item.get("checkpoint_id") or item.get("id"))
        for item in task.get("checkpoint_refs") or []
        if isinstance(item, dict) and (item.get("checkpoint_id") or item.get("id"))
    }


def _declared_surfaces(task: dict[str, Any], key: str) -> set[str]:
    contract = task.get("change_contract") or {}
    values = contract.get(key) or []
    return {str(value) for value in values if isinstance(value, str) and SURFACE_ID.fullmatch(value)}


def load_indexed_tasks(root: Path) -> dict[str, dict[str, Any]]:
    index = read_json(root / ".ai" / "governance" / "task-index.json", {}) or {}
    summaries = [item for item in index.get("tasks", []) if isinstance(item, dict)]
    tasks: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        task_id = safe_id(str(summary.get("task_id") or "")).upper()
        path = root / ".ai" / "tasks" / f"{task_id}.json"
        task = read_json(path, {}) or {}
        if not task:
            raise RuntimeError(f"task index references a missing task: {task_id}")
        if (task.get("goal_binding") or {}).get("scope") == "project":
            tasks[task_id] = task
    return tasks


def _validate_references(task: dict[str, Any], entry: dict[str, Any]) -> None:
    invalidations = entry["invalidations"]
    available = {
        "implementation_route_ids": _route_ids(task),
        "review_record_ids": _record_ids(task, "review"),
        "test_record_ids": _record_ids(task, "tests"),
        "checkpoint_ids": _checkpoint_ids(task),
        "acceptance_ids": {
            str(item.get("id"))
            for item in (task.get("convergence") or {}).get("criteria") or []
            if isinstance(item, dict) and item.get("id")
        },
    }
    for field, requested in invalidations.items():
        missing = sorted(set(requested) - available[field])
        if missing:
            raise RuntimeError(
                f"{entry['task_id']} {field} references unknown ids: {', '.join(missing)}"
            )


def _surface_bound_ids(items: list[dict[str, Any]], id_field: str, surfaces: set[str]) -> set[str]:
    result: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not item.get(id_field):
            continue
        item_surfaces = {str(value) for value in item.get("surface_ids") or []}
        if item_surfaces & surfaces:
            result.add(str(item[id_field]))
    return result


def _validate_surface_evidence(task: dict[str, Any], entry: dict[str, Any]) -> None:
    surfaces = set(entry["affected_surface_ids"])
    if not surfaces:
        return
    convergence = task.get("convergence") or {}
    expected = {
        "implementation_route_ids": _surface_bound_ids(
            convergence.get("implementation_routes") or [], "route_id", surfaces
        ),
        "review_record_ids": _surface_bound_ids(
            (task.get("review") or {}).get("records") or [], "id", surfaces
        ),
        "test_record_ids": _surface_bound_ids(
            (task.get("tests") or {}).get("records") or [], "id", surfaces
        ),
        "checkpoint_ids": _surface_bound_ids(
            task.get("checkpoint_refs") or [], "checkpoint_id", surfaces
        ),
    }
    for field, required in expected.items():
        omitted = sorted(required - set(entry["invalidations"][field]))
        if omitted:
            raise RuntimeError(
                f"{entry['task_id']} omits surface-bound {field}: {', '.join(omitted)}"
            )


def validate_plan(
    root: Path,
    raw_plan: dict[str, Any],
    current_goal: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not isinstance(raw_plan, dict) or raw_plan.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("goal change plan schema_version must be 1.0.0")
    allowed_plan = {
        "schema_version", "change_kind", "undo_of_revision", "base_goal",
        "new_goal", "changed_surface_ids", "tasks",
    }
    if set(raw_plan) - allowed_plan:
        raise RuntimeError("goal change plan contains unsupported top-level fields")
    base = raw_plan.get("base_goal") or {}
    if set(base) - {"goal_id", "revision", "fingerprint"}:
        raise RuntimeError("base_goal contains unsupported fields")
    for field in ("goal_id", "revision", "fingerprint"):
        if base.get(field) != current_goal.get(field):
            raise RuntimeError(f"goal change base {field} does not match the active goal")
    new_goal_input = raw_plan.get("new_goal") or {}
    allowed_goal = {
        "goal_id", "outcome", "non_goals", "acceptance_ids",
        "behavior_invariants", "constraints", "priority_order",
    }
    if set(new_goal_input) - allowed_goal:
        raise RuntimeError("new_goal contains unsupported fields")
    new_goal = build_contract(
        current_goal,
        str(new_goal_input.get("goal_id") or ""),
        str(new_goal_input.get("outcome") or ""),
        _unique_strings(new_goal_input.get("non_goals") or [], "new_goal.non_goals"),
        _unique_strings(new_goal_input.get("acceptance_ids") or [], "new_goal.acceptance_ids"),
        _unique_strings(new_goal_input.get("behavior_invariants") or [], "new_goal.behavior_invariants"),
        _unique_strings(new_goal_input.get("constraints") or [], "new_goal.constraints"),
        _unique_strings(new_goal_input.get("priority_order") or [], "new_goal.priority_order"),
    )
    if new_goal["goal_id"] != current_goal.get("goal_id"):
        raise RuntimeError("goal_id is immutable across revisions")
    changed_surfaces = _surface_ids(raw_plan.get("changed_surface_ids") or [], "changed_surface_ids")
    if not changed_surfaces:
        raise RuntimeError("goal change requires at least one changed_surface_id")
    tasks = load_indexed_tasks(root)
    entries = raw_plan.get("tasks")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("goal change requires structured task classifications")
    normalized_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise RuntimeError("each task classification must be an object")
        allowed_entry = {
            "task_id", "classification", "impact_summary", "affected_surface_ids",
            "retained_surface_ids", "invalidations", "invalidate_candidate",
            "change_contract_required",
        }
        if set(raw) - allowed_entry:
            raise RuntimeError("task classification contains unsupported fields")
        task_id = safe_id(str(raw.get("task_id") or "")).upper()
        if task_id in seen:
            raise RuntimeError(f"duplicate goal classification for {task_id}")
        seen.add(task_id)
        classification = str(raw.get("classification") or "").upper()
        if classification not in CLASSIFICATIONS:
            raise RuntimeError(f"unsupported goal impact classification for {task_id}")
        summary = str(raw.get("impact_summary") or "").strip()
        if not summary or len(summary) > 500:
            raise RuntimeError(f"{task_id} requires a bounded impact_summary")
        affected = _surface_ids(raw.get("affected_surface_ids") or [], f"{task_id}.affected_surface_ids")
        retained = _surface_ids(raw.get("retained_surface_ids") or [], f"{task_id}.retained_surface_ids")
        if set(affected) - set(changed_surfaces):
            raise RuntimeError(f"{task_id} affected surfaces are not declared by the goal revision")
        invalidations_raw = raw.get("invalidations") or {}
        if set(invalidations_raw) - INVALIDATION_FIELDS:
            raise RuntimeError(f"{task_id} contains unsupported invalidation fields")
        invalidations = {
            field: _unique_strings(invalidations_raw.get(field) or [], f"{task_id}.{field}")
            for field in sorted(INVALIDATION_FIELDS)
        }
        invalidate_candidate = bool(raw.get("invalidate_candidate", False))
        change_contract_required = bool(raw.get("change_contract_required", False))
        has_invalidation = any(invalidations.values()) or invalidate_candidate
        if classification == "AFFECTED" and (not affected or not (has_invalidation or change_contract_required)):
            raise RuntimeError(f"{task_id} AFFECTED requires surfaces and a deterministic rework action")
        if classification == "UNAFFECTED" and (affected or has_invalidation or change_contract_required or not retained):
            raise RuntimeError(f"{task_id} UNAFFECTED may only carry forward positively identified retained surfaces")
        if classification in {"SUPERSEDED", "REQUIRES_REVIEW"} and has_invalidation:
            raise RuntimeError(f"{task_id} {classification} cannot invalidate evidence automatically")
        entry = {
            "task_id": task_id,
            "classification": classification,
            "impact_summary": summary,
            "affected_surface_ids": affected,
            "retained_surface_ids": retained,
            "invalidations": invalidations,
            "invalidate_candidate": invalidate_candidate,
            "change_contract_required": change_contract_required,
        }
        normalized_entries.append(entry)
    if seen != set(tasks):
        missing = sorted(set(tasks) - seen)
        extra = sorted(seen - set(tasks))
        raise RuntimeError(f"goal classification must cover the bounded task index; missing={missing}, extra={extra}")
    changed_set = set(changed_surfaces)
    for entry in normalized_entries:
        task = tasks[entry["task_id"]]
        if task.get("state") in {"Merged", "Released"} and entry["classification"] == "AFFECTED":
            raise RuntimeError(
                f"{entry['task_id']} is closed; use REQUIRES_REVIEW or SUPERSEDED and create bounded follow-up work"
            )
        declared_impact = _declared_surfaces(task, "owned_surface_ids") | _declared_surfaces(
            task, "consumed_surface_ids"
        )
        if declared_impact & changed_set and entry["classification"] == "UNAFFECTED":
            raise RuntimeError(
                f"{entry['task_id']} consumes or owns a changed surface and cannot be UNAFFECTED"
            )
        _validate_references(task, entry)
        if entry["classification"] == "AFFECTED":
            _validate_surface_evidence(task, entry)
    change_kind = str(raw_plan.get("change_kind") or "MODIFY").upper()
    if change_kind not in CHANGE_KINDS:
        raise RuntimeError("unsupported goal change_kind")
    undo_of_revision = raw_plan.get("undo_of_revision")
    if change_kind == "UNDO":
        if not isinstance(undo_of_revision, int) or not 0 < undo_of_revision < int(current_goal["revision"]):
            raise RuntimeError("UNDO requires an earlier undo_of_revision")
        archive = (
            root / ".ai" / "archive" / "goal-contracts"
            / f"{safe_id(str(current_goal['goal_id']))}-r{undo_of_revision}.json"
        )
        target = read_json(archive, {}) or {}
        semantic_fields = (
            "goal_id", "outcome", "non_goals", "acceptance_ids",
            "behavior_invariants", "constraints", "priority_order",
        )
        if not target or any(new_goal.get(field) != target.get(field) for field in semantic_fields):
            raise RuntimeError("UNDO new_goal must reproduce the archived target revision")
    elif undo_of_revision is not None:
        raise RuntimeError("undo_of_revision is only valid for UNDO")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "change_kind": change_kind,
        "base_goal": {
            "goal_id": current_goal.get("goal_id"),
            "revision": current_goal.get("revision"),
            "fingerprint": current_goal.get("fingerprint"),
        },
        "new_goal": new_goal,
        "changed_surface_ids": changed_surfaces,
        "tasks": sorted(normalized_entries, key=lambda item: item["task_id"]),
    }
    if change_kind == "UNDO":
        normalized["undo_of_revision"] = undo_of_revision
    normalized["plan_fingerprint"] = stable_hash(normalized)
    return normalized, tasks


def _rebind_evidence(evidence: dict[str, Any], binding: dict[str, Any]) -> None:
    lineage = evidence.get("binding")
    if isinstance(lineage, dict):
        lineage["goal_revision"] = binding.get("revision")
        lineage["goal_fingerprint"] = binding.get("fingerprint")


def _mark_records(records: list[Any], selected: set[str]) -> list[dict[str, Any]]:
    invalidated: list[dict[str, Any]] = []
    for item in records:
        if isinstance(item, dict) and str(item.get("id")) in selected:
            invalidated.append(copy.deepcopy(item))
            item["status"] = "INVALID"
            item["invalidated_reason"] = "GOAL_REVISION_SCOPE"
    return invalidated


def project_task(
    task: dict[str, Any],
    entry: dict[str, Any],
    new_goal: dict[str, Any],
    operation_id: str,
    timestamp: str,
) -> dict[str, Any]:
    projected = copy.deepcopy(task)
    previous_binding = copy.deepcopy(projected.get("goal_binding") or {})
    new_binding = {
        "scope": "project",
        "goal_id": new_goal.get("goal_id"),
        "revision": new_goal.get("revision"),
        "fingerprint": new_goal.get("fingerprint"),
    }
    classification = entry["classification"]
    adjustment = {
        "status": "CURRENT",
        "classification": classification,
        "previous_binding": previous_binding,
        "target_binding": new_binding,
        "impact_summary": entry["impact_summary"],
        "affected_surface_ids": entry["affected_surface_ids"],
        "retained_surface_ids": entry["retained_surface_ids"],
        "operation_id": safe_id(operation_id),
        "recorded_at": timestamp,
    }
    if classification == "UNAFFECTED":
        projected["goal_binding"] = new_binding
        _rebind_evidence(projected.get("review") or {}, new_binding)
        _rebind_evidence(projected.get("tests") or {}, new_binding)
        projected.setdefault("carried_goal_evidence", []).append({
            "at": timestamp,
            "operation_id": safe_id(operation_id),
            "previous_binding": previous_binding,
            "current_binding": new_binding,
            "retained_surface_ids": entry["retained_surface_ids"],
        })
        projected["carried_goal_evidence"] = projected["carried_goal_evidence"][-10:]
    elif classification == "SUPERSEDED":
        adjustment["status"] = "SUPERSEDED"
        projected["control_status"] = "SUPERSEDED"
    elif classification == "REQUIRES_REVIEW":
        adjustment["status"] = "REQUIRES_REVIEW"
        projected["control_status"] = "REVIEW_REQUIRED"
    else:
        projected["goal_binding"] = new_binding
        adjustment["status"] = "REPLAN_REQUIRED"
        adjustment["change_contract_required"] = entry["change_contract_required"]
        projected["control_status"] = "ADJUSTING"
        invalidations = entry["invalidations"]
        invalidated: dict[str, Any] = {
            "at": timestamp,
            "operation_id": safe_id(operation_id),
            "goal_binding": previous_binding,
            "surface_ids": entry["affected_surface_ids"],
        }
        if entry["invalidate_candidate"] and projected.get("review_candidate"):
            invalidated["review_candidate"] = projected.pop("review_candidate")
        for key, field in (("review", "review_record_ids"), ("tests", "test_record_ids")):
            evidence = projected.get(key) or {"status": "PENDING", "records": []}
            selected = set(invalidations[field])
            invalidated[field] = _mark_records(evidence.get("records") or [], selected)
            if selected:
                valid = [item for item in evidence.get("records") or [] if item.get("status") != "INVALID"]
                evidence["status"] = "PARTIAL" if valid else "PENDING"
            _rebind_evidence(evidence, new_binding)
            projected[key] = evidence
        convergence = projected.get("convergence") or {}
        route_ids = set(invalidations["implementation_route_ids"])
        routes = convergence.get("implementation_routes") or []
        invalidated["implementation_routes"] = [
            copy.deepcopy(item) for item in routes if str(item.get("route_id")) in route_ids
        ]
        convergence["implementation_routes"] = [
            item for item in routes if str(item.get("route_id")) not in route_ids
        ]
        acceptance_ids = set(invalidations["acceptance_ids"])
        for criterion in convergence.get("criteria") or []:
            if str(criterion.get("id")) in acceptance_ids:
                criterion["status"] = "PENDING"
                criterion["invalidated_reason"] = "GOAL_REVISION_SCOPE"
        if any(invalidations.values()) or entry["invalidate_candidate"]:
            convergence["acceptance_revision"] = int(convergence.get("acceptance_revision") or 0) + 1
            convergence["status"] = "WARNING"
        projected["convergence"] = convergence
        checkpoint_ids = set(invalidations["checkpoint_ids"])
        invalidated["checkpoints"] = []
        for checkpoint in projected.get("checkpoint_refs") or []:
            checkpoint_id = str(checkpoint.get("checkpoint_id") or checkpoint.get("id"))
            if checkpoint_id in checkpoint_ids:
                invalidated["checkpoints"].append(copy.deepcopy(checkpoint))
                checkpoint["status"] = "INVALID"
                checkpoint["invalidated_reason"] = "GOAL_REVISION_SCOPE"
        projected.setdefault("invalidated_goal_evidence", []).append(invalidated)
        projected["invalidated_goal_evidence"] = projected["invalidated_goal_evidence"][-10:]
    projected["goal_adjustment"] = adjustment
    projected.setdefault("history", []).append({
        "at": timestamp,
        "event": f"GOAL_CHANGE_{classification}",
        "operation_id": safe_id(operation_id),
        "goal_revision": new_goal.get("revision"),
    })
    projected["updated_at"] = timestamp
    return projected
