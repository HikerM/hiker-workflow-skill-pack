from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, common_dir, locked_state, read_json, safe_id


CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))
from control_trace import index_file as trace_index_file  # noqa: E402
from control_trace import status as trace_status  # noqa: E402


SCHEMA_VERSION = "1.0.0"
EVENT_CLASSES = {"STATE_EVENT", "CONTROL_EVENT", "TRACE_EVENT", "STREAM_EVENT"}
MAX_STREAM_TURNS = 2
MAX_OBSERVATIONS = 32
MAX_OBSERVATION_IDS = 64
DRAINING_ACTIONS = {"checkpoint", "verify", "archive", "release", "recovery", "complete"}
SOFT_LIMITS = {
    "task_hot_events": 48,
    "turn_hot_events": 16,
    "hot_event_bytes": 1280 * 1024,
    "trace_segment_bytes": 192 * 1024,
    "growth_per_minute": 2_000,
    "active_turns": 2,
    "streaming_turns": 1,
    "largest_stream_events": 5_000,
}
HARD_LIMITS = {
    "task_hot_events": 64,
    "turn_hot_events": 32,
    "hot_event_bytes": 2 * 1024 * 1024,
    "trace_segment_bytes": 384 * 1024,
    "growth_per_minute": 5_000,
    "active_turns": 3,
    "streaming_turns": 2,
    "largest_stream_events": 10_000,
}


def classify_native_event(source: str, event_code: str | None = None) -> str:
    kind = str(source or "").strip().upper()
    if kind == "TRACE":
        return "TRACE_EVENT"
    if kind == "STREAM":
        return "STREAM_EVENT"
    if kind in {"DISPATCH", "SESSION", "CONTROL"} or str(event_code or "").startswith("CONTROL:"):
        return "CONTROL_EVENT"
    return "STATE_EVENT"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@lru_cache(maxsize=64)
def _runtime_file(root_text: str) -> Path:
    return common_dir(Path(root_text)) / "ai-engineering" / "event-runtime-v1.json"


def runtime_file(root: Path) -> Path:
    return _runtime_file(str(root.resolve()))


def _default_runtime() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stream_turns": {},
        "observations": [],
        "recent_observation_ids": [],
        "total_stream_events": 0,
        "total_stream_bytes": 0,
    }


def load_runtime(root: Path) -> dict[str, Any]:
    data = read_json(runtime_file(root), None)
    if data is None:
        return _default_runtime()
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("event runtime index is damaged or has an unsupported schema")
    data.setdefault("stream_turns", {})
    data.setdefault("observations", [])
    data.setdefault("recent_observation_ids", [])
    return data


@locked_state
def record_stream_activity(
    root: Path,
    turn_key: str,
    task_id: str | None,
    event_count: int,
    byte_count: int,
    observation_id: str,
) -> dict[str, Any]:
    """Aggregate numeric stream activity. Content is intentionally not accepted."""
    count = max(0, int(event_count))
    size = max(0, int(byte_count))
    if not count and not size:
        return {"write_performed": False, "event_count": 0, "byte_count": 0}
    key = safe_id(turn_key)
    observed = safe_id(observation_id)
    runtime = load_runtime(root)
    if observed in runtime["recent_observation_ids"]:
        return {"write_performed": False, "idempotent_replay": True, "observation_id": observed}
    streams = runtime["stream_turns"]
    item = dict(streams.get(key) or {
        "turn_key": key,
        "task_id": safe_id(task_id).upper() if task_id else None,
        "started_at": now(),
        "event_count": 0,
        "byte_count": 0,
        "hash_chain": None,
        "content_stored": False,
        "event_class": "STREAM_EVENT",
    })
    chain = str(item.get("hash_chain") or "")
    item.update({
        "event_count": int(item.get("event_count") or 0) + count,
        "byte_count": int(item.get("byte_count") or 0) + size,
        "updated_at": now(),
        "hash_chain": hashlib.sha256(f"{chain}|{observed}|{count}|{size}".encode("ascii")).hexdigest(),
    })
    streams[key] = item
    if len(streams) > MAX_STREAM_TURNS:
        raise RuntimeError("stream Turn budget exceeded; enter DRAINING before accepting more stream activity")
    runtime["total_stream_events"] = int(runtime.get("total_stream_events") or 0) + count
    runtime["total_stream_bytes"] = int(runtime.get("total_stream_bytes") or 0) + size
    runtime["recent_observation_ids"] = [*runtime["recent_observation_ids"], observed][-MAX_OBSERVATION_IDS:]
    runtime["updated_at"] = now()
    atomic_json(runtime_file(root), runtime)
    return {**item, "write_performed": True, "observation_id": observed}


@locked_state
def finalize_stream_activity(root: Path, turn_key: str) -> dict[str, Any]:
    runtime = load_runtime(root)
    item = runtime["stream_turns"].pop(safe_id(turn_key), None)
    if not isinstance(item, dict):
        return {"event_count": 0, "byte_count": 0, "content_stored": False, "write_performed": False}
    runtime["updated_at"] = now()
    atomic_json(runtime_file(root), runtime)
    return {
        "event_count": int(item.get("event_count") or 0),
        "byte_count": int(item.get("byte_count") or 0),
        "hash_chain": item.get("hash_chain"),
        "content_stored": False,
        "write_performed": True,
    }


def inspect_stream_activity(root: Path, turn_key: str) -> dict[str, Any]:
    item = load_runtime(root)["stream_turns"].get(safe_id(turn_key))
    if not isinstance(item, dict):
        return {"event_count": 0, "byte_count": 0, "hash_chain": None, "content_stored": False}
    return {
        "event_count": int(item.get("event_count") or 0),
        "byte_count": int(item.get("byte_count") or 0),
        "hash_chain": item.get("hash_chain"),
        "content_stored": False,
    }


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _task_metrics(root: Path, task_id: str | None) -> tuple[int, int]:
    if not task_id:
        return 0, 0
    path = root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json"
    data = read_json(path, {}) or {}
    return len(data.get("history") or []), _file_size(path)


def collect_metrics(root: Path, dispatch_state: dict[str, Any], task_id: str | None = None) -> dict[str, int]:
    runtime = load_runtime(root)
    trace = trace_status(root)
    trace_index = trace.get("index") or {}
    streams = [item for item in runtime["stream_turns"].values() if isinstance(item, dict)]
    turns = [item for item in (dispatch_state.get("turn_leases") or {}).values() if isinstance(item, dict)]
    task_events, task_bytes = _task_metrics(root, task_id)
    dispatch_bytes = _file_size(runtime_file(root).with_name("dispatch-state.json"))
    runtime_bytes = _file_size(runtime_file(root))
    trace_hot_bytes = int(trace_index.get("hot_segment_bytes") or trace_index.get("current_bytes") or 0)
    total = int(trace_index.get("total_event_count") or 0) + int(runtime.get("total_stream_events") or 0)
    observations = list(runtime.get("observations") or [])
    growth = 0
    if observations:
        previous = observations[-1]
        elapsed = max(0.001, time.time() - float(previous.get("epoch") or time.time()))
        growth = max(0, round((total - int(previous.get("total_event_count") or 0)) * 60.0 / elapsed))
    return {
        "task_hot_events": task_events,
        "turn_hot_events": max([int(item.get("lifecycle_event_count") or 0) for item in turns] or [0]),
        "hot_event_bytes": trace_hot_bytes + _file_size(trace_index_file(root)) + dispatch_bytes + runtime_bytes + task_bytes,
        "trace_segment_bytes": int(trace_index.get("current_bytes") or 0),
        "growth_per_minute": growth,
        "active_turns": sum(1 for item in turns if item.get("status") in {"RESERVED", "STARTED", "ACTIVE", "COMPLETING"}),
        "streaming_turns": len(streams),
        "largest_stream_events": max([int(item.get("event_count") or 0) for item in streams] or [0]),
        "total_event_count": total,
    }


def _reasons(metrics: dict[str, int], limits: dict[str, int]) -> list[str]:
    return [name for name, limit in limits.items() if int(metrics.get(name) or 0) >= limit]


@locked_state
def observe_budget(
    root: Path,
    dispatch_state: dict[str, Any],
    task_id: str | None,
    backend_status: str,
    observation_id: str,
) -> dict[str, Any]:
    backend = str(backend_status or "UNKNOWN").upper()
    if backend not in {"ALIVE", "MISSING", "RESTARTED", "UNKNOWN"}:
        raise ValueError("backend status must be ALIVE, MISSING, RESTARTED or UNKNOWN")
    metrics = collect_metrics(root, dispatch_state, task_id)
    runtime = load_runtime(root)
    observed = safe_id(observation_id)
    if observed not in runtime["recent_observation_ids"]:
        runtime["observations"] = [*runtime["observations"], {
            "observation_id": observed,
            "epoch": time.time(),
            "total_event_count": metrics["total_event_count"],
        }][-MAX_OBSERVATIONS:]
        runtime["recent_observation_ids"] = [*runtime["recent_observation_ids"], observed][-MAX_OBSERVATION_IDS:]
        runtime["updated_at"] = now()
        atomic_json(runtime_file(root), runtime)
    hard = _reasons(metrics, HARD_LIMITS)
    if backend in {"MISSING", "RESTARTED", "UNKNOWN"}:
        hard.append(f"backend:{backend.lower()}")
    soft = _reasons(metrics, SOFT_LIMITS)
    previous = dispatch_state.get("desktop_pressure") or {}
    if hard:
        state = "DRAINING" if metrics["active_turns"] or metrics["streaming_turns"] else "RED"
    elif soft:
        state = "YELLOW"
    else:
        state = "GREEN"
    safe_clear = state == "GREEN" and backend == "ALIVE" and metrics["active_turns"] == 0 and metrics["streaming_turns"] == 0
    if previous.get("state") in {"RED", "DRAINING"} and not safe_clear:
        state = "DRAINING"
    max_active = 2 if state == "GREEN" else 1 if state == "YELLOW" else 0
    recommended = (
        [] if state == "GREEN"
        else ["aggregate", "rotate", "checkpoint", "archive"] if state == "YELLOW"
        else ["checkpoint", "archive"] if state == "RED"
        else sorted(DRAINING_ACTIONS)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "level": state,
        "backend_status": backend,
        "metrics": metrics,
        "reasons": list(dict.fromkeys(hard if hard else soft)),
        "blocks_new_dispatch": state in {"RED", "DRAINING"},
        "max_active_turns": max_active,
        "allowed_actions": sorted(DRAINING_ACTIONS) if state == "DRAINING" else ["all"],
        "recommended_actions": recommended,
        "observation_id": observed,
        "observed_at": now(),
        "cold_archive_scanned": False,
    }


def action_allowed(pressure: dict[str, Any], action: str) -> bool:
    state = str(pressure.get("state") or "GREEN").upper()
    if state != "DRAINING":
        return not (state == "RED" and action == "dispatch")
    return str(action or "").strip().lower() in DRAINING_ACTIONS
