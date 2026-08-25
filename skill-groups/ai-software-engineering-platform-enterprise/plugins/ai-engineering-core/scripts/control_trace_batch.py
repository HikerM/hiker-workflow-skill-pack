from __future__ import annotations

import hashlib
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import control_trace as trace
from corelib import atomic_write_json, utc_now
from control_trace_store import control_root, trace_transaction


SCHEMA_VERSION = "1.0.0"
MAX_BATCH_EVENTS = 20_000
MAX_RECENT_IMPORTS = 64


@lru_cache(maxsize=64)
def _import_journal_file(root_text: str) -> Path:
    return control_root(Path(root_text)) / "event-import-journal.json"


def import_journal_file(root: Path) -> Path:
    return _import_journal_file(str(root.resolve()))


def _load_journal(root: Path) -> dict[str, Any]:
    path = import_journal_file(root)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "imports": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"event import journal is damaged: {type(exc).__name__}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("imports"), dict):
        raise RuntimeError("event import journal schema is invalid")
    return data


def _save_journal(root: Path, journal: dict[str, Any]) -> None:
    imports = journal["imports"]
    if len(imports) > MAX_RECENT_IMPORTS:
        ordered = sorted(imports.items(), key=lambda item: str(item[1].get("updated_at") or ""))
        for key, _ in ordered[: len(imports) - MAX_RECENT_IMPORTS]:
            imports.pop(key, None)
    atomic_write_json(import_journal_file(root), journal)


def _token(value: str, label: str) -> str:
    token = trace._token(value, "", 100)
    if not token:
        raise ValueError(f"{label} is required")
    return token


def _batch_fingerprint(entries: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _build_event(
    root: Path,
    entry: dict[str, Any],
    *,
    import_id: str,
    offset: int,
    previous_hash: str | None,
    suite: dict[str, Any],
    project_ref: str,
) -> tuple[dict[str, Any], str, str]:
    summary_code = str(entry.get("summary_code") or "CONTROL_EVENT")
    if summary_code not in trace.SUMMARY_MESSAGES:
        raise ValueError(f"unsupported summary code: {summary_code}")
    operation = _token(str(entry.get("operation_id") or ""), "operation id")
    stable_payload = {
        "event_class": "TRACE_EVENT",
        "event_type": trace._token(str(entry.get("event_type") or "batch-event"), "event"),
        "summary_code": summary_code,
        "task_id": trace._token(entry.get("task_id"), "", 100) or None,
        "phase": trace._token(entry.get("phase"), "unknown", 40),
        "skill": [trace._token(item, limit=80) for item in list(dict.fromkeys(entry.get("skills") or []))[:2]],
        "tool": trace._token(entry.get("tool"), "", 120) or None,
        "result": trace._token(entry.get("result"), "UNKNOWN", 40).upper(),
        "gate_result": trace._token(entry.get("gate_result"), "", 80) or None,
        "cache_hit": bool(entry.get("cache_hit")),
        "evidence": trace._relative_evidence(root, entry.get("evidence_paths")),
        "operation_fingerprint": trace._token(entry.get("operation_fingerprint"), "", 80) or None,
    }
    payload_hash = hashlib.sha256(json.dumps(
        stable_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    event = {
        "schema_version": trace.SCHEMA_VERSION,
        "event_id": uuid.uuid4().hex[:24],
        "trace_id": trace._token(entry.get("trace_id"), uuid.uuid4().hex, 64),
        "span_id": uuid.uuid4().hex[:16],
        "parent_id": trace._token(entry.get("parent_id"), "", 64) or None,
        "occurred_at": utc_now(),
        "project_ref": f"sha256:{project_ref}",
        **stable_payload,
        "summary": trace.SUMMARY_MESSAGES[summary_code],
        "duration_ms": round(max(0.0, float(entry.get("duration_ms") or 0.0)), 3),
        "operation_id": operation,
        "import_id": import_id,
        "import_offset": offset,
        "previous_event_hash": previous_hash,
        "privacy_class": "METADATA_ONLY",
        "suite_version": suite["version"],
        "suite_fingerprint": suite["fingerprint"],
    }
    event["event_hash"] = hashlib.sha256(json.dumps(
        event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    trace._validate_event_contract(event)
    return event, payload_hash, operation


def record_event_batch(
    root: Path,
    *,
    import_id: str,
    entries: list[dict[str, Any]],
    durable: bool = False,
) -> dict[str, Any]:
    """Persist a bounded batch with segment-level writes and crash-resumable offsets."""
    root = root.resolve()
    batch_id = _token(import_id, "import id")
    if not entries or len(entries) > MAX_BATCH_EVENTS:
        raise ValueError(f"event batch must contain 1..{MAX_BATCH_EVENTS} events")
    forbidden = {"prompt", "raw_prompt", "chat", "assistant_output", "source", "source_body", "stream_delta", "content"}
    leaked = sorted({key for entry in entries for key in entry if key in forbidden})
    if leaked:
        raise ValueError(f"event batch contains forbidden content fields: {leaked}")
    operations = [str(entry.get("operation_id") or "") for entry in entries]
    if len(set(operations)) != len(operations):
        raise ValueError("event batch operation ids must be unique")
    fingerprint = _batch_fingerprint(entries)
    suite = trace._suite()
    if not suite["consistent"]:
        raise RuntimeError("plugin suite version is inconsistent")
    project_ref = trace._cached_project_ref(str(root))
    with trace_transaction(root):
        index = trace._recover_unindexed_events(root, trace._load_index(root))
        journal = _load_journal(root)
        imports = journal["imports"]
        prior = imports.get(batch_id)
        if prior and prior.get("fingerprint") != fingerprint:
            raise RuntimeError("event import id was already used with a different batch")
        if prior and prior.get("status") == "COMPLETE":
            return {
                "import_id": batch_id,
                "event_count": len(entries),
                "committed_count": len(entries),
                "idempotent_replay": True,
                "total_event_count": int(index.get("total_event_count") or 0),
            }
        committed = int((prior or {}).get("committed_count") or 0)
        latest = index.get("latest") or {}
        if latest.get("import_id") == batch_id:
            committed = max(committed, int(latest.get("import_offset") or -1) + 1)
        imports[batch_id] = {
            "fingerprint": fingerprint,
            "status": "IN_PROGRESS",
            "event_count": len(entries),
            "committed_count": committed,
            "updated_at": utc_now(),
        }
        _save_journal(root, journal)
        buffer: list[str] = []
        buffer_bytes = 0
        buffered: list[tuple[dict[str, Any], str, str]] = []
        current_size = trace.event_file(root).stat().st_size if trace.event_file(root).is_file() else 0

        def flush() -> None:
            nonlocal buffer, buffer_bytes, buffered, committed, current_size, index
            if not buffer:
                return
            trace._append(trace.event_file(root), "".join(buffer), durable)
            recent = index.get("recent_operations") or {}
            total = int(index.get("total_event_count") or 0)
            for event, payload_hash, operation in buffered:
                total += 1
                recent[operation] = {"payload_hash": payload_hash, "result": trace._compact_event(event, total)}
                index["latest"] = {
                    "event_id": event["event_id"], "trace_id": event["trace_id"],
                    "event_type": event["event_type"], "summary_code": event["summary_code"],
                    "task_id": event["task_id"], "result": event["result"], "at": event["occurred_at"],
                    "import_id": batch_id, "import_offset": event["import_offset"],
                }
            if len(recent) > trace.MAX_RECENT_OPERATIONS:
                for key in list(recent)[: len(recent) - trace.MAX_RECENT_OPERATIONS]:
                    recent.pop(key, None)
            committed += len(buffered)
            current_size = trace.event_file(root).stat().st_size
            index.update({
                "current_event_count": int(index.get("current_event_count") or 0) + len(buffered),
                "current_bytes": current_size,
                "hot_segment_bytes": sum(path.stat().st_size for path in trace._event_paths(root)),
                "total_event_count": total,
                "segment_count": len(trace._event_paths(root)) or 1,
                "last_event_hash": buffered[-1][0]["event_hash"],
                "recent_operations": recent,
            })
            atomic_write_json(trace.index_file(root), index)
            imports[batch_id]["committed_count"] = committed
            imports[batch_id]["updated_at"] = utc_now()
            _save_journal(root, journal)
            buffer, buffered, buffer_bytes = [], [], 0

        for offset in range(committed, len(entries)):
            if current_size >= trace.MAX_SEGMENT_BYTES:
                trace._rotate(root, force=True)
                index["current_event_count"] = 0
                index["current_bytes"] = 0
                current_size = 0
            event, payload_hash, operation = _build_event(
                root, entries[offset], import_id=batch_id, offset=offset,
                previous_hash=index.get("last_event_hash") if not buffered else buffered[-1][0]["event_hash"],
                suite=suite, project_ref=project_ref,
            )
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            line_bytes = len(line.encode("utf-8"))
            if buffer and current_size + buffer_bytes + line_bytes > trace.MAX_SEGMENT_BYTES:
                flush()
                trace._rotate(root, force=True)
                index["current_event_count"] = 0
                index["current_bytes"] = 0
                current_size = 0
            buffer.append(line)
            buffer_bytes += line_bytes
            buffered.append((event, payload_hash, operation))
        flush()
        imports[batch_id].update({"status": "COMPLETE", "committed_count": len(entries), "updated_at": utc_now()})
        _save_journal(root, journal)
        return {
            "import_id": batch_id,
            "event_count": len(entries),
            "committed_count": len(entries),
            "idempotent_replay": False,
            "total_event_count": int(index.get("total_event_count") or 0),
            "hot_segment_count": len(trace._event_paths(root)),
        }
