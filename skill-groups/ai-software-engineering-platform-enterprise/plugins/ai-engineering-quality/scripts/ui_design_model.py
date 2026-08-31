from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from interaction_guard import evaluate_handoffs
from product_model_common import (
    MAX_DECISIONS,
    MAX_OBSERVATIONS,
    apply_decision,
    bounded_strings,
    make_decision,
    model_fingerprint,
    validate_decision,
    validate_observation,
)
from qualitylib import load_json, write_json


SCHEMA_VERSION = "2.0.0"
ARCHITECTURES = {"BS", "CS", "HYBRID"}
STRATEGY_KINDS = {"candidate", "hybrid", "custom"}
TEMPLATE_KEYS = {"sidebar", "cards", "columns", "card_count", "column_count"}
MAX_SCREENS = 256
MAX_SCREEN_ITEMS = 128
SCREEN_KEYS = {
    "screen_id", "primary_task", "information_hierarchy", "focal_point", "reading_path",
    "density_profile", "navigation_relationships", "content_regions", "components", "states",
    "interactions", "presentation_refs", "acceptance", "composition_strategy",
}


def default_model(project_ui_id: str, architecture: str) -> dict[str, Any]:
    model: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_ui_id": project_ui_id,
        "revision": 0,
        "architecture": architecture,
        "technology": {
            "status": "UNKNOWN",
            "subject": "technology-profile",
            "value": None,
            "source_refs": [],
        },
        "project_facts": [],
        "visual_context": [],
        "decisions": [],
        "screens": [],
        "migration": {"status": "NATIVE_5_18", "source_schema": None, "source_ref": None},
    }
    model["fingerprint"] = model_fingerprint(model)
    return model


def _strings(value: Any, field: str, errors: list[dict[str, str]], required: bool = False) -> list[str]:
    result = bounded_strings(value, MAX_SCREEN_ITEMS, field, errors)
    if required and not result:
        errors.append({"code": "MISSING_SEMANTIC_CONTENT", "field": field})
    return result


def _validate_strategy(value: Any, field: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, dict) or value.get("kind") not in STRATEGY_KINDS:
        errors.append({"code": "INVALID_COMPOSITION_STRATEGY", "field": field})
        return
    if not isinstance(value.get("rationale"), str) or not value.get("rationale", "").strip():
        errors.append({"code": "MISSING_STRATEGY_RATIONALE", "field": field})
    _strings(value.get("candidates", []), f"{field}.candidates", errors)


def _validate_screen(value: Any, index: int, errors: list[dict[str, str]]) -> None:
    field = f"screens[{index}]"
    if not isinstance(value, dict):
        errors.append({"code": "INVALID_SCREEN", "field": field})
        return
    illegal = sorted(TEMPLATE_KEYS.intersection(value))
    if illegal:
        errors.append({"code": "TEMPLATE_SHAPE_FORBIDDEN", "field": field, "detail": ",".join(illegal)})
    for required in ("screen_id", "primary_task", "focal_point", "density_profile"):
        if not isinstance(value.get(required), str) or not value.get(required, "").strip():
            errors.append({"code": "MISSING_SCREEN_FIELD", "field": f"{field}.{required}"})
    _strings(value.get("information_hierarchy"), f"{field}.information_hierarchy", errors, required=True)
    _strings(value.get("reading_path"), f"{field}.reading_path", errors, required=True)
    _strings(value.get("navigation_relationships", []), f"{field}.navigation_relationships", errors)
    _strings(value.get("components", []), f"{field}.components", errors)
    _strings(value.get("states", []), f"{field}.states", errors, required=True)
    _strings(value.get("interactions", []), f"{field}.interactions", errors)
    _strings(value.get("presentation_refs", []), f"{field}.presentation_refs", errors)
    _strings(value.get("acceptance"), f"{field}.acceptance", errors, required=True)
    regions = value.get("content_regions", [])
    if not isinstance(regions, list) or not regions:
        errors.append({"code": "MISSING_CONTENT_REGIONS", "field": field})
    else:
        for region_index, region in enumerate(regions[:MAX_SCREEN_ITEMS]):
            if not isinstance(region, dict) or not all(isinstance(region.get(key), str) and region.get(key, "").strip() for key in ("region_id", "semantic_role")):
                errors.append({"code": "INVALID_CONTENT_REGION", "field": f"{field}.content_regions[{region_index}]"})
    _validate_strategy(value.get("composition_strategy"), f"{field}.composition_strategy", errors)


def validate(model: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(model, dict):
        return {"status": "BLOCKED", "errors": [{"code": "MODEL_MUST_BE_OBJECT", "field": "$"}]}
    if model.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "UNSUPPORTED_SCHEMA_VERSION", "field": "schema_version"})
    if model.get("architecture") not in ARCHITECTURES:
        errors.append({"code": "INVALID_ARCHITECTURE", "field": "architecture"})
    if not isinstance(model.get("project_ui_id"), str) or not model.get("project_ui_id", "").strip():
        errors.append({"code": "MISSING_PROJECT_UI_ID", "field": "project_ui_id"})
    validate_observation(model.get("technology"), "technology", errors)
    for collection in ("project_facts", "visual_context"):
        values = model.get(collection, [])
        if not isinstance(values, list):
            errors.append({"code": "INVALID_OBSERVATION_LIST", "field": collection})
            continue
        if len(values) > MAX_OBSERVATIONS:
            errors.append({"code": "OBSERVATION_BUDGET_EXCEEDED", "field": collection})
        for index, value in enumerate(values[:MAX_OBSERVATIONS]):
            validate_observation(value, f"{collection}[{index}]", errors)
    decisions = model.get("decisions", [])
    if not isinstance(decisions, list):
        errors.append({"code": "INVALID_DECISION_LIST", "field": "decisions"})
    else:
        if len(decisions) > MAX_DECISIONS:
            errors.append({"code": "DECISION_BUDGET_EXCEEDED", "field": "decisions"})
        ids: set[str] = set()
        active_topics: set[str] = set()
        for index, decision in enumerate(decisions[:MAX_DECISIONS]):
            validate_decision(decision, f"decisions[{index}]", errors)
            if isinstance(decision, dict):
                decision_id = str(decision.get("decision_id") or "")
                topic = str(decision.get("topic") or "")
                if decision_id in ids:
                    errors.append({"code": "DUPLICATE_DECISION_ID", "field": f"decisions[{index}]"})
                ids.add(decision_id)
                if decision.get("status") == "ACTIVE" and topic in active_topics:
                    errors.append({"code": "MULTIPLE_ACTIVE_DECISIONS", "field": f"decisions[{index}]"})
                if decision.get("status") == "ACTIVE":
                    active_topics.add(topic)
    screens = model.get("screens", [])
    if not isinstance(screens, list):
        errors.append({"code": "INVALID_SCREEN_LIST", "field": "screens"})
    else:
        if len(screens) > MAX_SCREENS:
            errors.append({"code": "SCREEN_BUDGET_EXCEEDED", "field": "screens"})
        for index, screen in enumerate(screens[:MAX_SCREENS]):
            _validate_screen(screen, index, errors)
    handoff_continuity = evaluate_handoffs(model.get("handoffs"))
    errors.extend(
        {**item, "field": "handoffs"}
        for item in handoff_continuity.get("errors", [])
    )
    expected = model_fingerprint(model)
    if model.get("fingerprint") != expected:
        errors.append({"code": "MODEL_FINGERPRINT_MISMATCH", "field": "fingerprint"})
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "BLOCKED" if errors else "PASS",
        "errors": errors,
        "handoff_continuity": handoff_continuity,
        "summary": {
            "screens": len(screens) if isinstance(screens, list) else 0,
            "decisions": len(decisions) if isinstance(decisions, list) else 0,
            "handoffs": handoff_continuity["handoffs"],
            "observations": sum(len(model.get(key, [])) for key in ("project_facts", "visual_context") if isinstance(model.get(key), list)),
        },
    }


def migrate_legacy(legacy: Any, project_ui_id: str, architecture: str, source_ref: str) -> dict[str, Any]:
    model = default_model(project_ui_id, architecture)
    if not isinstance(legacy, dict):
        raise ValueError("legacy UI contract must be an object")
    model["migration"] = {
        "status": "MIGRATED_BOUNDED",
        "source_schema": str(legacy.get("schema_version") or "unknown"),
        "source_ref": source_ref,
    }
    known_technology = legacy.get("technology") or legacy.get("framework")
    if known_technology:
        model["technology"] = {
            "status": "INFERRED",
            "subject": "technology-profile",
            "value": str(known_technology),
            "source_refs": [source_ref],
        }
    legacy_screens = legacy.get("screens", [])
    if isinstance(legacy_screens, list):
        for raw in legacy_screens[:MAX_SCREENS]:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            model["screens"].append({
                "screen_id": str(raw["id"]),
                "primary_task": str(raw.get("primary_task") or "UNKNOWN: confirm with project evidence"),
                "information_hierarchy": list(raw.get("information_hierarchy") or ["UNKNOWN"]),
                "focal_point": str(raw.get("focal_point") or "UNKNOWN"),
                "reading_path": list(raw.get("reading_path") or ["UNKNOWN"]),
                "density_profile": str(raw.get("density_profile") or "UNKNOWN"),
                "navigation_relationships": list(raw.get("navigation_relationships") or []),
                "content_regions": list(raw.get("content_regions") or [{"region_id": "legacy-unknown", "semantic_role": "UNKNOWN"}]),
                "components": list(raw.get("components") or []),
                "states": list(raw.get("states") or ["default"]),
                "interactions": list(raw.get("interactions") or []),
                "presentation_refs": list(raw.get("presentation_refs") or []),
                "acceptance": list(raw.get("acceptance") or ["REQUIRES_REVIEW"]),
                "composition_strategy": {
                    "kind": "custom",
                    "candidates": [],
                    "rationale": "Migrated without inventing a template; requires review against current project facts.",
                },
            })
    model["fingerprint"] = model_fingerprint(model)
    return model


def patch_screen(model: dict[str, Any], screen_id: str, patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(patch, dict) or not patch:
        raise ValueError("screen patch must be a non-empty object")
    unsupported = sorted(set(patch) - SCREEN_KEYS)
    if unsupported:
        raise ValueError(f"screen patch has unsupported fields: {', '.join(unsupported)}")
    if "screen_id" in patch and patch["screen_id"] != screen_id:
        raise ValueError("screen_id cannot be changed by an incremental patch")
    screens = model.get("screens")
    if not isinstance(screens, list):
        raise ValueError("UI model screens are invalid")
    matches = [index for index, item in enumerate(screens) if isinstance(item, dict) and item.get("screen_id") == screen_id]
    if len(matches) != 1:
        raise ValueError("incremental screen patch requires exactly one existing screen")
    updated = copy.deepcopy(model)
    index = matches[0]
    before = model_fingerprint(updated["screens"][index])
    updated["screens"][index].update(copy.deepcopy(patch))
    errors: list[dict[str, str]] = []
    _validate_screen(updated["screens"][index], index, errors)
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    updated["revision"] = int(updated.get("revision", 0)) + 1
    updated["fingerprint"] = model_fingerprint(updated)
    return updated, {
        "mode": "INCREMENTAL_SCREEN_PATCH",
        "affected_scope": [f"screen:{screen_id}"],
        "before_screen_fingerprint": before,
        "after_screen_fingerprint": model_fingerprint(updated["screens"][index]),
        "preserved_screen_count": len(screens) - 1,
        "writes": 1,
    }


def inspect(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "status": "LEGACY_NO_UI_IR",
            "path": str(path),
            "writes": 0,
            "migration_required": True,
            "message": "No legacy UI IR exists; migrate incrementally for an affected UI scope only.",
        }
    model = load_json(path)
    result = validate(model)
    return {**result, "path": str(path), "writes": 0, "migration_required": result["status"] != "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker semantic UI design model")
    parser.add_argument("--root", default=".")
    parser.add_argument("--model", default=".ai/ui/project-ui.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    sub.add_parser("validate")
    command = sub.add_parser("init")
    command.add_argument("--project-ui-id", required=True)
    command.add_argument("--architecture", choices=sorted(ARCHITECTURES), required=True)
    command = sub.add_parser("migrate")
    command.add_argument("--legacy", required=True)
    command.add_argument("--project-ui-id", required=True)
    command.add_argument("--architecture", choices=sorted(ARCHITECTURES), required=True)
    command = sub.add_parser("decide")
    command.add_argument("--decision-id", required=True)
    command.add_argument("--authority", required=True)
    command.add_argument("--topic", required=True)
    command.add_argument("--value-json", required=True)
    command.add_argument("--rationale", required=True)
    command.add_argument("--source-ref", action="append", default=[])
    command.add_argument("--affected", action="append", default=[])
    command.add_argument("--supersedes")
    command = sub.add_parser("patch-screen")
    command.add_argument("--screen-id", required=True)
    command.add_argument("--patch-json", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    path = (root / args.model).resolve()
    if args.command == "inspect":
        result = inspect(path)
    elif args.command == "validate":
        result = validate(load_json(path)) if path.is_file() else inspect(path)
    elif args.command == "init":
        if path.exists():
            raise SystemExit("UI model already exists")
        model = default_model(args.project_ui_id, args.architecture)
        write_json(path, model)
        result = {"status": "CREATED", "path": str(path), "fingerprint": model["fingerprint"], "writes": 1}
    elif args.command == "migrate":
        legacy_path = (root / args.legacy).resolve()
        model = migrate_legacy(load_json(legacy_path), args.project_ui_id, args.architecture, args.legacy)
        checked = validate(model)
        if checked["status"] != "PASS":
            result = checked
        else:
            write_json(path, model)
            result = {"status": "MIGRATED", "path": str(path), "fingerprint": model["fingerprint"], "writes": 1}
    elif args.command == "decide":
        model = load_json(path)
        if not isinstance(model, dict):
            raise SystemExit("UI model is missing or invalid")
        decision = make_decision(
            args.decision_id,
            args.authority,
            args.topic,
            json.loads(args.value_json),
            args.rationale,
            args.source_ref,
            args.affected,
            args.supersedes,
        )
        updated, impact = apply_decision(model, decision)
        checked = validate(updated)
        if checked["status"] != "PASS":
            result = checked
        else:
            write_json(path, updated)
            result = {"status": "UPDATED", "path": str(path), "writes": 1, "impact": impact}
    else:
        model = load_json(path)
        if not isinstance(model, dict):
            raise SystemExit("UI model is missing or invalid")
        try:
            updated, impact = patch_screen(model, args.screen_id, json.loads(args.patch_json))
        except (ValueError, json.JSONDecodeError) as exc:
            result = {"status": "BLOCKED", "errors": [{"code": "INVALID_SCREEN_PATCH", "detail": str(exc)}]}
        else:
            checked = validate(updated)
            if checked["status"] != "PASS":
                result = checked
            else:
                write_json(path, updated)
                result = {"status": "UPDATED", "path": str(path), "writes": 1, "impact": impact}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
