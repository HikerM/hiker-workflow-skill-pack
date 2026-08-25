from __future__ import annotations

from typing import Any

from event_budget import DRAINING_ACTIONS, observe_budget

ACTIVE_LEASES = {"RESERVED", "STARTED", "ACTIVE", "COMPLETING"}
INTERRUPTED_LEASE = "INTERRUPTED_UNKNOWN"


def current_pressure(state: dict[str, Any]) -> dict[str, Any]:
    current = state.get("desktop_pressure")
    if isinstance(current, dict):
        if "state" not in current:
            legacy = str(current.get("level") or "NORMAL").upper()
            migrated = {"NORMAL": "GREEN", "ELEVATED": "YELLOW", "HARD": "DRAINING"}.get(legacy, "GREEN")
            return {
                **current,
                "state": migrated,
                "level": migrated,
                "max_active_turns": 2 if migrated == "GREEN" else 1 if migrated == "YELLOW" else 0,
            }
        return current
    return {
        "state": "GREEN",
        "level": "GREEN",
        "action": "ALLOW_BOUNDED_GOVERNED_TURNS",
        "blocks_new_dispatch": False,
        "max_active_turns": 2,
        "allowed_actions": ["all"],
        "observed_at": None,
    }


def active_lease_count(state: dict[str, Any]) -> int:
    return sum(
        1
        for lease in (state.get("turn_leases") or {}).values()
        if isinstance(lease, dict) and lease.get("status") in ACTIVE_LEASES
    )


def evaluate_local_pressure(
    root,
    state: dict[str, Any],
    *,
    task_id: str | None,
    backend_status: str,
    observation_id: str,
) -> dict[str, Any]:
    return observe_budget(root, state, task_id, backend_status, observation_id)


def apply_pressure(state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    interrupted: list[str] = []
    if report["backend_status"] in {"MISSING", "RESTARTED"}:
        for key, lease in (state.get("turn_leases") or {}).items():
            if isinstance(lease, dict) and lease.get("status") in ACTIVE_LEASES:
                lease["status"] = INTERRUPTED_LEASE
                lease["interrupted_at"] = report["observed_at"]
                lease["interruption_reason"] = f"backend:{report['backend_status'].lower()}"
                lease["lifecycle_event_count"] = int(lease.get("lifecycle_event_count") or 0) + 1
                interrupted.append(key)
    report = {
        **report,
        "action": (
            "ALLOW_BOUNDED_GOVERNED_TURNS" if report["state"] == "GREEN"
            else "REDUCE_TO_ONE_ACTIVE_TURN" if report["state"] == "YELLOW"
            else "REFUSE_NEW_GOVERNED_TURNS" if report["state"] == "RED"
            else "CHECKPOINT_VERIFY_ARCHIVE_RELEASE"
        ),
        "allowed_actions": sorted(DRAINING_ACTIONS) if report["state"] == "DRAINING" else report["allowed_actions"],
        "interrupted_dispatches": interrupted,
    }
    state["desktop_pressure"] = report
    return report
