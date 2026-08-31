from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from gate_applicability import plan_from_model_proposal, validate_plan as validate_gate_plan
from perspective_applicability import validate_plan as validate_perspective_plan
from workspacelib import RESOURCE_HARD_MAX, atomic_json


def request_metadata(text: str) -> dict[str, object]:
    raw = str(text or "")
    return {
        "request_fingerprint": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest(),
        "request_chars": len(raw),
        "request_persisted": False,
    }


EXECUTION_CONTRACTS = {
    "CONTROL": {"writes": ["governance state", "task coordination", "release decision", "documentation"], "forbidden": ["bypass failed gates", "unbounded direct writes"]},
    "WRITE": {"writes": ["assigned source files", "unit tests"], "forbidden": ["self approval", "protected branches", "unowned scope"]},
    "ASSURE": {"writes": ["review and test evidence"], "forbidden": ["approve own implementation when independence is required", "merge"]},
}
ROLE_EXECUTION_CLASS = {
    "Master Agent": "CONTROL", "Planning Agent": "CONTROL", "Merge Agent": "CONTROL", "Document Agent": "CONTROL",
    "Developer Agent": "WRITE", "Review Agent": "ASSURE", "Test Agent": "ASSURE",
}


def execution_class_for(value: str | None) -> str | None:
    token = str(value or "").strip()
    normalized = token.upper()
    if normalized in EXECUTION_CONTRACTS:
        return normalized
    return ROLE_EXECUTION_CLASS.get(token)
RESPONSIBILITY_BY_LANE = {
    "planning": "PLANNING", "contract-data": "CONTRACT", "review": "REVIEW", "testing": "TESTING",
    "documentation": "DOCUMENTATION", "merge": "MERGE", "release-control": "RELEASE",
}

VALID_ARCHITECTURES = {"bs", "cs", "backend", "hybrid", "unknown"}
VALID_CLIENT_FAMILIES = {
    "unity", "qt", "dotnet-desktop", "electron-tauri", "flutter", "android",
    "apple-native", "react-native", "java-desktop", "embedded-hmi", "unspecified",
}
VALID_RISK_CLASSES = {"local", "bounded", "structural"}
VALID_PARALLEL_MODES = {"auto-safe", "serial"}
RESERVED_LANE_IDS = {"planning", "contract-data", "review", "testing", "documentation", "merge", "release-control"}
PROJECT_FACT_FILE_MAX_BYTES = RESOURCE_HARD_MAX["input"]["project_fact_file_bytes"]


def lane(name: str, role: str, inputs: list[str], outputs: list[str], mode: str, depends: list[str] | None = None, required: bool = True) -> dict:
    execution_class = ROLE_EXECUTION_CLASS[role]
    contract = EXECUTION_CONTRACTS[execution_class]
    return {
        "lane": name,
        "responsibility": RESPONSIBILITY_BY_LANE.get(name, "IMPLEMENTATION"),
        "execution_class": execution_class,
        "agent_role": role,
        "agent_role_semantics": "COMPATIBILITY_RESPONSIBILITY_LABEL",
        "inputs": inputs,
        "outputs": outputs,
        "permissions": contract["writes"],
        "forbidden": contract["forbidden"],
        "mode": mode,
        "ownership_lane": name if execution_class == "WRITE" else role.lower().replace(" agent", ""),
        "parallel_eligible": execution_class == "WRITE",
        "required": required,
        "status": "PLANNED" if required else "NOT_APPLICABLE",
        "depends_on": depends or [],
    }


def _project_fact_plane(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("project_fact_plane")
    if isinstance(nested, dict):
        return nested
    return payload if "project_topology" in payload and "source_fingerprint" in payload else {}


def _project_fact_receipt(payload: dict | None) -> dict:
    plane = _project_fact_plane(payload)
    if not plane:
        legacy = payload if isinstance(payload, dict) else {}
        encoded = json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "status": "LEGACY_EVIDENCE_ONLY" if legacy else "NOT_PROVIDED",
            "source_fingerprint": hashlib.sha256(encoded).hexdigest() if legacy else None,
            "project_fact_plane_bound": False,
            "topology_root_count": 0,
            "changed_scope_count": 0,
        }
    topology_fact = plane.get("project_topology") if isinstance(plane.get("project_topology"), dict) else {}
    identity_fact = plane.get("project_identity") if isinstance(plane.get("project_identity"), dict) else {}
    topology = topology_fact.get("value") if isinstance(topology_fact.get("value"), dict) else {}
    root_keys = ("application_roots", "service_roots", "frontend_roots", "backend_roots", "client_roots")
    root_count = sum(len(topology.get(key) or []) for key in root_keys if isinstance(topology.get(key), list))
    changed_scope = plane.get("current_changed_scope") if isinstance(plane.get("current_changed_scope"), list) else []
    return {
        "status": "BOUND",
        "source_fingerprint": plane.get("source_fingerprint"),
        "project_fact_plane_bound": True,
        "authority": identity_fact.get("authority") or plane.get("authority"),
        "generation": identity_fact.get("generation") if identity_fact else plane.get("generation"),
        "topology_root_count": root_count,
        "changed_scope_count": len(changed_scope),
    }


def _validated_proposal(proposal: dict | None, request: str = "", project_facts: dict | None = None) -> tuple[dict | None, list[str]]:
    if not proposal:
        return None, ["PROPOSAL_REQUIRED: 由 ChatGPT 语义判断 architecture 与 client_families 后再生成工作区通道"]
    architecture = str(proposal.get("architecture", "")).strip().lower()
    if architecture not in VALID_ARCHITECTURES:
        return None, [f"UNKNOWN_ARCHITECTURE: {architecture or '<empty>'}"]
    raw_families = proposal.get("client_families", [])
    if not isinstance(raw_families, list):
        return None, ["INVALID_CLIENT_FAMILIES: client_families 必须是数组"]
    families = list(dict.fromkeys(str(item).strip().lower() for item in raw_families if str(item).strip()))
    unknown = sorted(set(families) - VALID_CLIENT_FAMILIES)
    errors = [f"UNKNOWN_CLIENT_FAMILY: {item}" for item in unknown]
    if errors:
        return None, errors
    risk_class = str(proposal.get("risk_class") or "bounded").strip().lower()
    if risk_class not in VALID_RISK_CLASSES:
        errors.append(f"UNKNOWN_RISK_CLASS: {risk_class}")
    parallel_mode = str(proposal.get("parallel_mode") or "auto-safe").strip().lower()
    if parallel_mode not in VALID_PARALLEL_MODES:
        errors.append(f"UNKNOWN_PARALLEL_MODE: {parallel_mode}")
    contract_change = proposal.get("contract_change")
    if contract_change is not None and not isinstance(contract_change, bool):
        errors.append("INVALID_CONTRACT_CHANGE: contract_change 必须是 true、false 或省略")
    independent_assurance = proposal.get("independent_assurance")
    if independent_assurance is not None and not isinstance(independent_assurance, bool):
        errors.append("INVALID_ASSURANCE_INDEPENDENCE: independent_assurance必须是boolean或省略")
    semantic_basis_fields = (
        "repository_change", "runtime_change", "architecture_impact",
        "shared_scope", "release_impact", "merge_required",
    )
    for field in semantic_basis_fields:
        value = proposal.get(field)
        if value is not None and type(value) is not bool:
            errors.append(f"INVALID_GATE_BASIS:{field}")
    project_fact_fingerprint = str(proposal.get("project_fact_fingerprint") or "").strip().lower() or None
    if project_fact_fingerprint and not re.fullmatch(r"[0-9a-f]{64}", project_fact_fingerprint):
        errors.append("INVALID_PROJECT_FACT_FINGERPRINT")
    project_fact_receipt = _project_fact_receipt(project_facts)
    observed_fact_fingerprint = project_fact_receipt.get("source_fingerprint")
    if project_fact_fingerprint and not observed_fact_fingerprint:
        errors.append("PROJECT_FACT_PLANE_REQUIRED")
    elif project_fact_fingerprint and project_fact_fingerprint != observed_fact_fingerprint:
        errors.append("PROJECT_FACT_FINGERPRINT_MISMATCH")
    gate_applicability = None
    raw_gate_applicability = proposal.get("gate_applicability")
    if raw_gate_applicability is not None:
        if not isinstance(raw_gate_applicability, dict):
            errors.append("INVALID_GATE_APPLICABILITY: gate_applicability 必须是对象")
        else:
            try:
                gate_applicability = validate_gate_plan(raw_gate_applicability, task_goal=request)
            except RuntimeError as exc:
                errors.append(str(exc))
    perspective_applicability = None
    if "perspective_applicability" in proposal:
        observed_fact_catalog = (
            project_facts.get("observed_fact_catalog")
            if isinstance(project_facts, dict)
            else None
        )
        expected_project_fact_fingerprint = (
            observed_fact_fingerprint
            if project_fact_receipt.get("project_fact_plane_bound")
            else None
        )
        try:
            perspective_applicability = validate_perspective_plan(
                proposal.get("perspective_applicability"),
                observed_fact_catalog=observed_fact_catalog,
                expected_scope_fingerprint=request_metadata(request)["request_fingerprint"],
                expected_project_fact_fingerprint=expected_project_fact_fingerprint,
            )
        except RuntimeError as exc:
            errors.append(str(exc))
    raw_lanes = proposal.get("implementation_lanes", [])
    implementation_lanes: list[dict] = []
    if not isinstance(raw_lanes, list):
        errors.append("INVALID_IMPLEMENTATION_LANES: implementation_lanes 必须是数组")
    elif len(raw_lanes) > RESOURCE_HARD_MAX["task"]["max_planned_lanes"]:
        errors.append(f"TOO_MANY_IMPLEMENTATION_LANES: 单阶段最多规划{RESOURCE_HARD_MAX['task']['max_planned_lanes']}个所有权通道")
    else:
        ids: set[str] = set()
        for index, item in enumerate(raw_lanes):
            if not isinstance(item, dict):
                errors.append(f"INVALID_IMPLEMENTATION_LANE: 第{index + 1}项必须是对象")
                continue
            lane_id = str(item.get("id") or "").strip().lower()
            surface = str(item.get("surface") or "generic").strip().lower()
            write_scope = item.get("write_scope", [])
            authority_ids = item.get("authority_ids", [])
            depends_on = item.get("depends_on", [])
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", lane_id):
                errors.append(f"INVALID_IMPLEMENTATION_LANE_ID: {lane_id or '<empty>'}")
            elif lane_id in RESERVED_LANE_IDS:
                errors.append(f"RESERVED_IMPLEMENTATION_LANE_ID: {lane_id}")
            elif lane_id in ids:
                errors.append(f"DUPLICATE_IMPLEMENTATION_LANE_ID: {lane_id}")
            else:
                ids.add(lane_id)
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", surface):
                errors.append(f"INVALID_IMPLEMENTATION_SURFACE: {surface or '<empty>'}")
            if not isinstance(write_scope, list) or not write_scope or len(write_scope) > 32 or any(not str(value).strip() for value in write_scope):
                errors.append(f"INVALID_WRITE_SCOPE: {lane_id or index + 1} 必须声明1至32个非空模块或路径")
                write_scope = []
            if not isinstance(depends_on, list):
                errors.append(f"INVALID_LANE_DEPENDENCIES: {lane_id or index + 1}")
                depends_on = []
            if not isinstance(authority_ids, list) or len(authority_ids) > 16:
                errors.append(f"INVALID_AUTHORITY_IDS: {lane_id or index + 1} 必须是最多16项的数组")
                authority_ids = []
            repository_key = str(item.get("repository_key") or "current").strip().lower()
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", repository_key):
                errors.append(f"INVALID_REPOSITORY_KEY: {repository_key or '<empty>'}")
            normalized_scopes = list(dict.fromkeys(str(value).strip().replace("\\", "/") for value in write_scope))
            normalized_authorities = list(dict.fromkeys(str(value).strip().upper() for value in authority_ids if str(value).strip()))
            for scope in normalized_scopes:
                parts = [part for part in scope.split("/") if part]
                if len(scope) > 240 or scope.startswith("/") or ".." in parts:
                    errors.append(f"UNSAFE_WRITE_SCOPE: {lane_id or index + 1} -> {scope[:80]}")
            for authority_id in normalized_authorities:
                if not re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{0,127}", authority_id):
                    errors.append(f"INVALID_AUTHORITY_ID: {lane_id or index + 1} -> {authority_id[:80]}")
            implementation_lanes.append({
                "id": lane_id,
                "surface": surface,
                "write_scope": normalized_scopes,
                "authority_ids": normalized_authorities,
                "depends_on": list(dict.fromkeys(str(value).strip().lower() for value in depends_on if str(value).strip())),
                "repository_key": repository_key,
            })
        known = {item["id"] for item in implementation_lanes if item["id"]}
        for item in implementation_lanes:
            unknown_dependencies = sorted(set(item["depends_on"]) - known)
            if item["id"] in item["depends_on"]:
                errors.append(f"SELF_DEPENDENCY: {item['id']}")
            for dependency in unknown_dependencies:
                errors.append(f"UNKNOWN_LANE_DEPENDENCY: {item['id']} -> {dependency}")
        graph = {item["id"]: item["depends_on"] for item in implementation_lanes if item["id"] in known}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            cyclic = any(visit(dependency) for dependency in graph.get(node, []) if dependency in graph)
            visiting.remove(node)
            visited.add(node)
            return cyclic

        if any(visit(node) for node in graph):
            errors.append("CYCLIC_IMPLEMENTATION_LANES: 动态实现通道存在循环依赖")
    if not errors and gate_applicability is None:
        gate_applicability = plan_from_model_proposal(request, {
            **proposal,
            "implementation_lanes": implementation_lanes,
        })
    if gate_applicability is not None:
        if gate_applicability["risk_class"] != risk_class:
            errors.append("GATE_RISK_CLASS_CONFLICT: routing与gate applicability风险等级不一致")
        assurance_required = any(
            gate_applicability["gates"][name]["status"] == "REQUIRED"
            for name in ("review", "testing")
        )
        hard_independence = assurance_required and (
            risk_class == "structural"
            or any(gate_applicability["basis"].get(name) for name in ("architecture_impact", "shared_scope", "release_impact"))
        )
        if independent_assurance is False and hard_independence:
            errors.append("ASSURANCE_INDEPENDENCE_REQUIRED_BY_RISK")
    if errors:
        return None, errors
    if gate_applicability and gate_applicability["gates"]["development"]["status"] == "NOT_APPLICABLE" and implementation_lanes:
        return None, ["NON_APPLICABLE_DEVELOPMENT_HAS_WRITE_LANES"]
    return {"architecture": architecture, "client_families": families, "risk_class": risk_class, "parallel_mode": parallel_mode, "contract_change": contract_change, "implementation_lanes": implementation_lanes, "gate_applicability": gate_applicability, "perspective_applicability": perspective_applicability, "independent_assurance": independent_assurance, "project_fact_fingerprint": project_fact_fingerprint}, []


def _scopes_overlap(left: list[str], right: list[str]) -> bool:
    for first in left:
        a = first.strip("/").casefold()
        for second in right:
            b = second.strip("/").casefold()
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                return True
    return False


def _execution_topology(lanes: list[dict], risk_class: str, gate_applicability: dict | None, independent_assurance_proposal: bool | None) -> dict:
    active = [item for item in lanes if item.get("required")]
    writers = [item for item in active if item.get("execution_class") == "WRITE"]
    basis = (gate_applicability or {}).get("basis") or {}
    assurance_required = any(
        item.get("required") and item.get("execution_class") == "ASSURE"
        for item in active
    )
    risk_requires_independence = assurance_required and (
        risk_class == "structural"
        or any(bool(basis.get(name)) for name in ("architecture_impact", "shared_scope", "release_impact"))
    )
    independent_assurance = risk_requires_independence or independent_assurance_proposal is True
    local_writer_reuse = risk_class == "local" and len(writers) == 1
    bindings: dict[str, dict] = {}

    def bind(item: dict, binding_id: str, session_policy: str, worktree_policy: str, independence: str) -> None:
        item["binding_id"] = binding_id
        item["provider_session_policy"] = session_policy
        item["worktree_policy"] = worktree_policy
        item["independence"] = independence
        binding = bindings.setdefault(binding_id, {
            "binding_id": binding_id,
            "execution_classes": [],
            "responsibilities": [],
            "provider_session_policy": session_policy,
            "worktree_policy": worktree_policy,
            "independence": independence,
        })
        if item["execution_class"] not in binding["execution_classes"]:
            binding["execution_classes"].append(item["execution_class"])
        binding["responsibilities"].append(item["responsibility"])

    for item in lanes:
        if not item.get("required"):
            item.update({"binding_id": None, "provider_session_policy": "NONE", "worktree_policy": "NONE", "independence": "NOT_APPLICABLE"})
        elif item["execution_class"] == "CONTROL":
            bind(item, "current-controller", "REUSE_CURRENT_PROVIDER_SESSION", "CURRENT_WORKTREE_IF_SAFE", "NOT_REQUIRED")
        elif item["execution_class"] == "WRITE" and local_writer_reuse:
            bind(item, "current-controller", "REUSE_CURRENT_PROVIDER_SESSION", "CURRENT_WORKTREE_IF_SAFE", "NOT_REQUIRED")
        elif item["execution_class"] == "WRITE":
            bind(item, f"writer:{item['ownership_lane']}", "REUSE_OR_CREATE_IF_READY", "SEPARATE_IF_WRITE_CONFLICT", "CONDITIONAL")
        elif independent_assurance:
            bind(item, "assurance", "SEPARATE_PROVIDER_SESSION", "NONE_READ_ONLY", "REQUIRED")
        else:
            bind(item, "current-controller", "REUSE_CURRENT_PROVIDER_SESSION", "NONE_READ_ONLY", "CONDITIONAL")
    return {
        "execution_classes": ["CONTROL", "WRITE", "ASSURE"],
        "bindings": list(bindings.values()),
        "default_new_agent_count": 0,
        "default_new_provider_session_count": 0,
        "active_turn_hard_limit": RESOURCE_HARD_MAX["execution"]["max_active_turns"],
        "writer_binding_hard_limit": RESOURCE_HARD_MAX["execution"]["max_writer_slots"],
        "independent_assurance_required": independent_assurance and any(item.get("execution_class") == "ASSURE" for item in active),
        "assurance_independence_authority": "HARD_RISK_INVARIANT" if risk_requires_independence else "MODEL_PROPOSAL",
        "invariants": [
            "responsibility != agent", "agent != provider session", "provider session != worktree", "worktree != task",
        ],
    }


def route(text: str, tech_stack: dict | None = None, proposal: dict | None = None) -> dict:
    """Validate ChatGPT's proposal and expand deterministic execution lanes.

    Request text and shallow tech-stack facts are evidence only. This function
    must never infer architecture or client family from request keywords.
    """
    selected, diagnostics = _validated_proposal(proposal, text, tech_stack)
    if not selected:
        return {
            "schema_version": "3.0.0",
            "status": "REJECTED",
            **request_metadata(text),
            "routing_authority": "chatgpt-semantic-selection",
            "guard_role": "constraints-and-workflow-expansion-only",
            "diagnostics": diagnostics,
            "architecture": "unknown",
            "client_families": [],
            "lanes": [],
        }

    architecture = selected["architecture"]
    client_families = selected["client_families"]
    risk_class = selected["risk_class"]
    parallel_mode = selected["parallel_mode"]
    contract_change = selected["contract_change"]
    proposed_implementation = selected["implementation_lanes"]
    independent_assurance_proposal = selected["independent_assurance"]
    gate_applicability = selected["gate_applicability"]
    perspective_applicability = selected["perspective_applicability"]
    gate_status = lambda name, fallback=True: gate_applicability["gates"][name]["status"]
    gate_is_required = lambda name, fallback=True: gate_status(name, fallback) != "NOT_APPLICABLE"
    lanes = [
        lane(
            "planning",
            "Planning Agent",
            ["user request", "PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md", "git status"],
            ["task breakdown", "acceptance criteria", "technical plan", "estimate"],
            "control-responsibility",
            required=gate_is_required("planning"),
        ),
    ]
    implementation: list[str] = []
    development_required = gate_is_required("development")
    planning_dependencies = ["planning"] if gate_is_required("planning") else []
    if development_required and proposed_implementation:
        for proposed in proposed_implementation:
            implementation_lane = lane(
                proposed["id"],
                "Developer Agent",
                ["approved plan", "change contract", "detected technology and version", "bound task context"],
                ["implementation", "focused tests", "bounded evidence packet"],
                "write-responsibility",
                [*planning_dependencies, *proposed["depends_on"]],
            )
            implementation_lane.update({
                "surface": proposed["surface"],
                "write_scope": proposed["write_scope"],
                "authority_ids": proposed["authority_ids"],
                "repository_key": proposed["repository_key"],
                "serial_with": [],
                "scope_conflicts": [],
                "authority_conflicts": [],
            })
            lanes.append(implementation_lane)
            implementation.append(proposed["id"])
        for current in lanes:
            if current["lane"] not in implementation:
                continue
            for candidate in lanes:
                if candidate["lane"] not in implementation or candidate["lane"] == current["lane"]:
                    continue
                same_repository = candidate.get("repository_key") == current.get("repository_key")
                scope_conflict = same_repository and _scopes_overlap(
                    current.get("write_scope", []), candidate.get("write_scope", [])
                )
                shared_authorities = sorted(
                    set(current.get("authority_ids", [])) & set(candidate.get("authority_ids", []))
                )
                if scope_conflict:
                    current["scope_conflicts"].append(candidate["lane"])
                if shared_authorities:
                    current["authority_conflicts"].append({
                        "lane": candidate["lane"], "shared_authority_ids": shared_authorities,
                    })
                if scope_conflict or shared_authorities:
                    current["serial_with"].append(candidate["lane"])
            current["serial_with"].sort()
            current["scope_conflicts"].sort()
            current["authority_conflicts"].sort(key=lambda value: value["lane"])
    elif development_required:
        lanes.append(lane("implementation", "Developer Agent", ["approved plan"], ["implementation", "unit tests"], "write-responsibility", planning_dependencies))
        implementation = ["implementation"]
    if development_required and contract_change is True:
        lanes.append(lane("contract-data", "Planning Agent", ["declared consumers", "current contract facts"], ["versioned contract impact", "compatibility rules"], "control-responsibility", planning_dependencies))
        for item in lanes:
            if item["lane"] in implementation and "contract-data" not in item["depends_on"]:
                item["depends_on"].append("contract-data")
    last_required = list(implementation) or planning_dependencies
    review_required = gate_is_required("review")
    testing_required = gate_is_required("testing")
    documentation_required = gate_is_required("documentation", risk_class != "local")
    merge_required = gate_is_required("merge", risk_class != "local")
    release_required = gate_is_required("release", risk_class == "structural")
    review_dependencies = last_required
    testing_dependencies = ["review"] if review_required else last_required
    documentation_dependencies = ["testing"] if testing_required else (["review"] if review_required else last_required)
    merge_dependencies = ["documentation"] if documentation_required else documentation_dependencies
    release_dependencies = ["merge"] if merge_required else merge_dependencies
    lanes.extend([
        lane("review", "Review Agent", ["diff", "architecture", "ownership", "risk list"], ["independent review report", "PASS or BLOCKED"], "assure-responsibility", review_dependencies, required=review_required),
        lane("testing", "Test Agent", ["acceptance criteria", "review result", "build"], ["automated tests", "regression result", "screenshots or logs"], "assure-responsibility", testing_dependencies, required=testing_required),
        lane("documentation", "Document Agent", ["approved implementation", "test evidence"], ["CHANGELOG.md", "ARCHITECTURE.md or justified N/A", "knowledge update"], "control-responsibility", documentation_dependencies, required=documentation_required),
        lane("merge", "Merge Agent", ["review PASS", "test PASS", "closure PASS", "clean branch"], ["merge commit", "task state update"], "control-responsibility", merge_dependencies, required=merge_required),
        lane("release-control", "Master Agent", ["merged task", "release evidence", "risk and rollback plan"], ["release decision", "Released state or rollback"], "control-responsibility", release_dependencies, required=release_required),
    ])
    lane_gate = {
        "planning": "planning", "contract-data": "planning", "review": "review", "testing": "testing",
        "documentation": "documentation", "merge": "merge", "release-control": "release",
    }
    for item in lanes:
        applicability = gate_status(lane_gate.get(item["lane"], "development"), item.get("required", True))
        item["applicability"] = applicability
        item["required"] = applicability != "NOT_APPLICABLE"
        item["status"] = "PLANNED" if applicability == "REQUIRED" else applicability
    execution_topology = _execution_topology(lanes, risk_class, gate_applicability, independent_assurance_proposal)
    return {
        "schema_version": "3.0.0",
        "status": "ACCEPTED",
        **request_metadata(text),
        "routing_authority": "chatgpt-semantic-selection",
        "guard_role": "constraints-and-workflow-expansion-only",
        "architecture": architecture,
        "client_families": client_families,
        "risk_class": risk_class,
        "contract_change": contract_change,
        "gate_applicability": gate_applicability,
        **({"perspective_applicability": perspective_applicability} if perspective_applicability is not None else {}),
        "evidence_snapshot": _project_fact_receipt(tech_stack),
        "diagnostics": [],
        "lanes": lanes,
        "execution_topology": execution_topology,
        "policy": {
            "control_plane": "CONTROL responsibility bound to the current controller",
            "architecture_label": "coarse classification only; it never creates an execution lane",
            "topology_authority": "ChatGPT proposal grounded in bounded Project Fact Plane surfaces, changed scope, dependencies and current task",
            "parallel_write": "activate at most two safe WRITE bindings; create a provider session or worktree only when conflict, independence or runtime facts require it",
            "parallel_mode": parallel_mode,
            "parallel_decision": "ChatGPT evaluates file/module ownership, shared contracts, migrations, protected assets, test environment and current budget; user does not need to repeat a parallel keyword",
            "dynamic_lanes": "ChatGPT may propose up to eight evidence-backed ownership lanes; the runtime activates at most two non-overlapping lanes and serializes serial_with conflicts",
            "same_file_write": "serial",
            "protected_branches": ["main", "develop", "release"],
            "human_controls": ["pause", "adjust", "insert", "resume"],
            "context_isolation": "project_id plus repository root plus task_id plus ownership_lane",
        },
    }


def _read_proposal(args: argparse.Namespace) -> dict | None:
    if args.proposal_json:
        return json.loads(args.proposal_json)
    if args.proposal_file:
        return json.loads(Path(args.proposal_file).read_text(encoding="utf-8"))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 ChatGPT 的工作区语义提案并生成确定性执行通道")
    parser.add_argument("--root", default=".")
    parser.add_argument("--request", required=True)
    parser.add_argument("--proposal-json")
    parser.add_argument("--proposal-file")
    parser.add_argument("--project-facts-file")
    parser.add_argument("--output", default=".ai/workspace/task-map.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    stack_path = root / ".ai" / "context" / "tech-stack.json"
    facts_path = Path(args.project_facts_file).resolve() if args.project_facts_file else stack_path
    try:
        if facts_path.exists() and facts_path.stat().st_size > PROJECT_FACT_FILE_MAX_BYTES:
            raise RuntimeError("project facts exceed bounded input budget")
        stack = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        stack = {}
    data = route(args.request, stack, _read_proposal(args))
    atomic_json(root / args.output, data)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data["status"] == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
