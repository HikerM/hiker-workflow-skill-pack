from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from workspacelib import atomic_json


ROLE_CONTRACTS = {
    "Master Agent": {"writes": ["project state", "task assignment", "release decision"], "forbidden": ["direct feature implementation", "direct main modification"]},
    "Planning Agent": {"writes": ["requirements", "technical plan", "estimate"], "forbidden": ["merge", "release"]},
    "Developer Agent": {"writes": ["assigned source files", "unit tests"], "forbidden": ["self approval", "protected branches"]},
    "Review Agent": {"writes": ["review evidence"], "forbidden": ["implement then approve own change", "merge"]},
    "Test Agent": {"writes": ["test evidence", "screenshots and logs"], "forbidden": ["change acceptance criteria", "merge"]},
    "Merge Agent": {"writes": ["merge commit", "CHANGELOG"], "forbidden": ["bypass failed gates", "force overwrite conflicts"]},
    "Document Agent": {"writes": ["documentation", "architecture diagrams", "knowledge base"], "forbidden": ["change runtime behavior without a task"]},
}

VALID_ARCHITECTURES = {"bs", "cs", "backend", "hybrid", "unknown"}
VALID_CLIENT_FAMILIES = {
    "unity", "qt", "dotnet-desktop", "electron-tauri", "flutter", "android",
    "apple-native", "react-native", "java-desktop", "embedded-hmi", "unspecified",
}
VALID_RISK_CLASSES = {"local", "bounded", "structural"}
VALID_PARALLEL_MODES = {"auto-safe", "serial"}
VALID_IMPLEMENTATION_SURFACES = {"bs-frontend", "cs-client", "backend-service", "infrastructure", "generic"}
RESERVED_LANE_IDS = {"planning", "contract-data", "review", "testing", "documentation", "merge", "release-control"}


def lane(name: str, role: str, inputs: list[str], outputs: list[str], mode: str, depends: list[str] | None = None, required: bool = True) -> dict:
    contract = ROLE_CONTRACTS[role]
    return {
        "lane": name,
        "agent_role": role,
        "inputs": inputs,
        "outputs": outputs,
        "permissions": contract["writes"],
        "forbidden": contract["forbidden"],
        "mode": mode,
        "ownership_lane": name if role == "Developer Agent" else role.lower().replace(" agent", ""),
        "parallel_eligible": role == "Developer Agent",
        "required": required,
        "status": "PLANNED",
        "depends_on": depends or [],
    }


def _validated_proposal(proposal: dict | None) -> tuple[dict | None, list[str]]:
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
    if architecture not in {"cs", "hybrid"} and families:
        errors.append("CLIENT_FAMILY_ARCHITECTURE_CONFLICT: 非 C/S 或混合架构不能声明客户端技术族")
    if architecture in {"cs", "hybrid"} and not families:
        families = ["unspecified"]
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
    raw_lanes = proposal.get("implementation_lanes", [])
    implementation_lanes: list[dict] = []
    if not isinstance(raw_lanes, list):
        errors.append("INVALID_IMPLEMENTATION_LANES: implementation_lanes 必须是数组")
    elif len(raw_lanes) > 8:
        errors.append("TOO_MANY_IMPLEMENTATION_LANES: 单阶段最多规划8个所有权通道")
    else:
        ids: set[str] = set()
        for index, item in enumerate(raw_lanes):
            if not isinstance(item, dict):
                errors.append(f"INVALID_IMPLEMENTATION_LANE: 第{index + 1}项必须是对象")
                continue
            lane_id = str(item.get("id") or "").strip().lower()
            surface = str(item.get("surface") or "generic").strip().lower()
            write_scope = item.get("write_scope", [])
            depends_on = item.get("depends_on", [])
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", lane_id):
                errors.append(f"INVALID_IMPLEMENTATION_LANE_ID: {lane_id or '<empty>'}")
            elif lane_id in RESERVED_LANE_IDS:
                errors.append(f"RESERVED_IMPLEMENTATION_LANE_ID: {lane_id}")
            elif lane_id in ids:
                errors.append(f"DUPLICATE_IMPLEMENTATION_LANE_ID: {lane_id}")
            else:
                ids.add(lane_id)
            if surface not in VALID_IMPLEMENTATION_SURFACES:
                errors.append(f"UNKNOWN_IMPLEMENTATION_SURFACE: {surface}")
            if not isinstance(write_scope, list) or not write_scope or len(write_scope) > 32 or any(not str(value).strip() for value in write_scope):
                errors.append(f"INVALID_WRITE_SCOPE: {lane_id or index + 1} 必须声明1至32个非空模块或路径")
                write_scope = []
            if not isinstance(depends_on, list):
                errors.append(f"INVALID_LANE_DEPENDENCIES: {lane_id or index + 1}")
                depends_on = []
            repository_key = str(item.get("repository_key") or "current").strip().lower()
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", repository_key):
                errors.append(f"INVALID_REPOSITORY_KEY: {repository_key or '<empty>'}")
            normalized_scopes = list(dict.fromkeys(str(value).strip().replace("\\", "/") for value in write_scope))
            for scope in normalized_scopes:
                parts = [part for part in scope.split("/") if part]
                if len(scope) > 240 or scope.startswith("/") or ".." in parts:
                    errors.append(f"UNSAFE_WRITE_SCOPE: {lane_id or index + 1} -> {scope[:80]}")
            implementation_lanes.append({
                "id": lane_id,
                "surface": surface,
                "write_scope": normalized_scopes,
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
    if errors:
        return None, errors
    return {"architecture": architecture, "client_families": families, "risk_class": risk_class, "parallel_mode": parallel_mode, "contract_change": contract_change, "implementation_lanes": implementation_lanes}, []


def _scopes_overlap(left: list[str], right: list[str]) -> bool:
    for first in left:
        a = first.strip("/").casefold()
        for second in right:
            b = second.strip("/").casefold()
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                return True
    return False


def route(text: str, tech_stack: dict | None = None, proposal: dict | None = None) -> dict:
    """Validate ChatGPT's proposal and expand deterministic execution lanes.

    Request text and shallow tech-stack facts are evidence only. This function
    must never infer architecture or client family from request keywords.
    """
    selected, diagnostics = _validated_proposal(proposal)
    if not selected:
        return {
            "schema_version": "3.0.0",
            "status": "REJECTED",
            "request": text,
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
    bs = architecture in {"bs", "hybrid"}
    cs = architecture in {"cs", "hybrid"}
    backend = architecture in {"bs", "cs", "backend", "hybrid"}
    lanes = [
        lane(
            "planning",
            "Planning Agent",
            ["user request", "PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md", "git status"],
            ["task breakdown", "acceptance criteria", "technical plan", "estimate"],
            "main-or-read-only-agent",
        ),
    ]
    implementation: list[str] = []
    if proposed_implementation:
        for proposed in proposed_implementation:
            implementation_lane = lane(
                proposed["id"],
                "Developer Agent",
                ["approved plan", "change contract", "detected technology and version", "bound task context"],
                ["implementation", "focused tests", "bounded evidence packet"],
                "separate-worktree",
                ["planning", *proposed["depends_on"]],
            )
            implementation_lane.update({
                "surface": proposed["surface"],
                "write_scope": proposed["write_scope"],
                "repository_key": proposed["repository_key"],
                "serial_with": [],
            })
            lanes.append(implementation_lane)
            implementation.append(proposed["id"])
        for current in lanes:
            if current["lane"] not in implementation:
                continue
            current["serial_with"] = sorted(
                candidate["lane"] for candidate in lanes
                if candidate["lane"] in implementation
                and candidate["lane"] != current["lane"]
                and (
                    candidate.get("repository_key") == current.get("repository_key")
                    and _scopes_overlap(current.get("write_scope", []), candidate.get("write_scope", []))
                )
            )
    elif bs:
        lanes.append(lane("bs-frontend", "Developer Agent", ["approved plan", "UI/design contracts", "API contracts"], ["browser frontend", "frontend tests"], "separate-worktree", ["planning"]))
        implementation.append("bs-frontend")
    if cs:
        lanes.append(lane("cs-client", "Developer Agent", ["approved plan", "client family receipt", "client UI and lifecycle contracts", "versioned API contracts"], ["client implementation in existing framework", "client tests"], "separate-worktree", ["planning"]))
        implementation.append("cs-client")
    if backend:
        if not proposed_implementation:
            backend_lane = lane("backend-service", "Developer Agent", ["approved plan", "data and API contracts", "detected backend stack and version"], ["server implementation", "backend tests", "compatibility evidence"], "separate-worktree", ["planning"])
            backend_lane["skill_sequence"] = ["服务端技术路由", "接口与事件契约设计或数据库迁移治理", "服务端功能实现", "服务端质量审核"]
            lanes.append(backend_lane)
            implementation.append("backend-service")
        if contract_change is not False:
            lanes.append(lane("contract-data", "Planning Agent", ["frontend/client needs", "backend capabilities"], ["versioned API contract", "database impact", "compatibility rules"], "serial-contract-owner", ["planning"]))
            for item in lanes:
                if item["lane"] in implementation:
                    item["depends_on"].append("contract-data")
    if not implementation:
        lanes.append(lane("implementation", "Developer Agent", ["approved plan"], ["implementation", "unit tests"], "worktree-if-writing", ["planning"]))
        implementation = ["implementation"]
    lanes.extend([
        lane("review", "Review Agent", ["diff", "architecture", "ownership", "risk list"], ["independent review report", "PASS or BLOCKED"], "independent-read-only-agent", implementation),
        lane("testing", "Test Agent", ["acceptance criteria", "review result", "build"], ["automated tests", "regression result", "screenshots or logs"], "independent-test-agent", ["review"]),
        lane("documentation", "Document Agent", ["approved implementation", "test evidence"], ["CHANGELOG.md", "ARCHITECTURE.md or justified N/A", "knowledge update"], "serial-after-testing", ["testing"], required=risk_class != "local"),
        lane("merge", "Merge Agent", ["review PASS", "test PASS", "closure PASS", "clean branch"], ["merge commit", "task state update"], "serial-gated", ["documentation"], required=risk_class != "local"),
        lane("release-control", "Master Agent", ["merged task", "release evidence", "risk and rollback plan"], ["release decision", "Released state or rollback"], "automatic-checkpoint", ["merge"], required=risk_class == "structural"),
    ])
    return {
        "schema_version": "3.0.0",
        "status": "ACCEPTED",
        "request": text,
        "routing_authority": "chatgpt-semantic-selection",
        "guard_role": "constraints-and-workflow-expansion-only",
        "architecture": architecture,
        "client_families": client_families,
        "risk_class": risk_class,
        "contract_change": contract_change,
        "evidence_snapshot": tech_stack or {},
        "diagnostics": [],
        "lanes": lanes,
        "policy": {
            "control_plane": "Master Agent",
            "parallel_write": "automatically schedule up to two independent ownership lanes; separate Git worktree plus file locks",
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
    parser.add_argument("--output", default=".ai/workspace/task-map.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    stack_path = root / ".ai" / "context" / "tech-stack.json"
    try:
        stack = json.loads(stack_path.read_text(encoding="utf-8")) if stack_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        stack = {}
    data = route(args.request, stack, _read_proposal(args))
    atomic_json(root / args.output, data)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data["status"] == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
