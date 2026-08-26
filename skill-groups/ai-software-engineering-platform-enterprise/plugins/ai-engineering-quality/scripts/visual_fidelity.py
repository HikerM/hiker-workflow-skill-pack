from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from component_registry_v2 import validate as validate_registry
from product_model_common import fingerprint
from qualitylib import load_json, write_json
from runtime_ui_evidence import objective_checks, validate_snapshot
from ui_design_model import validate as validate_design


PERCEPTUAL_VERDICTS = {"PASS", "BLOCKED", "REQUIRES_REVIEW"}


def _screen(model: dict[str, Any], screen_id: str) -> dict[str, Any] | None:
    return next((item for item in model.get("screens", []) if item.get("screen_id") == screen_id), None)


def _registry_expectations(
    registry: dict[str, Any], component_ids: list[str]
) -> tuple[list[str], dict[str, dict[str, Any]], list[str]]:
    by_id = {str(item.get("component_id")): item for item in registry.get("components", []) if isinstance(item, dict)}
    expected = list(dict.fromkeys(str(component_id) for component_id in component_ids if str(component_id)))
    registered = [component_id for component_id in expected if component_id in by_id]
    missing = [component_id for component_id in expected if component_id not in by_id]
    tokens: dict[str, dict[str, Any]] = {}
    for component_id in registered:
        values: dict[str, Any] = {}
        for token in by_id[component_id].get("tokens", []):
            if "=" in token:
                name, value = token.split("=", 1)
                values[name] = value
        if values:
            tokens[component_id] = values
    return expected, tokens, missing


def evaluate(
    design: dict[str, Any],
    registry: dict[str, Any],
    snapshot: dict[str, Any],
    perceptual: dict[str, Any] | None = None,
    candidate_id: str | None = None,
    goal_revision: int | None = None,
) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if validate_design(design)["status"] != "PASS":
        blockers.append({"code": "INVALID_DESIGN_BASELINE"})
    if validate_registry(registry)["status"] == "BLOCKED":
        blockers.append({"code": "INVALID_COMPONENT_REGISTRY"})
    if validate_snapshot(snapshot)["status"] != "PASS":
        blockers.append({"code": "INVALID_RUNTIME_SNAPSHOT"})
    screen_id = str(snapshot.get("screen_id") or "")
    screen = _screen(design, screen_id)
    if screen is None:
        blockers.append({"code": "SCREEN_NOT_IN_DESIGN_BASELINE"})
        screen = {}
    elif snapshot.get("state") not in screen.get("states", []):
        blockers.append({"code": "RUNTIME_STATE_NOT_IN_DESIGN", "detail": str(snapshot.get("state"))})
    if snapshot.get("design_fingerprint") != design.get("fingerprint"):
        blockers.append({"code": "STALE_DESIGN_FINGERPRINT"})
    if snapshot.get("registry_fingerprint") != registry.get("fingerprint"):
        blockers.append({"code": "STALE_REGISTRY_FINGERPRINT"})
    expected_components, expected_tokens, missing_registry_components = _registry_expectations(
        registry, list(screen.get("components", []))
    )
    blockers.extend(
        {"code": "DESIGN_COMPONENT_NOT_IN_REGISTRY", "detail": component_id}
        for component_id in missing_registry_components
    )
    objective = objective_checks(snapshot, expected_components, str(snapshot.get("state") or ""), expected_tokens)
    perceptual_result = perceptual or {"verdict": "REQUIRES_REVIEW", "reviewer": None, "evidence_refs": [], "findings": []}
    if perceptual_result.get("verdict") not in PERCEPTUAL_VERDICTS:
        blockers.append({"code": "INVALID_PERCEPTUAL_VERDICT"})
    if perceptual_result.get("verdict") == "PASS" and not perceptual_result.get("evidence_refs"):
        blockers.append({"code": "PERCEPTUAL_PASS_REQUIRES_EVIDENCE"})
    stale = any(item["code"].startswith("STALE_") for item in blockers)
    if stale:
        verdict = "STALE"
    elif blockers or objective["status"] == "BLOCKED" or perceptual_result.get("verdict") == "BLOCKED":
        verdict = "BLOCKED"
    elif perceptual_result.get("verdict") != "PASS":
        verdict = "REQUIRES_REVIEW"
    else:
        verdict = "PASS"
    evidence: dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_type": "VISUAL_FIDELITY",
        "evidence_id": str(snapshot.get("capture_id") or ""),
        "candidate_id": candidate_id,
        "goal_revision": goal_revision,
        "design_version": design.get("revision"),
        "design_fingerprint": design.get("fingerprint"),
        "registry_fingerprint": registry.get("fingerprint"),
        "source_commit": snapshot.get("source_commit"),
        "workspace_fingerprint": snapshot.get("workspace_fingerprint"),
        "source_fingerprint": snapshot.get("source_fingerprint"),
        "screen_id": screen_id,
        "state": snapshot.get("state"),
        "architecture": snapshot.get("architecture"),
        "technology": snapshot.get("technology"),
        "viewport": snapshot.get("viewport"),
        "expected": {"screen": screen_id, "components": expected_components, "acceptance": screen.get("acceptance", [])},
        "actual": {"capture_artifact": snapshot.get("capture_artifact"), "runtime_fingerprint": snapshot.get("fingerprint")},
        "objective_checks": objective,
        "perceptual_review": perceptual_result,
        "blockers": blockers,
        "verdict": verdict,
    }
    evidence["fingerprint"] = fingerprint({key: value for key, value in evidence.items() if key != "fingerprint"})
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker visual fidelity evidence builder")
    parser.add_argument("--design", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--perceptual")
    parser.add_argument("--candidate-id")
    parser.add_argument("--goal-revision", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(
        load_json(Path(args.design).resolve()),
        load_json(Path(args.registry).resolve()),
        load_json(Path(args.snapshot).resolve()),
        load_json(Path(args.perceptual).resolve()) if args.perceptual else None,
        args.candidate_id,
        args.goal_revision,
    )
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
