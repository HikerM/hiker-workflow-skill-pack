from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


SUITE = Path(__file__).resolve().parents[1]


# Fixed, bounded call sites. This is deliberately not a repository-wide scan.
ENFORCEMENT_POINTS: dict[str, tuple[str, ...]] = {
    "plugins/ai-engineering-core/scripts/bounded_run.py": ("effective_value", '"output"'),
    "plugins/ai-engineering-core/scripts/community_pro_bridge.py": ("RESOURCE_HARD_MAX", '"runtime_locator_bytes"'),
    "plugins/ai-engineering-core/scripts/control_common.py": ("RESOURCE_HARD_MAX", '"admission_output_chars"'),
    "plugins/ai-engineering-core/scripts/engineering_manifests.py": ("effective_budget", '"manifest_scan"'),
    "plugins/ai-engineering-workspace/scripts/workspacelib.py": ("resource_budget", "RESOURCE_HARD_MAX"),
    "plugins/ai-engineering-workspace/scripts/bounded_context.py": ("effective_budget", '"context"'),
    "plugins/ai-engineering-workspace/scripts/session_pool.py": ("effective_budget", '"execution"'),
    "plugins/ai-engineering-workspace/scripts/governance_state.py": ("effective_budget", '"task"'),
    "plugins/ai-engineering-workspace/scripts/implementation_guard.py": ("RESOURCE_HARD_MAX", '"implementation_registry"'),
    "plugins/ai-engineering-workspace/scripts/task_router.py": ("RESOURCE_HARD_MAX", '"max_planned_lanes"'),
    "plugins/ai-engineering-workspace/scripts/event_budget.py": ("RESOURCE_HARD_MAX", '"event"'),
    "plugins/ai-engineering-workspace/scripts/desktop_pressure.py": ("RESOURCE_HARD_MAX", '"execution"'),
    "plugins/ai-engineering-web/scripts/backend_guard.py": ("effective_budget", '"source_scan"'),
    "plugins/ai-engineering-web/scripts/backend_specialization.py": ("effective_budget", '"source_scan"'),
    "plugins/ai-engineering-web/scripts/weblib.py": ("effective_value", '"source_scan"'),
    "plugins/ai-engineering-unity/scripts/unity_specialization.py": ("effective_budget", '"source_scan"'),
    "plugins/ai-engineering-unity/scripts/qt_specialization.py": ("effective_budget", '"source_scan"'),
    "plugins/ai-engineering-quality/scripts/test_plan.py": ("effective_budget", '"source_scan"'),
}


def _load_authority(suite: Path) -> ModuleType:
    path = suite / "plugins" / "ai-engineering-core" / "scripts" / "resource_budget.py"
    spec = importlib.util.spec_from_file_location("hiker_resource_budget_audit_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load resource budget authority: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(suite: Path = SUITE) -> dict[str, Any]:
    errors: list[str] = []
    try:
        authority = _load_authority(suite)
    except Exception as exc:  # noqa: BLE001 - release audit must fail closed
        return {
            "ok": False,
            "errors": [f"resource budget authority load failed: {type(exc).__name__}: {exc}"],
            "checked_files": 0,
            "full_repository_scan": False,
            "default_prompt_bytes_added": 0,
        }

    hard_max = getattr(authority, "HARD_MAX", {})
    defaults = getattr(authority, "DEFAULT_BUDGETS", {})
    effective_budget = getattr(authority, "effective_budget", None)
    receipt = authority.authority_receipt() if hasattr(authority, "authority_receipt") else {}
    if not isinstance(hard_max, dict) or not hard_max:
        errors.append("resource budget HARD_MAX is missing")
    if set(defaults) != set(hard_max):
        errors.append("resource budget defaults and hard-max domains differ")
    if not callable(effective_budget):
        errors.append("resource budget effective_budget function is missing")
    else:
        for domain, limits in hard_max.items():
            if not isinstance(limits, dict) or not limits:
                errors.append(f"resource budget domain is empty: {domain}")
                continue
            resolved = effective_budget(domain, {key: int(value) * 1_000_000 for key, value in limits.items()})
            if resolved != limits:
                errors.append(f"resource budget can exceed hard max: {domain}")
            for key, value in defaults.get(domain, {}).items():
                if int(value) > int(limits.get(key, -1)):
                    errors.append(f"default exceeds hard max: {domain}.{key}")
    if receipt.get("rule") != "EFFECTIVE_BUDGET_LESS_THAN_OR_EQUAL_TO_HARD_MAX":
        errors.append("resource budget receipt does not declare the hard-max invariant")

    for relative, markers in ENFORCEMENT_POINTS.items():
        path = suite / relative
        if not path.is_file():
            errors.append(f"resource budget enforcement point missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            errors.append(f"resource budget enforcement disconnected: {relative}: {', '.join(missing)}")

    return {
        "ok": not errors,
        "errors": errors,
        "schema_version": receipt.get("schema_version"),
        "domains": sorted(hard_max),
        "checked_files": len(ENFORCEMENT_POINTS),
        "full_repository_scan": False,
        "default_prompt_bytes_added": 0,
    }


if __name__ == "__main__":
    import json

    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)
