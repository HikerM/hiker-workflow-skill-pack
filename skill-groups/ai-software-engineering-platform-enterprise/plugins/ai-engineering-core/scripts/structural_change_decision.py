from __future__ import annotations

from typing import Any

from observed_fact_catalog import AUTHORITY as CATALOG_AUTHORITY
from observed_fact_catalog import SCHEMA_VERSION as CATALOG_SCHEMA
from observed_fact_catalog import validate_catalog
from structural_decision_contract import (
    ACTIONS,
    AUTHORITY,
    CONFIDENCE,
    GAIN_CLASSES,
    LEVELS,
    MAX_SCOPE,
    SCHEMA_VERSION,
    alternatives_field,
    decision_fingerprint,
    detail_field,
    ground_refs,
    refs_field,
    safe_scope,
    text_field,
    validate_action_prerequisites,
)
from structural_decision_receipt import validate_receipt


def not_applicable() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "NOT_APPLICABLE",
        "authority": AUTHORITY,
        "runtime_selected_action": False,
    }


def validate_decision(
    value: object,
    *,
    observed_fact_catalog: object = None,
    expected_scope_fingerprint: str | None = None,
    expected_project_fact_fingerprint: str | None = None,
) -> dict[str, Any]:
    if value is None:
        return not_applicable()
    if not isinstance(value, dict):
        raise RuntimeError("INVALID_STRUCTURAL_CHANGE_DECISION:must be an object or omitted")
    errors: list[str] = []
    if "observed_fact_catalog" in value or "evidence_receipt" in value:
        errors.append("STRUCTURAL_PROPOSAL_CANNOT_DECLARE_EVIDENCE_CATALOG")
    catalog, catalog_errors = validate_catalog(
        observed_fact_catalog,
        expected_scope_fingerprint=expected_scope_fingerprint,
        expected_project_fact_fingerprint=expected_project_fact_fingerprint,
        required_error="STRUCTURAL_OBSERVED_FACT_CATALOG_REQUIRED",
    )
    errors.extend(catalog_errors)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("INVALID_STRUCTURAL_DECISION_SCHEMA")
    if value.get("authority") != AUTHORITY:
        errors.append("INVALID_STRUCTURAL_DECISION_AUTHORITY")
    action = str(value.get("action") or "").strip().upper()
    if action not in ACTIONS:
        errors.append(f"INVALID_STRUCTURAL_DECISION_ACTION:{action or '<empty>'}")
    scope = refs_field(value.get("decision_scope"), "decision_scope", errors, limit=MAX_SCOPE)
    for ref in scope:
        if not safe_scope(ref):
            errors.append(f"UNSAFE_STRUCTURAL_DECISION_SCOPE:{ref}")
    ground_refs(scope, catalog, errors, kind="SCOPE")
    problem_refs = refs_field(value.get("problem_refs"), "problem_refs", errors)
    ground_refs(problem_refs, catalog, errors, kind="PROBLEM")
    evidence_refs = refs_field(value.get("evidence_refs"), "evidence_refs", errors)
    evidence_facts = ground_refs(evidence_refs, catalog, errors)
    decision_evidence = set(evidence_refs)
    reason = text_field(value.get("reason"), "reason", errors)
    alternatives = alternatives_field(value.get("alternatives_rejected"), action, errors)
    expected_gain = detail_field(value.get("expected_gain"), "expected_gain", GAIN_CLASSES, catalog, decision_evidence, errors)
    if expected_gain["classification"] == "OBSERVED" and not expected_gain["evidence_refs"]:
        errors.append("OBSERVED_GAIN_EVIDENCE_REQUIRED")
    migration_cost = detail_field(value.get("migration_cost"), "migration_cost", LEVELS, catalog, decision_evidence, errors)
    regression_risk = detail_field(value.get("regression_risk"), "regression_risk", LEVELS, catalog, decision_evidence, errors)
    rollback = text_field(value.get("rollback_or_exit_condition"), "rollback_or_exit_condition", errors)
    confidence = str(value.get("confidence") or "").strip().upper()
    if confidence not in CONFIDENCE:
        errors.append(f"INVALID_STRUCTURAL_DECISION_CONFIDENCE:{confidence or '<empty>'}")
    claims = {claim for fact in evidence_facts for claim in fact.get("claims", [])}
    validate_action_prerequisites(action, claims, errors)
    for ref in sorted(set(catalog.get("critical_risk_refs", set())) - decision_evidence):
        errors.append(f"KNOWN_SAFETY_CRITICAL_RISK_OMITTED:{ref}")
    if errors:
        raise RuntimeError(";".join(errors))
    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "VALIDATED",
        "authority": AUTHORITY,
        "runtime_selected_action": False,
        "action": action,
        "decision_scope": scope,
        "problem_refs": problem_refs,
        "evidence_refs": evidence_refs,
        "reason": reason,
        "alternatives_rejected": alternatives,
        "expected_gain": expected_gain,
        "migration_cost": migration_cost,
        "regression_risk": regression_risk,
        "rollback_or_exit_condition": rollback,
        "confidence": confidence,
        "evidence_grounding": {
            "catalog_schema_version": CATALOG_SCHEMA,
            "catalog_authority": CATALOG_AUTHORITY,
            "scope_fingerprint": catalog["scope_fingerprint"],
            "project_fact_fingerprint": catalog["project_fact_fingerprint"],
            "observed_fact_count": catalog["fact_count"],
            "referenced_fact_count": len(set(scope + problem_refs + evidence_refs)),
            "claims": sorted(claims),
        },
    }
    normalized["decision_fingerprint"] = decision_fingerprint(normalized)
    return normalized
