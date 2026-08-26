from __future__ import annotations

import hashlib
import json
from typing import Any


MAX_SCOPE = 64
MAX_FINDINGS = 32
MAX_ARTIFACTS = 32
FORBIDDEN_CONTENT_FIELDS = {
    "prompt", "assistant_output", "source", "source_code", "stream_delta", "screenshot_bytes",
    "log", "logs", "raw_log", "raw_content", "full_content",
}
IDENTITY_FIELDS = (
    "source_fingerprint",
    "design_fingerprint",
    "project_config_fingerprint",
    "technology_fingerprint",
    "environment_fingerprint",
    "relevant_state_fingerprint",
)


def _scope(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_SCOPE:
        raise ValueError(f"affected_scope must contain at most {MAX_SCOPE} strings")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(value):
        raise ValueError("affected_scope must contain non-empty strings")
    return list(dict.fromkeys(result))


def evidence_key(identity: dict[str, Any]) -> str:
    payload = {field: str(identity.get(field) or "") for field in IDENTITY_FIELDS}
    if any(not value for value in payload.values()):
        raise ValueError("all evidence identity fingerprints are required")
    payload["affected_scope"] = sorted(_scope(identity.get("affected_scope")))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decide(record: dict[str, Any] | None, identity: dict[str, Any]) -> dict[str, Any]:
    expected = evidence_key(identity)
    if record is None:
        return {"status": "MISS", "reuse": False, "expected_key": expected}
    if record.get("status") != "VALID":
        return {"status": "STALE", "reuse": False, "expected_key": expected}
    if record.get("evidence_key") != expected:
        return {"status": "STALE", "reuse": False, "expected_key": expected}
    return {"status": "REUSE", "reuse": True, "expected_key": expected}


def invalidate(records: list[dict[str, Any]], affected_scope: list[str], reason: str) -> dict[str, Any]:
    affected = set(_scope(affected_scope))
    updated: list[dict[str, Any]] = []
    invalidated: list[str] = []
    for record in records:
        item = dict(record)
        record_scope = set(_scope(item.get("affected_scope", [])))
        if affected.intersection(record_scope):
            item["status"] = "STALE"
            item["stale_reason"] = str(reason)[:240]
            invalidated.append(str(item.get("evidence_id") or item.get("evidence_key") or "unknown"))
        updated.append(item)
    return {"records": updated, "invalidated": invalidated, "preserved": len(updated) - len(invalidated)}


def compact_summary(
    identity: dict[str, Any],
    *,
    evidence_id: str,
    status: str,
    findings: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    if status not in {"VALID", "BLOCKED"}:
        raise ValueError("evidence status is invalid")
    if len(findings) > MAX_FINDINGS or len(artifacts) > MAX_ARTIFACTS:
        raise ValueError("evidence summary exceeds its bounded budget")
    for collection in (findings, artifacts):
        for item in collection:
            if not isinstance(item, dict) or FORBIDDEN_CONTENT_FIELDS.intersection(item):
                raise ValueError("cold evidence summary contains forbidden raw content")
    compact_artifacts: list[dict[str, Any]] = []
    for item in artifacts:
        if not all(item.get(field) for field in ("ref", "sha256")) or not isinstance(item.get("bytes"), int):
            raise ValueError("artifact must contain ref, sha256 and bytes")
        compact_artifacts.append({field: item[field] for field in ("ref", "sha256", "bytes")})
    return {
        "schema_version": "1.0.0",
        "evidence_id": evidence_id,
        "status": status,
        "affected_scope": _scope(identity.get("affected_scope")),
        "evidence_key": evidence_key(identity),
        "findings": [dict(item) for item in findings],
        "artifacts": compact_artifacts,
        "summary_only": True,
    }
