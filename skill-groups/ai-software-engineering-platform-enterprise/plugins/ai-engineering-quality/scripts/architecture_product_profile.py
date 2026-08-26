from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from product_model_common import bounded_strings, fingerprint, validate_observation
from qualitylib import load_json, write_json


DIMENSIONS = {
    "BS": {
        "browser", "route", "responsive", "network", "async_state", "browser_history",
        "accessibility", "api", "hidden_surfaces",
    },
    "CS": {
        "window", "screen", "dpi", "resolution", "input", "offline", "local_state",
        "device", "resource", "lifecycle", "update", "crash_recovery",
    },
}
STATUSES = {"PASS", "BLOCKED", "UNKNOWN", "NOT_APPLICABLE"}
MAX_DIMENSIONS = 32
SCHEMA_VERSION = "1.0.0"


def profile_fingerprint(profile: dict[str, Any]) -> str:
    return fingerprint({key: value for key, value in profile.items() if key not in {"fingerprint", "updated_at"}})


def validate(profile: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    blockers: list[dict[str, str]] = []
    if not isinstance(profile, dict):
        return {"status": "BLOCKED", "errors": [{"code": "PROFILE_MUST_BE_OBJECT", "field": "$"}], "blockers": []}
    if profile.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "UNSUPPORTED_SCHEMA_VERSION", "field": "schema_version"})
    if not isinstance(profile.get("profile_id"), str) or not profile.get("profile_id", "").strip():
        errors.append({"code": "MISSING_PROFILE_ID", "field": "profile_id"})
    architecture = profile.get("architecture")
    if architecture not in DIMENSIONS:
        errors.append({"code": "INVALID_ARCHITECTURE", "field": "architecture"})
        allowed: set[str] = set()
    else:
        allowed = DIMENSIONS[str(architecture)]
    facts = profile.get("project_facts", [])
    if not isinstance(facts, list):
        errors.append({"code": "INVALID_PROJECT_FACTS", "field": "project_facts"})
    else:
        if len(facts) > 128:
            errors.append({"code": "PROJECT_FACT_BUDGET_EXCEEDED", "field": "project_facts"})
        for index, fact in enumerate(facts[:128]):
            validate_observation(fact, f"project_facts[{index}]", errors)
    required = profile.get("required_dimensions", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        errors.append({"code": "INVALID_REQUIRED_DIMENSIONS", "field": "required_dimensions"})
        required = []
    if len(required) > MAX_DIMENSIONS or set(required) - allowed:
        errors.append({"code": "UNSUPPORTED_REQUIRED_DIMENSION", "field": "required_dimensions"})
    dimensions = profile.get("dimensions", {})
    if not isinstance(dimensions, dict):
        errors.append({"code": "INVALID_DIMENSION_EVIDENCE", "field": "dimensions"})
        dimensions = {}
    if len(dimensions) > MAX_DIMENSIONS:
        errors.append({"code": "DIMENSION_EVIDENCE_BUDGET_EXCEEDED", "field": "dimensions"})
    if set(dimensions) - allowed:
        errors.append({"code": "UNSUPPORTED_DIMENSION_EVIDENCE", "field": "dimensions"})
    for name, evidence in dimensions.items():
        field = f"dimensions.{name}"
        if not isinstance(evidence, dict) or evidence.get("status") not in STATUSES:
            errors.append({"code": "INVALID_DIMENSION_STATUS", "field": field})
            continue
        refs = evidence.get("evidence_refs", [])
        bounded_strings(refs, 32, f"{field}.evidence_refs", errors)
        if evidence.get("status") == "PASS" and (not isinstance(refs, list) or not refs):
            errors.append({"code": "PASS_REQUIRES_EVIDENCE", "field": field})
        reason = evidence.get("reason")
        if reason is not None and not isinstance(reason, str):
            errors.append({"code": "INVALID_DIMENSION_REASON", "field": field})
        if evidence.get("status") == "NOT_APPLICABLE" and not reason:
            errors.append({"code": "NOT_APPLICABLE_REQUIRES_REASON", "field": field})
    for name in required:
        evidence = dimensions.get(name, {})
        if evidence.get("status") != "PASS":
            blockers.append({"code": "REQUIRED_DIMENSION_NOT_PASS", "field": f"dimensions.{name}", "detail": str(evidence.get("status") or "MISSING")})
    if profile.get("fingerprint") != profile_fingerprint(profile):
        errors.append({"code": "PROFILE_FINGERPRINT_MISMATCH", "field": "fingerprint"})
    status = "BLOCKED" if errors or blockers else "PASS"
    return {
        "status": status,
        "errors": errors,
        "blockers": blockers,
        "summary": {"architecture": architecture, "required": len(required), "evidenced": len(dimensions)},
        "selection_policy": "project-facts-and-target-environment",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker B/S and C/S architecture evidence profile")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate(load_json(Path(args.profile).resolve()))
    if args.output:
        write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
