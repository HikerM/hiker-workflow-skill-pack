from __future__ import annotations

from typing import Any

from structural_decision_contract import ACTIONS, AUTHORITY, CONFIDENCE, GAIN_CLASSES, LEVELS, MAX_REFS, MAX_SCOPE, SCHEMA_VERSION, decision_fingerprint, validate_action_prerequisites


def validate_receipt(value: object) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return None, ["INVALID_STRUCTURAL_DECISION_RECEIPT"]
    required = {
        "schema_version", "status", "authority", "runtime_selected_action", "action",
        "decision_scope", "problem_refs", "evidence_refs", "reason", "alternatives_rejected",
        "expected_gain", "migration_cost", "regression_risk", "rollback_or_exit_condition",
        "confidence", "evidence_grounding", "decision_fingerprint",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append("INCOMPLETE_STRUCTURAL_DECISION_RECEIPT:" + ",".join(missing))
    if value.get("schema_version") != SCHEMA_VERSION or value.get("authority") != AUTHORITY:
        errors.append("INVALID_STRUCTURAL_DECISION_RECEIPT_AUTHORITY")
    if value.get("status") != "VALIDATED" or value.get("runtime_selected_action") is not False:
        errors.append("UNVALIDATED_STRUCTURAL_DECISION_RECEIPT")
    if value.get("action") not in ACTIONS:
        errors.append("INVALID_STRUCTURAL_DECISION_RECEIPT_ACTION")
    scope = value.get("decision_scope")
    if not isinstance(scope, list) or not scope or len(scope) > MAX_SCOPE:
        errors.append("INVALID_STRUCTURAL_DECISION_RECEIPT_SCOPE")
    for field in ("problem_refs", "evidence_refs"):
        refs = value.get(field)
        if not isinstance(refs, list) or not refs or len(refs) > MAX_REFS:
            errors.append(f"INVALID_STRUCTURAL_DECISION_RECEIPT_REFS:{field}")
    for field, allowed in (("expected_gain", GAIN_CLASSES), ("migration_cost", LEVELS), ("regression_risk", LEVELS)):
        detail = value.get(field)
        if not isinstance(detail, dict) or detail.get("classification") not in allowed:
            errors.append(f"INVALID_STRUCTURAL_DECISION_RECEIPT_DETAIL:{field}")
    if value.get("confidence") not in CONFIDENCE:
        errors.append("INVALID_STRUCTURAL_DECISION_RECEIPT_CONFIDENCE")
    grounding = value.get("evidence_grounding")
    if not isinstance(grounding, dict):
        errors.append("INVALID_STRUCTURAL_DECISION_RECEIPT_GROUNDING")
        claims: set[str] = set()
    else:
        raw_claims = grounding.get("claims")
        claims = {str(claim).strip().upper() for claim in raw_claims if str(claim).strip()} if isinstance(raw_claims, list) else set()
        validate_action_prerequisites(str(value.get("action") or ""), claims, errors)
    claimed = str(value.get("decision_fingerprint") or "")
    payload = {key: item for key, item in value.items() if key != "decision_fingerprint"}
    if claimed != decision_fingerprint(payload):
        errors.append("STRUCTURAL_DECISION_RECEIPT_FINGERPRINT_MISMATCH")
    return (dict(value) if not errors else None), errors
