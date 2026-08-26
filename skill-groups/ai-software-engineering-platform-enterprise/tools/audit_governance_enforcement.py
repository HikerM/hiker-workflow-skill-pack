from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUITE = Path(__file__).resolve().parents[1]
MAP = SUITE / "docs" / "5.18-governance-enforcement-map.json"
CLASSIFICATIONS = {"reasoning_guidance", "machine_enforceable", "hybrid"}
DEFAULT_PATHS = (
    "plugins/ai-engineering-core/skills/ai-engineering-router/SKILL.md",
    "plugins/ai-engineering-core/scripts/suite_router.py",
    "plugins/ai-engineering-core/scripts/control_admission.py",
)


def audit(suite: Path = SUITE, map_path: Path | None = None) -> dict[str, Any]:
    path = map_path or suite / "docs" / "5.18-governance-enforcement-map.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"governance enforcement map is invalid: {exc}"]}
    errors: list[str] = []
    rules = payload.get("rules")
    if payload.get("schema_version") != "1.0.0" or not isinstance(rules, list) or not rules:
        errors.append("governance enforcement map has an invalid shape")
        rules = []
    ids: set[str] = set()
    machine_paths: set[str] = set()
    counts = {name: 0 for name in CLASSIFICATIONS}
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"rules[{index}] must be an object")
            continue
        rule_id = str(rule.get("id") or "")
        classification = rule.get("classification")
        runtime = rule.get("runtime_enforcement")
        tests = rule.get("tests")
        if not rule_id or rule_id in ids:
            errors.append(f"rules[{index}] has a missing or duplicate id")
        ids.add(rule_id)
        if classification not in CLASSIFICATIONS:
            errors.append(f"{rule_id}: invalid classification")
            continue
        counts[classification] += 1
        if not isinstance(runtime, list) or not isinstance(tests, list):
            errors.append(f"{rule_id}: runtime_enforcement and tests must be arrays")
            continue
        if classification == "reasoning_guidance":
            if runtime or tests:
                errors.append(f"{rule_id}: reasoning guidance claims deterministic enforcement")
            if not rule.get("model_responsibility"):
                errors.append(f"{rule_id}: reasoning guidance lacks model responsibility")
        else:
            if not runtime or not tests:
                errors.append(f"{rule_id}: deterministic rule lacks runtime or test evidence")
            for relative in [*runtime, *tests]:
                target = suite / str(relative)
                if not target.is_file():
                    errors.append(f"{rule_id}: referenced evidence does not exist: {relative}")
            machine_paths.update(str(item) for item in runtime)
        if rule.get("default_activation") is not False:
            errors.append(f"{rule_id}: 5.18 governance must not enter the default path")
    if payload.get("default_prompt_bytes_added") != 0:
        errors.append("governance enforcement map reports default prompt growth")
    default_text = "\n".join((suite / relative).read_text(encoding="utf-8", errors="ignore") for relative in DEFAULT_PATHS)
    for runtime_path in machine_paths:
        module = Path(runtime_path).stem
        if module in default_text:
            errors.append(f"machine governance entered the default routing path: {module}")
    return {
        "ok": not errors,
        "map": path.relative_to(suite).as_posix(),
        "rule_count": len(rules),
        "classifications": counts,
        "default_prompt_bytes_added": payload.get("default_prompt_bytes_added"),
        "default_path_imports": 0 if not errors else None,
        "errors": errors,
    }


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 2)
