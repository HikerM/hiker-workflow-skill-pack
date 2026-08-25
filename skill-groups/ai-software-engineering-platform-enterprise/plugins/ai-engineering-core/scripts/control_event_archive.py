from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from corelib import atomic_write_json, utc_now
from control_trace_store import control_root


SCHEMA_VERSION = "1.0.0"
MAX_RECENT_SEGMENTS = 64


class EventArchiveError(RuntimeError):
    """A cold event segment cannot be trusted or recovered safely."""


@lru_cache(maxsize=64)
def _archive_root(root_text: str) -> Path:
    return control_root(Path(root_text)) / "archive" / "trace-v1"


def archive_root(root: Path) -> Path:
    return _archive_root(str(root.resolve()))


def archive_index_file(root: Path) -> Path:
    return archive_root(root) / "index.json"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_index(root: Path) -> dict[str, Any]:
    path = archive_index_file(root)
    if not path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "archived_segment_count": 0,
            "archived_event_count": 0,
            "compacted_segment_count": 0,
            "compacted_hash_chain": None,
            "recent_segments": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EventArchiveError(f"trace archive index is damaged: {type(exc).__name__}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise EventArchiveError("trace archive index schema is invalid")
    return data


def _inspect_source(payload: bytes) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise EventArchiveError("trace segment is not valid UTF-8") from exc
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EventArchiveError("trace segment contains an incomplete event") from exc
        if not isinstance(event, dict) or not event.get("event_hash"):
            raise EventArchiveError("trace segment event schema is invalid")
        claimed = str(event["event_hash"])
        hash_input = {key: value for key, value in event.items() if key != "event_hash"}
        actual = _sha256_bytes(json.dumps(
            hash_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))
        if claimed != actual:
            raise EventArchiveError("trace segment event hash is invalid")
        events.append(event)
    if not events:
        raise EventArchiveError("empty trace segment cannot be archived")
    for previous, current in zip(events, events[1:]):
        if current.get("previous_event_hash") != previous.get("event_hash"):
            raise EventArchiveError("trace segment hash chain is broken")
    return {
        "event_count": len(events),
        "first_event_hash": events[0]["event_hash"],
        "first_previous_event_hash": events[0].get("previous_event_hash"),
        "last_event_hash": events[-1]["event_hash"],
    }


def _compressed_payload(payload: bytes) -> bytes:
    return gzip.compress(payload, compresslevel=6, mtime=0)


def archive_segment(root: Path, source: Path) -> dict[str, Any]:
    """Archive one complete hot segment, verify it, then remove the source."""
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise EventArchiveError(f"trace segment cannot be read: {type(exc).__name__}") from exc
    facts = _inspect_source(payload)
    source_hash = _sha256_bytes(payload)
    segment_id = f"seg-{source_hash[:32]}"
    folder = archive_root(root)
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / f"{segment_id}.jsonl.gz"
    metadata_path = folder / f"{segment_id}.json"
    compressed = _compressed_payload(payload)
    descriptor, temp_name = tempfile.mkstemp(prefix=archive.name + ".", suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(compressed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, archive)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    restored = gzip.decompress(archive.read_bytes())
    if restored != payload:
        raise EventArchiveError("trace archive verification failed")
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "segment_id": segment_id,
        "created_at": utc_now(),
        "archive_file": archive.name,
        "source_sha256": source_hash,
        "archive_sha256": _sha256_bytes(archive.read_bytes()),
        "source_bytes": len(payload),
        **facts,
    }
    atomic_write_json(metadata_path, metadata)
    index = _load_index(root)
    recent = list(index.get("recent_segments") or [])
    already_indexed = next((item for item in recent if item.get("segment_id") == segment_id), None)
    recent = [item for item in recent if item.get("segment_id") != segment_id]
    recent.append({
        key: metadata[key]
        for key in ("segment_id", "created_at", "event_count", "source_sha256", "archive_sha256", "last_event_hash")
    })
    compacted_count = int(index.get("compacted_segment_count") or 0)
    compacted_chain = str(index.get("compacted_hash_chain") or "")
    overflow = recent[:-MAX_RECENT_SEGMENTS]
    for item in overflow:
        compacted_chain = hashlib.sha256(
            f"{compacted_chain}|{item['segment_id']}|{item['archive_sha256']}".encode("ascii")
        ).hexdigest()
        compacted_count += 1
    index.update({
        "archived_segment_count": int(index.get("archived_segment_count") or 0) + (0 if already_indexed else 1),
        "archived_event_count": int(index.get("archived_event_count") or 0) + (0 if already_indexed else int(metadata["event_count"])),
        "compacted_segment_count": compacted_count,
        "compacted_hash_chain": compacted_chain or None,
        "recent_segments": recent[-MAX_RECENT_SEGMENTS:],
        "latest_segment": recent[-1],
    })
    atomic_write_json(archive_index_file(root), index)
    try:
        source.unlink()
    except OSError as exc:
        raise EventArchiveError("trace segment archived but hot source could not be removed") from exc
    return metadata


def read_archive_segment(root: Path, segment_id: str) -> list[dict[str, Any]]:
    """Explicit cold read. Daily status paths never call this function."""
    token = str(segment_id or "").strip()
    if not token.startswith("seg-") or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for ch in token):
        raise ValueError("invalid trace archive segment id")
    folder = archive_root(root)
    metadata_path = folder / f"{token}.json"
    archive = folder / f"{token}.jsonl.gz"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        compressed = archive.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise EventArchiveError(f"trace archive segment is unavailable: {type(exc).__name__}") from exc
    if not isinstance(metadata, dict) or metadata.get("segment_id") != token:
        raise EventArchiveError("trace archive metadata is invalid")
    if _sha256_bytes(compressed) != metadata.get("archive_sha256"):
        raise EventArchiveError("trace archive compressed hash is invalid")
    try:
        payload = gzip.decompress(compressed)
    except (OSError, EOFError) as exc:
        raise EventArchiveError("trace archive segment is damaged") from exc
    if _sha256_bytes(payload) != metadata.get("source_sha256"):
        raise EventArchiveError("trace archive source hash is invalid")
    facts = _inspect_source(payload)
    if facts["event_count"] != metadata.get("event_count") or facts["last_event_hash"] != metadata.get("last_event_hash"):
        raise EventArchiveError("trace archive metadata does not match its segment")
    return [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]


def archive_status(root: Path) -> dict[str, Any]:
    index = _load_index(root)
    return {
        key: value
        for key, value in index.items()
        if key not in {"recent_segments"}
    } | {"recent_segment_count": len(index.get("recent_segments") or [])}
