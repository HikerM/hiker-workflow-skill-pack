from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "hiker-gate-applicability/v1"
GATES = (
    "planning",
    "development",
    "architecture",
    "review",
    "testing",
    "documentation",
    "merge",
    "release",
)
STATUSES = {"REQUIRED", "CONDITIONAL", "NOT_APPLICABLE"}
AUTHORITIES = {"CHATGPT_SEMANTIC_SELECTION", "USER_EXPLICIT_CONSTRAINT"}
RISK_CLASSES = {"local", "bounded", "structural"}
BASIS_FIELDS = {
    "repository_change",
    "runtime_change",
    "architecture_impact",
    "shared_scope",
    "release_impact",
}
STATE_GATES = {
    "Planning": "planning",
    "Development": "development",
    "Review": "review",
    "Testing": "testing",
    "MergedPendingCleanup": "merge",
    "Merged": "merge",
    "Released": "release",
}
STATE_ORDER = (
    "Created",
    "Planning",
    "Development",
    "Review",
    "Testing",
    "MergedPendingCleanup",
    "Merged",
    "Released",
)


def fingerprint(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def default_plan(task_goal: str = "", change_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed compatibility for tasks created before applicability existed."""
    contract = change_contract or {}
    return {
        "schema_version": SCHEMA,
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "task_intent_fingerprint": fingerprint(task_goal),
        "deliverable_fingerprint": fingerprint("compatibility-all-required"),
        "risk_class": "structural",
        "basis": {
            "architecture_impact": bool(contract.get("structural_decisions")),
            "release_impact": False,
            "repository_change": bool(contract.get("allowed_files") or contract.get("allowed_modules")),
            "runtime_change": bool(contract.get("required_tests") or contract.get("characterization_tests") or contract.get("consumer_tests")),
            "shared_scope": bool(contract.get("public_contract_changes") or contract.get("consumers")),
        },
        "gates": {
            name: {"status": "REQUIRED", "reason_code": "COMPATIBILITY_FAIL_CLOSED"}
            for name in GATES
        },
    }


def load_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"gate applicability plan is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("gate applicability plan must be a JSON object")
    return value


def validate_plan(
    plan: dict[str, Any],
    *,
    task_goal: str | None = None,
    change_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate ChatGPT's semantic classification without inferring from keywords."""
    errors: list[str] = []
    if plan.get("schema_version") != SCHEMA:
        errors.append("UNKNOWN_GATE_APPLICABILITY_SCHEMA")
    authority = str(plan.get("authority") or "")
    if authority not in AUTHORITIES:
        errors.append("INVALID_GATE_APPLICABILITY_AUTHORITY")
    risk_class = str(plan.get("risk_class") or "").lower()
    if risk_class not in RISK_CLASSES:
        errors.append("INVALID_GATE_RISK_CLASS")
    intent_fingerprint = str(plan.get("task_intent_fingerprint") or "").lower()
    deliverable_fingerprint = str(plan.get("deliverable_fingerprint") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", intent_fingerprint):
        errors.append("INVALID_TASK_INTENT_FINGERPRINT")
    elif task_goal is not None and intent_fingerprint != fingerprint(task_goal):
        errors.append("STALE_TASK_INTENT_FINGERPRINT")
    if not re.fullmatch(r"[0-9a-f]{64}", deliverable_fingerprint):
        errors.append("INVALID_DELIVERABLE_FINGERPRINT")

    basis = plan.get("basis")
    if not isinstance(basis, dict) or set(basis) != BASIS_FIELDS:
        errors.append("INVALID_GATE_APPLICABILITY_BASIS")
        basis = {}
    elif any(type(basis.get(name)) is not bool for name in BASIS_FIELDS):
        errors.append("NON_BOOLEAN_GATE_APPLICABILITY_BASIS")

    raw_gates = plan.get("gates")
    normalized_gates: dict[str, dict[str, str]] = {}
    if not isinstance(raw_gates, dict) or set(raw_gates) != set(GATES):
        errors.append("INCOMPLETE_GATE_APPLICABILITY")
        raw_gates = {}
    for name in GATES:
        item = raw_gates.get(name)
        if not isinstance(item, dict):
            errors.append(f"INVALID_GATE:{name}")
            continue
        status = str(item.get("status") or "")
        reason_code = str(item.get("reason_code") or "")
        if status not in STATUSES:
            errors.append(f"INVALID_GATE_STATUS:{name}")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", reason_code):
            errors.append(f"INVALID_GATE_REASON:{name}")
        normalized_gates[name] = {"status": status, "reason_code": reason_code}

    required: set[str] = set()
    if risk_class == "structural":
        required.update(GATES)
    if basis.get("repository_change"):
        required.update({"development", "merge"})
    if basis.get("runtime_change"):
        required.add("testing")
    if basis.get("architecture_impact"):
        required.update({"planning", "architecture", "review", "testing", "documentation"})
    if basis.get("shared_scope"):
        required.update({"planning", "review", "testing"})
    if basis.get("release_impact"):
        required.update({"review", "testing", "documentation", "release"})

    if change_contract is not None:
        has_scope = bool(change_contract.get("allowed_files") or change_contract.get("allowed_modules"))
        has_tests = bool(
            change_contract.get("required_tests")
            or change_contract.get("characterization_tests")
            or change_contract.get("consumer_tests")
        )
        has_shared_scope = bool(change_contract.get("public_contract_changes") or change_contract.get("consumers"))
        has_architecture = bool(change_contract.get("structural_decisions"))
        if has_scope and not basis.get("repository_change"):
            errors.append("REPOSITORY_SCOPE_REQUIRES_REPOSITORY_CHANGE")
        if basis.get("repository_change") and not has_scope:
            errors.append("REPOSITORY_CHANGE_REQUIRES_BOUNDED_SCOPE")
        if has_tests:
            required.add("testing")
        if has_shared_scope:
            required.update({"planning", "review", "testing"})
            if not basis.get("shared_scope"):
                errors.append("SHARED_CONTRACT_REQUIRES_SHARED_SCOPE")
        if has_architecture:
            required.update({"planning", "architecture", "review", "testing", "documentation"})
            if not basis.get("architecture_impact"):
                errors.append("STRUCTURAL_DECISION_REQUIRES_ARCHITECTURE_IMPACT")

    for name in sorted(required):
        if normalized_gates.get(name, {}).get("status") != "REQUIRED":
            errors.append(f"REQUIRED_GATE_CANNOT_BE_SKIPPED:{name}")
    if errors:
        raise RuntimeError("invalid gate applicability: " + "; ".join(errors))

    return {
        "schema_version": SCHEMA,
        "authority": authority,
        "task_intent_fingerprint": intent_fingerprint,
        "deliverable_fingerprint": deliverable_fingerprint,
        "risk_class": risk_class,
        "basis": {name: bool(basis[name]) for name in sorted(BASIS_FIELDS)},
        "gates": {name: normalized_gates[name] for name in GATES},
    }


def plan_for(task: dict[str, Any]) -> dict[str, Any]:
    plan = task.get("gate_applicability")
    if not isinstance(plan, dict):
        plan = default_plan(str(task.get("goal") or ""), task.get("change_contract") or {})
    elif set((plan.get("gates") or {}).keys()) == set(GATES) and all(
        isinstance(item, dict) and item.get("reason_code") == "COMPATIBILITY_FAIL_CLOSED"
        for item in (plan.get("gates") or {}).values()
    ):
        plan = default_plan(str(task.get("goal") or ""), task.get("change_contract") or {})
    try:
        return validate_plan(plan, task_goal=str(task.get("goal") or ""), change_contract=task.get("change_contract") or {})
    except RuntimeError as exc:
        raise RuntimeError(f"task gate applicability is unsafe: {exc}") from exc


def gate_required(task: dict[str, Any], gate: str) -> bool:
    if gate not in GATES:
        raise RuntimeError(f"unknown lifecycle gate: {gate}")
    return plan_for(task)["gates"][gate]["status"] != "NOT_APPLICABLE"


def last_applicable_state(task: dict[str, Any], before_gate: str) -> str:
    sequences = {
        "merge": (("planning", "Planning"), ("development", "Development"), ("review", "Review"), ("testing", "Testing")),
        "release": (("planning", "Planning"), ("development", "Development"), ("review", "Review"), ("testing", "Testing"), ("merge", "Merged")),
    }
    if before_gate not in sequences:
        raise RuntimeError(f"unsupported lifecycle boundary: {before_gate}")
    state = "Created"
    for gate, candidate in sequences[before_gate]:
        if gate_required(task, gate):
            state = candidate
    return state


def transition_path(task: dict[str, Any], current: str, target: str, legacy_targets: set[str]) -> list[str]:
    """Return skipped states; legacy adjacent/rework transitions remain compatible."""
    if target in legacy_targets:
        return []
    if current not in STATE_ORDER or target not in STATE_ORDER:
        raise RuntimeError(f"invalid transition: {current} -> {target}")
    current_index = STATE_ORDER.index(current)
    target_index = STATE_ORDER.index(target)
    if target_index <= current_index:
        raise RuntimeError(f"invalid transition: {current} -> {target}")
    plan = plan_for(task)
    skipped = list(STATE_ORDER[current_index + 1:target_index])
    for state in skipped:
        gate = STATE_GATES.get(state)
        if gate and plan["gates"][gate]["status"] != "NOT_APPLICABLE":
            raise RuntimeError(f"required lifecycle gate cannot be skipped: {gate}")
    target_gate = STATE_GATES.get(target)
    if target_gate and plan["gates"][target_gate]["status"] == "NOT_APPLICABLE":
        if target != "Released":
            raise RuntimeError(f"cannot transition into a non-applicable lifecycle gate: {target_gate}")
        remaining = STATE_ORDER[current_index + 1:]
        if any(
            STATE_GATES.get(state)
            and plan["gates"][STATE_GATES[state]]["status"] != "NOT_APPLICABLE"
            for state in remaining
        ):
            raise RuntimeError("cannot close task while a required lifecycle gate remains")
    return skipped
