from __future__ import annotations

import json
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, common_dir


CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))
from process_identity import owner_status, process_identity  # noqa: E402


SCHEMA = "1.0.0"
DEFAULT_LEASE_SECONDS = 180
MIN_REFRESH_SECONDS = 30
ACTIVE_LEASE_STATES = {"ACTIVE"}


@lru_cache(maxsize=32)
def _cached_lease_dir(root_text: str) -> Path:
    return common_dir(Path(root_text)) / "ai-engineering" / "turn-leases"


def lease_dir(root: Path) -> Path:
    return _cached_lease_dir(str(root.resolve()))


def lease_file(root: Path, thread_key: str) -> Path:
    return lease_dir(root) / f"{thread_key}.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"turn lease is damaged; dispatch remains blocked: {exc}")
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        raise RuntimeError("turn lease is damaged; schema is invalid")
    return value


def read_turn_lease(root: Path, thread_key: str) -> dict[str, Any]:
    return _load(lease_file(root, thread_key))


def open_turn_lease(
    root: Path,
    thread_key: str,
    turn_attempt_id: str,
    task_id: str | None,
    dispatch_id: str,
    operation_id: str,
    owner_pid: int | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    at: float | None = None,
) -> dict[str, Any]:
    path = lease_file(root, thread_key)
    existing = _load(path)
    if existing.get("lease_state") in ACTIVE_LEASE_STATES:
        same = existing.get("turn_attempt_id") == turn_attempt_id and existing.get("dispatch_id") == dispatch_id
        if same:
            return {**existing, "write_performed": False, "idempotent": True}
        raise RuntimeError("an active turn lease already exists for this desktop task")
    seconds = max(60, min(int(lease_seconds), 3600))
    moment = float(at if at is not None else time.time())
    identity = process_identity(int(owner_pid)) if owner_pid else None
    if owner_pid and identity is None:
        raise RuntimeError("turn lease owner identity cannot be verified")
    value = {
        "schema_version": SCHEMA,
        "thread_key": thread_key,
        "turn_attempt_id": turn_attempt_id,
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "operation_id": operation_id,
        "lease_state": "ACTIVE",
        "owner_identity": identity,
        "lease_seconds": seconds,
        "opened_epoch": moment,
        "last_refresh_epoch": moment,
        "expires_epoch": moment + seconds,
        "refresh_count": 0,
    }
    atomic_json(path, value)
    return {**value, "write_performed": True, "idempotent": False}


def inspect_turn_lease(root: Path, thread_key: str, at: float | None = None) -> dict[str, Any]:
    value = _load(lease_file(root, thread_key))
    if not value:
        return {"lease_state": "MISSING", "owner_status": "UNKNOWN", "expired_hint": False}
    moment = float(at if at is not None else time.time())
    identity = value.get("owner_identity")
    status = owner_status({"pid": identity.get("pid"), "runtime_identity": identity}) if isinstance(identity, dict) else "UNKNOWN"
    return {
        **value,
        "owner_status": status,
        "expired_hint": moment >= float(value.get("expires_epoch") or 0),
    }


def refresh_turn_lease(
    root: Path,
    thread_key: str,
    owner_pid: int | None = None,
    force: bool = False,
    at: float | None = None,
) -> dict[str, Any]:
    path = lease_file(root, thread_key)
    value = _load(path)
    if not value or value.get("lease_state") not in ACTIVE_LEASE_STATES:
        raise RuntimeError("active turn lease not found")
    moment = float(at if at is not None else time.time())
    identity = value.get("owner_identity")
    status = owner_status({"pid": identity.get("pid"), "runtime_identity": identity}) if isinstance(identity, dict) else "UNKNOWN"
    observed = {
        **value,
        "owner_status": status,
        "expired_hint": moment >= float(value.get("expires_epoch") or 0),
    }
    if observed["owner_status"] in {"DEAD", "IDENTITY_CHANGED"}:
        return {**observed, "write_performed": False, "refresh_allowed": False}
    if owner_pid:
        current = process_identity(int(owner_pid))
        stored = value.get("owner_identity")
        if stored and current != stored:
            return {**observed, "owner_status": "IDENTITY_CHANGED", "write_performed": False, "refresh_allowed": False}
        if stored is None and current is not None:
            value["owner_identity"] = current
    elapsed = moment - float(value.get("last_refresh_epoch") or 0)
    due = bool(force or elapsed >= MIN_REFRESH_SECONDS)
    if not due:
        return {**observed, "write_performed": False, "refresh_allowed": True, "next_refresh_in": MIN_REFRESH_SECONDS - elapsed}
    seconds = int(value.get("lease_seconds") or DEFAULT_LEASE_SECONDS)
    value["last_refresh_epoch"] = moment
    value["expires_epoch"] = moment + seconds
    value["refresh_count"] = int(value.get("refresh_count") or 0) + 1
    atomic_json(path, value)
    return {**value, "owner_status": observed["owner_status"], "expired_hint": False, "write_performed": True, "refresh_allowed": True}


def close_turn_lease(root: Path, thread_key: str, resolution: str) -> dict[str, Any]:
    path = lease_file(root, thread_key)
    value = _load(path)
    if not value:
        return {"lease_state": "MISSING", "write_performed": False}
    if value.get("lease_state") == "CLOSED" and value.get("resolution") == resolution:
        return {**value, "write_performed": False}
    value["lease_state"] = "CLOSED"
    value["resolution"] = resolution
    value["closed_epoch"] = time.time()
    atomic_json(path, value)
    return {**value, "write_performed": True}


def active_lease_count(root: Path) -> int:
    directory = lease_dir(root)
    if not directory.is_dir():
        return 0
    count = 0
    for path in directory.glob("*.json"):
        if _load(path).get("lease_state") in ACTIVE_LEASE_STATES:
            count += 1
    return count
