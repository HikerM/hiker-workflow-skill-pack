from __future__ import annotations

import hashlib
import json
from typing import Any


MAX_SCOPE = 64
MAX_FINDINGS = 32
MAX_ARTIFACTS = 32
MAX_VERIFICATIONS = 128
FORBIDDEN_CONTENT_FIELDS = {
    "prompt", "assistant_output", "source", "source_code", "stream_delta", "screenshot_bytes",
    "log", "logs", "raw_log", "raw_content", "full_content",
}
REQUIRED_IDENTITY_FIELDS = (
    "source_fingerprint",
    "contract_fingerprint",
    "dependency_fingerprint",
)
OPTIONAL_IDENTITY_FIELDS = (
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
    payload = {field: str(identity.get(field) or "") for field in (*REQUIRED_IDENTITY_FIELDS, *OPTIONAL_IDENTITY_FIELDS)}
    if any(not payload[field] for field in REQUIRED_IDENTITY_FIELDS):
        raise ValueError("source, contract and dependency fingerprints are required")
    payload["affected_scope"] = sorted(_scope(identity.get("affected_scope")))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decide(record: dict[str, Any] | None, identity: dict[str, Any]) -> dict[str, Any]:
    expected = evidence_key(identity)
    if record is None:
        return {"status": "MISS", "reuse": False, "expected_key": expected}
    if record.get("status") != "VALID":
        return {"status": "STALE", "reuse": False, "expected_key": expected}
    if record.get("freshness") not in {None, "CURRENT"} or record.get("result") not in {None, "PASS"}:
        return {"status": "STALE", "reuse": False, "expected_key": expected}
    if record.get("evidence_key") != expected:
        return {"status": "STALE", "reuse": False, "expected_key": expected}
    return {"status": "REUSE", "reuse": True, "expected_key": expected}


def _overlaps(left: str, right: str) -> bool:
    left = left.strip().replace("\\", "/").strip("/")
    right = right.strip().replace("\\", "/").strip("/")
    if not left or not right:
        return False
    if left == right:
        return True
    return left.startswith(right + "/") or right.startswith(left + "/")


def invalidate(records: list[dict[str, Any]], affected_scope: list[str], reason: str) -> dict[str, Any]:
    affected = set(_scope(affected_scope))
    updated: list[dict[str, Any]] = []
    invalidated: list[str] = []
    for record in records:
        item = dict(record)
        record_scope = set(_scope(item.get("affected_scope", [])))
        intersects = not record_scope or bool(affected.intersection(record_scope)) or any(
            _overlaps(changed, covered) for changed in affected for covered in record_scope
        )
        if intersects:
            item["status"] = "STALE"
            item["stale_reason"] = str(reason)[:240]
            invalidated.append(str(item.get("evidence_id") or item.get("evidence_key") or "unknown"))
        updated.append(item)
    return {"records": updated, "invalidated": invalidated, "preserved": len(updated) - len(invalidated)}


def minimum_verification_set(
    checks: list[dict[str, Any]],
    records: list[dict[str, Any]],
    base_identity: dict[str, Any],
) -> dict[str, Any]:
    if len(checks) > MAX_VERIFICATIONS or len(records) > MAX_VERIFICATIONS:
        raise ValueError("verification set exceeds its bounded budget")
    by_id = {
        str(record.get("verification_id") or record.get("evidence_id")): record
        for record in records if isinstance(record, dict) and (record.get("verification_id") or record.get("evidence_id"))
    }
    execute: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    for raw in checks:
        if not isinstance(raw, dict) or not str(raw.get("verification_id") or "").strip():
            raise ValueError("each verification requires verification_id")
        check = dict(raw)
        verification_id = str(check["verification_id"]).strip()[:160]
        identity = dict(base_identity)
        if isinstance(check.get("identity"), dict):
            identity.update(check["identity"])
        identity["affected_scope"] = check.get("affected_scope", [])
        decision = decide(by_id.get(verification_id), identity)
        check.pop("identity", None)
        check["verification_id"] = verification_id
        check["affected_scope"] = _scope(identity["affected_scope"])
        check["evidence_key"] = decision["expected_key"]
        if decision["reuse"]:
            check["status"] = "REUSED"
            check["evidence_id"] = by_id[verification_id].get("evidence_id")
            reused.append(check)
        else:
            check["status"] = "PLANNED"
            check["reuse_status"] = decision["status"]
            execute.append(check)
    return {
        "status": "PASS",
        "execute": execute,
        "reused": reused,
        "required_count": len(checks),
        "execution_count": len(execute),
        "reuse_count": len(reused),
        "full_rerun": False,
    }


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
        "result": "PASS" if status == "VALID" else "BLOCKED",
        "freshness": "CURRENT",
        "affected_scope": _scope(identity.get("affected_scope")),
        "evidence_key": evidence_key(identity),
        "findings": [dict(item) for item in findings],
        "artifacts": compact_artifacts,
        "summary_only": True,
    }
