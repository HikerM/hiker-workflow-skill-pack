from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from product_model_common import bounded_strings, fingerprint
from qualitylib import load_json, write_json


SCHEMA_VERSION = "2.0.0"
PLATFORMS = {"BS", "CS", "SHARED"}
OBSERVATION_STATUSES = {"OBSERVED", "INFERRED", "UNKNOWN"}
IMPLEMENTATION_LAYERS = {"token", "primitive", "reusable_component", "domain_component", "page_composition", "project_native"}
MAX_COMPONENTS = 2000
MAX_ITEMS = 64


def registry_fingerprint(registry: dict[str, Any]) -> str:
    payload = {key: value for key, value in registry.items() if key not in {"fingerprint", "updated_at"}}
    return fingerprint(payload)


def empty_registry(registry_id: str, scope: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry_id,
        "revision": 0,
        "scope": scope or {"mode": "AFFECTED", "refs": []},
        "components": [],
        "migration": {"status": "NATIVE_5_18", "source_schema": None, "source_ref": None},
    }
    data["fingerprint"] = registry_fingerprint(data)
    return data


def _status_value(value: Any, field: str, errors: list[dict[str, str]], required_value: bool = False) -> None:
    if not isinstance(value, dict) or value.get("status") not in OBSERVATION_STATUSES:
        errors.append({"code": "INVALID_EVIDENCED_VALUE", "field": field})
        return
    refs = value.get("source_refs", [])
    bounded_strings(refs, 16, f"{field}.source_refs", errors)
    if value.get("status") == "OBSERVED" and not refs:
        errors.append({"code": "OBSERVED_REQUIRES_SOURCE", "field": field})
    if value.get("status") == "UNKNOWN" and value.get("value") not in (None, "", [], {}):
        errors.append({"code": "UNKNOWN_MUST_NOT_ASSERT_VALUE", "field": field})
    if required_value and value.get("status") != "UNKNOWN" and value.get("value") in (None, "", [], {}):
        errors.append({"code": "EVIDENCED_VALUE_MISSING", "field": field})


def component_fingerprint(component: dict[str, Any]) -> str:
    payload = {key: value for key, value in component.items() if key != "fingerprint"}
    return fingerprint(payload)


def validate(registry: Any, release: bool = False) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    gaps: list[dict[str, str]] = []
    if not isinstance(registry, dict):
        return {"status": "BLOCKED", "errors": [{"code": "REGISTRY_MUST_BE_OBJECT", "field": "$"}], "gaps": []}
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "UNSUPPORTED_SCHEMA_VERSION", "field": "schema_version"})
    if not isinstance(registry.get("registry_id"), str) or not registry.get("registry_id", "").strip():
        errors.append({"code": "MISSING_REGISTRY_ID", "field": "registry_id"})
    scope = registry.get("scope")
    if not isinstance(scope, dict) or scope.get("mode") not in {"AFFECTED", "EXPLICIT"}:
        errors.append({"code": "INVALID_BOUNDED_SCOPE", "field": "scope"})
    else:
        bounded_strings(scope.get("refs", []), MAX_ITEMS, "scope.refs", errors)
    components = registry.get("components", [])
    if not isinstance(components, list):
        errors.append({"code": "INVALID_COMPONENT_LIST", "field": "components"})
        components = []
    if len(components) > MAX_COMPONENTS:
        errors.append({"code": "COMPONENT_BUDGET_EXCEEDED", "field": "components"})
    ids: set[str] = set()
    for index, component in enumerate(components[:MAX_COMPONENTS]):
        field = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append({"code": "INVALID_COMPONENT", "field": field})
            continue
        component_id = str(component.get("component_id") or "")
        if not component_id:
            errors.append({"code": "MISSING_COMPONENT_ID", "field": field})
        elif component_id in ids:
            errors.append({"code": "DUPLICATE_COMPONENT_ID", "field": field})
        ids.add(component_id)
        if component.get("platform") not in PLATFORMS:
            errors.append({"code": "INVALID_PLATFORM", "field": field})
        if component.get("implementation_layer") not in IMPLEMENTATION_LAYERS:
            errors.append({"code": "INVALID_IMPLEMENTATION_LAYER", "field": field})
        for key in ("semantic_role", "design_component", "code_component", "technology_adapter"):
            _status_value(component.get(key), f"{field}.{key}", errors, required_value=key in {"semantic_role", "code_component"})
            if isinstance(component.get(key), dict) and component[key].get("status") == "UNKNOWN":
                gaps.append({"code": f"UNKNOWN_{key.upper()}", "field": f"{field}.{key}"})
        for key in ("variants", "states", "tokens", "accessibility", "usage_rules"):
            bounded_strings(component.get(key, []), MAX_ITEMS, f"{field}.{key}", errors)
        if component.get("fingerprint") != component_fingerprint(component):
            errors.append({"code": "COMPONENT_FINGERPRINT_MISMATCH", "field": field})
    if registry.get("fingerprint") != registry_fingerprint(registry):
        errors.append({"code": "REGISTRY_FINGERPRINT_MISMATCH", "field": "fingerprint"})
    if release and gaps:
        errors.extend({"code": "RELEASE_COMPONENT_GAP", "field": item["field"]} for item in gaps)
    status = "BLOCKED" if errors else "PASS_WITH_GAPS" if gaps else "PASS"
    return {"schema_version": SCHEMA_VERSION, "status": status, "errors": errors, "gaps": gaps, "summary": {"components": len(components), "gaps": len(gaps)}}


def migrate_legacy(legacy: Any, registry_id: str, source_ref: str, platform: str = "BS") -> dict[str, Any]:
    if not isinstance(legacy, dict):
        raise ValueError("legacy component registry must be an object")
    registry = empty_registry(registry_id, {"mode": "EXPLICIT", "refs": [source_ref]})
    registry["migration"] = {"status": "MIGRATED_BOUNDED", "source_schema": str(legacy.get("schema_version") or "unknown"), "source_ref": source_ref}
    for row in list(legacy.get("components") or [])[:MAX_COMPONENTS]:
        if not isinstance(row, dict) or not row.get("path"):
            continue
        name = str(row.get("name") or Path(str(row["path"])).stem)
        code_ref = str(row["path"])
        component = {
            "component_id": f"legacy:{platform.lower()}:{name}",
            "semantic_role": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "design_component": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "code_component": {"status": "OBSERVED", "value": {"path": code_ref, "symbol": name, "source_fingerprint": row.get("sha256")}, "source_refs": [source_ref, code_ref]},
            "variants": [],
            "states": [],
            "tokens": [],
            "accessibility": [],
            "platform": platform,
            "usage_rules": [],
            "technology_adapter": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "implementation_layer": "project_native",
        }
        component["fingerprint"] = component_fingerprint(component)
        registry["components"].append(component)
    registry["fingerprint"] = registry_fingerprint(registry)
    return registry


def merge_observations(registry: dict[str, Any], observations: Any) -> dict[str, Any]:
    if not isinstance(observations, dict) or observations.get("scope", {}).get("mode") not in {"AFFECTED", "EXPLICIT"}:
        raise ValueError("adapter observations require a bounded scope")
    rows = observations.get("components", [])
    if not isinstance(rows, list):
        raise ValueError("adapter components must be a list")
    updated = copy.deepcopy(registry)
    by_id = {str(item.get("component_id")): item for item in updated.get("components", []) if isinstance(item, dict)}
    for row in rows[:MAX_COMPONENTS]:
        if not isinstance(row, dict) or not row.get("component_id"):
            continue
        component_id = str(row["component_id"])
        current = by_id.get(component_id)
        if current is None:
            current = copy.deepcopy(row)
            updated.setdefault("components", []).append(current)
            by_id[component_id] = current
        else:
            # Adapter observations refresh code facts only. Design semantics remain
            # owned by the explicit product registry decision.
            for key in ("code_component", "technology_adapter", "tokens", "states", "variants", "accessibility"):
                if key in row:
                    current[key] = copy.deepcopy(row[key])
        current["fingerprint"] = component_fingerprint(current)
    updated["revision"] = int(updated.get("revision", 0)) + 1
    updated["scope"] = copy.deepcopy(observations["scope"])
    updated["fingerprint"] = registry_fingerprint(updated)
    return updated


def design_to_code_plan(registry: dict[str, Any], affected: list[str]) -> dict[str, Any]:
    selected = [item for item in registry.get("components", []) if item.get("component_id") in set(affected)]
    layers = ["token", "primitive", "reusable_component", "domain_component", "page_composition", "project_native"]
    ordered = sorted(selected, key=lambda item: (layers.index(str(item.get("implementation_layer"))), str(item.get("component_id"))))
    return {
        "schema_version": "1.0.0",
        "registry_fingerprint": registry.get("fingerprint"),
        "scope": list(dict.fromkeys(affected)),
        "architecture_policy": "respect-project-native",
        "steps": [{"component_id": item.get("component_id"), "implementation_layer": item.get("implementation_layer"), "code_component": item.get("code_component")} for item in ordered],
        "unresolved": sorted(set(affected) - {str(item.get("component_id")) for item in selected}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker component registry 2.0")
    parser.add_argument("--root", default=".")
    parser.add_argument("--registry", default=".ai/ui/component-registry.json")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("init")
    command.add_argument("--registry-id", required=True)
    command.add_argument("--scope-ref", action="append", default=[])
    command = sub.add_parser("migrate")
    command.add_argument("--legacy", required=True)
    command.add_argument("--registry-id", required=True)
    command.add_argument("--platform", choices=sorted(PLATFORMS), default="BS")
    command = sub.add_parser("validate")
    command.add_argument("--release", action="store_true")
    command = sub.add_parser("merge-observations")
    command.add_argument("--observations", required=True)
    command = sub.add_parser("plan")
    command.add_argument("--component", action="append", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    path = (root / args.registry).resolve()
    if args.command == "init":
        if path.exists():
            raise SystemExit("component registry already exists")
        registry = empty_registry(args.registry_id, {"mode": "EXPLICIT", "refs": args.scope_ref})
        write_json(path, registry)
        result = {"status": "CREATED", "path": str(path), "writes": 1}
    elif args.command == "migrate":
        legacy_path = (root / args.legacy).resolve()
        registry = migrate_legacy(load_json(legacy_path), args.registry_id, args.legacy, args.platform)
        write_json(path, registry)
        result = {"status": "MIGRATED", "path": str(path), "writes": 1, "validation": validate(registry)}
    elif args.command == "validate":
        result = validate(load_json(path), args.release)
    elif args.command == "merge-observations":
        registry = load_json(path)
        if not isinstance(registry, dict):
            raise SystemExit("component registry is missing or invalid")
        observations_path = (root / args.observations).resolve()
        updated = merge_observations(registry, load_json(observations_path))
        checked = validate(updated)
        if checked["status"] == "BLOCKED":
            result = checked
        else:
            write_json(path, updated)
            result = {"status": "UPDATED", "path": str(path), "writes": 1, "validation": checked}
    else:
        registry = load_json(path)
        result = design_to_code_plan(registry, args.component) if isinstance(registry, dict) else {"status": "BLOCKED", "error": "registry missing"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
