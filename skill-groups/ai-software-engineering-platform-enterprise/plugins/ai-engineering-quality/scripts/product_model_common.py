from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


OBSERVATION_STATUSES = {"OBSERVED", "INFERRED", "UNKNOWN"}
DECISION_AUTHORITIES = {
    "SYSTEM_INVARIANT",
    "USER_LOCKED_DECISION",
    "PROJECT_FACT",
    "ARCHITECTURE_CONSTRAINT",
    "APPROVED_BASELINE",
    "ADAPTIVE_POLICY",
    "MODEL_PROPOSAL",
}
DECISION_STATUSES = {"ACTIVE", "SUPERSEDED"}

# Facts and architecture constraints describe reality and cannot be displaced by a
# preference. User decisions still override approved baselines and model policy.
AUTHORITY_RANK = {
    "MODEL_PROPOSAL": 10,
    "ADAPTIVE_POLICY": 20,
    "APPROVED_BASELINE": 30,
    "USER_LOCKED_DECISION": 40,
    "ARCHITECTURE_CONSTRAINT": 50,
    "PROJECT_FACT": 60,
    "SYSTEM_INVARIANT": 70,
}

MAX_DECISIONS = 256
MAX_OBSERVATIONS = 256
MAX_SOURCE_REFS = 16
MAX_AFFECTED_SCOPE = 64


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def bounded_strings(value: Any, limit: int, field: str, errors: list[dict[str, str]]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append({"code": "INVALID_STRING_LIST", "field": field})
        return []
    if len(value) > limit:
        errors.append({"code": "BOUNDED_LIST_EXCEEDED", "field": field})
    return list(dict.fromkeys(item.strip() for item in value[:limit]))


def validate_observation(value: Any, field: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append({"code": "INVALID_OBSERVATION", "field": field})
        return
    status = value.get("status")
    if status not in OBSERVATION_STATUSES:
        errors.append({"code": "INVALID_OBSERVATION_STATUS", "field": field})
    if not isinstance(value.get("subject"), str) or not value.get("subject", "").strip():
        errors.append({"code": "MISSING_OBSERVATION_SUBJECT", "field": field})
    refs = value.get("source_refs", [])
    bounded_strings(refs, MAX_SOURCE_REFS, f"{field}.source_refs", errors)
    if status == "OBSERVED" and not refs:
        errors.append({"code": "OBSERVED_REQUIRES_SOURCE", "field": field})
    if status == "UNKNOWN" and value.get("value") not in (None, "", [], {}):
        errors.append({"code": "UNKNOWN_MUST_NOT_ASSERT_VALUE", "field": field})


def decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        key: decision.get(key)
        for key in (
            "decision_id",
            "authority",
            "status",
            "topic",
            "value",
            "rationale",
            "source_refs",
            "affected_scope",
            "supersedes",
            "superseded_by",
        )
    }


def validate_decision(value: Any, field: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        errors.append({"code": "INVALID_DECISION", "field": field})
        return
    for required in ("decision_id", "authority", "status", "topic", "rationale"):
        if not isinstance(value.get(required), str) or not value.get(required, "").strip():
            errors.append({"code": "MISSING_DECISION_FIELD", "field": f"{field}.{required}"})
    if value.get("authority") not in DECISION_AUTHORITIES:
        errors.append({"code": "INVALID_DECISION_AUTHORITY", "field": field})
    if value.get("status") not in DECISION_STATUSES:
        errors.append({"code": "INVALID_DECISION_STATUS", "field": field})
    bounded_strings(value.get("source_refs", []), MAX_SOURCE_REFS, f"{field}.source_refs", errors)
    bounded_strings(value.get("affected_scope", []), MAX_AFFECTED_SCOPE, f"{field}.affected_scope", errors)
    if value.get("authority") in {"SYSTEM_INVARIANT", "PROJECT_FACT", "ARCHITECTURE_CONSTRAINT", "USER_LOCKED_DECISION"} and not value.get("source_refs"):
        errors.append({"code": "AUTHORITATIVE_DECISION_REQUIRES_SOURCE", "field": field})
    expected = fingerprint(decision_payload({**value, "fingerprint": None}))
    if value.get("fingerprint") != expected:
        errors.append({"code": "DECISION_FINGERPRINT_MISMATCH", "field": field})


def make_decision(
    decision_id: str,
    authority: str,
    topic: str,
    value: Any,
    rationale: str,
    source_refs: list[str] | None = None,
    affected_scope: list[str] | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    decision = {
        "decision_id": decision_id,
        "authority": authority,
        "status": "ACTIVE",
        "topic": topic,
        "value": value,
        "rationale": rationale,
        "source_refs": list(dict.fromkeys(source_refs or []))[:MAX_SOURCE_REFS],
        "affected_scope": list(dict.fromkeys(affected_scope or []))[:MAX_AFFECTED_SCOPE],
        "supersedes": supersedes,
        "superseded_by": None,
    }
    decision["fingerprint"] = fingerprint(decision_payload(decision))
    return decision


def apply_decision(model: dict[str, Any], decision: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    validate_decision(decision, "decision", errors)
    if errors:
        raise ValueError(stable_json(errors))
    updated = copy.deepcopy(model)
    decisions = updated.setdefault("decisions", [])
    if len(decisions) >= MAX_DECISIONS:
        raise ValueError("decision budget exceeded")
    if any(item.get("decision_id") == decision["decision_id"] for item in decisions):
        raise ValueError("duplicate decision_id")

    active_same_topic = [item for item in decisions if item.get("status") == "ACTIVE" and item.get("topic") == decision["topic"]]
    requested = decision.get("supersedes")
    target = next((item for item in active_same_topic if item.get("decision_id") == requested), None) if requested else None
    if active_same_topic and target is None:
        raise ValueError("an active decision exists; explicit supersedes is required")
    if target is not None:
        old_rank = AUTHORITY_RANK[str(target.get("authority"))]
        new_rank = AUTHORITY_RANK[str(decision.get("authority"))]
        if new_rank < old_rank:
            raise ValueError("lower authority cannot supersede the active decision")
        if target.get("authority") == "SYSTEM_INVARIANT" and decision.get("authority") != "SYSTEM_INVARIANT":
            raise ValueError("SYSTEM_INVARIANT can only be superseded by SYSTEM_INVARIANT")
        target["status"] = "SUPERSEDED"
        target["superseded_by"] = decision["decision_id"]
        target["fingerprint"] = fingerprint(decision_payload(target))

    decisions.append(decision)
    updated["revision"] = int(updated.get("revision", 0)) + 1
    updated["fingerprint"] = model_fingerprint(updated)
    impact = {
        "classification": "AFFECTED" if target else "NEW",
        "topic": decision["topic"],
        "affected_scope": decision.get("affected_scope", []),
        "superseded_decision_id": target.get("decision_id") if target else None,
        "goal_change_required": bool(target),
        "new_model_fingerprint": updated["fingerprint"],
    }
    return updated, impact


def model_fingerprint(model: dict[str, Any]) -> str:
    payload = {key: value for key, value in model.items() if key not in {"fingerprint", "updated_at"}}
    return fingerprint(payload)
