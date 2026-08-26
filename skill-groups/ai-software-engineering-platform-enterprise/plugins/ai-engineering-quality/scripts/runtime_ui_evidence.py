from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from product_model_common import fingerprint
from qualitylib import load_json, write_json


MAX_ELEMENTS = 512
MAX_FINDINGS = 256
ARCHITECTURES = {"BS", "CS"}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_snapshot(snapshot: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(snapshot, dict):
        return {"status": "BLOCKED", "errors": [{"code": "SNAPSHOT_MUST_BE_OBJECT", "field": "$"}]}
    for field in ("capture_id", "screen_id", "state", "technology", "source_fingerprint", "design_fingerprint", "registry_fingerprint"):
        if not isinstance(snapshot.get(field), str) or not snapshot.get(field, "").strip():
            errors.append({"code": "MISSING_CAPTURE_FIELD", "field": field})
    if not snapshot.get("source_commit") and not snapshot.get("workspace_fingerprint"):
        errors.append({"code": "MISSING_SOURCE_IDENTITY", "field": "source_commit|workspace_fingerprint"})
    if snapshot.get("architecture") not in ARCHITECTURES:
        errors.append({"code": "INVALID_ARCHITECTURE", "field": "architecture"})
    viewport = snapshot.get("viewport")
    if not isinstance(viewport, dict) or not all(_number(viewport.get(key)) and viewport[key] > 0 for key in ("width", "height")):
        errors.append({"code": "INVALID_VIEWPORT", "field": "viewport"})
    elements = snapshot.get("elements", [])
    if not isinstance(elements, list):
        errors.append({"code": "INVALID_ELEMENT_LIST", "field": "elements"})
        elements = []
    if len(elements) > MAX_ELEMENTS:
        errors.append({"code": "ELEMENT_BUDGET_EXCEEDED", "field": "elements"})
    ids: set[str] = set()
    for index, element in enumerate(elements[:MAX_ELEMENTS]):
        field = f"elements[{index}]"
        if not isinstance(element, dict) or not isinstance(element.get("component_id"), str) or not element.get("component_id", "").strip():
            errors.append({"code": "INVALID_RUNTIME_ELEMENT", "field": field})
            continue
        if element["component_id"] in ids:
            errors.append({"code": "DUPLICATE_RUNTIME_ELEMENT", "field": field})
        ids.add(element["component_id"])
        rect = element.get("rect")
        if not isinstance(rect, dict) or not all(_number(rect.get(key)) for key in ("x", "y", "width", "height")):
            errors.append({"code": "INVALID_ELEMENT_RECT", "field": field})
    return {"status": "BLOCKED" if errors else "PASS", "errors": errors, "summary": {"elements": len(elements)}}


def _overlap(left: dict[str, float], right: dict[str, float]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"]
        or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"]
        or right["y"] + right["height"] <= left["y"]
    )


def objective_checks(
    snapshot: dict[str, Any],
    expected_components: list[str] | None = None,
    expected_state: str | None = None,
    expected_tokens: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    checked = validate_snapshot(snapshot)
    if checked["status"] == "BLOCKED":
        return {"status": "BLOCKED", "findings": checked["errors"], "checks": 0}
    findings: list[dict[str, Any]] = []
    viewport = snapshot["viewport"]
    elements = snapshot.get("elements", [])[:MAX_ELEMENTS]
    by_id = {item["component_id"]: item for item in elements}
    for component_id in expected_components or []:
        if component_id not in by_id:
            findings.append({"code": "MISSING_COMPONENT", "component_id": component_id})
    if expected_state and snapshot.get("state") != expected_state:
        findings.append({"code": "WRONG_STATE", "expected": expected_state, "actual": snapshot.get("state")})
    for element in elements:
        component_id = element["component_id"]
        rect = element["rect"]
        if rect["width"] < 0 or rect["height"] < 0:
            findings.append({"code": "INVALID_SIZE", "component_id": component_id})
        if rect["x"] < 0 or rect["y"] < 0 or rect["x"] + rect["width"] > viewport["width"] or rect["y"] + rect["height"] > viewport["height"]:
            findings.append({"code": "OFFSCREEN", "component_id": component_id})
        scroll_width = element.get("scroll_width")
        client_width = element.get("client_width")
        scroll_height = element.get("scroll_height")
        client_height = element.get("client_height")
        if _number(scroll_width) and _number(client_width) and scroll_width > client_width + 1:
            findings.append({"code": "HORIZONTAL_OVERFLOW", "component_id": component_id})
        if _number(scroll_height) and _number(client_height) and scroll_height > client_height + 1:
            findings.append({"code": "VERTICAL_OVERFLOW", "component_id": component_id})
        if element.get("clipped") is True:
            findings.append({"code": "CLIPPED", "component_id": component_id})
        expected = (expected_tokens or {}).get(component_id, {})
        actual = element.get("tokens", {}) if isinstance(element.get("tokens"), dict) else {}
        for token, expected_value in expected.items():
            if actual.get(token) != expected_value:
                findings.append({"code": "TOKEN_DRIFT", "component_id": component_id, "token": token, "expected": expected_value, "actual": actual.get(token)})
    for index, left in enumerate(elements):
        if left.get("allow_overlap"):
            continue
        for right in elements[index + 1 :]:
            if right.get("allow_overlap") or left.get("overlap_group") == right.get("overlap_group") and left.get("overlap_group"):
                continue
            if _overlap(left["rect"], right["rect"]):
                findings.append({"code": "OVERLAP", "component_ids": [left["component_id"], right["component_id"]]})
                if len(findings) >= MAX_FINDINGS:
                    break
        if len(findings) >= MAX_FINDINGS:
            break
    findings = findings[:MAX_FINDINGS]
    return {
        "status": "BLOCKED" if findings else "PASS",
        "checks": len(elements) + len(expected_components or []),
        "findings": findings,
        "truncated": len(findings) >= MAX_FINDINGS,
    }


def bind_artifact(snapshot: dict[str, Any], artifact: Path | None) -> dict[str, Any]:
    data = dict(snapshot)
    if artifact is not None:
        if not artifact.is_file():
            raise ValueError("capture artifact does not exist")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        data["capture_artifact"] = {"ref": artifact.name, "sha256": digest, "bytes": artifact.stat().st_size}
    data["fingerprint"] = fingerprint({key: value for key, value in data.items() if key != "fingerprint"})
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker bounded runtime UI evidence")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--artifact")
    parser.add_argument("--expected-component", action="append", default=[])
    parser.add_argument("--expected-state")
    parser.add_argument("--output")
    args = parser.parse_args()
    snapshot_path = Path(args.snapshot).resolve()
    snapshot = load_json(snapshot_path)
    if not isinstance(snapshot, dict):
        raise SystemExit("runtime snapshot is missing or invalid")
    bound = bind_artifact(snapshot, Path(args.artifact).resolve() if args.artifact else None)
    result = {"snapshot": bound, "objective": objective_checks(bound, args.expected_component, args.expected_state)}
    if args.output:
        write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["objective"]["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
