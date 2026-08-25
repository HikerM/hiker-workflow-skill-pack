from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from workspacelib import common_dir, read_json


SCHEMA = "2.0.0"
ACTIVE_STATES = {"SETUP_PENDING", "BOUND", "READY", "RUNNING", "WAITING_APPROVAL", "UNKNOWN_RUNNING"}
TERMINAL_STATES = {"DELIVERED", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}
HOST_REUSABLE_STATES = {"IDLE", "NOTLOADED"}
HOST_ACTIVE_STATES = {"ACTIVE", "RUNNING"}
TURN_ACTIVE_STATES = {"INPROGRESS", "ACTIVE", "RUNNING"}
TURN_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}
TURN_LIFECYCLE_STATES = {
    "RESERVED", "STARTED", "ACTIVE", "COMPLETING", "CONFIRMED",
    "INTERRUPTED_UNKNOWN", "RECOVERY_PROBE", "RECOVERED", "RETRYABLE", "REVIEW_REQUIRED",
}
TURN_IN_FLIGHT_STATES = {"RESERVED", "STARTED", "ACTIVE", "COMPLETING"}
TURN_RECOVERY_STATES = {"INTERRUPTED_UNKNOWN", "RECOVERY_PROBE", "REVIEW_REQUIRED"}
TURN_RESOLVED_STATES = {"CONFIRMED", "RECOVERED", "RETRYABLE"}
OUTSTANDING_TURN_LEASES = TURN_IN_FLIGHT_STATES | TURN_RECOVERY_STATES
LEGACY_TURN_STATES = {"SENT": "STARTED", "COMPLETED": "CONFIRMED", "INTERRUPTED_UNCONFIRMED": "INTERRUPTED_UNKNOWN"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@lru_cache(maxsize=64)
def _dispatch_file(root_text: str) -> Path:
    return common_dir(Path(root_text)) / "ai-engineering" / "dispatch-state.json"


def dispatch_file(root: Path) -> Path:
    return _dispatch_file(str(root.resolve()))


def load_dispatch(root: Path) -> dict[str, Any]:
    state = read_json(dispatch_file(root), {}) or {}
    state.setdefault("schema_version", SCHEMA)
    state.setdefault("dispatches", {})
    state.setdefault("notifications", {})
    state.setdefault("turn_leases", {})
    state.setdefault("turn_archive", [])
    for lease in state["turn_leases"].values():
        if isinstance(lease, dict) and lease.get("status") in LEGACY_TURN_STATES:
            lease["status"] = LEGACY_TURN_STATES[lease["status"]]
    return state


def status_token(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum()) or "UNKNOWN"


def turn_pair(host_status: str | None, turn_status: str | None) -> str:
    host = status_token(host_status)
    turn = status_token(turn_status)
    if host in HOST_ACTIVE_STATES and turn in TURN_ACTIVE_STATES:
        return "ACTIVE"
    if host in HOST_REUSABLE_STATES and turn in TURN_TERMINAL_STATES | {"NONE", "UNKNOWN"}:
        return "REUSABLE"
    if host in {"ERROR", "TIMEOUT", "UNKNOWN"} or turn == "ERROR":
        return "UNKNOWN"
    return "INCONSISTENT"
