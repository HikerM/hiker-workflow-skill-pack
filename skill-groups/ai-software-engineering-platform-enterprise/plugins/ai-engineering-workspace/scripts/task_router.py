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


def lane(name: str, role: str, inputs: list[str], outputs: list[str], mode: str, depends: list[str] | None = None) -> dict:
    contract = ROLE_CONTRACTS[role]
    return {"lane": name, "agent_role": role, "inputs": inputs, "outputs": outputs, "permissions": contract["writes"], "forbidden": contract["forbidden"], "mode": mode, "status": "PLANNED", "depends_on": depends or []}


def route(text: str) -> dict:
    low = text.lower()
    bs = any(x in low for x in ["b/s", "bs架构", "web", "vue", "react", "浏览器", "前端页面", "saas", "cms"])
    cs = any(x in low for x in ["c/s", "cs架构", "unity", "桌面", "客户端", "winforms", "wpf", "qt"])
    if not bs and not cs:
        bs = any(x in low for x in ["前端", "后台", "门户"])
        cs = "客户端" in low
    architecture = "hybrid" if bs and cs else "bs" if bs else "cs" if cs else "unknown"
    lanes = [
        lane("planning", "Planning Agent", ["user request", "PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md", "git status"], ["task breakdown", "acceptance criteria", "technical plan", "estimate"], "main-or-read-only-agent"),
    ]
    implementation = []
    if bs:
        lanes += [
            lane("bs-frontend", "Developer Agent", ["approved plan", "UI/design contracts", "API contracts"], ["browser frontend", "frontend tests"], "separate-worktree", ["planning"]),
            lane("bs-backend", "Developer Agent", ["approved plan", "data and API contracts"], ["server implementation", "backend tests"], "separate-worktree", ["planning"]),
        ]
        implementation += ["bs-frontend", "bs-backend"]
    if cs:
        lanes += [
            lane("cs-client", "Developer Agent", ["approved plan", "client UI and lifecycle contracts", "API contracts"], ["desktop or Unity client", "client tests"], "separate-worktree", ["planning"]),
            lane("cs-backend", "Developer Agent", ["approved plan", "data and API contracts"], ["server implementation", "backend tests"], "separate-worktree", ["planning"]),
        ]
        implementation += ["cs-client", "cs-backend"]
    if bs or cs:
        lanes.append(lane("contract-data", "Planning Agent", ["frontend/client needs", "backend capabilities"], ["versioned API contract", "database impact", "compatibility rules"], "serial-contract-owner", ["planning"]))
        for item in lanes:
            if item["lane"] in implementation:
                item["depends_on"].append("contract-data")
    if not implementation:
        lanes.append(lane("implementation", "Developer Agent", ["approved plan"], ["implementation", "unit tests"], "worktree-if-writing", ["planning"]))
        implementation = ["implementation"]
    lanes += [
        lane("review", "Review Agent", ["diff", "architecture", "ownership", "risk list"], ["independent review report", "PASS or BLOCKED"], "independent-read-only-agent", implementation),
        lane("testing", "Test Agent", ["acceptance criteria", "review result", "build"], ["automated tests", "regression result", "screenshots or logs"], "independent-test-agent", ["review"]),
        lane("documentation", "Document Agent", ["approved implementation", "test evidence"], ["CHANGELOG.md", "ARCHITECTURE.md or justified N/A", "knowledge update"], "serial-after-testing", ["testing"]),
        lane("merge", "Merge Agent", ["review PASS", "test PASS", "closure PASS", "clean branch"], ["merge commit", "task state update"], "serial-gated", ["documentation"]),
        lane("release-control", "Master Agent", ["merged task", "release evidence", "risk and rollback plan"], ["release decision", "Released state or rollback"], "human-controlled", ["merge"]),
    ]
    return {
        "schema_version": "2.0.0", "request": text, "architecture": architecture, "lanes": lanes,
        "policy": {"control_plane": "Master Agent", "parallel_write": "separate Git worktree plus file locks", "same_file_write": "serial", "protected_branches": ["main", "develop", "release"], "human_controls": ["pause", "adjust", "insert", "resume"], "context_isolation": "project_id plus repository root"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--request", required=True); ap.add_argument("--output", default=".ai/workspace/task-map.json"); args = ap.parse_args()
    root = Path(args.root).resolve(); data = route(args.request); atomic_json(root / args.output, data); print(json.dumps(data, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
