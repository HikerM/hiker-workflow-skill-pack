from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from event_budget import finalize_stream_activity, inspect_stream_activity, now
from workspacelib import atomic_json, common_dir, locked_state, read_json, safe_id


SCHEMA_VERSION = "1.0.0"
MAX_RECENT_SUMMARIES = 64
MAX_CHANGED_SURFACES = 16
MAX_EVIDENCE_REFS = 12


def summary_root(root: Path) -> Path:
    return common_dir(root) / "ai-engineering" / "turn-summaries"


def summary_index_file(root: Path) -> Path:
    return summary_root(root) / "index.json"


def _token_list(values: list[str] | None, limit: int) -> list[str]:
    return [safe_id(str(value)) for value in list(dict.fromkeys(values or []))[:limit]]


def _summary_hash(summary: dict[str, Any]) -> str:
    payload = {key: value for key, value in summary.items() if key != "summary_hash"}
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


@locked_state
def write_turn_summary(
    root: Path,
    turn: dict[str, Any],
    *,
    checkpoint_id: str | None = None,
    changed_surfaces: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    attempt = safe_id(str(turn.get("turn_attempt_id") or turn.get("thread_key") or "turn"))
    task_id = safe_id(str(turn.get("task_id") or "UNBOUND")).upper()
    stream_key = str(turn.get("thread_key") or attempt)
    stream = inspect_stream_activity(root, stream_key)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "event_class": "CONTROL_EVENT",
        "turn_id": attempt,
        "task_id": task_id,
        "start": turn.get("active_at") or turn.get("reserved_at"),
        "end": (
            turn.get("confirmed_at") or turn.get("recovery_completed_at")
            or turn.get("acknowledged_at") or turn.get("host_terminal_at")
            or turn.get("interrupted_at") or turn.get("reserved_at")
        ),
        "status": str(turn.get("status") or "UNKNOWN"),
        "operations": _token_list([str(turn.get("operation_id"))] if turn.get("operation_id") else [], 8),
        "changed_surfaces": _token_list(changed_surfaces, MAX_CHANGED_SURFACES),
        "test_evidence_refs": _token_list(evidence_refs, MAX_EVIDENCE_REFS),
        "checkpoint_ref": safe_id(checkpoint_id) if checkpoint_id else None,
        "stream_summary": {
            "event_count": int(stream.get("event_count") or 0),
            "byte_count": int(stream.get("byte_count") or 0),
            "hash_chain": stream.get("hash_chain"),
            "content_stored": False,
        },
        "hashes": {
            "turn_intent_sha256": turn.get("message_digest"),
            "stream_hash_chain": stream.get("hash_chain"),
        },
        "privacy_class": "METADATA_ONLY",
    }
    summary["summary_hash"] = _summary_hash(summary)
    folder = summary_root(root)
    path = folder / f"{attempt}.json"
    existing = read_json(path, None)
    summary_preexisting = isinstance(existing, dict)
    if isinstance(existing, dict):
        if existing.get("summary_hash") != summary["summary_hash"]:
            raise RuntimeError("Turn summary identity already exists with different facts")
    else:
        atomic_json(path, summary)
    index = read_json(summary_index_file(root), {}) or {}
    already_indexed = summary_preexisting or any(item.get("turn_id") == attempt for item in index.get("recent", []))
    recent = [item for item in index.get("recent", []) if item.get("turn_id") != attempt]
    recent.append({
        "turn_id": attempt,
        "task_id": task_id,
        "status": summary["status"],
        "dispatch_id": turn.get("dispatch_id"),
        "message_digest": turn.get("message_digest"),
        "summary_hash": summary["summary_hash"],
        "path": path.name,
        "end": summary["end"],
    })
    compacted_count = int(index.get("compacted_count") or 0)
    compacted_chain = str(index.get("compacted_hash_chain") or "")
    for item in recent[:-MAX_RECENT_SUMMARIES]:
        compacted_chain = hashlib.sha256(
            f"{compacted_chain}|{item['turn_id']}|{item['summary_hash']}".encode("ascii")
        ).hexdigest()
        compacted_count += 1
    atomic_json(summary_index_file(root), {
        "schema_version": SCHEMA_VERSION,
        "total_count": int(index.get("total_count") or 0) + (0 if already_indexed else 1),
        "recent": recent[-MAX_RECENT_SUMMARIES:],
        "compacted_count": compacted_count,
        "compacted_hash_chain": compacted_chain or None,
        "updated_at": now(),
    })
    finalize_stream_activity(root, stream_key)
    return summary


def read_turn_summary(root: Path, turn_id: str) -> dict[str, Any]:
    path = summary_root(root) / f"{safe_id(turn_id)}.json"
    summary = read_json(path, None)
    if not isinstance(summary, dict) or summary.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("Turn summary is unavailable or damaged")
    if summary.get("summary_hash") != _summary_hash(summary):
        raise RuntimeError("Turn summary hash is invalid")
    return summary
