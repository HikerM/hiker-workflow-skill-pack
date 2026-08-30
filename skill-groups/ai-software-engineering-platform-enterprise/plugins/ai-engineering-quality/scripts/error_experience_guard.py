from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from presentation_guard import INTERNAL_VALUE
from product_model_common import fingerprint
from qualitylib import load_json, write_json


PROTOCOL_FAMILIES = {"REST", "PROBLEM_DETAILS", "GRAPHQL", "GRPC", "CS_LOCAL", "CUSTOM"}
ERROR_KINDS = {"EXPECTED_BUSINESS", "UNEXPECTED_SYSTEM"}
RETRY_SEMANTICS = {"NEVER", "SAFE", "AFTER_CHANGE", "UNKNOWN"}
RECOVERY_SEMANTICS = {"NONE", "USER_ACTION", "AUTOMATIC", "OPERATOR_ACTION", "UNKNOWN"}
CHANNEL_VISIBILITY = {"user": "USER", "developer": "DEVELOPER", "operations": "OPERATIONS"}
SHARED_SEMANTICS = {
    "classification", "user_action", "diagnostic_reference", "visibility",
    "retry_semantics", "recovery_semantics", "correlation",
}
CLIENT_FAILURES = {"UNHANDLED_PROMISE", "RENDER_CRASH", "ROUTER_FAILURE", "CHUNK_RESOURCE_FAILURE"}
USER_INTERNAL_FIELDS = {
    "stack", "stack_trace", "stack_ref", "path", "database", "db_details",
    "raw_exception", "exception", "exception_type", "secret", "token",
}
MAX_CLASSIFICATIONS = 256
MAX_SOURCE_FILES = 500
MAX_FINDINGS = 256
ERROR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{5,127}$")
TECHNICAL_USER_TEXT = re.compile(r"(?:\b(?:exception|stack|traceback|SQLSTATE|segmentation fault|errno)\b|\b[A-Z][A-Z0-9_]+_EXCEPTION\b)", re.I)
SECRET_TEXT = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*\S+")


def contract_fingerprint(contract: dict[str, Any]) -> str:
    return fingerprint({key: value for key, value in contract.items() if key not in {"fingerprint", "updated_at"}})


def _internal_user_fields(value: object, *, max_nodes: int = 256) -> set[str]:
    found: set[str] = set()
    queue: list[object] = [value]
    visited = 0
    while queue and visited < max_nodes:
        current = queue.pop()
        visited += 1
        if isinstance(current, dict):
            for key, child in current.items():
                normalized = str(key).lower()
                if normalized in USER_INTERNAL_FIELDS:
                    found.add(normalized)
                queue.append(child)
        elif isinstance(current, list):
            queue.extend(current[:max_nodes - visited])
    return found


def validate_contract(contract: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(contract, dict):
        return {"status": "BLOCKED", "errors": [{"code": "CONTRACT_MUST_BE_OBJECT", "field": "$"}]}
    if contract.get("schema_version") != "1.0.0":
        errors.append({"code": "UNSUPPORTED_SCHEMA_VERSION", "field": "schema_version"})
    protocol = contract.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("family") not in PROTOCOL_FAMILIES:
        errors.append({"code": "INVALID_PROTOCOL_FAMILY", "field": "protocol"})
    else:
        mappings = protocol.get("semantic_mappings")
        required = SHARED_SEMANTICS | {"error_code"}
        if not isinstance(mappings, dict) or not required.issubset({key for key, value in mappings.items() if isinstance(value, str) and value.strip()}):
            errors.append({"code": "INCOMPLETE_SEMANTIC_MAPPINGS", "field": "protocol.semantic_mappings"})
        if protocol.get("family") == "CUSTOM" and not protocol.get("existing_contract_ref"):
            errors.append({"code": "CUSTOM_PROTOCOL_REQUIRES_REFERENCE", "field": "protocol.existing_contract_ref"})
    rows = contract.get("classifications", [])
    if not isinstance(rows, list):
        errors.append({"code": "INVALID_CLASSIFICATIONS", "field": "classifications"})
        rows = []
    if len(rows) > MAX_CLASSIFICATIONS:
        errors.append({"code": "CLASSIFICATION_BUDGET_EXCEEDED", "field": "classifications"})
    codes: set[str] = set()
    for index, row in enumerate(rows[:MAX_CLASSIFICATIONS]):
        field = f"classifications[{index}]"
        if not isinstance(row, dict):
            errors.append({"code": "INVALID_CLASSIFICATION", "field": field})
            continue
        code = str(row.get("code") or "")
        if not code:
            errors.append({"code": "MISSING_CLASSIFICATION_CODE", "field": field})
        elif code in codes:
            errors.append({"code": "DUPLICATE_CLASSIFICATION", "field": field})
        codes.add(code)
        if row.get("kind") not in ERROR_KINDS:
            errors.append({"code": "INVALID_ERROR_KIND", "field": field})
        if row.get("retry_semantics") not in RETRY_SEMANTICS:
            errors.append({"code": "INVALID_RETRY_SEMANTICS", "field": field})
        if row.get("recovery_semantics") not in RECOVERY_SEMANTICS:
            errors.append({"code": "INVALID_RECOVERY_SEMANTICS", "field": field})
        if not row.get("user_message_policy") or not row.get("user_action_policy") or not isinstance(row.get("diagnostic_requirements"), list):
            errors.append({"code": "INCOMPLETE_CLASSIFICATION_POLICY", "field": field})
    client_coverage = contract.get("client_failure_coverage", [])
    if contract.get("client_surface") is True:
        covered = set(client_coverage) if isinstance(client_coverage, list) else set()
        missing = sorted(CLIENT_FAILURES - covered)
        if missing:
            errors.append({"code": "INCOMPLETE_CLIENT_FAILURE_COVERAGE", "field": "client_failure_coverage", "detail": ",".join(missing)})
    if contract.get("fingerprint") != contract_fingerprint(contract):
        errors.append({"code": "CONTRACT_FINGERPRINT_MISMATCH", "field": "fingerprint"})
    return {
        "status": "BLOCKED" if errors else "PASS", "errors": errors,
        "shared_semantics": sorted(SHARED_SEMANTICS),
        "summary": {
            "classifications": len(rows),
            "protocol": protocol.get("family") if isinstance(protocol, dict) else None,
            "client_failure_coverage": len(client_coverage) if isinstance(client_coverage, list) else 0,
        },
    }


def validate_event(contract: dict[str, Any], event: Any, correlations: Any | None = None) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    if validate_contract(contract)["status"] == "BLOCKED":
        return {"status": "BLOCKED", "findings": [{"code": "INVALID_ERROR_CONTRACT", "field": "contract"}]}
    if not isinstance(event, dict):
        return {"status": "BLOCKED", "findings": [{"code": "EVENT_MUST_BE_OBJECT", "field": "$"}]}
    error_id = str(event.get("error_id") or "")
    trace_id = str(event.get("trace_id") or "")
    for field in ("timestamp", "operation", "version", "source_fingerprint", "classification"):
        if not isinstance(event.get(field), str) or not event.get(field, "").strip():
            findings.append({"code": "MISSING_ERROR_FACT", "field": field})
    if not ERROR_ID.fullmatch(error_id):
        findings.append({"code": "INVALID_ERROR_ID", "field": "error_id"})
    if not trace_id:
        findings.append({"code": "MISSING_TRACE_ID", "field": "trace_id"})
    classifications = {str(item.get("code")): item for item in contract.get("classifications", []) if isinstance(item, dict)}
    policy = classifications.get(str(event.get("classification") or ""))
    if policy is None:
        findings.append({"code": "UNKNOWN_ERROR_CLASSIFICATION", "field": "classification"})
    elif event.get("kind") != policy.get("kind"):
        findings.append({"code": "ERROR_KIND_MISMATCH", "field": "kind"})
    else:
        if event.get("retry_semantics") != policy.get("retry_semantics"):
            findings.append({"code": "RETRY_SEMANTICS_MISMATCH", "field": "retry_semantics"})
        if event.get("recovery_semantics") != policy.get("recovery_semantics"):
            findings.append({"code": "RECOVERY_SEMANTICS_MISMATCH", "field": "recovery_semantics"})
    user = event.get("user")
    developer = event.get("developer")
    operations = event.get("operations")
    if not isinstance(user, dict):
        findings.append({"code": "MISSING_USER_CHANNEL", "field": "user"})
        user = {}
    if not isinstance(developer, dict):
        findings.append({"code": "MISSING_DEVELOPER_CHANNEL", "field": "developer"})
        developer = {}
    if not isinstance(operations, dict):
        findings.append({"code": "MISSING_OPERATIONS_CHANNEL", "field": "operations"})
        operations = {}
    for channel_name, channel in (("user", user), ("developer", developer), ("operations", operations)):
        if channel.get("visibility") != CHANNEL_VISIBILITY[channel_name]:
            findings.append({"code": "ERROR_CHANNEL_VISIBILITY_MISMATCH", "field": f"{channel_name}.visibility"})
    if user.get("error_id") != error_id or developer.get("error_id") != error_id:
        findings.append({"code": "ERROR_ID_CORRELATION_MISMATCH", "field": "error_id"})
    if operations.get("error_id") != error_id:
        findings.append({"code": "ERROR_ID_CORRELATION_MISMATCH", "field": "operations.error_id"})
    if developer.get("trace_id") != trace_id or operations.get("trace_id") != trace_id:
        findings.append({"code": "TRACE_ID_CORRELATION_MISMATCH", "field": "trace_id"})
    message = str(user.get("message") or "")
    if not message or not user.get("next_step"):
        findings.append({"code": "INCOMPLETE_USER_MESSAGE", "field": "user"})
    user_serialized = json.dumps(user, ensure_ascii=False)
    internal_fields = _internal_user_fields(user)
    if internal_fields or INTERNAL_VALUE.search(user_serialized) or TECHNICAL_USER_TEXT.search(user_serialized) or SECRET_TEXT.search(user_serialized):
        findings.append({"code": "UNSAFE_USER_ERROR_MESSAGE", "field": "user.message"})
    if not isinstance(developer.get("diagnostic_evidence_refs"), list) or not developer.get("diagnostic_evidence_refs"):
        findings.append({"code": "MISSING_DIAGNOSTIC_EVIDENCE", "field": "developer.diagnostic_evidence_refs"})
    if developer.get("redaction_status") != "PASS":
        findings.append({"code": "DIAGNOSTIC_REDACTION_UNVERIFIED", "field": "developer.redaction_status"})
    if not isinstance(operations.get("diagnostic_evidence_refs"), list) or not operations.get("diagnostic_evidence_refs"):
        findings.append({"code": "MISSING_OPERATIONS_EVIDENCE", "field": "operations.diagnostic_evidence_refs"})
    if operations.get("redaction_status") != "PASS":
        findings.append({"code": "OPERATIONS_REDACTION_UNVERIFIED", "field": "operations.redaction_status"})
    if event.get("kind") == "UNEXPECTED_SYSTEM":
        for field in ("exception_type", "cause", "stack_ref"):
            if not developer.get(field):
                findings.append({"code": "INCOMPLETE_UNEXPECTED_DIAGNOSTIC", "field": f"developer.{field}"})
    if correlations is not None:
        entries = correlations.get("correlations", {}) if isinstance(correlations, dict) else {}
        correlation = entries.get(error_id) if isinstance(entries, dict) else None
        if not isinstance(correlation, dict) or correlation.get("trace_id") != trace_id or not correlation.get("diagnostic_ref"):
            findings.append({"code": "ERROR_ID_NOT_TRACEABLE", "field": "correlations"})
    return {
        "status": "BLOCKED" if findings else "PASS",
        "findings": findings,
        "correlation": {"error_id": error_id, "trace_id": trace_id, "classification": event.get("classification")},
    }


def _catch_blocks(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    for match in re.finditer(r"\bcatch(?:\s*\([^)]*\))?\s*\{(.{0,1600}?)\}", text, re.I | re.S):
        blocks.append((text.count("\n", 0, match.start()) + 1, match.group(1)))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)except\b[^:]*:\s*$", line)
        if not match:
            continue
        indent = len(match.group(1)); body: list[str] = []
        for following in lines[index + 1 : index + 40]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        blocks.append((index + 1, "\n".join(body)))
    return blocks


def audit_sources(root: Path, requested: list[str]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned = 0
    for raw in requested[:MAX_SOURCE_FILES]:
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts:
            findings.append({"code": "UNSAFE_SOURCE_SCOPE", "path": raw})
            continue
        path = root / relative
        if not path.is_file():
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")[:1_000_000]
        for line, body in _catch_blocks(text):
            user_response = re.search(r"\b(?:return|toast|message|showError|notify|alert)\b", body, re.I)
            diagnostic = re.search(r"\b(?:log(?:ger)?|trace|throw|raise|rethrow|errorMapper|mapError|diagnostic|evidence|emit)\b", body, re.I)
            if user_response and not diagnostic:
                findings.append({"code": "CATCH_AND_HIDE", "path": relative.as_posix(), "line": line, "block_sha256": hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()})
            elif not diagnostic:
                findings.append({"code": "UNKNOWN_EXCEPTION_SILENTLY_SWALLOWED", "path": relative.as_posix(), "line": line, "block_sha256": hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()})
            if len(findings) >= MAX_FINDINGS:
                break
        if len(findings) >= MAX_FINDINGS:
            break
    if len(requested) > MAX_SOURCE_FILES:
        findings.append({"code": "SOURCE_SCOPE_BUDGET_EXCEEDED"})
    return {"status": "BLOCKED" if findings else "PASS", "findings": findings, "summary": {"scanned_files": scanned, "max_files": MAX_SOURCE_FILES}, "source_content_retained": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker protocol-neutral error experience guard")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--event")
    parser.add_argument("--correlations")
    parser.add_argument("--root", default=".")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--output")
    args = parser.parse_args()
    contract = load_json(Path(args.contract).resolve())
    result: dict[str, Any] = {"contract": validate_contract(contract)}
    if args.event:
        result["event"] = validate_event(contract, load_json(Path(args.event).resolve()), load_json(Path(args.correlations).resolve()) if args.correlations else None)
    if args.source:
        result["source_audit"] = audit_sources(Path(args.root).resolve(), args.source)
    result["status"] = "BLOCKED" if any(value.get("status") == "BLOCKED" for value in result.values() if isinstance(value, dict)) else "PASS"
    if args.output:
        write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
