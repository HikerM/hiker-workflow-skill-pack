from __future__ import annotations

import hashlib
import json
from typing import Any


PLATFORMS = {"BS_BROWSER", "CS_CLIENT"}
ACTIVE_STATUSES = {"READY", "IDLE"}
MAX_TARGETS = 32
FINGERPRINT_FIELDS = (
    "source_fingerprint",
    "project_config_fingerprint",
    "technology_fingerprint",
    "environment_fingerprint",
    "relevant_state_fingerprint",
    "authenticated_session_fingerprint",
)


def _text(value: Any, field: str, errors: list[str], *, digest: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        errors.append(f"{field} is required")
    elif len(text) > 160:
        errors.append(f"{field} exceeds 160 characters")
    if digest and text and (len(text) != 64 or any(character not in "0123456789abcdef" for character in text.lower())):
        errors.append(f"{field} must be an opaque sha256 fingerprint")
    return text


def validate_descriptor(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["runtime descriptor must be an object"]
    allowed = {
        "schema_version", "runtime_id", "platform", "status", "capabilities", "targets",
        *FINGERPRINT_FIELDS,
    }
    errors: list[str] = []
    extras = sorted(set(value) - allowed)
    if extras:
        errors.append(f"unsupported runtime fields: {', '.join(extras)}")
    if value.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    _text(value.get("runtime_id"), "runtime_id", errors)
    if value.get("platform") not in PLATFORMS:
        errors.append("platform is invalid")
    if value.get("status") not in ACTIVE_STATUSES | {"BUSY", "FAILED", "CLOSED"}:
        errors.append("status is invalid")
    for field in FINGERPRINT_FIELDS:
        _text(value.get(field), field, errors, digest=field == "authenticated_session_fingerprint")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("capabilities must be an object")
    else:
        if set(capabilities) - {"session_reuse", "incremental_reload"}:
            errors.append("capabilities contain unsupported fields")
        for name in ("session_reuse", "incremental_reload"):
            if not isinstance(capabilities.get(name), bool):
                errors.append(f"capabilities.{name} must be boolean")
    targets = value.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append("targets must be a non-empty array")
    elif len(targets) > MAX_TARGETS:
        errors.append(f"targets exceed {MAX_TARGETS} items")
    else:
        for index, target in enumerate(targets):
            _text(target, f"targets[{index}]", errors)
    return errors


def descriptor_fingerprint(value: dict[str, Any]) -> str:
    payload = {key: value.get(key) for key in sorted(value) if key != "runtime_id"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decide(existing: dict[str, Any], required: dict[str, Any]) -> dict[str, Any]:
    existing_errors = validate_descriptor(existing)
    required_errors = validate_descriptor(required)
    if existing_errors or required_errors:
        return {
            "status": "BLOCKED",
            "decision": "DO_NOT_REUSE",
            "errors": [*existing_errors, *required_errors],
            "reason": "runtime identity is not safely provable",
        }
    if existing["platform"] != required["platform"]:
        return {"status": "PASS", "decision": "START_TARGETED", "reason": "platform changed"}
    if existing["status"] not in ACTIVE_STATUSES:
        return {"status": "PASS", "decision": "START_TARGETED", "reason": "runtime is not reusable"}
    if existing["authenticated_session_fingerprint"] != required["authenticated_session_fingerprint"]:
        return {"status": "PASS", "decision": "RESTART_TARGETED", "reason": "authenticated session changed"}
    for field in ("project_config_fingerprint", "environment_fingerprint", "relevant_state_fingerprint"):
        if existing[field] != required[field]:
            return {"status": "PASS", "decision": "RESTART_TARGETED", "reason": f"{field} changed"}
    if existing["technology_fingerprint"] != required["technology_fingerprint"]:
        return {"status": "PASS", "decision": "REBUILD_REQUIRED", "reason": "technology identity changed"}
    required_targets = set(required["targets"])
    if not required_targets.issubset(set(existing["targets"])):
        return {"status": "PASS", "decision": "START_TARGETED", "reason": "required target is not loaded"}
    capabilities = existing["capabilities"]
    if not capabilities["session_reuse"]:
        return {"status": "PASS", "decision": "RESTART_TARGETED", "reason": "session reuse is unsupported"}
    if existing["source_fingerprint"] != required["source_fingerprint"]:
        decision = "INCREMENTAL_RELOAD" if capabilities["incremental_reload"] else "RESTART_TARGETED"
        return {"status": "PASS", "decision": decision, "reason": "source fingerprint changed"}
    return {
        "status": "PASS",
        "decision": "REUSE",
        "reason": "all runtime identity and affected-target facts match",
        "runtime_fingerprint": descriptor_fingerprint(existing),
    }
