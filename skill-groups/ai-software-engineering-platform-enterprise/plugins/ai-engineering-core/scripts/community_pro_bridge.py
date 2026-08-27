from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

MINIMUM_PRO_VERSION = (5, 19)
REQUIRED_LIVE_ADOPTION_PROTOCOL = 2
PROBE_TIMEOUT_SECONDS = 5
ACTION_TIMEOUT_SECONDS = 30


def _result(status: str, **values: Any) -> dict[str, Any]:
    return {"status": status, **values}


def _provider_session_available(environment: Mapping[str, str]) -> bool:
    return any(
        environment.get(name, "").strip()
        for name in ("HIKER_PROVIDER_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID")
    )


def _parse_semantic_version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _protocol_facts(output: str) -> tuple[tuple[int, int, int], tuple[int, int, int], int] | None:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    product = _parse_semantic_version(payload.get("product_version"))
    runtime = _parse_semantic_version(payload.get("runtime_api_version"))
    protocol = payload.get("live_adoption_protocol")
    if product is None or runtime is None or not isinstance(protocol, int):
        return None
    return product, runtime, protocol


def detect_pro_runtime(
    environment: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    effective_environment = os.environ if environment is None else environment
    executable = effective_environment.get("HIKER_EXECUTABLE", "").strip() or shutil.which("hiker")
    if not executable:
        return _result("COMMUNITY_FALLBACK", reason="PRO_RUNTIME_NOT_FOUND", pro_available=False)
    try:
        completed = runner(
            [executable, "version", "--json"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            env=dict(effective_environment),
        )
    except (OSError, subprocess.SubprocessError):
        return _result("COMMUNITY_FALLBACK", reason="PRO_RUNTIME_UNAVAILABLE", pro_available=False)
    facts = _protocol_facts(completed.stdout)
    if completed.returncode != 0 or facts is None:
        return _result(
            "COMMUNITY_FALLBACK",
            reason="PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE",
            pro_available=False,
        )
    product_version, runtime_version, protocol_version = facts
    if product_version[:2] < MINIMUM_PRO_VERSION or protocol_version != REQUIRED_LIVE_ADOPTION_PROTOCOL:
        return _result(
            "COMMUNITY_FALLBACK",
            reason="PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE",
            pro_available=False,
            product_version=".".join(str(value) for value in product_version),
            runtime_api_version=".".join(str(value) for value in runtime_version),
            live_adoption_protocol=protocol_version,
        )
    return _result(
        "PRO_RUNTIME_DETECTED",
        pro_available=True,
        executable=str(Path(executable).resolve()),
        product_version=".".join(str(value) for value in product_version),
        runtime_api_version=".".join(str(value) for value in runtime_version),
        live_adoption_protocol=protocol_version,
        provider_session_available=_provider_session_available(effective_environment),
    )


def invoke_bridge(
    root: Path,
    action: str,
    boundary_proof: str | None,
    environment: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    effective_environment = os.environ if environment is None else environment
    if not _provider_session_available(effective_environment):
        return _result("COMMUNITY_FALLBACK", reason="PROVIDER_SESSION_UNAVAILABLE", pro_available=False)
    detected = detect_pro_runtime(effective_environment, runner)
    if not detected.get("pro_available"):
        return detected
    if not root.is_dir():
        return _result("BLOCKED", reason="PROJECT_ROOT_NOT_FOUND", pro_available=True)
    executable = detected["executable"]
    command = [executable, action, "--root", str(root.resolve())]
    if action in {"attach", "resume"}:
        if boundary_proof not in {"NEW_TASK", "TURN_TERMINAL", "NATURAL_CHECKPOINT", "RECOVERY_CHECKPOINT"}:
            return _result("WAIT_SAFE_BOUNDARY", reason="SAFE_BOUNDARY_NOT_CONFIRMED", pro_available=True)
        command.extend(["--boundary-proof", boundary_proof])
    try:
        completed = runner(
            command,
            cwd=str(root.resolve()),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=ACTION_TIMEOUT_SECONDS,
            check=False,
            env=dict(effective_environment),
        )
    except subprocess.TimeoutExpired:
        return _result("BLOCKED", reason="PRO_RUNTIME_TIMEOUT", pro_available=True)
    except OSError:
        return _result("COMMUNITY_FALLBACK", reason="PRO_RUNTIME_UNAVAILABLE", pro_available=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _result(
            "BLOCKED",
            reason="PRO_RUNTIME_RESPONSE_INVALID",
            pro_available=True,
            exit_code=completed.returncode,
        )
    status = str(payload.get("status", "BLOCKED"))
    return _result(
        status,
        pro_available=True,
        adopted=status in {"LIVE_SESSION_ADOPTED", "ALREADY_ADOPTED"},
        checkpointed=status in {"TURN_CHECKPOINTED", "ALREADY_CHECKPOINTED"},
        exit_code=completed.returncode,
        project_id=payload.get("project_id"),
        goal_id=payload.get("goal_id"),
        task_id=payload.get("task_id"),
        checkpoint_id=payload.get("checkpoint_id"),
        provider_session_fingerprint=payload.get("provider_session_fingerprint"),
        context_fingerprint=payload.get("context_fingerprint"),
        context_bytes=payload.get("context_bytes", 0),
        state_reads=payload.get("state_reads", 0),
        state_writes=payload.get("state_writes", 0),
        reasons=payload.get("reasons", []),
    )


def router_boundary_adoption(
    root: Path,
    environment: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Adopt only at the router's existing pre-write boundary; fallback stays silent."""
    report = invoke_bridge(root, "attach", "NEW_TASK", environment, runner)
    if not report.get("pro_available"):
        return {}
    if report.get("adopted"):
        report["terminal_action"] = "checkpoint"
        report["terminal_boundary"] = "TURN_TERMINAL"
        report["authority"] = "PRO_5_19_RUNTIME"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thin Community 5.18 to Pro 5.19 bridge")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--action", choices=("probe", "attach", "resume", "checkpoint"), default="probe")
    parser.add_argument("--boundary-proof", choices=("NEW_TASK", "TURN_TERMINAL", "NATURAL_CHECKPOINT", "RECOVERY_CHECKPOINT"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    report = (
        detect_pro_runtime()
        if arguments.action == "probe"
        else invoke_bridge(arguments.root, arguments.action, arguments.boundary_proof)
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    if report["status"] in {
        "PRO_RUNTIME_DETECTED",
        "COMMUNITY_FALLBACK",
        "LIVE_SESSION_ADOPTED",
        "ALREADY_ADOPTED",
        "TURN_CHECKPOINTED",
        "ALREADY_CHECKPOINTED",
    }:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
