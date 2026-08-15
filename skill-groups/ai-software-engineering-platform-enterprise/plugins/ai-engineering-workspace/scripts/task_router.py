from __future__ import annotations

import argparse
import json
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


def lane(name: str, role: str, inputs: list[str], outputs: list[str], mode: str, depends: list[str] | None = None) -> dict:
    contract = ROLE_CONTRACTS[role]
    return {
        "lane": name,
        "agent_role": role,
        "inputs": inputs,
        "outputs": outputs,
        "permissions": contract["writes"],
        "forbidden": contract["forbidden"],
        "mode": mode,
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
    return {"architecture": architecture, "client_families": families}, []


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
    if bs:
        lanes.append(lane("bs-frontend", "Developer Agent", ["approved plan", "UI/design contracts", "API contracts"], ["browser frontend", "frontend tests"], "separate-worktree", ["planning"]))
        implementation.append("bs-frontend")
    if cs:
        lanes.append(lane("cs-client", "Developer Agent", ["approved plan", "client family receipt", "client UI and lifecycle contracts", "versioned API contracts"], ["client implementation in existing framework", "client tests"], "separate-worktree", ["planning"]))
        implementation.append("cs-client")
    if backend:
        backend_lane = lane("backend-service", "Developer Agent", ["approved plan", "data and API contracts", "detected backend stack and version"], ["server implementation", "backend tests", "compatibility evidence"], "separate-worktree", ["planning"])
        backend_lane["skill_sequence"] = ["服务端技术路由", "接口与事件契约设计或数据库迁移治理", "服务端功能实现", "服务端质量审核"]
        lanes.append(backend_lane)
        implementation.append("backend-service")
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
        lane("documentation", "Document Agent", ["approved implementation", "test evidence"], ["CHANGELOG.md", "ARCHITECTURE.md or justified N/A", "knowledge update"], "serial-after-testing", ["testing"]),
        lane("merge", "Merge Agent", ["review PASS", "test PASS", "closure PASS", "clean branch"], ["merge commit", "task state update"], "serial-gated", ["documentation"]),
        lane("release-control", "Master Agent", ["merged task", "release evidence", "risk and rollback plan"], ["release decision", "Released state or rollback"], "automatic-checkpoint", ["merge"]),
    ])
    return {
        "schema_version": "3.0.0",
        "status": "ACCEPTED",
        "request": text,
        "routing_authority": "chatgpt-semantic-selection",
        "guard_role": "constraints-and-workflow-expansion-only",
        "architecture": architecture,
        "client_families": client_families,
        "evidence_snapshot": tech_stack or {},
        "diagnostics": [],
        "lanes": lanes,
        "policy": {
            "control_plane": "Master Agent",
            "parallel_write": "default maximum two active write tasks; separate Git worktree plus file locks",
            "same_file_write": "serial",
            "protected_branches": ["main", "develop", "release"],
            "human_controls": ["pause", "adjust", "insert", "resume"],
            "context_isolation": "project_id plus repository root",
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
