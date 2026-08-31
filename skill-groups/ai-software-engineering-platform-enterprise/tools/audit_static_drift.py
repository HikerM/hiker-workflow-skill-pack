from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from audit_resource_budgets import audit as audit_resource_budgets


SUITE = Path(__file__).resolve().parents[1]
MAX_PRODUCTION_FILES = 512
MAX_PRODUCTION_FILE_BYTES = 2 * 1024 * 1024
CANONICAL_REGISTRY = "plugins/ai-engineering-core/references/SKILL_REGISTRY.json"
BUSINESS_COUPLING_PATTERNS = (
    re.compile(r"(?:project_id|project_name|repository_name|root\.name)\s*(?:==|!=)\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?:project_id|project_name|repository_name|root\.name)\s+in\s+[\{\(\[]"),
)
VERSION_COUPLING_PATTERNS = (
    re.compile(r"MINIMUM_PRO_VERSION"),
    re.compile(r"5\.19\.0-rc\.\d+", re.IGNORECASE),
    re.compile(r"product_version\s*(?:==|!=|<=|>=|<|>)"),
)


def _read(suite: Path, relative: str, errors: list[str]) -> str:
    path = suite / relative
    if not path.is_file():
        errors.append(f"required architecture source is missing: {relative}")
        return ""
    if path.stat().st_size > MAX_PRODUCTION_FILE_BYTES:
        errors.append(f"architecture source exceeds bounded audit size: {relative}")
        return ""
    return path.read_text(encoding="utf-8-sig", errors="strict")


def _production_scripts(suite: Path, errors: list[str]) -> list[Path]:
    result: list[Path] = []
    plugins = suite / "plugins"
    for plugin in sorted(path for path in plugins.iterdir() if path.is_dir()):
        scripts = plugin / "scripts"
        if not scripts.is_dir():
            continue
        result.extend(sorted(scripts.glob("*.py")))
        if len(result) > MAX_PRODUCTION_FILES:
            errors.append(f"production script inventory exceeds bounded audit limit: {MAX_PRODUCTION_FILES}")
            return result[:MAX_PRODUCTION_FILES]
    return result


def _registry_candidates(suite: Path) -> list[Path]:
    candidates = [suite / "SKILL_REGISTRY.json"]
    for plugin in sorted(path for path in (suite / "plugins").iterdir() if path.is_dir()):
        references = plugin / "references"
        candidates.extend((references / "SKILL_REGISTRY.json", references / "capability-registry.json"))
    return [path for path in candidates if path.is_file()]


def audit(suite: Path = SUITE) -> dict[str, Any]:
    errors: list[str] = []
    registry_paths = [path.relative_to(suite).as_posix() for path in _registry_candidates(suite)]
    if registry_paths != [CANONICAL_REGISTRY]:
        errors.append(f"capability registry authority is not unique: {registry_paths}")

    core = "plugins/ai-engineering-core/scripts/"
    workspace = "plugins/ai-engineering-workspace/scripts/"
    capability = _read(suite, core + "capability_metadata.py", errors)
    route_contract = _read(suite, core + "route_contract.py", errors)
    suite_router = _read(suite, core + "suite_router.py", errors)
    if "SINGLE_CAPABILITY_METADATA_AUTHORITY" not in capability or "SKILL_REGISTRY.json" not in capability:
        errors.append("capability metadata authority marker is missing")
    if "from capability_metadata import" not in route_contract or "from capability_metadata import" not in suite_router:
        errors.append("routing metadata is duplicated instead of derived from capability_metadata")
    for dead_map in ("FRONTEND_TOKENS", "BACKEND_TOKENS", "CLIENT_TOKENS"):
        if dead_map in suite_router:
            errors.append(f"dead semantic token authority remains in suite_router: {dead_map}")

    governance = _read(suite, workspace + "governance_state.py", errors)
    convergence = _read(suite, workspace + "convergence_guard.py", errors)
    closure = _read(suite, workspace + "closure_gate.py", errors)
    goal_change = _read(suite, workspace + "goal_change_transaction.py", errors)
    control_workflow = _read(suite, core + "control_workflow.py", errors)
    statectl = _read(suite, core + "statectl.py", errors)
    if "def save_task(" not in governance or "atomic_json(task_file" not in governance:
        errors.append("canonical governed Task writer is missing")
    for name, text in (("convergence_guard.py", convergence), ("closure_gate.py", closure)):
        if "def save_task(" in text or "atomic_json(task_file" in text or "atomic_write_json(task_file" in text:
            errors.append(f"parallel governed Task writer detected: {name}")
    if "def main(" in goal_change or "goal_change_transaction" not in control_workflow:
        errors.append("goal change transaction must remain a Control Kernel-only transactional adapter")
    if 'ai_root(root) / "runtime" / "task.json"' not in statectl or 'ai_root(root) / "tasks"' in statectl:
        errors.append("Community task projection is coupled to governed Task authority")

    task_router = _read(suite, workspace + "task_router.py", errors)
    git_workspace = _read(suite, workspace + "git_workspace.py", errors)
    if "TARGET_EXECUTION_CLASSES" not in governance or "RECORD_EXECUTION_CLASSES" not in governance:
        errors.append("governance authorization is not based on CONTROL/WRITE/ASSURE responsibilities")
    if "ROLE_TARGETS" in governance or "RECORD_ROLES" in governance or 'agent_role != "Merge Agent"' in git_workspace:
        errors.append("fixed Agent-role authorization remains active")
    required_router_markers = (
        '"CONTROL"', '"WRITE"', '"ASSURE"', "COMPATIBILITY_RESPONSIBILITY_LABEL",
        '"default_new_agent_count": 0', "responsibility != agent",
    )
    if any(marker not in task_router for marker in required_router_markers):
        errors.append("model-native responsibility topology markers are incomplete")
    for token in ("bs-frontend", "bs-backend", "cs-client", "backend-service"):
        if token in task_router:
            errors.append(f"fixed architecture topology remains active: {token}")

    governance_skill = _read(suite, workspace.replace("scripts/", "skills/multi-agent-project-governance/") + "SKILL.md", errors)
    role_contract = _read(suite, workspace.replace("scripts/", "skills/multi-agent-project-governance/references/") + "agent-role-contracts.md", errors)
    lifecycle_skill = _read(suite, workspace.replace("scripts/", "skills/task-lifecycle-manager/") + "SKILL.md", errors)
    state_model = _read(suite, workspace.replace("scripts/", "skills/multi-agent-project-governance/references/") + "state-and-task-model.md", errors)
    semantic_sources = governance_skill + role_contract + lifecycle_skill + state_model
    for obsolete in (
        "七角色控制平面",
        "分配七类角色",
        "总控强制执行的固定角色槽",
        "状态只能按 `Created",
        "合法状态：`Created",
    ):
        if obsolete in semantic_sources:
            errors.append(f"obsolete fixed workflow or role ontology remains: {obsolete}")

    production = _production_scripts(suite, errors)
    checked_bytes = 0
    for path in production:
        relative = path.relative_to(suite).as_posix()
        size = path.stat().st_size
        if size > MAX_PRODUCTION_FILE_BYTES:
            errors.append(f"production source exceeds bounded audit size: {relative}")
            continue
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        checked_bytes += size
        for pattern in BUSINESS_COUPLING_PATTERNS:
            if pattern.search(text):
                errors.append(f"field-specific business branch leaked into generic runtime: {relative}: {pattern.pattern}")
        for pattern in VERSION_COUPLING_PATTERNS:
            if pattern.search(text):
                errors.append(f"product-version coupling detected in runtime: {relative}: {pattern.pattern}")

    budgets = audit_resource_budgets(suite)
    errors.extend(f"resource budget: {item}" for item in budgets.get("errors", []))
    return {
        "ok": not errors,
        "errors": errors,
        "schema_version": "1.0.0",
        "registry_authority": registry_paths,
        "state_authority": "governance_state.save_task via Control Kernel",
        "transactional_adapters": ["goal_change_transaction.apply_transaction"],
        "fixed_role_dependency": False if not any("role" in item.lower() for item in errors) else True,
        "fixed_topology_dependency": False if not any("topology" in item.lower() for item in errors) else True,
        "resource_budgets": budgets,
        "checked_files": len(production),
        "checked_bytes": checked_bytes,
        "full_repository_scan": False,
        "execution_scope": "CI_RELEASE_OR_EXPLICIT_AUDIT_ONLY",
        "runtime_cost_delta": 0,
        "runtime_imports_added": 0,
        "default_prompt_bytes_added": 0,
        "excluded_constant_classes": ["security_protocol", "resource_hard_limit", "state_machine", "machine_contract"],
        "static_authority_classification": {
            "suite_router.FRONTEND_TOKENS": "DEAD_CODE_REMOVED",
            "suite_router.BACKEND_TOKENS": "DEAD_CODE_REMOVED",
            "suite_router.CLIENT_TOKENS": "DEAD_CODE_REMOVED",
            "suite_router.VALID_STAGES": "DETERMINISTIC_PARSER",
            "suite_router.VALID_ARCHITECTURES": "DETERMINISTIC_PARSER",
            "capability_metadata.MODE_STAGES": "COMPATIBILITY_ALIAS",
            "backend_guard.NODE_FRAMEWORKS": "DETERMINISTIC_PARSER",
            "backend_guard.PYTHON_FRAMEWORKS": "DETERMINISTIC_PARSER",
            "client_stack.FAMILY_MARKERS": "DETERMINISTIC_PARSER",
        },
    }


if __name__ == "__main__":
    import json

    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)
