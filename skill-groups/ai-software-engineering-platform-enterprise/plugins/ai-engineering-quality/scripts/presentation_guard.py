from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from product_model_common import fingerprint
from qualitylib import load_json, write_json


VISIBILITY = {"USER_VISIBLE", "DEVELOPER_ONLY", "HIDDEN"}
IDENTIFIER_KINDS = {"NONE", "TECHNICAL", "BUSINESS"}
SENSITIVITY = {"PUBLIC", "PERSONAL", "SENSITIVE", "SECRET"}
OVERFLOW_STRATEGIES = {"wrap", "truncate_with_access", "scroll", "adaptive", "project_native"}
MAX_FIELDS = 1000
MAX_BINDINGS = 2000
MAX_STATE_MAPPINGS = 256

TECHNICAL_FIELD = re.compile(r"(?:^|_)(?:id|uuid|guid|status_code|type_code|sqlstate|stack_trace|debug|exception)(?:$|_)", re.I)
RAW_TIME_FIELD = re.compile(r"(?:^|_)(?:created_at|updated_at|deleted_at|timestamp)(?:$|_)", re.I)
INTERNAL_VALUE = re.compile(r"(?:SQLSTATE|Traceback \(most recent call last\)|\bat [A-Za-z0-9_.<>]+\([^)]*:\d+\)|[A-Za-z]:\\(?:Users|Windows)\\|/(?:home|Users)/[^/]+/|\bundefined\b)", re.I)
RAW_ENUM = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


def contract_fingerprint(contract: dict[str, Any]) -> str:
    return fingerprint({key: value for key, value in contract.items() if key not in {"fingerprint", "updated_at"}})


STATE_PERSISTENCE = {
    "BOOLEAN": {"NATIVE_BOOLEAN", "PROJECT_NATIVE"},
    "FINITE_STATE": {"COMPACT_ENUM", "SEMANTIC_CODE", "PROJECT_NATIVE"},
    "EXTENSIBLE_CATEGORY": {"SEMANTIC_CODE", "REFERENCE", "PROJECT_NATIVE"},
    "SOFT_DELETE": {"DELETED_AT", "PROJECT_LIFECYCLE", "PROJECT_NATIVE"},
}
PRESENTATION_STRATEGIES = {"LOCALIZATION", "PRESENTATION_MAPPING", "DEVELOPER_RAW"}


def validate_state_mappings(contract: dict[str, Any]) -> list[dict[str, str]]:
    raw = contract.get("state_mappings", [])
    if not isinstance(raw, list):
        return [{"code": "INVALID_STATE_MAPPING_LIST", "field": "state_mappings"}]
    errors: list[dict[str, str]] = []
    if len(raw) > MAX_STATE_MAPPINGS:
        errors.append({"code": "STATE_MAPPING_BUDGET_EXCEEDED", "field": "state_mappings"})
    seen: set[str] = set()
    for index, mapping in enumerate(raw[:MAX_STATE_MAPPINGS]):
        location = f"state_mappings[{index}]"
        if not isinstance(mapping, dict):
            errors.append({"code": "INVALID_STATE_MAPPING", "field": location}); continue
        mapping_id = str(mapping.get("mapping_id") or "").strip()
        if not mapping_id:
            errors.append({"code": "MISSING_STATE_MAPPING_ID", "field": location})
        elif mapping_id in seen:
            errors.append({"code": "DUPLICATE_STATE_MAPPING_ID", "field": location})
        seen.add(mapping_id)
        semantic_type = str(mapping.get("semantic_type") or "").strip().upper()
        if semantic_type not in STATE_PERSISTENCE:
            errors.append({"code": "INVALID_STATE_SEMANTIC_TYPE", "field": location}); continue
        layers = {name: mapping.get(name) for name in ("persistence", "domain", "transport", "presentation")}
        for name, layer in layers.items():
            if not isinstance(layer, dict):
                errors.append({"code": "MISSING_STATE_LAYER", "field": f"{location}.{name}"})
        if errors and any(not isinstance(layer, dict) for layer in layers.values()):
            continue
        persistence = layers["persistence"]
        domain = layers["domain"]
        transport = layers["transport"]
        presentation = layers["presentation"]
        if persistence.get("representation") not in STATE_PERSISTENCE[semantic_type]:
            errors.append({"code": "INVALID_PERSISTENCE_REPRESENTATION", "field": f"{location}.persistence"})
        if domain.get("representation") != semantic_type:
            errors.append({"code": "DOMAIN_STATE_TYPE_MISMATCH", "field": f"{location}.domain"})
        if not transport.get("representation"):
            errors.append({"code": "MISSING_TRANSPORT_REPRESENTATION", "field": f"{location}.transport"})
        strategy = presentation.get("strategy")
        visibility = presentation.get("visibility")
        if strategy not in PRESENTATION_STRATEGIES:
            errors.append({"code": "INVALID_PRESENTATION_MAPPING", "field": f"{location}.presentation"})
        if visibility == "USER_VISIBLE" and (strategy == "DEVELOPER_RAW" or not presentation.get("mapping_ref")):
            errors.append({"code": "RAW_INTERNAL_STATUS_TO_USER", "field": f"{location}.presentation"})
        if semantic_type == "FINITE_STATE" and not isinstance(domain.get("values"), list):
            errors.append({"code": "FINITE_STATE_VALUES_REQUIRED", "field": f"{location}.domain.values"})
        if semantic_type == "SOFT_DELETE":
            extra = set(persistence.get("fields", [])) & {"deleted_by", "deleted_reason"}
            requirements = set(mapping.get("requirements", []))
            if "deleted_by" in extra and "audit_actor" not in requirements:
                errors.append({"code": "UNJUSTIFIED_DELETED_BY", "field": f"{location}.persistence.fields"})
            if "deleted_reason" in extra and "deletion_reason" not in requirements:
                errors.append({"code": "UNJUSTIFIED_DELETED_REASON", "field": f"{location}.persistence.fields"})
    return errors


def audit_state_usages(contract: dict[str, Any], usages: Any) -> dict[str, Any]:
    contract_errors = validate_state_mappings(contract)
    rows = usages.get("usages", []) if isinstance(usages, dict) else []
    if not isinstance(rows, list):
        return {"status": "BLOCKED", "findings": [{"code": "INVALID_STATE_USAGE_LIST", "field": "usages"}]}
    mappings = {str(item.get("mapping_id")): item for item in contract.get("state_mappings", []) if isinstance(item, dict)}
    findings = list(contract_errors)
    topic_mappings: dict[str, set[str]] = {}
    for index, usage in enumerate(rows[:MAX_BINDINGS]):
        location = f"usages[{index}]"
        if not isinstance(usage, dict):
            findings.append({"code": "INVALID_STATE_USAGE", "field": location}); continue
        mapping_id = str(usage.get("mapping_id") or "").strip()
        topic = str(usage.get("state_topic") or usage.get("source_field") or "").strip()
        literal = usage.get("literal")
        developer_only = usage.get("developer_only") is True
        user_visible = usage.get("user_visible") is True
        if mapping_id and mapping_id not in mappings:
            findings.append({"code": "UNKNOWN_STATE_MAPPING", "field": location})
        if topic and mapping_id:
            topic_mappings.setdefault(topic, set()).add(mapping_id)
        if isinstance(literal, (int, float)) and not isinstance(literal, bool) and not mapping_id:
            findings.append({"code": "MAGIC_NUMBER_STATE", "field": location})
        raw = "" if literal is None else str(literal)
        direct = usage.get("mapping") in {None, "direct", "schema-direct"}
        if user_visible and not developer_only and (not mapping_id or direct) and (RAW_ENUM.fullmatch(raw) or re.fullmatch(r"STATUS[_-]?\d+", raw, re.I)):
            findings.append({"code": "RAW_INTERNAL_STATUS_TO_USER", "field": location})
        if user_visible and not developer_only and usage.get("source_layer") == "PERSISTENCE" and direct:
            findings.append({"code": "STATE_LAYER_BYPASS", "field": location})
    for topic, ids in topic_mappings.items():
        if len(ids) > 1:
            findings.append({"code": "NON_CENTRALIZED_STATE_MAPPING", "field": topic})
    if len(rows) > MAX_BINDINGS:
        findings.append({"code": "STATE_USAGE_BUDGET_EXCEEDED", "field": "usages"})
    return {"status": "BLOCKED" if findings else "PASS", "findings": findings, "summary": {"usages": len(rows), "mappings": len(mappings)}}


def validate_contract(contract: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(contract, dict):
        return {"status": "BLOCKED", "errors": [{"code": "CONTRACT_MUST_BE_OBJECT", "field": "$"}]}
    if contract.get("schema_version") != "1.0.0":
        errors.append({"code": "UNSUPPORTED_SCHEMA_VERSION", "field": "schema_version"})
    if not isinstance(contract.get("contract_id"), str) or not contract.get("contract_id", "").strip():
        errors.append({"code": "MISSING_CONTRACT_ID", "field": "contract_id"})
    fields = contract.get("fields", [])
    if not isinstance(fields, list):
        errors.append({"code": "INVALID_FIELD_LIST", "field": "fields"})
        fields = []
    if len(fields) > MAX_FIELDS:
        errors.append({"code": "FIELD_BUDGET_EXCEEDED", "field": "fields"})
    errors.extend(validate_state_mappings(contract))
    ids: set[str] = set()
    for index, field in enumerate(fields[:MAX_FIELDS]):
        location = f"fields[{index}]"
        if not isinstance(field, dict):
            errors.append({"code": "INVALID_PRESENTATION_FIELD", "field": location})
            continue
        field_id = str(field.get("field_id") or "")
        if not field_id:
            errors.append({"code": "MISSING_FIELD_ID", "field": location})
        elif field_id in ids:
            errors.append({"code": "DUPLICATE_FIELD_ID", "field": location})
        ids.add(field_id)
        for required in ("semantic_role", "presentation_role", "priority"):
            if not isinstance(field.get(required), str) or not field.get(required, "").strip():
                errors.append({"code": "MISSING_PRESENTATION_SEMANTIC", "field": f"{location}.{required}"})
        if field.get("visibility") not in VISIBILITY:
            errors.append({"code": "INVALID_VISIBILITY", "field": location})
        if field.get("identifier_kind") not in IDENTIFIER_KINDS:
            errors.append({"code": "INVALID_IDENTIFIER_KIND", "field": location})
        if field.get("sensitivity") not in SENSITIVITY:
            errors.append({"code": "INVALID_SENSITIVITY", "field": location})
        overflow = field.get("overflow_policy")
        if not isinstance(overflow, dict) or overflow.get("strategy") not in OVERFLOW_STRATEGIES or overflow.get("runtime_validation_required") is not True:
            errors.append({"code": "INVALID_OVERFLOW_POLICY", "field": location})
        if field.get("visibility") == "USER_VISIBLE" and field.get("sensitivity") == "SECRET":
            errors.append({"code": "SECRET_CANNOT_BE_USER_VISIBLE", "field": location})
        if field.get("visibility") == "USER_VISIBLE" and field.get("identifier_kind") == "TECHNICAL":
            errors.append({"code": "TECHNICAL_IDENTIFIER_CANNOT_BE_USER_VISIBLE", "field": location})
        if field.get("identifier_kind") == "BUSINESS" and not field.get("business_meaning"):
            errors.append({"code": "BUSINESS_IDENTIFIER_REQUIRES_MEANING", "field": location})
        if not isinstance(field.get("format"), dict) or not field["format"].get("kind"):
            errors.append({"code": "MISSING_FORMAT_POLICY", "field": location})
        if not isinstance(field.get("fallback"), dict) or not field["fallback"].get("kind"):
            errors.append({"code": "MISSING_FALLBACK_POLICY", "field": location})
    if contract.get("fingerprint") != contract_fingerprint(contract):
        errors.append({"code": "CONTRACT_FINGERPRINT_MISMATCH", "field": "fingerprint"})
    return {"status": "BLOCKED" if errors else "PASS", "errors": errors, "summary": {"fields": len(fields)}}


def _safe_sample(value: Any) -> dict[str, Any]:
    raw = "" if value is None else str(value)
    return {"kind": "null" if value is None else type(value).__name__, "sha256": hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest(), "length": len(raw)}


def audit_bindings(contract: dict[str, Any], bindings: Any) -> dict[str, Any]:
    contract_check = validate_contract(contract)
    if contract_check["status"] == "BLOCKED":
        return {"status": "BLOCKED", "findings": contract_check["errors"], "samples": []}
    rows = bindings.get("bindings", []) if isinstance(bindings, dict) else []
    if not isinstance(rows, list):
        return {"status": "BLOCKED", "findings": [{"code": "INVALID_BINDINGS", "field": "bindings"}], "samples": []}
    fields = {str(item["field_id"]): item for item in contract["fields"]}
    findings: list[dict[str, str]] = []
    samples: list[dict[str, Any]] = []
    for index, binding in enumerate(rows[:MAX_BINDINGS]):
        location = f"bindings[{index}]"
        if not isinstance(binding, dict):
            findings.append({"code": "INVALID_BINDING", "field": location})
            continue
        presentation_field = str(binding.get("presentation_field") or "")
        source_field = str(binding.get("source_field") or "")
        policy = fields.get(presentation_field)
        samples.append({"presentation_field": presentation_field, "sample": _safe_sample(binding.get("sample"))})
        if policy is None:
            findings.append({"code": "UNCONTRACTED_PRESENTATION_FIELD", "field": presentation_field or location})
            continue
        if binding.get("visible") is True and policy.get("visibility") != "USER_VISIBLE":
            findings.append({"code": "VISIBILITY_POLICY_VIOLATION", "field": presentation_field})
        direct = binding.get("mapping") in {None, "direct", "schema-direct"}
        if direct and (TECHNICAL_FIELD.search(source_field) or RAW_TIME_FIELD.search(source_field)):
            if not (policy.get("identifier_kind") == "BUSINESS" and policy.get("business_meaning")):
                findings.append({"code": "SCHEMA_TO_UI_DIRECT_LEAKAGE", "field": presentation_field})
        if policy.get("visibility") == "USER_VISIBLE" and binding.get("sample") is None and policy.get("fallback", {}).get("kind") == "raw":
            findings.append({"code": "RAW_NULL_FALLBACK", "field": presentation_field})
        sample = "" if binding.get("sample") is None else str(binding.get("sample"))
        if policy.get("visibility") == "USER_VISIBLE" and INTERNAL_VALUE.search(sample):
            findings.append({"code": "INTERNAL_VALUE_LEAKAGE", "field": presentation_field})
        if policy.get("visibility") == "USER_VISIBLE" and RAW_ENUM.fullmatch(sample) and binding.get("mapping") in {None, "direct", "schema-direct"}:
            findings.append({"code": "RAW_ENUM_LEAKAGE", "field": presentation_field})
    if len(rows) > MAX_BINDINGS:
        findings.append({"code": "BINDING_BUDGET_EXCEEDED", "field": "bindings"})
    return {"status": "BLOCKED" if findings else "PASS", "findings": findings, "samples": samples, "summary": {"bindings": len(rows), "findings": len(findings)}}


def audit_copy(entries: Any) -> dict[str, Any]:
    rows = entries.get("entries", []) if isinstance(entries, dict) else []
    findings: list[dict[str, str]] = []
    seen: dict[tuple[str, str], str] = {}
    for index, entry in enumerate(rows[:MAX_BINDINGS]):
        location = f"entries[{index}]"
        if not isinstance(entry, dict):
            findings.append({"code": "INVALID_COPY_ENTRY", "field": location})
            continue
        for required in ("copy_id", "control_role", "surface", "text", "intent"):
            if not isinstance(entry.get(required), str) or not entry.get(required, "").strip():
                findings.append({"code": "MISSING_COPY_SEMANTIC", "field": f"{location}.{required}"})
        text = str(entry.get("text") or "")
        if INTERNAL_VALUE.search(text) or re.search(r"\b(?:exception|stack|SQL|HTTP\s*5\d\d|undefined|null)\b", text, re.I):
            findings.append({"code": "TECHNICAL_COPY_LEAKAGE", "field": str(entry.get("copy_id") or location)})
        if entry.get("control_role") in {"error", "empty_state", "destructive_dialog"} and not entry.get("next_step"):
            findings.append({"code": "COPY_MISSING_NEXT_STEP", "field": str(entry.get("copy_id") or location)})
        if entry.get("runtime_fit") not in {"PASS", "NOT_APPLICABLE"}:
            findings.append({"code": "COPY_RUNTIME_FIT_UNVERIFIED", "field": str(entry.get("copy_id") or location)})
        key = (str(entry.get("surface") or ""), text.strip().casefold())
        if text and key in seen and seen[key] != entry.get("copy_id"):
            findings.append({"code": "DUPLICATE_COPY_IN_SURFACE", "field": str(entry.get("copy_id") or location)})
        seen[key] = str(entry.get("copy_id") or "")
    return {"status": "BLOCKED" if findings else "PASS", "findings": findings, "summary": {"entries": len(rows), "findings": len(findings)}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker presentation and schema leakage guard")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--bindings")
    parser.add_argument("--copy")
    parser.add_argument("--state-usages")
    parser.add_argument("--output")
    args = parser.parse_args()
    contract = load_json(Path(args.contract).resolve())
    result: dict[str, Any] = {"contract": validate_contract(contract)}
    if args.bindings:
        result["bindings"] = audit_bindings(contract, load_json(Path(args.bindings).resolve()))
    if args.copy:
        result["copy"] = audit_copy(load_json(Path(args.copy).resolve()))
    if args.state_usages:
        result["state_usages"] = audit_state_usages(contract, load_json(Path(args.state_usages).resolve()))
    result["status"] = "BLOCKED" if any(value.get("status") == "BLOCKED" for value in result.values() if isinstance(value, dict)) else "PASS"
    if args.output:
        write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
