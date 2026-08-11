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


def flatten(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key); yield from flatten(item)
    elif isinstance(value, list):
        for item in value: yield from flatten(item)
    elif value is not None: yield str(value)


def route(text: str, tech_stack: dict | None = None) -> dict:
    low = text.lower()
    evidence = " ".join(flatten(tech_stack or {})).lower()
    explicit_bs = any(x in low for x in ["b/s", "bs架构", "web", "vue", "react", "浏览器", "前端页面", "saas", "cms"])
    client_markers = {
        "unity": ["unity", "ugui", "ui toolkit"],
        "qt": ["qt", "qml", "pyside", "pyqt"],
        "dotnet-desktop": ["winforms", "wpf", "winui", "avalonia", "maui"],
        "electron-tauri": ["electron", "tauri"],
        "flutter": ["flutter"],
        "android": ["android", "compose"],
        "apple-native": ["ios", "macos", "swiftui", "uikit", "appkit"],
        "react-native": ["react native", "react-native"],
        "java-desktop": ["javafx", "swing"],
        "embedded-hmi": ["lvgl", "hmi", "嵌入式界面"],
    }
    request_families = [family for family, markers in client_markers.items() if any(x in low for x in markers)]
    evidence_families = [family for family, markers in client_markers.items() if any(x in evidence for x in markers)]
    client_families = request_families or evidence_families
    explicit_cs = any(x in low for x in ["c/s", "cs架构", "桌面", "客户端", "移动端"]) or bool(request_families)
    explicit_backend = any(x in low for x in ["后端", "服务端", "服务器", "nodets", "nestjs", "express", "fastapi", "django", "spring", "asp.net", "laravel", "数据库", "migration", "api接口", "接口契约"])
    any_explicit = explicit_bs or explicit_cs or explicit_backend
    bs = explicit_bs or (not any_explicit and any(x in evidence for x in ["vue", "react", "next.js", "nuxt", "angular", "svelte", "web-node"]))
    cs = explicit_cs or (not any_explicit and bool(evidence_families))
    backend = explicit_backend or (not any_explicit and any(x in evidence for x in ["nestjs", "express", "fastapi", "django", "spring boot", "asp.net", "laravel", "rails", "server", "backend"]))
    if not any((bs, cs, backend)):
        bs = any(x in low for x in ["前端", "后台页面", "门户"]); cs = "客户端" in low
    kinds = sum(bool(x) for x in (bs, cs, backend)); architecture = "hybrid" if kinds > 1 else "bs" if bs else "cs" if cs else "backend" if backend else "unknown"
    lanes = [
        lane("planning", "Planning Agent", ["user request", "PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md", "git status"], ["task breakdown", "acceptance criteria", "technical plan", "estimate"], "main-or-read-only-agent"),
    ]
    implementation = []
    if bs:
        lanes += [
            lane("bs-frontend", "Developer Agent", ["approved plan", "UI/design contracts", "API contracts"], ["browser frontend", "frontend tests"], "separate-worktree", ["planning"]),
        ]
        implementation += ["bs-frontend"]
    if cs:
        lanes += [
            lane("cs-client", "Developer Agent", ["approved plan", "client family receipt", "client UI and lifecycle contracts", "versioned API contracts"], ["client implementation in existing framework", "client tests"], "separate-worktree", ["planning"]),
        ]
        implementation += ["cs-client"]
    if bs or cs or backend:
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
    lanes += [
        lane("review", "Review Agent", ["diff", "architecture", "ownership", "risk list"], ["independent review report", "PASS or BLOCKED"], "independent-read-only-agent", implementation),
        lane("testing", "Test Agent", ["acceptance criteria", "review result", "build"], ["automated tests", "regression result", "screenshots or logs"], "independent-test-agent", ["review"]),
        lane("documentation", "Document Agent", ["approved implementation", "test evidence"], ["CHANGELOG.md", "ARCHITECTURE.md or justified N/A", "knowledge update"], "serial-after-testing", ["testing"]),
        lane("merge", "Merge Agent", ["review PASS", "test PASS", "closure PASS", "clean branch"], ["merge commit", "task state update"], "serial-gated", ["documentation"]),
        lane("release-control", "Master Agent", ["merged task", "release evidence", "risk and rollback plan"], ["release decision", "Released state or rollback"], "human-controlled", ["merge"]),
    ]
    return {
        "schema_version": "2.1.0", "request": text, "architecture": architecture, "client_families": client_families or (["unspecified"] if cs else []), "lanes": lanes,
        "policy": {"control_plane": "Master Agent", "parallel_write": "default maximum two active write tasks; separate Git worktree plus file locks", "same_file_write": "serial", "protected_branches": ["main", "develop", "release"], "human_controls": ["pause", "adjust", "insert", "resume"], "context_isolation": "project_id plus repository root"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--request", required=True); ap.add_argument("--output", default=".ai/workspace/task-map.json"); args = ap.parse_args()
    root = Path(args.root).resolve(); stack_path = root / ".ai" / "context" / "tech-stack.json"
    try: stack = json.loads(stack_path.read_text(encoding="utf-8")) if stack_path.exists() else {}
    except (OSError, json.JSONDecodeError): stack = {}
    data = route(args.request, stack); atomic_json(root / args.output, data); print(json.dumps(data, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
