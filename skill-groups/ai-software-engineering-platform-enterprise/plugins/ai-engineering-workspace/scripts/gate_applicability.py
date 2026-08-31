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
EXECUTABLE_STATUSES = {"REQUIRED", "NOT_APPLICABLE"}
AUTHORITIES = {
    "CHATGPT_SEMANTIC_SELECTION",
    "USER_EXPLICIT_CONSTRAINT",
    "RUNTIME_LEGACY_COMPATIBILITY",
}
RISK_CLASSES = {"local", "bounded", "structural"}
BASIS_FIELDS = {
    "repository_change",
    "runtime_change",
    "architecture_impact",
    "shared_scope",
    "release_impact",
    "merge_required",
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
    return {
        "schema_version": SCHEMA,
        "authority": "RUNTIME_LEGACY_COMPATIBILITY",
        "task_intent_fingerprint": fingerprint(task_goal),
        "deliverable_fingerprint": fingerprint("compatibility-all-required"),
        "risk_class": "structural",
        "basis": {
            "architecture_impact": True,
            "release_impact": True,
            "repository_change": True,
            "runtime_change": True,
            "shared_scope": True,
            "merge_required": True,
        },
        "gates": {
            name: {"status": "REQUIRED", "reason_code": "COMPATIBILITY_FAIL_CLOSED"}
            for name in GATES
        },
    }


def _required_gates(risk_class: str, basis: dict[str, bool]) -> set[str]:
    """Project explicit work into required gates without inventing absent work."""
    required: set[str] = set()
    if basis.get("repository_change"):
        required.add("development")
    if basis.get("runtime_change"):
        required.update({"development", "testing"})
    if basis.get("architecture_impact"):
        required.update({"planning", "architecture", "review", "testing", "documentation"})
    if basis.get("shared_scope"):
        required.update({"planning", "review", "testing"})
    if basis.get("release_impact"):
        required.update({"review", "testing", "documentation", "release"})
    if basis.get("merge_required"):
        required.add("merge")

    work_exists = any(basis.values())
    if work_exists and risk_class == "bounded":
        required.add("review")
    elif work_exists and risk_class == "structural":
        required.update({"review", "testing"})
    return required


def plan_from_model_proposal(task_goal: str, proposal: dict[str, Any]) -> dict[str, Any]:
    """Build a machine-valid plan only from the model's structured work facts."""
    lanes = proposal.get("implementation_lanes")
    lanes = lanes if isinstance(lanes, list) else []
    risk_class = str(proposal.get("risk_class") or "bounded").lower()
    basis = {
        "repository_change": bool(proposal.get("repository_change")) or bool(lanes),
        "runtime_change": bool(proposal.get("runtime_change")),
        "architecture_impact": bool(proposal.get("architecture_impact")),
        "shared_scope": bool(proposal.get("shared_scope")) or proposal.get("contract_change") is True,
        "release_impact": bool(proposal.get("release_impact")),
        "merge_required": bool(proposal.get("merge_required")),
    }
    required = _required_gates(risk_class, basis)
    deliverable = json.dumps(
        {"basis": basis, "lanes": lanes, "risk_class": risk_class},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return validate_plan({
        "schema_version": SCHEMA,
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "task_intent_fingerprint": fingerprint(task_goal),
        "deliverable_fingerprint": fingerprint(deliverable),
        "risk_class": risk_class,
        "basis": basis,
        "gates": {
            name: {
                "status": "REQUIRED" if name in required else "NOT_APPLICABLE",
                "reason_code": "MODEL_STRUCTURED_WORK" if name in required else "NO_STRUCTURED_WORK_FACT",
            }
            for name in GATES
        },
    }, task_goal=task_goal)


def plan_from_change_contract(
    task_goal: str,
    change_contract: dict[str, Any],
    *,
    risk_class: str = "local",
    merge_required: bool = False,
) -> dict[str, Any]:
    """Project a CONTROL-authored structured contract; never inspect prose keywords."""
    scope = list(change_contract.get("allowed_files") or []) + list(change_contract.get("allowed_modules") or [])
    return plan_from_model_proposal(task_goal, {
        "risk_class": risk_class,
        "repository_change": bool(scope),
        "runtime_change": bool(
            change_contract.get("required_tests")
            or change_contract.get("characterization_tests")
            or change_contract.get("consumer_tests")
        ),
        "architecture_impact": bool(change_contract.get("structural_decisions")),
        "shared_scope": bool(change_contract.get("public_contract_changes") or change_contract.get("consumers")),
        "release_impact": False,
        "merge_required": merge_required,
        "implementation_lanes": [{"scope": item} for item in scope],
    })


def resolve_plan_input(
    root: Path,
    *,
    task_goal: str,
    change_contract: dict[str, Any],
    raw_plan: dict[str, Any] | None = None,
    plan_file: str | None = None,
) -> dict[str, Any] | None:
    """Load one bounded semantic plan source without widening Task-writer duties."""
    if raw_plan is not None and plan_file:
        raise RuntimeError("one semantic gate plan source is allowed")
    if plan_file:
        path = Path(plan_file)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError("gate applicability plan must remain inside the project root") from exc
        raw_plan = load_plan(path)
    if raw_plan is None:
        return None
    if not isinstance(raw_plan, dict):
        raise RuntimeError("gate applicability plan must be a JSON object")
    return validate_plan(raw_plan, task_goal=task_goal, change_contract=change_contract)


def plan_from_pending_contract(
    task: dict[str, Any],
    change_contract: dict[str, Any],
    *,
    risk_class: str | None = None,
    merge_required: bool | None = None,
) -> dict[str, Any]:
    """Resolve a new task at Planning from structured scope and integration facts."""
    integration_required = (
        bool(merge_required)
        if merge_required is not None
        else bool(
            (change_contract.get("allowed_files") or change_contract.get("allowed_modules"))
            and task.get("branch")
            and task.get("base_branch")
            and task.get("branch") != task.get("base_branch")
        )
    )
    return plan_from_change_contract(
        str(task.get("goal") or ""),
        change_contract,
        risk_class=str(risk_class or "local"),
        merge_required=integration_required,
    )


def resolve_existing_or_pending_plan(
    task: dict[str, Any],
    change_contract: dict[str, Any],
    *,
    risk_class: str | None = None,
    merge_required: bool | None = None,
) -> tuple[dict[str, Any], str]:
    plan = task.get("gate_applicability")
    if not isinstance(plan, dict) and task.get("gate_plan_origin") == "NEW_TASK_MODEL_PLAN_PENDING":
        return plan_from_pending_contract(
            task, change_contract, risk_class=risk_class, merge_required=merge_required,
        ), "MODEL_STRUCTURED_CONTRACT"
    gates = plan.get("gates") if isinstance(plan, dict) else None
    is_legacy_compatibility = (
        isinstance(gates, dict)
        and set(gates) == set(GATES)
        and all(
            isinstance(item, dict) and item.get("reason_code") == "COMPATIBILITY_FAIL_CLOSED"
            for item in gates.values()
        )
    )
    if not isinstance(plan, dict) or is_legacy_compatibility:
        plan = default_plan(str(task.get("goal") or ""), change_contract)
        return validate_plan(plan, task_goal=str(task.get("goal") or ""), change_contract=change_contract), "LEGACY_FAIL_CLOSED"
    return validate_plan(
        plan, task_goal=str(task.get("goal") or ""), change_contract=change_contract,
    ), str(task.get("gate_plan_origin") or "MODEL_SEMANTIC_SELECTION")


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
        if status == "CONDITIONAL":
            errors.append(f"UNRESOLVED_CONDITIONAL_CANNOT_EXECUTE:{name}")
        elif status not in EXECUTABLE_STATUSES:
            errors.append(f"INVALID_GATE_STATUS:{name}")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", reason_code):
            errors.append(f"INVALID_GATE_REASON:{name}")
        normalized_gates[name] = {"status": status, "reason_code": reason_code}

    required = _required_gates(risk_class, basis)
    if basis.get("merge_required") and not basis.get("repository_change"):
        errors.append("MERGE_REQUIRES_REPOSITORY_CHANGE")
    if normalized_gates.get("merge", {}).get("status") == "REQUIRED" and not basis.get("merge_required"):
        errors.append("MERGE_GATE_REQUIRES_INTEGRATION_FACT")

    if change_contract is not None and authority != "RUNTIME_LEGACY_COMPATIBILITY":
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
        if task.get("gate_plan_origin") == "NEW_TASK_MODEL_PLAN_PENDING":
            raise RuntimeError("NORMAL_NEW_TASK_REQUIRES_SEMANTIC_GATE_PLAN")
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
    return plan_for(task)["gates"][gate]["status"] == "REQUIRED"


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
    if not isinstance(task.get("gate_applicability"), dict) and task.get("gate_plan_origin") == "NEW_TASK_MODEL_PLAN_PENDING":
        if current == "Created" and target == "Planning":
            return []
        raise RuntimeError("NORMAL_NEW_TASK_REQUIRES_SEMANTIC_GATE_PLAN")
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
