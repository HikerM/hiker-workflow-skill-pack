from __future__ import annotations

import json
import re
import subprocess
from typing import Any


MACHINE_CONTRACT_VERSION = "hiker-cli/v1"
VALID_PRO_STATES = {"PRO_ACTIVE", "PRO_DEGRADED", "COMMUNITY_FALLBACK", "PRO_REQUIRED_BLOCKED"}
VALID_MACHINE_EXIT_CODES = {0, 2, 64, 70}


def parse_semantic_version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def single_json_document(output: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    stripped = output.lstrip()
    try:
        payload, end = decoder.raw_decode(stripped)
    except (TypeError, json.JSONDecodeError):
        return None
    if stripped[end:].strip() or not isinstance(payload, dict):
        return None
    return payload


def machine_payload(
    completed: subprocess.CompletedProcess[str],
    command: str,
) -> tuple[dict[str, Any] | None, str | None]:
    payload = single_json_document(completed.stdout)
    if payload is None:
        return None, "STDOUT_NOT_SINGLE_JSON_DOCUMENT"
    if completed.stderr.strip() and single_json_document(completed.stderr) is not None:
        return None, "PRIMARY_PAYLOAD_ON_STDERR"
    if payload.get("contract_version") != MACHINE_CONTRACT_VERSION:
        return None, "MACHINE_CONTRACT_VERSION_MISMATCH"
    if payload.get("command") != command:
        return None, "MACHINE_COMMAND_MISMATCH"
    if payload.get("exit_code") != completed.returncode or completed.returncode not in VALID_MACHINE_EXIT_CODES:
        return None, "EXIT_CODE_CONTRACT_MISMATCH"
    if not isinstance(payload.get("ok"), bool) or not isinstance(payload.get("status"), str):
        return None, "MACHINE_ENVELOPE_INVALID"
    if payload.get("pro_state") not in VALID_PRO_STATES:
        return None, "PRO_STATE_INVALID"
    if (completed.returncode == 0) != bool(payload["ok"]):
        return None, "SUCCESS_EXIT_STATUS_MISMATCH"
    return payload, None


def protocol_facts(payload: dict[str, Any]) -> tuple[str, tuple[int, int, int], int, str] | None:
    product = str(payload.get("product_version") or "unknown").strip() or "unknown"
    runtime = parse_semantic_version(payload.get("runtime_api_version"))
    protocol = payload.get("live_adoption_protocol")
    state_schema = str(payload.get("state_schema_version") or "unknown").strip() or "unknown"
    if runtime is None or not isinstance(protocol, int):
        return None
    return product, runtime, protocol, state_schema
