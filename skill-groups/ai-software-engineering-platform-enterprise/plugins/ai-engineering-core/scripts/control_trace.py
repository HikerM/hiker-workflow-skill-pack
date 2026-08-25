from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from corelib import atomic_write_json, sha256_file, utc_now
from control_event_archive import archive_segment, archive_status, read_archive_segment
from control_trace_store import (
    TraceStateError as _TraceStateError,
    TraceWriteError,
    control_root,
    event_file as _event_file_path,
    index_file as _index_file_path,
    project_ref as _project_ref,
    trace_transaction as _trace_transaction,
)
from suite_version import inspect_suite


SCHEMA_VERSION = "1.0.0"
MAX_SEGMENT_BYTES = 256 * 1024
MAX_SEGMENTS = 3
MAX_EVIDENCE_PATHS = 8
MAX_RECENT_OPERATIONS = 128
EVENT_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "control-event.schema.json"
TOKEN_RE = re.compile(r"[^A-Za-z0-9._:-]+")
SUMMARY_MESSAGES = {
    "ADMISSION_ACCEPTED": "控制内核准入通过",
    "ADMISSION_BLOCKED": "控制内核准入阻断",
    "STATE_TRANSITIONED": "任务状态迁移完成",
    "STATE_TRANSITION_BLOCKED": "任务状态迁移阻断",
    "CHECKPOINT_SAVED": "任务检查点已保存",
    "HANDOFF_CREATED": "有界交接包已创建",
    "HANDOFF_ACKNOWLEDGED": "交接包已确认接管",
    "GOAL_REBOUND": "任务目标影响已重新绑定",
    "GATE_PASSED": "工程门禁通过",
    "GATE_BLOCKED": "工程门禁阻断",
    "RUNTIME_RELEASE_UNVERIFIED": "运行时释放尚未验证",
    "CONTROL_EVENT": "本地控制事件已记录"
}


@lru_cache(maxsize=64)
def _cached_event_file(root_text: str) -> Path:
    return _event_file_path(Path(root_text))


@lru_cache(maxsize=64)
def _cached_index_file(root_text: str) -> Path:
    return _index_file_path(Path(root_text))


def event_file(root: Path) -> Path:
    return _cached_event_file(str(root.resolve()))


def index_file(root: Path) -> Path:
    return _cached_index_file(str(root.resolve()))


def _token(value: str | None, fallback: str = "unknown", limit: int = 120) -> str:
    normalized = TOKEN_RE.sub("-", str(value or "").strip()).strip("-._:")
    return (normalized or fallback)[:limit]


def _relative_evidence(root: Path, values: list[str] | None) -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    for value in list(dict.fromkeys(values or []))[:MAX_EVIDENCE_PATHS]:
        target = Path(value)
        if not target.is_absolute():
            target = root / target
        try:
            resolved = target.resolve()
            relative = resolved.relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            raise ValueError(f"evidence path is outside project: {value}")
        items.append({"path": relative, "sha256": sha256_file(resolved)})
    return items


def _default_index() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "current_event_count": 0,
        "current_bytes": 0,
        "hot_segment_bytes": 0,
        "total_event_count": 0,
        "segment_count": 1,
        "latest": None,
        "last_event_hash": None,
        "recent_operations": {},
    }


def _load_index(root: Path) -> dict[str, Any]:
    path = index_file(root)
    if not path.is_file():
        return _default_index()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _TraceStateError(f"trace index is damaged: {type(exc).__name__}")
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise _TraceStateError("trace index schema is invalid")
    data.setdefault("recent_operations", {})
    data.setdefault("current_bytes", 0)
    data.setdefault("hot_segment_bytes", data.get("current_bytes", 0))
    return data


def _event_paths(root: Path) -> list[Path]:
    current = event_file(root)
    paths = [current.with_name(f"events-v1.{item}.jsonl") for item in range(MAX_SEGMENTS - 1, 0, -1)]
    paths.append(current)
    return [path for path in paths if path.is_file()]


def _read_events(root: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    current_count = 0
    current = event_file(root)
    for path in _event_paths(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise _TraceStateError(f"trace segment is unreadable: {type(exc).__name__}") from exc
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise _TraceStateError("trace segment contains an incomplete event") from exc
            if not isinstance(event, dict) or event.get("schema_version") != SCHEMA_VERSION or not event.get("event_hash"):
                raise _TraceStateError("trace segment event schema is invalid")
            claimed_hash = str(event.get("event_hash"))
            hash_input = {key: value for key, value in event.items() if key != "event_hash"}
            actual_hash = hashlib.sha256(
                json.dumps(hash_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if claimed_hash != actual_hash:
                raise _TraceStateError("trace segment event hash is invalid")
            events.append(event)
            if path == current:
                current_count += 1
    return events, current_count


def _event_payload_hash(event: dict[str, Any]) -> str:
    stable = {
        key: event.get(key)
        for key in (
            "event_class", "event_type", "summary_code", "task_id", "phase", "skill", "tool", "result",
            "gate_result", "cache_hit", "evidence", "operation_fingerprint",
        )
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _compact_event(event: dict[str, Any], total: int) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "trace_id": event["trace_id"],
        "span_id": event["span_id"],
        "event_ref": "local-control/events-v1.jsonl",
        "index_ref": "local-control/event-index.json",
        "event_hash": event["event_hash"],
        "total_event_count": total,
        "idempotent_replay": False,
    }


def _recover_unindexed_events(root: Path, index: dict[str, Any]) -> dict[str, Any]:
    current = event_file(root)
    current_bytes = current.stat().st_size if current.is_file() else 0
    if current_bytes == int(index.get("current_bytes") or 0):
        return index
    events, current_count = _read_events(root)
    previous_hash = index.get("last_event_hash")
    start = 0
    if previous_hash:
        positions = [offset for offset, event in enumerate(events) if event.get("event_hash") == previous_hash]
        if not positions:
            raise _TraceStateError("trace index anchor is outside retained segments")
        start = positions[-1] + 1
    elif int(index.get("total_event_count") or 0) > 0:
        raise _TraceStateError("trace index has no recovery anchor")
    pending = events[start:]
    cursor = previous_hash
    recent = index.get("recent_operations") or {}
    total = int(index.get("total_event_count") or 0)
    for event in pending:
        if event.get("previous_event_hash") != cursor:
            raise _TraceStateError("trace event hash chain cannot be reconciled")
        cursor = event.get("event_hash")
        total += 1
        operation = event.get("operation_id")
        if operation:
            recent[operation] = {
                "payload_hash": _event_payload_hash(event),
                "result": _compact_event(event, total),
            }
        index["latest"] = {
            "event_id": event.get("event_id"),
            "trace_id": event.get("trace_id"),
            "event_type": event.get("event_type"),
            "summary_code": event.get("summary_code"),
            "task_id": event.get("task_id"),
            "result": event.get("result"),
            "at": event.get("occurred_at"),
            "import_id": event.get("import_id"),
            "import_offset": event.get("import_offset"),
        }
    if len(recent) > MAX_RECENT_OPERATIONS:
        for key in list(recent)[: len(recent) - MAX_RECENT_OPERATIONS]:
            recent.pop(key, None)
    index.update({
        "current_event_count": current_count,
        "current_bytes": current_bytes,
        "hot_segment_bytes": sum(path.stat().st_size for path in _event_paths(root)),
        "total_event_count": total,
        "segment_count": len(_event_paths(root)) or 1,
        "last_event_hash": cursor,
        "recent_operations": recent,
    })
    atomic_write_json(index_file(root), index)
    return index


def _rotate(root: Path, force: bool = False) -> bool:
    current = event_file(root)
    if not current.is_file() or (not force and current.stat().st_size < MAX_SEGMENT_BYTES):
        return False
    oldest = current.with_name(f"events-v1.{MAX_SEGMENTS - 1}.jsonl")
    if oldest.exists():
        archive_segment(root, oldest)
    for index in range(MAX_SEGMENTS - 2, 0, -1):
        source = current.with_name(f"events-v1.{index}.jsonl")
        target = current.with_name(f"events-v1.{index + 1}.jsonl")
        if source.exists():
            os.replace(source, target)
    os.replace(current, current.with_name("events-v1.1.jsonl"))
    return True


def _append(path: Path, line: str, durable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        if durable:
            os.fsync(handle.fileno())


@lru_cache(maxsize=1)
def _suite() -> dict[str, Any]:
    return inspect_suite()


@lru_cache(maxsize=32)
def _cached_project_ref(root_text: str) -> str:
    return _project_ref(Path(root_text))


@lru_cache(maxsize=1)
def _event_schema() -> dict[str, Any]:
    try:
        schema = json.loads(EVENT_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("control event schema is unavailable or invalid") from exc
    if not isinstance(schema.get("required"), list) or not isinstance(schema.get("properties"), dict):
        raise RuntimeError("control event schema contract is incomplete")
    return schema


def _validate_event_contract(event: dict[str, Any]) -> None:
    schema = _event_schema()
    missing = set(schema["required"]) - set(event)
    extras = set(event) - set(schema["properties"])
    if missing or (schema.get("additionalProperties") is False and extras):
        raise RuntimeError(f"control event violates schema keys: missing={sorted(missing)}, extras={sorted(extras)}")
    allowed_codes = set((schema["properties"].get("summary_code") or {}).get("enum") or [])
    if event.get("summary_code") not in allowed_codes:
        raise RuntimeError("control event summary code is absent from the published schema")


def record_event(
    root: Path,
    *,
    event_type: str,
    summary_code: str,
    task_id: str | None = None,
    phase: str | None = None,
    skills: list[str] | None = None,
    tool: str | None = None,
    result: str = "UNKNOWN",
    gate_result: str | None = None,
    cache_hit: bool = False,
    evidence_paths: list[str] | None = None,
    duration_ms: float | None = None,
    trace_id: str | None = None,
    parent_id: str | None = None,
    operation_id: str | None = None,
    operation_fingerprint: str | None = None,
    durable: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    if summary_code not in SUMMARY_MESSAGES:
        raise ValueError(f"unsupported summary code: {summary_code}")
    suite = _suite()
    if not suite["consistent"]:
        raise RuntimeError("plugin suite version is inconsistent")
    now = utc_now()
    stable_payload = {
        "event_class": "TRACE_EVENT",
        "event_type": _token(event_type, "event"),
        "summary_code": summary_code,
        "task_id": _token(task_id, "", 100) or None,
        "phase": _token(phase, "unknown", 40),
        "skill": [_token(item, limit=80) for item in list(dict.fromkeys(skills or []))[:2]],
        "tool": _token(tool, "", 120) or None,
        "result": _token(result, "UNKNOWN", 40).upper(),
        "gate_result": _token(gate_result, "", 80) or None,
        "cache_hit": bool(cache_hit),
        "evidence": _relative_evidence(root, evidence_paths),
        "operation_fingerprint": _token(operation_fingerprint, "", 80) or None,
    }
    payload_hash = hashlib.sha256(json.dumps(stable_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    operation = _token(operation_id, "", 100) or None
    if not operation:
        raise ValueError("control events require an operation id")
    with _trace_transaction(root):
        index = _recover_unindexed_events(root, _load_index(root))
        recent = index.get("recent_operations") or {}
        if operation and operation in recent:
            previous = recent[operation]
            if previous.get("payload_hash") != payload_hash:
                raise RuntimeError("operation id was already used with a different payload")
            return {**previous.get("result", {}), "idempotent_replay": True}
        rotated = _rotate(root)
        if rotated:
            index["current_event_count"] = 0
        previous_hash = index.get("last_event_hash")
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_id": uuid.uuid4().hex[:24],
            "trace_id": _token(trace_id, uuid.uuid4().hex, 64),
            "span_id": uuid.uuid4().hex[:16],
            "parent_id": _token(parent_id, "", 64) or None,
            "occurred_at": now,
            "project_ref": f"sha256:{_cached_project_ref(str(root))}",
            **stable_payload,
            "summary": SUMMARY_MESSAGES[summary_code],
            "duration_ms": round(max(0.0, float(duration_ms or 0.0)), 3),
            "operation_id": operation,
            "previous_event_hash": previous_hash,
            "privacy_class": "METADATA_ONLY",
            "suite_version": suite["version"],
            "suite_fingerprint": suite["fingerprint"],
        }
        event_hash = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        event["event_hash"] = event_hash
        _validate_event_contract(event)
        _append(event_file(root), json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n", durable)
        index["current_event_count"] = int(index.get("current_event_count") or 0) + 1
        index["total_event_count"] = int(index.get("total_event_count") or 0) + 1
        index["current_bytes"] = event_file(root).stat().st_size
        index["hot_segment_bytes"] = sum(path.stat().st_size for path in _event_paths(root))
        index["segment_count"] = 1 + sum(
            event_file(root).with_name(f"events-v1.{item}.jsonl").is_file()
            for item in range(1, MAX_SEGMENTS)
        )
        index["last_event_hash"] = event_hash
        index["latest"] = {
            "event_id": event["event_id"],
            "trace_id": event["trace_id"],
            "event_type": event["event_type"],
            "summary_code": summary_code,
            "task_id": event["task_id"],
            "result": event["result"],
            "at": now,
            "import_id": None,
            "import_offset": None,
        }
        compact_result = _compact_event(event, index["total_event_count"])
        if operation:
            recent[operation] = {"payload_hash": payload_hash, "result": compact_result}
            if len(recent) > MAX_RECENT_OPERATIONS:
                for key in list(recent)[: len(recent) - MAX_RECENT_OPERATIONS]:
                    recent.pop(key, None)
            index["recent_operations"] = recent
        atomic_write_json(index_file(root), index)
    return compact_result


def status(root: Path) -> dict[str, Any]:
    index = _load_index(root.resolve())
    return {
        "schema_version": SCHEMA_VERSION,
        "index": {key: value for key, value in index.items() if key != "recent_operations"},
        "archive": archive_status(root.resolve()),
        "policy": {
            "storage": "git-common-local-control-or-local-app-state",
            "raw_prompt": False,
            "raw_chat": False,
            "source_body": False,
            "assistant_output": False,
            "free_text_summary": False,
            "max_segment_bytes": MAX_SEGMENT_BYTES,
            "max_segments": MAX_SEGMENTS,
        },
    }


def archived_segment(root: Path, segment_id: str) -> list[dict[str, Any]]:
    return read_archive_segment(root.resolve(), segment_id)


def main() -> int:
    from control_trace_cli import run_cli
    return run_cli(record_event, status, SUMMARY_MESSAGES, archived_segment)


if __name__ == "__main__":
    raise SystemExit(main())
