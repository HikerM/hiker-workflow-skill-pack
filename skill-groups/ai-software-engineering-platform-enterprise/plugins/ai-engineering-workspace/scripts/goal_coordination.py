from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from state_consistency import assess as assess_state
except ModuleNotFoundError:  # direct workspace CLI execution
    core_scripts = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
    if str(core_scripts) not in sys.path:
        sys.path.insert(0, str(core_scripts))
    from state_consistency import assess as assess_state

from workspacelib import read_json, safe_id


ACTIVE_TASK_STATES = {"CREATED", "PLANNED", "DEVELOPMENT", "REVIEW", "TESTING", "PAUSED"}
TERMINAL_TASK_STATES = {"MERGED", "RELEASED", "CANCELLED", "FAILED", "SUPERSEDED"}
OPEN_GOAL_CHANGE_STATES = {"PREPARED", "APPLYING", "PROJECTED"}
MAX_TASKS = 256


def _task_index(root: Path) -> list[dict[str, Any]]:
    index = read_json(root / ".ai" / "governance" / "task-index.json", {}) or {}
    entries = index.get("tasks") if isinstance(index, dict) else []
    if not isinstance(entries, list):
        entries = []
    return [item for item in entries if isinstance(item, dict)][:MAX_TASKS]


def _load_tasks(root: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for summary in _task_index(root):
        task_id = str(summary.get("task_id") or "").strip()
        if not task_id:
            continue
        task = read_json(root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json", {}) or {}
        if isinstance(task, dict) and task:
            tasks.append(task)
    return tasks


def _active(task: dict[str, Any]) -> bool:
    if str(task.get("control_status") or "ACTIVE").upper() != "ACTIVE":
        return False
    state = str(task.get("state") or "").upper()
    return state in ACTIVE_TASK_STATES or (state and state not in TERMINAL_TASK_STATES)


def _goal(task: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    binding = task.get("goal_binding") or {}
    goal_id = binding.get("goal_id") or task.get("goal_id")
    revision = binding.get("revision", task.get("goal_revision"))
    try:
        revision = int(revision) if revision is not None else None
    except (TypeError, ValueError):
        revision = None
    return (str(goal_id) if goal_id else None, revision, binding.get("fingerprint"))


def _surface_set(task: dict[str, Any]) -> set[str] | None:
    contract = task.get("change_contract") or {}
    values: list[str] = []
    for key in ("owned_surface_ids", "consumed_surface_ids", "allowed_files", "affected_files"):
        raw = contract.get(key) if key in contract else task.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip().replace("\\", "/").lower() for item in raw if str(item).strip())
    values = sorted(set(values))
    return set(values) if values else None


def _overlap(left: set[str] | None, right: set[str] | None) -> bool:
    if not left or not right:
        return True
    return any(
        a == b or a.startswith(f"{b}/") or b.startswith(f"{a}/")
        for a in left for b in right
    )


def evaluate(root: Path, *, task_id: str | None = None, changed_paths: list[str] | None = None) -> dict[str, Any]:
    root = root.resolve()
    marker_path = root / ".ai" / "governance" / "goal-change-active.json"
    marker = read_json(marker_path, {}) or {}
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if marker_path.exists() and not marker:
        blockers.append({"code": "GOAL_CHANGE_STATE_DAMAGED"})
    elif marker.get("status") in OPEN_GOAL_CHANGE_STATES:
        blockers.append({
            "code": "GOAL_CHANGE_IN_PROGRESS",
            "operation_id": marker.get("operation_id"),
            "target_revision": marker.get("new_goal_revision"),
        })

    tasks = [task for task in _load_tasks(root) if _active(task)]
    task_ids = [str(task.get("task_id") or "").upper() for task in tasks]
    for duplicate in sorted({item for item in task_ids if item and task_ids.count(item) > 1}):
        blockers.append({"code": "DUPLICATE_ACTIVE_TASK", "task_id": duplicate})

    selected = next((item for item in tasks if str(item.get("task_id") or "").upper() == str(task_id or "").upper()), None)
    selected_surfaces = _surface_set(selected) if selected else None
    conflicts: list[dict[str, Any]] = []
    for index, left in enumerate(tasks):
        for right in tasks[index + 1:]:
            if str(left.get("task_id")) == str(right.get("task_id")):
                continue
            left_goal = _goal(left)
            right_goal = _goal(right)
            revision_conflict = (
                left_goal[0] == right_goal[0]
                and left_goal[0] is not None
                and (left_goal[1], left_goal[2]) != (right_goal[1], right_goal[2])
            )
            if revision_conflict:
                conflicts.append({"code": "GOAL_REVISION_CONFLICT", "task_ids": [left.get("task_id"), right.get("task_id")]})
            elif _overlap(_surface_set(left), _surface_set(right)):
                conflicts.append({"code": "GOAL_SCOPE_CONFLICT", "task_ids": [left.get("task_id"), right.get("task_id")]})
    selected_key = str(task_id or "").upper()
    for conflict in conflicts:
        if selected_key and selected_key in {str(item).upper() for item in conflict["task_ids"]}:
            blockers.append(conflict)

    consistency = {"status": "STATELESS_UNMANAGED", "ok": True}
    # A partially initialized project may legitimately contain task fixtures
    # without a provenance record. Only invoke the heavier identity audit
    # once the governed state has its explicit schema/provenance anchor.
    if (root / ".ai" / "schema.json").is_file() or (root / ".ai" / "governance" / "source-provenance.json").is_file():
        consistency = assess_state(root)
        if consistency.get("status") in {"PROJECT_IDENTITY_DRIFT", "HISTORY_DIVERGED", "UNTRUSTED_AI_STATE"}:
            blockers.append({"code": consistency.get("status"), "changed_paths": consistency.get("changed_paths", [])[:32]})
        elif consistency.get("status") in {"MATERIAL_DRIFT", "INCREMENTAL_DRIFT"}:
            warnings.append({"code": consistency.get("status"), "changed_paths": consistency.get("changed_paths", [])[:32]})
            if changed_paths and selected_surfaces and consistency.get("changed_paths"):
                changed = {str(item).replace("\\", "/").lower() for item in changed_paths}
                if any(_overlap({path}, selected_surfaces) for path in changed):
                    blockers.append({"code": "SOURCE_CHANGED_IN_ACTIVE_SCOPE", "changed_paths": sorted(changed)[:32]})

    return {
        "ok": not blockers,
        "status": "READY" if not blockers else "BLOCKED",
        "task_id": task_id,
        "active_task_count": len(tasks),
        "active_goals": sorted({str(_goal(item)[0]) for item in tasks if _goal(item)[0]}),
        "conflicts": conflicts,
        "blockers": blockers,
        "warnings": warnings,
        "consistency": {"status": consistency.get("status"), "recovery_level": consistency.get("recovery_level")},
        "policy": "one coordinator; disjoint active goals may proceed, overlapping or drifting scope is serialized",
    }
