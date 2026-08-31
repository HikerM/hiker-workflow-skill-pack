from __future__ import annotations

import re


SCHEMA_VERSION = "hiker-perspective-applicability/v1"
AUTHORITY = "CHATGPT_SEMANTIC_SELECTION"
ARTIFACT_TYPES = {
    "REQUIREMENT",
    "ARCHITECTURE",
    "UI_PROTOTYPE",
    "UI_IMPLEMENTATION",
    "CODE",
    "API",
    "SCHEMA_DATA",
    "TEST",
    "COPY_TEXT",
    "DOCUMENTATION",
    "DEPLOYMENT",
    "OPERATIONS",
    "REFACTORING",
}
MAX_ARTIFACTS = 8
MAX_FACTS_PER_KIND = 16
MAX_PERSPECTIVES = 8
MAX_REFS = 16
MAX_REF_CHARS = 240
MAX_RATIONALE_CHARS = 480
_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._:-]{0,95}")


def not_applicable() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "NOT_APPLICABLE",
        "authority": AUTHORITY,
        "perspectives": [],
    }


def _identifier(value: object, field: str, errors: list[str]) -> str:
    token = str(value or "").strip().lower()
    if not _ID_PATTERN.fullmatch(token):
        errors.append(f"INVALID_PERSPECTIVE_ID:{field}")
    return token


def _refs(value: object, field: str, errors: list[str], *, required: bool = True) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"INVALID_PERSPECTIVE_REFS:{field}")
        return []
    refs = list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
    if required and not refs:
        errors.append(f"MISSING_PERSPECTIVE_REFS:{field}")
    if len(refs) > MAX_REFS:
        errors.append(f"TOO_MANY_PERSPECTIVE_REFS:{field}")
    if any(len(item) > MAX_REF_CHARS for item in refs):
        errors.append(f"OVERSIZED_PERSPECTIVE_REF:{field}")
    return refs[:MAX_REFS]


def _facts(
    value: object,
    field: str,
    errors: list[str],
    *,
    allow_safety_critical: bool = False,
) -> list[dict]:
    if not isinstance(value, list):
        errors.append(f"INVALID_PERSPECTIVE_FACTS:{field}")
        return []
    if len(value) > MAX_FACTS_PER_KIND:
        errors.append(f"TOO_MANY_PERSPECTIVE_FACTS:{field}")
    normalized: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(value[:MAX_FACTS_PER_KIND]):
        if not isinstance(item, dict):
            errors.append(f"INVALID_PERSPECTIVE_FACT:{field}[{index}]")
            continue
        fact_id = _identifier(item.get("id"), f"{field}[{index}].id", errors)
        if fact_id in seen:
            errors.append(f"DUPLICATE_PERSPECTIVE_FACT:{field}:{fact_id}")
        seen.add(fact_id)
        fact = {
            "id": fact_id,
            "fact_refs": _refs(item.get("fact_refs"), f"{field}[{index}].fact_refs", errors),
        }
        if allow_safety_critical:
            critical = item.get("safety_critical", False)
            if type(critical) is not bool:
                errors.append(f"INVALID_SAFETY_CRITICAL:{field}[{index}]")
                critical = False
            fact["safety_critical"] = critical
        normalized.append(fact)
    return normalized


def validate_plan(value: object) -> dict:
    """Validate a model-selected, task-local perspective plan.

    The runtime validates bounded references and safety coverage only. It does
    not infer perspectives from keywords, artifact types, roles, or workflows.
    """
    if value is None:
        return not_applicable()
    if not isinstance(value, dict):
        raise RuntimeError("INVALID_PERSPECTIVE_APPLICABILITY:必须是对象或省略")

    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("INVALID_PERSPECTIVE_SCHEMA_VERSION")
    if value.get("authority") != AUTHORITY:
        errors.append("INVALID_PERSPECTIVE_AUTHORITY")

    artifacts_raw = value.get("artifacts")
    if not isinstance(artifacts_raw, list) or not artifacts_raw:
        errors.append("PERSPECTIVE_ARTIFACT_REQUIRED")
        artifacts_raw = []
    if len(artifacts_raw) > MAX_ARTIFACTS:
        errors.append("TOO_MANY_PERSPECTIVE_ARTIFACTS")
    artifacts: list[dict] = []
    artifact_ids: set[str] = set()
    for index, item in enumerate(artifacts_raw[:MAX_ARTIFACTS]):
        if not isinstance(item, dict):
            errors.append(f"INVALID_PERSPECTIVE_ARTIFACT:{index}")
            continue
        artifact_id = _identifier(item.get("id"), f"artifacts[{index}].id", errors)
        artifact_type = str(item.get("type") or "").strip().upper()
        if artifact_type not in ARTIFACT_TYPES:
            errors.append(f"UNKNOWN_PERSPECTIVE_ARTIFACT_TYPE:{artifact_type or '<empty>'}")
        if artifact_id in artifact_ids:
            errors.append(f"DUPLICATE_PERSPECTIVE_ARTIFACT:{artifact_id}")
        artifact_ids.add(artifact_id)
        artifacts.append({
            "id": artifact_id,
            "type": artifact_type,
            "fact_refs": _refs(item.get("fact_refs"), f"artifacts[{index}].fact_refs", errors),
        })

    actors = _facts(value.get("actors", []), "actors", errors)
    usage_conditions = _facts(value.get("usage_conditions", []), "usage_conditions", errors)
    risk_facts = _facts(value.get("risk_facts", []), "risk_facts", errors, allow_safety_critical=True)
    project_fact_refs = _refs(value.get("project_fact_refs", []), "project_fact_refs", errors, required=False)
    known = {
        "artifact_ids": artifact_ids,
        "actor_ids": {item["id"] for item in actors},
        "usage_condition_ids": {item["id"] for item in usage_conditions},
        "risk_ids": {item["id"] for item in risk_facts},
    }

    raw_perspectives = value.get("perspectives")
    if not isinstance(raw_perspectives, list) or not raw_perspectives:
        errors.append("PERSPECTIVE_SELECTION_REQUIRED")
        raw_perspectives = []
    if len(raw_perspectives) > MAX_PERSPECTIVES:
        errors.append("TOO_MANY_APPLICABLE_PERSPECTIVES")
    perspectives: list[dict] = []
    perspective_ids: set[str] = set()
    covered_risks: set[str] = set()
    for index, item in enumerate(raw_perspectives[:MAX_PERSPECTIVES]):
        if not isinstance(item, dict):
            errors.append(f"INVALID_APPLICABLE_PERSPECTIVE:{index}")
            continue
        perspective_id = _identifier(item.get("id"), f"perspectives[{index}].id", errors)
        if perspective_id in perspective_ids:
            errors.append(f"DUPLICATE_APPLICABLE_PERSPECTIVE:{perspective_id}")
        perspective_ids.add(perspective_id)
        rationale = str(item.get("rationale") or "").strip()
        if not rationale or len(rationale) > MAX_RATIONALE_CHARS:
            errors.append(f"INVALID_PERSPECTIVE_RATIONALE:{perspective_id or index}")
        basis = item.get("basis")
        if not isinstance(basis, dict):
            errors.append(f"INVALID_PERSPECTIVE_BASIS:{perspective_id or index}")
            basis = {}
        normalized_basis: dict[str, list[str]] = {}
        for field in ("artifact_ids", "actor_ids", "usage_condition_ids", "risk_ids"):
            refs = _refs(basis.get(field, []), f"perspectives[{index}].basis.{field}", errors, required=field == "artifact_ids")
            unknown = sorted(set(refs) - known[field])
            for ref in unknown:
                errors.append(f"UNKNOWN_PERSPECTIVE_BASIS:{field}:{ref}")
            normalized_basis[field] = refs
        local_project_refs = _refs(
            basis.get("project_fact_refs", []),
            f"perspectives[{index}].basis.project_fact_refs",
            errors,
            required=False,
        )
        for ref in sorted(set(local_project_refs) - set(project_fact_refs)):
            errors.append(f"UNKNOWN_PERSPECTIVE_PROJECT_FACT_REF:{ref}")
        normalized_basis["project_fact_refs"] = local_project_refs
        if not any(normalized_basis[field] for field in ("actor_ids", "usage_condition_ids", "risk_ids", "project_fact_refs")):
            errors.append(f"PERSPECTIVE_FACTUAL_BASIS_REQUIRED:{perspective_id or index}")
        covered_risks.update(normalized_basis["risk_ids"])
        perspectives.append({
            "id": perspective_id,
            "rationale": rationale,
            "basis": normalized_basis,
            "acceptance_refs": _refs(item.get("acceptance_refs"), f"perspectives[{index}].acceptance_refs", errors),
        })

    missing_critical = sorted(
        item["id"] for item in risk_facts
        if item.get("safety_critical") and item["id"] not in covered_risks
    )
    for risk_id in missing_critical:
        errors.append(f"SAFETY_CRITICAL_PERSPECTIVE_GAP:{risk_id}")
    if errors:
        raise RuntimeError(";".join(errors))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "APPLICABLE",
        "authority": AUTHORITY,
        "artifacts": artifacts,
        "actors": actors,
        "usage_conditions": usage_conditions,
        "risk_facts": risk_facts,
        "project_fact_refs": project_fact_refs,
        "perspectives": perspectives,
    }
