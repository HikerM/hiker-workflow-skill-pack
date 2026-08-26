from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from component_registry_v2 import validate as validate_registry
from architecture_product_profile import validate as validate_architecture_profile
from error_experience_guard import validate_contract as validate_error_contract
from presentation_guard import validate_contract as validate_presentation_contract
from qualitylib import load_json
from ui_design_model import validate as validate_design


MAX_EVIDENCE_RECORDS = 512
REQUIRED_RESULTS = ("content", "presentation", "error")


def evaluate(root: Path) -> dict[str, Any]:
    ui = root / ".ai" / "ui"
    design_path = ui / "project-ui.json"
    if not design_path.is_file():
        return {"status": "NOT_APPLICABLE", "blockers": [], "reason": "no 5.18 UI model", "reads": 1}
    design = load_json(design_path)
    registry = load_json(ui / "component-registry.json")
    presentation = load_json(ui / "presentation-contract.json")
    error_contract = load_json(ui / "error-contract.json")
    architecture_profile = load_json(ui / "architecture-profile.json")
    index = load_json(ui / "evidence" / "index.json")
    blockers: list[dict[str, str]] = []
    checks = {
        "design": validate_design(design),
        "registry": validate_registry(registry, release=True),
        "presentation": validate_presentation_contract(presentation),
        "error_contract": validate_error_contract(error_contract),
        "architecture_profile": validate_architecture_profile(architecture_profile),
    }
    for name, result in checks.items():
        if result.get("status") != "PASS":
            blockers.append({"code": f"{name.upper()}_NOT_RELEASE_READY", "detail": str(result.get("status"))})
    screens = design.get("screens", []) if isinstance(design, dict) else []
    if not screens:
        blockers.append({"code": "NO_RELEASE_UI_SCREENS", "detail": "UI model has no screen baseline"})
    registry_component_ids = {
        str(component.get("component_id"))
        for component in registry.get("components", [])
        if isinstance(component, dict) and component.get("component_id")
    } if isinstance(registry, dict) else set()
    for screen in screens:
        for component_id in dict.fromkeys(screen.get("components", [])):
            if component_id not in registry_component_ids:
                blockers.append({"code": "DESIGN_COMPONENT_NOT_REGISTERED", "detail": str(component_id)})
    records = index.get("records", []) if isinstance(index, dict) else []
    if not isinstance(records, list):
        blockers.append({"code": "INVALID_PRODUCT_EVIDENCE_INDEX", "detail": "records must be an array"})
        records = []
    if len(records) > MAX_EVIDENCE_RECORDS:
        blockers.append({"code": "PRODUCT_EVIDENCE_BUDGET_EXCEEDED", "detail": str(len(records))})
    current_visual: set[tuple[str, str]] = set()
    for record in records[:MAX_EVIDENCE_RECORDS]:
        if not isinstance(record, dict):
            blockers.append({"code": "INVALID_PRODUCT_EVIDENCE_RECORD", "detail": "non-object record"})
            continue
        if record.get("evidence_type") == "VISUAL_FIDELITY" and record.get("verdict") == "PASS":
            if record.get("design_fingerprint") == design.get("fingerprint") and record.get("registry_fingerprint") == registry.get("fingerprint") and record.get("candidate_id") and isinstance(record.get("goal_revision"), int):
                current_visual.add((str(record.get("screen_id")), str(record.get("state"))))
            else:
                blockers.append({"code": "STALE_OR_UNBOUND_VISUAL_EVIDENCE", "detail": str(record.get("evidence_id") or "unknown")})
        elif record.get("status") in {"STALE", "BLOCKED", "INVALID"} or record.get("verdict") in {"STALE", "BLOCKED"}:
            blockers.append({"code": "NON_CURRENT_PRODUCT_EVIDENCE", "detail": str(record.get("id") or record.get("evidence_id") or "unknown")})
    for screen in screens:
        screen_id = str(screen.get("screen_id") or "")
        if (screen_id, "default") not in current_visual:
            blockers.append({"code": "MISSING_CURRENT_DEFAULT_VISUAL", "detail": screen_id})
    result_checks: dict[str, Any] = {}
    for name in REQUIRED_RESULTS:
        result = load_json(ui / "evidence" / f"{name}.json")
        result_checks[name] = result
        if not isinstance(result, dict) or result.get("status") != "PASS":
            blockers.append({"code": f"{name.upper()}_EVIDENCE_NOT_PASS", "detail": "missing or blocked"})
    return {
        "status": "BLOCKED" if blockers else "PASS",
        "blockers": blockers,
        "checks": checks,
        "result_checks": {name: value.get("status") if isinstance(value, dict) else None for name, value in result_checks.items()},
        "summary": {"screens": len(screens), "evidence_records": len(records), "current_default_visuals": len(current_visual)},
        "reads": 9,
        "cold_history_scanned": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker 5.18 product release gate")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    result = evaluate(Path(args.root).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
