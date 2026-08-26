from __future__ import annotations

import hashlib
import json
from typing import Any


DIMENSIONS = (
    "business_criticality",
    "data_impact",
    "security_impact",
    "reversibility",
    "shared_scope",
    "architecture_impact",
    "runtime_impact",
    "user_visibility",
    "release_impact",
    "evidence_uncertainty",
)
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
LEVEL_VALUE = {name: index for index, name in enumerate(LEVELS)}
EVENTS = {
    "ORDINARY_IMPLEMENTATION",
    "GOAL_CHANGE",
    "ARCHITECTURE_BOUNDARY_CHANGE",
    "SHARED_WRITER_CONFLICT",
    "CANDIDATE_FREEZE",
    "HIGH_RISK_DATA_CHANGE",
    "SECURITY_BOUNDARY",
    "RELEASE",
}
DELIVERY_INTENTS = {"PRODUCTION", "PROTOTYPE", "EXPERIMENTAL", "DEMO"}
BASES = {"MODEL_ASSESSMENT", "PROJECT_FACT", "USER_DECISION", "APPROVED_BASELINE", "UNKNOWN"}
HARD_DIMENSIONS = ("data_impact", "security_impact", "release_impact")
HARD_BOUNDARIES = (
    "SECRETS_AND_PRIVACY",
    "DESTRUCTIVE_OPERATION_AUTHORITY",
    "DATA_INTEGRITY",
    "SECURITY_BOUNDARY",
    "PRODUCTION_RELEASE",
    "STATE_CONSISTENCY",
)
MAX_SCOPE = 64
MAX_REFS = 16
MAX_TEXT = 240
MAX_RUNTIME_TARGETS = 16
VALIDATORS = {
    "DESIGN_FIDELITY",
    "PRESENTATION",
    "CONTENT_STRESS",
    "ERROR_DIAGNOSTIC",
    "INTERACTION",
    "CONTRACT",
    "DATA",
    "SECURITY",
    "RUNTIME",
    "REGRESSION",
    "ARCHITECTURE",
    "RELEASE_GATE",
}
FULL_SCAN_REASONS = {
    "REGISTRY_MISSING",
    "REGISTRY_CORRUPTION",
    "TECHNOLOGY_MIGRATION",
    "MAJOR_COMPONENT_ARCHITECTURE_CHANGE",
    "EXPLICIT_REBUILD",
}
TAX_METRICS = (
    "injected_context_bytes",
    "injected_prompt_bytes",
    "governance_tool_calls",
    "repository_scans",
    "state_reads",
    "state_writes",
    "evidence_writes",
    "screenshots",
    "browser_or_client_launches",
    "review_cycles",
    "validation_cycles",
    "generated_governance_artifacts",
    "runtime_duration_ms",
)


CONTROL_BUDGETS = {
    "LOW": {
        "injected_context_bytes": 2048,
        "injected_prompt_bytes": 0,
        "governance_tool_calls": 2,
        "repository_scans": 1,
        "state_reads": 2,
        "state_writes": 0,
        "evidence_writes": 2,
        "screenshots": 1,
        "browser_or_client_launches": 1,
        "review_cycles": 1,
        "validation_cycles": 1,
        "generated_governance_artifacts": 2,
        "runtime_duration_ms": 2000,
    },
    "MEDIUM": {
        "injected_context_bytes": 8192,
        "injected_prompt_bytes": 0,
        "governance_tool_calls": 8,
        "repository_scans": 2,
        "state_reads": 8,
        "state_writes": 2,
        "evidence_writes": 6,
        "screenshots": 4,
        "browser_or_client_launches": 3,
        "review_cycles": 2,
        "validation_cycles": 3,
        "generated_governance_artifacts": 6,
        "runtime_duration_ms": 10000,
    },
    "HIGH": {
        "injected_context_bytes": 24576,
        "injected_prompt_bytes": 0,
        "governance_tool_calls": 24,
        "repository_scans": 4,
        "state_reads": 24,
        "state_writes": 8,
        "evidence_writes": 16,
        "screenshots": 12,
        "browser_or_client_launches": 8,
        "review_cycles": 2,
        "validation_cycles": 8,
        "generated_governance_artifacts": 16,
        "runtime_duration_ms": 60000,
    },
    "CRITICAL": {
        "injected_context_bytes": 49152,
        "injected_prompt_bytes": 0,
        "governance_tool_calls": 48,
        "repository_scans": 8,
        "state_reads": 48,
        "state_writes": 16,
        "evidence_writes": 32,
        "screenshots": 24,
        "browser_or_client_launches": 16,
        "review_cycles": 2,
        "validation_cycles": 16,
        "generated_governance_artifacts": 32,
        "runtime_duration_ms": 180000,
    },
}

VERIFICATION_LIMITS = {
    "LOW": {"validators": 2, "targets": 1, "states": 1, "environments": 1},
    "MEDIUM": {"validators": 5, "targets": 8, "states": 3, "environments": 2},
    "HIGH": {"validators": 12, "targets": 16, "states": 8, "environments": 8},
    "CRITICAL": {"validators": 12, "targets": 16, "states": 16, "environments": 16},
}


def _bounded_text(value: Any, field: str, errors: list[str], *, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        errors.append(f"{field} is required")
    if len(text) > MAX_TEXT:
        errors.append(f"{field} exceeds {MAX_TEXT} characters")
    return text[:MAX_TEXT]


def _bounded_strings(value: Any, field: str, errors: list[str], limit: int) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    if len(value) > limit:
        errors.append(f"{field} exceeds {limit} items")
    result: list[str] = []
    for index, item in enumerate(value[:limit]):
        text = _bounded_text(item, f"{field}[{index}]", errors)
        if text:
            result.append(text)
    return list(dict.fromkeys(result))


def _validate_runtime_targets(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("runtime_targets must be an array")
        return
    if len(value) > MAX_RUNTIME_TARGETS:
        errors.append(f"runtime_targets exceeds {MAX_RUNTIME_TARGETS} items")
    for index, target in enumerate(value[:MAX_RUNTIME_TARGETS]):
        field = f"runtime_targets[{index}]"
        if not isinstance(target, dict):
            errors.append(f"{field} must be an object")
            continue
        if set(target) - {"surface_id", "states", "environments"}:
            errors.append(f"{field} has unsupported fields")
        _bounded_text(target.get("surface_id"), f"{field}.surface_id", errors)
        _bounded_strings(target.get("states"), f"{field}.states", errors, 16)
        _bounded_strings(target.get("environments"), f"{field}.environments", errors, 16)


def validate_assessment(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["risk assessment must be an object"]
    allowed = {
        "schema_version", "assessment_id", "event_type", "delivery_intent",
        "user_requested_reduction", "affected_scope", "dimensions",
        "affected_capabilities", "requested_validators", "runtime_targets", "full_scan_reason",
        "source_fingerprint", "design_fingerprint", "project_config_fingerprint",
        "technology_fingerprint", "environment_fingerprint", "state_id",
    }
    extras = sorted(set(value) - allowed)
    if extras:
        errors.append(f"unsupported assessment fields: {', '.join(extras)}")
    if value.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    _bounded_text(value.get("assessment_id"), "assessment_id", errors)
    if value.get("event_type") not in EVENTS:
        errors.append("event_type is invalid")
    if value.get("delivery_intent") not in DELIVERY_INTENTS:
        errors.append("delivery_intent is invalid")
    if not isinstance(value.get("user_requested_reduction"), bool):
        errors.append("user_requested_reduction must be boolean")
    if value.get("delivery_intent") == "PRODUCTION" and value.get("user_requested_reduction") is True:
        errors.append("production governance cannot be reduced")
    _bounded_strings(value.get("affected_scope"), "affected_scope", errors, MAX_SCOPE)
    _bounded_strings(value.get("affected_capabilities", []), "affected_capabilities", errors, MAX_REFS)
    validators = _bounded_strings(value.get("requested_validators", []), "requested_validators", errors, len(VALIDATORS))
    unknown_validators = sorted(set(validators) - VALIDATORS)
    if unknown_validators:
        errors.append(f"requested_validators are invalid: {', '.join(unknown_validators)}")
    _validate_runtime_targets(value.get("runtime_targets", []), errors)
    if value.get("full_scan_reason") is not None and value.get("full_scan_reason") not in FULL_SCAN_REASONS:
        errors.append("full_scan_reason is invalid")
    for field in (
        "source_fingerprint", "design_fingerprint", "project_config_fingerprint",
        "technology_fingerprint", "environment_fingerprint", "state_id",
    ):
        _bounded_text(value.get(field), field, errors, required=False)
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, dict):
        errors.append("dimensions must be an object")
        return errors
    missing = sorted(set(DIMENSIONS) - set(dimensions))
    extra_dimensions = sorted(set(dimensions) - set(DIMENSIONS))
    if missing:
        errors.append(f"missing dimensions: {', '.join(missing)}")
    if extra_dimensions:
        errors.append(f"unsupported dimensions: {', '.join(extra_dimensions)}")
    for name in DIMENSIONS:
        item = dimensions.get(name)
        if not isinstance(item, dict):
            continue
        if set(item) - {"level", "basis", "reason", "evidence_refs"}:
            errors.append(f"dimensions.{name} has unsupported fields")
        if item.get("level") not in LEVELS:
            errors.append(f"dimensions.{name}.level is invalid")
        if item.get("basis") not in BASES:
            errors.append(f"dimensions.{name}.basis is invalid")
        _bounded_text(item.get("reason"), f"dimensions.{name}.reason", errors)
        _bounded_strings(item.get("evidence_refs"), f"dimensions.{name}.evidence_refs", errors, MAX_REFS)
    return errors


def _max_level(*levels: str) -> str:
    return max((level for level in levels if level in LEVEL_VALUE), key=LEVEL_VALUE.get, default="LOW")


def _semantic_level(dimensions: dict[str, Any]) -> str:
    values = [LEVEL_VALUE[str(dimensions[name]["level"])] for name in DIMENSIONS]
    if 3 in values:
        return "CRITICAL"
    if 2 in values or values.count(1) >= 3:
        return "HIGH"
    if 1 in values:
        return "MEDIUM"
    return "LOW"


def _artifact_status(intent: str) -> str:
    return {
        "PRODUCTION": "RELEASE_CANDIDATE",
        "PROTOTYPE": "PROTOTYPE",
        "EXPERIMENTAL": "EXPERIMENTAL",
        "DEMO": "NOT_RELEASE_READY",
    }[intent]


def _reuse_key(value: dict[str, Any], level: str) -> str:
    payload = {
        "source_fingerprint": value.get("source_fingerprint"),
        "design_fingerprint": value.get("design_fingerprint"),
        "project_config_fingerprint": value.get("project_config_fingerprint"),
        "technology_fingerprint": value.get("technology_fingerprint"),
        "environment_fingerprint": value.get("environment_fingerprint"),
        "state_id": value.get("state_id"),
        "affected_scope": value.get("affected_scope", []),
        "event_type": value.get("event_type"),
        "risk_level": level,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _control_contract(level: str, activation: str, event_type: str) -> dict[str, Any]:
    evidence = {
        "LOW": ["affected-result"],
        "MEDIUM": ["affected-result", "targeted-tests", "scope-bound-fingerprint"],
        "HIGH": ["affected-result", "targeted-tests", "impact-evidence", "rollback-or-recovery", "independent-assurance"],
        "CRITICAL": ["affected-result", "full-required-tests", "impact-evidence", "rollback-or-recovery", "independent-assurance", "release-evidence"],
    }[level]
    return {
        "preconditions": ["current-goal-and-source-identity", "bounded-affected-scope"],
        "invariants": [*HARD_BOUNDARIES, "USER_LOCKED_DECISIONS", "PROJECT_FACTS", "NO_SECOND_AUTHORITATIVE_WRITER"],
        "required_evidence": evidence if activation != "NONE" else ["affected-result"],
        "acceptance": ["requested-outcome-satisfied", "no-hard-boundary-violation", "evidence-fresh-for-affected-scope"],
        "fixed_steps": [],
        "event": event_type,
    }


def _required_validators(value: dict[str, Any], status: str) -> set[str]:
    required: set[str] = set()
    if status != "VERIFIED":
        return required
    dimensions = value["dimensions"]
    if LEVEL_VALUE[dimensions["data_impact"]["level"]] >= LEVEL_VALUE["HIGH"]:
        required.add("DATA")
    if LEVEL_VALUE[dimensions["security_impact"]["level"]] >= LEVEL_VALUE["HIGH"]:
        required.add("SECURITY")
    if LEVEL_VALUE[dimensions["architecture_impact"]["level"]] >= LEVEL_VALUE["HIGH"]:
        required.add("ARCHITECTURE")
    if LEVEL_VALUE[dimensions["runtime_impact"]["level"]] >= LEVEL_VALUE["HIGH"]:
        required.add("RUNTIME")
    if LEVEL_VALUE[dimensions["user_visibility"]["level"]] >= LEVEL_VALUE["HIGH"]:
        required.add("PRESENTATION")
    if LEVEL_VALUE[dimensions["release_impact"]["level"]] >= LEVEL_VALUE["HIGH"]:
        required.update({"REGRESSION", "RELEASE_GATE"})
    if value.get("event_type") == "RELEASE":
        required.update({"REGRESSION", "RELEASE_GATE"})
    if value.get("event_type") == "ARCHITECTURE_BOUNDARY_CHANGE":
        required.add("ARCHITECTURE")
    return required


def _verification_budget(value: dict[str, Any], status: str, control_level: str) -> dict[str, Any]:
    limits = VERIFICATION_LIMITS[control_level]
    requested = list(dict.fromkeys(value.get("requested_validators", [])))
    validators = sorted(set(requested) | _required_validators(value, status))
    runtime_targets = list(value.get("runtime_targets", []))[:MAX_RUNTIME_TARGETS]
    state_count = sum(len(target.get("states", [])) for target in runtime_targets if isinstance(target, dict))
    environment_count = sum(len(target.get("environments", [])) for target in runtime_targets if isinstance(target, dict))
    blockers: list[str] = []
    if len(validators) > limits["validators"]:
        blockers.append("requested validators exceed the risk-proportionate budget")
    if len(runtime_targets) > limits["targets"]:
        blockers.append("runtime targets exceed the risk-proportionate budget")
    if state_count > limits["states"]:
        blockers.append("runtime states exceed the risk-proportionate budget")
    if environment_count > limits["environments"]:
        blockers.append("runtime environments exceed the risk-proportionate budget")
    full_scan_reason = value.get("full_scan_reason")
    architecture_review = (
        value.get("event_type") == "ARCHITECTURE_BOUNDARY_CHANGE"
        or "ARCHITECTURE" in validators
    )
    release_matrix = value.get("event_type") == "RELEASE" and control_level == "CRITICAL"
    return {
        "status": "REQUIRES_RECLASSIFICATION" if blockers else "PASS",
        "blockers": blockers,
        "affected_capabilities": list(dict.fromkeys(value.get("affected_capabilities", [])))[:MAX_REFS],
        "authorized_validators": validators,
        "runtime_targets": runtime_targets,
        "limits": dict(limits),
        "runtime_mode": "RELEASE_MATRIX" if release_matrix else "TARGETED" if runtime_targets else "NONE",
        "visual_matrix": "RELEASE_REQUIRED" if release_matrix else "TARGETED_ONLY",
        "regression": (
            "RELEASE_REQUIRED" if release_matrix else
            "EXPANDED_AFFECTED" if control_level in {"HIGH", "CRITICAL"} else
            "TARGETED"
        ),
        "architecture_review": architecture_review,
        "independent_review": control_level in {"HIGH", "CRITICAL"},
        "full_repository_scan": {
            "allowed": full_scan_reason in FULL_SCAN_REASONS,
            "reason": full_scan_reason,
            "allowed_reasons": sorted(FULL_SCAN_REASONS),
        },
        "runtime_reuse_required": True,
        "unrelated_scope_reopen": False,
    }


def authorize(profile: dict[str, Any], action: str, validator: str | None = None) -> dict[str, Any]:
    budget = profile.get("verification_budget", {})
    if budget.get("status") != "PASS":
        return {"allowed": False, "reason": "verification budget requires risk reclassification"}
    if action == "FULL_PROJECT_SCAN":
        allowed = budget.get("full_repository_scan", {}).get("allowed") is True
    elif action == "FULL_VISUAL_MATRIX":
        allowed = budget.get("visual_matrix") == "RELEASE_REQUIRED"
    elif action == "ARCHITECTURE_REVIEW":
        allowed = budget.get("architecture_review") is True
    elif action == "INDEPENDENT_REVIEW":
        allowed = budget.get("independent_review") is True
    elif action == "VALIDATOR":
        allowed = validator in set(budget.get("authorized_validators", []))
    elif action in {"TARGETED_RUNTIME", "TARGETED_EVIDENCE", "TARGETED_REGRESSION"}:
        allowed = True
    else:
        return {"allowed": False, "reason": "unknown verification action"}
    return {
        "allowed": allowed,
        "reason": "authorized by the current verification budget" if allowed else "outside the current verification budget",
    }


def assess(
    value: dict[str, Any] | None,
    *,
    observed_level: str = "LOW",
    observed_tags: list[str] | None = None,
) -> dict[str, Any]:
    observed = observed_level if observed_level in LEVEL_VALUE else "HIGH"
    tags = set(observed_tags or [])
    if value is None:
        value = {
            "event_type": "ORDINARY_IMPLEMENTATION",
            "delivery_intent": "PRODUCTION",
            "user_requested_reduction": False,
            "affected_scope": [],
        }
        status, errors, semantic = "NOT_PROVIDED", [], "UNKNOWN"
        effective = observed
        hard_floor = "HIGH" if tags & {"database", "security", "release"} else "LOW"
    else:
        errors = validate_assessment(value)
        status = "INVALID" if errors else "VERIFIED"
        semantic = _semantic_level(value["dimensions"]) if not errors else "UNKNOWN"
        effective = _max_level(observed, semantic, "HIGH" if errors else "LOW")
        hard_floor = _max_level(
            *(str(value["dimensions"][name]["level"]) for name in HARD_DIMENSIONS)
        ) if not errors else "HIGH"
        if tags & {"database", "security", "release"}:
            hard_floor = _max_level(hard_floor, "HIGH")
    intent_candidate = str(value.get("delivery_intent") or "PRODUCTION")
    intent = intent_candidate if intent_candidate in DELIVERY_INTENTS else "PRODUCTION"
    requested_reduction = value.get("user_requested_reduction") is True
    control_level = effective
    if status == "VERIFIED" and intent != "PRODUCTION" and requested_reduction:
        non_safety_floor = "MEDIUM" if LEVEL_VALUE[effective] >= LEVEL_VALUE["HIGH"] else "LOW"
        control_level = _max_level(hard_floor, non_safety_floor)
    event_candidate = str(value.get("event_type") or "ORDINARY_IMPLEMENTATION")
    event_type = event_candidate if event_candidate in EVENTS else "ORDINARY_IMPLEMENTATION"
    requested_verification = bool(
        value.get("requested_validators")
        or value.get("runtime_targets")
        or value.get("full_scan_reason")
    )
    if control_level in {"HIGH", "CRITICAL"}:
        activation = "GOVERNED"
    elif event_type == "ORDINARY_IMPLEMENTATION" and control_level == "LOW" and not requested_verification:
        activation = "NONE"
    else:
        activation = "TARGETED"
    budget = {name: 0 for name in TAX_METRICS} if activation == "NONE" else dict(CONTROL_BUDGETS[control_level])
    scope_mode = "NONE" if activation == "NONE" else "AFFECTED_SCOPE" if event_type != "RELEASE" else "RELEASE_SCOPE"
    verification_budget = _verification_budget(value, status, control_level)
    requires_review = status == "INVALID" or verification_budget["status"] != "PASS"
    return {
        "schema_version": "1.0.0",
        "status": status,
        "errors": errors,
        "observed_level": observed,
        "semantic_level": semantic,
        "risk_level": effective,
        "control_level": control_level,
        "event_type": event_type,
        "delivery_intent": intent,
        "artifact_status": _artifact_status(intent),
        "release_ready": intent == "PRODUCTION" and not requires_review,
        "activation": activation,
        "scope_mode": scope_mode,
        "requested_verification": requested_verification,
        "affected_scope": list(dict.fromkeys(value.get("affected_scope", [])))[:MAX_SCOPE],
        "dimensions": {
            name: {
                "level": value["dimensions"][name]["level"],
                "basis": value["dimensions"][name]["basis"],
                "reason": value["dimensions"][name]["reason"][:MAX_TEXT],
                "evidence_refs": value["dimensions"][name]["evidence_refs"][:MAX_REFS],
            }
            for name in DIMENSIONS
        } if status == "VERIFIED" else {},
        "decision": "REQUIRES_REVIEW" if requires_review else "ALLOW_WITH_PROFILE",
        "model_freedom": {
            "reasoning_path": "MODEL_DECIDES",
            "implementation_order": "MODEL_DECIDES",
            "code_organization": "PROJECT_NATIVE",
            "design_solution": "MODEL_DECIDES_WITHIN_AUTHORITIES",
            "diagnostic_method": "MODEL_DECIDES",
            "tool_choice": "MODEL_DECIDES_WITHIN_PERMISSIONS",
        },
        "contract": _control_contract(control_level, activation, event_type),
        "evidence_policy": {
            "qualities": ["SUFFICIENT", "FRESH", "SCOPE_BOUND", "RISK_PROPORTIONATE"],
            "reuse": "REUSE_IF_FINGERPRINT_STATE_AND_SCOPE_MATCH",
            "reuse_key": _reuse_key(value, effective),
            "cold_history_scan": False,
        },
        "review_policy": {
            "depth": {"NONE": "NONE", "TARGETED": "TARGETED", "GOVERNED": "INDEPENDENT"}[activation],
            "max_cycles_without_new_risk_or_business_evidence": 0 if activation == "NONE" else 1,
        },
        "verification_budget": verification_budget,
        "hard_boundaries": list(HARD_BOUNDARIES),
        "governance_tax_budget": budget,
    }


def evaluate_tax(profile: dict[str, Any], observed: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    normalized: dict[str, float] = {}
    normalized_baseline: dict[str, float] = {}
    budget = profile.get("governance_tax_budget", {})
    for metric in TAX_METRICS:
        current = observed.get(metric, 0)
        previous = baseline.get(metric, 0)
        if not isinstance(current, (int, float)) or current < 0:
            errors.append(f"{metric} must be a non-negative number")
            current = 0
        if not isinstance(previous, (int, float)) or previous < 0:
            errors.append(f"baseline {metric} must be a non-negative number")
            previous = 0
        normalized[metric] = current
        normalized_baseline[metric] = previous
        if current > float(budget.get(metric, 0)):
            errors.append(f"{metric} exceeds governance tax budget")
    delta = {metric: normalized[metric] - normalized_baseline[metric] for metric in TAX_METRICS}
    if profile.get("activation") == "NONE" and any(value > 0 for value in delta.values()):
        errors.append("inactive sparse governance added cost to the simple-task baseline")
    return {
        "ok": not errors,
        "risk_level": profile.get("risk_level"),
        "activation": profile.get("activation"),
        "baseline": normalized_baseline,
        "observed": normalized,
        "delta": delta,
        "budget": budget,
        "errors": errors,
    }
