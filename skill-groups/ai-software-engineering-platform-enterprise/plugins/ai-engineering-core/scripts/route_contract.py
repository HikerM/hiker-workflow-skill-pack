from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Iterable


INTENT_STATES = {
    "CURRENT",
    "NEGATED",
    "CONDITIONAL",
    "HISTORICAL",
    "RESOLVED",
    "FUTURE",
    "HYPOTHETICAL",
    "DEFERRED",
}
AMBIGUITY_POLICIES = {"SAFE_INFERENCE", "EVIDENCE_FIRST", "ASK_REQUIRED", "BLOCK"}
ROUTING_COSTS = {"FAST", "STANDARD", "DEEP"}
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

CAPABILITY_FAMILIES: dict[str, tuple[str, ...]] = {
    "frontend": (
        "web-ui-design", "web-component-implementation", "web-quality-review",
        "interaction-conflict-governance", "regression-test-planner",
    ),
    "backend": (
        "backend-technology-router", "api-event-contract-design", "backend-component-implementation",
        "database-migration-governance", "backend-quality-review", "full-change-risk-review",
    ),
    "database": (
        "database-migration-governance", "api-event-contract-design", "backend-component-implementation",
        "backend-quality-review", "regression-test-planner",
    ),
    "client": (
        "cs-client-router", "cs-ui-design", "cs-component-implementation", "cs-quality-review",
        "regression-test-planner",
    ),
    "unity": (
        "unity-ui-design", "unity-component-implementation", "unity-quality-review",
        "regression-test-planner",
    ),
    "workspace": (
        "project-state-manager", "task-lifecycle-manager", "workspace-task-router",
        "multi-agent-project-governance", "long-chain-change-convergence", "worktree-safe-convergence",
    ),
    "quality": (
        "design-readiness-review", "full-change-risk-review", "regression-test-planner",
        "feature-acceptance-closure", "release-readiness-review",
    ),
    "architecture": (
        "architecture-decision-challenge", "brownfield-requirement-reconciliation",
        "api-event-contract-design", "full-change-risk-review",
    ),
}


def _bounded_strings(raw: Any, limit: int = 16, max_chars: int = 200) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip()[:max_chars] for item in raw[:limit] if str(item).strip()]


def _scopes(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    aliases = {
        "web": "frontend",
        "bs": "fullstack",
        "api": "backend",
        "service": "backend",
        "server": "backend",
        "db": "database",
        "cs": "client",
        "desktop": "client",
    }
    values: list[str] = []
    for item in raw[:12]:
        value = str(item).strip().lower().replace("_", "-")
        value = aliases.get(value, value)
        if value and value not in values:
            values.append(value)
    return values


def _risk(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        level = raw.strip().upper()
        return {"level": level if level in RISK_LEVELS else "MEDIUM", "signals": []}
    if not isinstance(raw, dict):
        return {"level": "LOW", "signals": []}
    level = str(raw.get("level") or "LOW").strip().upper()
    return {
        "level": level if level in RISK_LEVELS else "MEDIUM",
        "signals": _bounded_strings(raw.get("signals"), 12, 80),
        "reversible": bool(raw.get("reversible", True)),
    }


def _intent_atom(raw: Any, index: int, state: str | None = None) -> dict[str, Any] | None:
    if isinstance(raw, str):
        return {
            "id": f"I{index}",
            "state": state or "CURRENT",
            "operation": raw.strip()[:200],
            "target": "current_project",
            "dependencies": [],
            "capability_family": None,
            "candidate_capabilities": [],
        } if raw.strip() else None
    if not isinstance(raw, dict):
        return None
    intent_state = str(raw.get("state") or state or "CURRENT").strip().upper()
    return {
        "id": str(raw.get("id") or f"I{index}").strip()[:48],
        "state": intent_state,
        "operation": str(raw.get("operation") or raw.get("action") or "").strip()[:200],
        "target": str(raw.get("target") or "current_project").strip()[:160],
        "dependencies": _bounded_strings(raw.get("dependencies"), 12, 48),
        "capability_family": str(raw.get("capability_family") or "").strip().lower() or None,
        "candidate_capabilities": _bounded_strings(raw.get("candidate_capabilities"), 6, 80),
    }


def _intent_atoms(proposal: dict[str, Any], current_action: str) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    raw_atoms = proposal.get("intent_atoms")
    if isinstance(raw_atoms, list):
        for item in raw_atoms[:24]:
            atom = _intent_atom(item, len(atoms) + 1)
            if atom:
                atoms.append(atom)
    if not atoms:
        atoms.append({
            "id": "I1",
            "state": "CURRENT",
            "operation": str(proposal.get("operation") or current_action or "project_action")[:200],
            "target": str(proposal.get("target") or "current_project")[:160],
            "dependencies": [],
            "capability_family": str(proposal.get("intent_family") or "").strip().lower() or None,
            "candidate_capabilities": [],
        })
    categories = (
        ("negative_intents", "NEGATED"),
        ("negated_terms", "NEGATED"),
        ("conditional_intents", "CONDITIONAL"),
        ("historical_intents", "HISTORICAL"),
        ("future_intents", "FUTURE"),
        ("future_terms", "FUTURE"),
        ("deferred_intents", "DEFERRED"),
    )
    for field, state in categories:
        raw = proposal.get(field)
        if not isinstance(raw, list):
            continue
        for item in raw[:12]:
            atom = _intent_atom(item, len(atoms) + 1, state)
            if atom:
                atoms.append(atom)
    return atoms[:24]


def _validate_dag(atoms: list[dict[str, Any]]) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    ids = [atom["id"] for atom in atoms]
    if len(ids) != len(set(ids)):
        diagnostics.append({"code": "DUPLICATE_INTENT_ID", "message": "Intent Atom ID必须唯一"})
        return diagnostics
    graph = {atom["id"]: list(atom["dependencies"]) for atom in atoms}
    for atom in atoms:
        if atom["state"] not in INTENT_STATES:
            diagnostics.append({"code": "INVALID_INTENT_STATE", "message": f"未知Intent状态：{atom['state']}"})
        for dependency in atom["dependencies"]:
            if dependency not in graph:
                diagnostics.append({"code": "UNKNOWN_INTENT_DEPENDENCY", "message": f"Intent依赖不存在：{dependency}"})
    indegree = {key: 0 for key in graph}
    consumers: dict[str, list[str]] = {key: [] for key in graph}
    for child, dependencies in graph.items():
        for parent in dependencies:
            if parent in graph:
                indegree[child] += 1
                consumers[parent].append(child)
    queue = deque(key for key, value in indegree.items() if value == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for consumer in consumers[current]:
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                queue.append(consumer)
    if visited != len(graph):
        diagnostics.append({"code": "INTENT_DAG_CYCLE", "message": "Intent依赖图存在循环"})
    return diagnostics


def _prefilter(atoms: list[dict[str, Any]], proposal: dict[str, Any], known_skills: set[str]) -> dict[str, Any]:
    explicit = _bounded_strings(proposal.get("candidate_capabilities"), 6, 80)
    if explicit:
        candidates = [item for item in explicit if item in known_skills]
        return {"source": "MODEL_STRUCTURED_CANDIDATES", "candidates": candidates[:6], "bounded": len(explicit) <= 6}
    families: list[str] = []
    for atom in atoms:
        if atom["state"] not in {"CURRENT", "HYPOTHETICAL"}:
            continue
        family = atom.get("capability_family")
        if family and family not in families:
            families.append(family)
    candidates: list[str] = []
    for family in families[:3]:
        for skill in CAPABILITY_FAMILIES.get(family, ()):
            if skill in known_skills and skill not in candidates:
                candidates.append(skill)
            if len(candidates) >= 6:
                break
    if not candidates:
        candidates = [
            str(item.get("skill") if isinstance(item, dict) else item).strip()
            for item in list(proposal.get("candidates") or []) + list(proposal.get("deferred") or [])
        ]
        candidates = [item for item in dict.fromkeys(candidates) if item in known_skills][:6]
    return {"source": "STRUCTURED_INTENT_FAMILY" if families else "LEGACY_MODEL_SELECTION", "families": families, "candidates": candidates, "bounded": True}


def _ambiguity_policy(ambiguities: list[Any], risk: dict[str, Any], positive_conflict: bool) -> str:
    if positive_conflict:
        return "BLOCK"
    if not ambiguities:
        return "SAFE_INFERENCE"
    for item in ambiguities:
        if isinstance(item, dict) and bool(item.get("block")):
            return "BLOCK"
    high_risk = risk["level"] in {"HIGH", "CRITICAL"}
    direction_required = any(
        isinstance(item, dict) and bool(item.get("direction_required") or item.get("irreversible") or item.get("data_direction"))
        for item in ambiguities
    )
    if high_risk and direction_required:
        return "ASK_REQUIRED"
    return "EVIDENCE_FIRST"


def _routing_cost(atoms: list[dict[str, Any]], scopes: list[str], risk: dict[str, Any], ambiguities: list[Any]) -> str:
    active = [atom for atom in atoms if atom["state"] == "CURRENT"]
    conditional = any(atom["state"] in {"CONDITIONAL", "HYPOTHETICAL"} for atom in atoms)
    families = {atom.get("capability_family") for atom in active if atom.get("capability_family")}
    deep = (
        len(active) > 1
        or len(families) > 1
        or conditional
        or risk["level"] in {"HIGH", "CRITICAL"}
        or bool({"database", "architecture", "cross-repository"} & set(scopes))
    )
    if deep:
        return "DEEP"
    if len(active) <= 1 and risk["level"] == "LOW" and len(scopes) <= 1 and not ambiguities:
        return "FAST"
    return "STANDARD"


def _architectures_compatible(first: str, second: str) -> bool:
    if not first or not second or first == second or "hybrid" in {first, second}:
        return True
    return {first, second} == {"bs", "backend"}


def conflict_receipt(fact_plane: dict[str, Any], expected: str, task_scope: list[str]) -> dict[str, Any]:
    observed_fact = fact_plane.get("project_architecture") or {}
    observed = str(observed_fact.get("value") or "").lower()
    expected = str(expected or "").lower()
    positive = bool(observed and expected and not _architectures_compatible(observed, expected))
    return {
        "conflict_type": "ARCHITECTURE_CONFLICT" if positive else "NO_CONFLICT",
        "expected_fact": expected or None,
        "observed_fact": observed or None,
        "authority_a": "MODEL_ROUTE_CONTRACT" if expected else None,
        "authority_b": observed_fact.get("authority"),
        "source_a": "route_contract.project_architecture" if expected else None,
        "source_b": observed_fact.get("source_fingerprint"),
        "scope": "project_architecture",
        "task_scope": task_scope,
        "confidence": "high" if positive else "high" if observed else "low",
        "is_positive_contradiction": positive,
        "resolution_policy": "BLOCK_AND_RECONCILE_AUTHORITY" if positive else "TASK_SCOPE_DOES_NOT_MUTATE_PROJECT_ARCHITECTURE",
    }


def normalize_route_contract(
    proposal: dict[str, Any],
    fact_plane: dict[str, Any],
    known_skills: Iterable[str],
) -> dict[str, Any]:
    known = set(known_skills)
    current_action = str(proposal.get("current_action") or "").strip()[:240]
    atoms = _intent_atoms(proposal, current_action)
    diagnostics = _validate_dag(atoms)
    observed_architecture = str((fact_plane.get("project_architecture") or {}).get("value") or "").lower()
    explicit_project_architecture = str(proposal.get("project_architecture") or "").strip().lower()
    legacy_architecture = str(proposal.get("architecture") or "").strip().lower()
    task_scope = _scopes(proposal.get("task_scope"))
    if not task_scope and legacy_architecture not in {"", "unknown", "tooling", observed_architecture}:
        task_scope = _scopes([legacy_architecture])
    if not task_scope and legacy_architecture in {"backend", "bs", "cs"}:
        task_scope = _scopes([legacy_architecture])
    project_architecture = explicit_project_architecture or observed_architecture or legacy_architecture
    receipt = conflict_receipt(fact_plane, explicit_project_architecture, task_scope)
    risk = _risk(proposal.get("risk"))
    ambiguities = list(proposal.get("ambiguities") or [])[:12] if isinstance(proposal.get("ambiguities"), list) else []
    prefilter = _prefilter(atoms, proposal, known)
    selected = [
        str(item.get("skill") if isinstance(item, dict) else item).strip()
        for item in proposal.get("candidates") or []
    ]
    if proposal.get("candidate_capabilities") and any(skill not in prefilter["candidates"] for skill in selected):
        diagnostics.append({"code": "SELECTED_OUTSIDE_CAPABILITY_PREFILTER", "message": "Selected Skill不在结构化候选集内"})
    inactive_candidates = {
        skill
        for atom in atoms
        if atom["state"] in {"NEGATED", "HISTORICAL", "RESOLVED", "FUTURE", "CONDITIONAL", "DEFERRED"}
        for skill in atom.get("candidate_capabilities") or []
    }
    forbidden_selected = sorted(inactive_candidates.intersection(selected))
    if forbidden_selected:
        diagnostics.append({"code": "NON_CURRENT_INTENT_SELECTED", "message": f"非CURRENT意图不能激活Skill：{forbidden_selected}"})
    ambiguity_policy = _ambiguity_policy(ambiguities, risk, receipt["is_positive_contradiction"])
    routing_cost = _routing_cost(atoms, task_scope, risk, ambiguities)
    dependencies = [
        {"from": dependency, "to": atom["id"]}
        for atom in atoms
        for dependency in atom["dependencies"]
    ]
    contract = {
        "schema_version": "1.0.0",
        "operation": str(proposal.get("operation") or "project_action").strip()[:120],
        "target": str(proposal.get("target") or "current_project").strip()[:160],
        "project_architecture": project_architecture or "unknown",
        "task_scope": task_scope,
        "stage": str(proposal.get("stage") or "unknown").strip().lower(),
        "current_action": current_action,
        "intent_atoms": atoms,
        "negative_intents": [atom["id"] for atom in atoms if atom["state"] == "NEGATED"],
        "conditional_intents": [atom["id"] for atom in atoms if atom["state"] in {"CONDITIONAL", "HYPOTHETICAL"}],
        "historical_intents": [atom["id"] for atom in atoms if atom["state"] in {"HISTORICAL", "RESOLVED"}],
        "future_intents": [atom["id"] for atom in atoms if atom["state"] in {"FUTURE", "DEFERRED"}],
        "constraints": _bounded_strings(proposal.get("constraints"), 16, 200),
        "dependencies": dependencies,
        "risk": risk,
        "ambiguities": ambiguities,
        "ambiguity_policy": ambiguity_policy,
        "required_evidence": _bounded_strings(proposal.get("required_evidence"), 16, 200),
        "candidate_capabilities": prefilter["candidates"],
        "capability_prefilter": prefilter,
        "routing_cost": routing_cost,
        "conflict_receipt": receipt,
    }
    fingerprint_basis = {key: value for key, value in contract.items() if key != "route_contract_fingerprint"}
    contract["route_contract_fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_basis, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {"contract": contract, "diagnostics": diagnostics}

