from __future__ import annotations

import hashlib
import json
from pathlib import PurePath
from typing import Any

SCHEMA_VERSION = "hiker-structural-change-decision/v1"
AUTHORITY = "CHATGPT_SEMANTIC_SELECTION"
ACTIONS = {"MODIFY_EXISTING", "INTRODUCE_ABSTRACTION", "CONSOLIDATE_SIMPLIFY", "DELETE_SAFELY", "KEEP_CURRENT_STRUCTURE"}
GAIN_CLASSES = {"OBSERVED", "INFERRED", "EXPECTED"}
LEVELS = {"NONE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"}
CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
MAX_REFS = 24
MAX_SCOPE = 16
MAX_ALTERNATIVES = 4
MAX_TEXT = 800
MAX_REF_CHARS = 240
CONTRADICTIONS = (
    {"SAME_CHANGE_REASON", "DIFFERENT_CHANGE_REASON"},
    {"SAME_LIFECYCLE", "DIVERGENT_LIFECYCLE"},
    {"NO_RUNTIME_CONSUMER_PROVEN", "KNOWN_RUNTIME_CONSUMER"},
    {"NO_RUNTIME_CONSUMER_PROVEN", "MULTIPLE_CONSUMERS_PROVEN"},
    {"NO_RUNTIME_CONSUMER_PROVEN", "UNKNOWN_RUNTIME_CONSUMER"},
    {"SINGLE_ACTIVE_IMPLEMENTATION", "MULTIPLE_ACTIVE_IMPLEMENTATIONS"},
    {"MIGRATION_COMPLETE", "MIGRATION_ACTIVE"},
    {"MIGRATION_COMPLETE", "MIGRATION_UNKNOWN"},
    {"MIGRATION_NOT_APPLICABLE", "MIGRATION_ACTIVE"},
    {"REVERSIBLE", "IRREVERSIBLE"},
)


def text_field(value: object, field: str, errors: list[str]) -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_TEXT:
        errors.append(f"INVALID_STRUCTURAL_DECISION_TEXT:{field}")
    return text[:MAX_TEXT]


def refs_field(value: object, field: str, errors: list[str], *, required: bool = True, limit: int = MAX_REFS) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"INVALID_STRUCTURAL_DECISION_REFS:{field}")
        return []
    refs = list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
    if required and not refs:
        errors.append(f"MISSING_STRUCTURAL_DECISION_REFS:{field}")
    if len(refs) > limit:
        errors.append(f"TOO_MANY_STRUCTURAL_DECISION_REFS:{field}")
    if any(len(ref) > MAX_REF_CHARS for ref in refs):
        errors.append(f"OVERSIZED_STRUCTURAL_DECISION_REF:{field}")
    return refs[:limit]


def safe_scope(ref: str) -> bool:
    if not ref or "\x00" in ref:
        return False
    if "://" in ref:
        return not ref.startswith(("file:///", "file://.."))
    path = PurePath(ref.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and not (len(ref) > 1 and ref[1] == ":")


def ground_refs(refs: list[str], catalog: dict[str, Any], errors: list[str], *, kind: str | None = None) -> list[dict[str, Any]]:
    grounded: list[dict[str, Any]] = []
    facts = catalog.get("facts_by_ref", {})
    for ref in refs:
        fact = facts.get(ref)
        if not isinstance(fact, dict):
            errors.append(f"UNKNOWN_STRUCTURAL_EVIDENCE_REF:{ref}")
            continue
        if kind and fact.get("kind") != kind:
            errors.append(f"INVALID_STRUCTURAL_EVIDENCE_KIND:{ref}:{fact.get('kind')}")
        if fact.get("freshness") != "CURRENT":
            errors.append(f"STALE_STRUCTURAL_EVIDENCE_REF:{ref}")
        grounded.append(fact)
    return grounded


def detail_field(value: object, field: str, allowed: set[str], catalog: dict[str, Any], decision_evidence: set[str], errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"INVALID_STRUCTURAL_DECISION_DETAIL:{field}")
        value = {}
    classification = str(value.get("classification") or value.get("level") or "").strip().upper()
    if classification not in allowed:
        errors.append(f"INVALID_STRUCTURAL_DECISION_CLASSIFICATION:{field}:{classification or '<empty>'}")
    statement = text_field(value.get("statement") or value.get("reason"), f"{field}.statement", errors)
    refs = refs_field(value.get("evidence_refs", []), f"{field}.evidence_refs", errors, required=False)
    for ref in sorted(set(refs) - decision_evidence):
        errors.append(f"STRUCTURAL_DETAIL_REF_OUTSIDE_DECISION:{field}:{ref}")
    ground_refs(refs, catalog, errors)
    return {"classification": classification, "statement": statement, "evidence_refs": refs}


def alternatives_field(value: object, selected: str, errors: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        errors.append("INVALID_STRUCTURAL_ALTERNATIVES")
        return []
    if len(value) > MAX_ALTERNATIVES:
        errors.append("TOO_MANY_STRUCTURAL_ALTERNATIVES")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value[:MAX_ALTERNATIVES]):
        if not isinstance(item, dict):
            errors.append(f"INVALID_STRUCTURAL_ALTERNATIVE:{index}")
            continue
        action = str(item.get("action") or "").strip().upper()
        if action not in ACTIONS or action == selected:
            errors.append(f"INVALID_STRUCTURAL_ALTERNATIVE_ACTION:{action or '<empty>'}")
        if action in seen:
            errors.append(f"DUPLICATE_STRUCTURAL_ALTERNATIVE:{action}")
        seen.add(action)
        normalized.append({"action": action, "reason": text_field(item.get("reason"), f"alternatives[{index}].reason", errors)})
    return normalized


def validate_action_prerequisites(action: str, claims: set[str], errors: list[str]) -> None:
    for pair in CONTRADICTIONS:
        if pair <= claims:
            errors.append("CONTRADICTORY_STRUCTURAL_EVIDENCE:" + ",".join(sorted(pair)))
    if action == "MODIFY_EXISTING" and not claims & {"COHESIVE_RESPONSIBILITY", "LOCALIZED_CHANGE"}:
        errors.append("MODIFY_EXISTING_COHESIVE_SCOPE_REQUIRED")
    elif action == "INTRODUCE_ABSTRACTION":
        if "DIFFERENT_CHANGE_REASON" in claims or "DIVERGENT_LIFECYCLE" in claims:
            errors.append("ABSTRACTION_BOUNDARY_CONFLICT")
        if "SHARED_INVARIANT" not in claims:
            errors.append("ABSTRACTION_SHARED_INVARIANT_REQUIRED")
        if "MULTIPLE_CONSUMERS_PROVEN" not in claims:
            errors.append("ABSTRACTION_MULTIPLE_CONSUMERS_REQUIRED")
    elif action == "CONSOLIDATE_SIMPLIFY":
        if "DIVERGENT_LIFECYCLE" in claims:
            errors.append("CONSOLIDATION_LIFECYCLE_CONFLICT")
        if "MULTIPLE_ACTIVE_IMPLEMENTATIONS" not in claims:
            errors.append("CONSOLIDATION_ACTIVE_IMPLEMENTATIONS_REQUIRED")
        if "SAME_AUTHORITY" not in claims:
            errors.append("CONSOLIDATION_SAME_AUTHORITY_REQUIRED")
    elif action == "DELETE_SAFELY":
        if claims & {"KNOWN_RUNTIME_CONSUMER", "MULTIPLE_CONSUMERS_PROVEN", "UNKNOWN_RUNTIME_CONSUMER"}:
            errors.append("DELETE_RUNTIME_CONSUMER_NOT_CLOSED")
        if "NO_RUNTIME_CONSUMER_PROVEN" not in claims:
            errors.append("DELETE_NO_CONSUMER_EVIDENCE_REQUIRED")
        if not claims & {"MIGRATION_COMPLETE", "MIGRATION_NOT_APPLICABLE"}:
            errors.append("DELETE_MIGRATION_CLOSURE_REQUIRED")
        if "IRREVERSIBLE" in claims and "ROLLBACK_AVAILABLE" not in claims:
            errors.append("DELETE_IRREVERSIBLE_CONTROL_REQUIRED")


def decision_fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
