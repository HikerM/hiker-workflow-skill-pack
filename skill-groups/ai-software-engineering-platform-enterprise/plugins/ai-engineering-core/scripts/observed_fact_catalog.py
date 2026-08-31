from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = "hiker-observed-fact-catalog/v1"
AUTHORITY = "EXTERNAL_OBSERVED_EVIDENCE"
FACT_KINDS = {
    "ARTIFACT",
    "ACTOR",
    "USAGE",
    "RISK",
    "PROJECT",
    "PROBLEM",
    "SCOPE",
    "STRUCTURE",
    "CONSUMER",
    "AUTHORITY",
    "MIGRATION",
    "CONTROL",
}
CLAIMS_BY_KIND = {
    "STRUCTURE": {
        "COHESIVE_RESPONSIBILITY",
        "LOCALIZED_CHANGE",
        "SHARED_INVARIANT",
        "SAME_CHANGE_REASON",
        "DIFFERENT_CHANGE_REASON",
        "SAME_LIFECYCLE",
        "DIVERGENT_LIFECYCLE",
    },
    "CONSUMER": {
        "MULTIPLE_CONSUMERS_PROVEN",
        "KNOWN_RUNTIME_CONSUMER",
        "NO_RUNTIME_CONSUMER_PROVEN",
        "UNKNOWN_RUNTIME_CONSUMER",
    },
    "AUTHORITY": {
        "SAME_AUTHORITY",
        "OVERLAPPING_AUTHORITY",
        "MULTIPLE_ACTIVE_IMPLEMENTATIONS",
        "SINGLE_ACTIVE_IMPLEMENTATION",
        "AUTHORITY_UNKNOWN",
    },
    "MIGRATION": {
        "MIGRATION_COMPLETE",
        "MIGRATION_NOT_APPLICABLE",
        "MIGRATION_ACTIVE",
        "MIGRATION_UNKNOWN",
    },
    "CONTROL": {
        "ROLLBACK_AVAILABLE",
        "REVERSIBLE",
        "IRREVERSIBLE",
    },
}
MAX_FACTS, MAX_ACCEPTANCE_REFS, MAX_CLAIMS_PER_FACT, MAX_REF_CHARS = 64, 32, 8, 240
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")

def _fingerprint(value: Any) -> str:
    return str(value or "").strip().lower()

def validate_catalog(
    value: object,
    *,
    expected_scope_fingerprint: str | None = None,
    expected_project_fact_fingerprint: str | None = None,
    required_error: str = "OBSERVED_FACT_CATALOG_REQUIRED",
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    empty = {
        "scope_fingerprint": "",
        "project_fact_fingerprint": None,
        "facts_by_kind": {kind: set() for kind in FACT_KINDS},
        "facts_by_ref": {},
        "critical_risk_refs": set(),
        "acceptance_refs": set(),
        "fact_count": 0,
    }
    if not isinstance(value, dict):
        errors.append(required_error)
        return empty, errors
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("INVALID_OBSERVED_FACT_CATALOG_SCHEMA")
    if value.get("authority") != AUTHORITY:
        errors.append("INVALID_OBSERVED_FACT_CATALOG_AUTHORITY")

    scope_fingerprint = _fingerprint(value.get("scope_fingerprint"))
    if not _FINGERPRINT.fullmatch(scope_fingerprint):
        errors.append("INVALID_OBSERVED_FACT_SCOPE_FINGERPRINT")
    if expected_scope_fingerprint and scope_fingerprint != _fingerprint(expected_scope_fingerprint):
        errors.append("OBSERVED_FACT_SCOPE_FINGERPRINT_MISMATCH")
    project_fingerprint = _fingerprint(value.get("project_fact_fingerprint")) or None
    if project_fingerprint and not _FINGERPRINT.fullmatch(project_fingerprint):
        errors.append("INVALID_OBSERVED_PROJECT_FACT_FINGERPRINT")
    if expected_project_fact_fingerprint:
        expected = _fingerprint(expected_project_fact_fingerprint)
        if not project_fingerprint:
            errors.append("OBSERVED_PROJECT_FACT_FINGERPRINT_REQUIRED")
        elif project_fingerprint != expected:
            errors.append("OBSERVED_PROJECT_FACT_FINGERPRINT_MISMATCH")

    raw_facts = value.get("facts")
    if not isinstance(raw_facts, list):
        errors.append("INVALID_OBSERVED_FACTS")
        raw_facts = []
    if len(raw_facts) > MAX_FACTS:
        errors.append("TOO_MANY_OBSERVED_FACTS")
    facts_by_kind: dict[str, set[str]] = {kind: set() for kind in FACT_KINDS}
    facts_by_ref: dict[str, dict[str, Any]] = {}
    critical_risk_refs: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_facts[:MAX_FACTS]):
        if not isinstance(item, dict):
            errors.append(f"INVALID_OBSERVED_FACT:{index}")
            continue
        ref = str(item.get("ref") or "").strip()
        kind = str(item.get("kind") or "").strip().upper()
        evidence_fingerprint = _fingerprint(item.get("evidence_fingerprint"))
        freshness = str(item.get("freshness") or "CURRENT").strip().upper()
        if not ref or len(ref) > MAX_REF_CHARS:
            errors.append(f"INVALID_OBSERVED_FACT_REF:{index}")
        if kind not in FACT_KINDS:
            errors.append(f"INVALID_OBSERVED_FACT_KIND:{kind or '<empty>'}")
        if not _FINGERPRINT.fullmatch(evidence_fingerprint):
            errors.append(f"INVALID_OBSERVED_FACT_FINGERPRINT:{index}")
        if freshness not in {"CURRENT", "STALE", "UNKNOWN"}:
            errors.append(f"INVALID_OBSERVED_FACT_FRESHNESS:{index}")
        critical = item.get("safety_critical", False)
        if type(critical) is not bool:
            errors.append(f"INVALID_OBSERVED_SAFETY_CRITICAL:{index}")
            critical = False
        if critical and kind != "RISK":
            errors.append(f"INVALID_OBSERVED_CRITICAL_KIND:{kind or '<empty>'}")
        raw_claims = item.get("claims", [])
        if not isinstance(raw_claims, list):
            errors.append(f"INVALID_OBSERVED_FACT_CLAIMS:{index}")
            raw_claims = []
        if len(raw_claims) > MAX_CLAIMS_PER_FACT:
            errors.append(f"TOO_MANY_OBSERVED_FACT_CLAIMS:{index}")
        claims = list(dict.fromkeys(str(claim).strip().upper() for claim in raw_claims if str(claim).strip()))
        allowed_claims = CLAIMS_BY_KIND.get(kind, set())
        for claim in claims[:MAX_CLAIMS_PER_FACT]:
            if claim not in allowed_claims:
                errors.append(f"INVALID_OBSERVED_FACT_CLAIM:{kind}:{claim}")
        key = (kind, ref)
        if key in seen:
            errors.append(f"DUPLICATE_OBSERVED_FACT:{kind}:{ref}")
        if ref in facts_by_ref and facts_by_ref[ref].get("kind") != kind:
            errors.append(f"AMBIGUOUS_OBSERVED_FACT_REF:{ref}")
        seen.add(key)
        if ref and kind in facts_by_kind:
            normalized = {
                "ref": ref,
                "kind": kind,
                "evidence_fingerprint": evidence_fingerprint,
                "freshness": freshness,
                "claims": claims[:MAX_CLAIMS_PER_FACT],
                "safety_critical": critical,
            }
            facts_by_kind[kind].add(ref)
            facts_by_ref[ref] = normalized
            if critical:
                critical_risk_refs.add(ref)

    raw_acceptance = value.get("acceptance_refs", [])
    if not isinstance(raw_acceptance, list):
        errors.append("INVALID_BOUND_ACCEPTANCE_REFS")
        raw_acceptance = []
    if len(raw_acceptance) > MAX_ACCEPTANCE_REFS:
        errors.append("TOO_MANY_BOUND_ACCEPTANCE_REFS")
    acceptance_refs: set[str] = set()
    for index, item in enumerate(raw_acceptance[:MAX_ACCEPTANCE_REFS]):
        if not isinstance(item, dict):
            errors.append(f"INVALID_BOUND_ACCEPTANCE_REF:{index}")
            continue
        ref = str(item.get("ref") or "").strip()
        classification = str(item.get("classification") or "").strip().upper()
        evidence_fingerprint = _fingerprint(item.get("evidence_fingerprint"))
        if not ref or len(ref) > MAX_REF_CHARS:
            errors.append(f"INVALID_BOUND_ACCEPTANCE_REF:{index}")
        if classification != "BOUND_ACCEPTANCE_REF":
            errors.append(f"INVALID_ACCEPTANCE_REF_CLASSIFICATION:{classification or '<empty>'}")
        if not _FINGERPRINT.fullmatch(evidence_fingerprint):
            errors.append(f"INVALID_BOUND_ACCEPTANCE_FINGERPRINT:{index}")
        if ref in acceptance_refs:
            errors.append(f"DUPLICATE_BOUND_ACCEPTANCE_REF:{ref}")
        if ref:
            acceptance_refs.add(ref)

    return {
        "scope_fingerprint": scope_fingerprint,
        "project_fact_fingerprint": project_fingerprint,
        "facts_by_kind": facts_by_kind,
        "facts_by_ref": facts_by_ref,
        "critical_risk_refs": critical_risk_refs,
        "acceptance_refs": acceptance_refs,
        "fact_count": len(facts_by_ref),
    }, errors
