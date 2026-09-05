from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from result_fuse import CaptureBudget,CaptureReceipt,start_capture_thread


MINIMUM_PRO_VERSION = (5, 19)
REQUIRED_LIVE_ADOPTION_PROTOCOL = 2
MACHINE_CONTRACT_VERSION = "hiker-cli/v1"
VALID_PRO_STATES = {"PRO_ACTIVE", "PRO_DEGRADED", "COMMUNITY_FALLBACK", "PRO_REQUIRED_BLOCKED"}
VALID_MACHINE_EXIT_CODES = {0, 2, 64, 70}
PROBE_TIMEOUT_SECONDS = 5
ACTION_TIMEOUT_SECONDS = 30
LOCATOR_CONTRACT_VERSION = "hiker-pro-locator/v1"
MAX_LOCATOR_BYTES = 64 * 1024
MAX_MACHINE_STDOUT_BYTES = 512 * 1024
MAX_MACHINE_STDERR_BYTES = 128 * 1024


def bounded_machine_run(command:list[str],**kwargs:Any)->subprocess.CompletedProcess[str]:
    process=subprocess.Popen(command,cwd=kwargs.get("cwd"),env=kwargs.get("env"),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if process.stdout is None or process.stderr is None:
        process.kill();raise OSError("machine command pipes unavailable")
    stdout=io.BytesIO();stderr=io.BytesIO();stdout_receipt=CaptureReceipt();stderr_receipt=CaptureReceipt()
    stdout_thread=start_capture_thread(process.stdout,stdout,CaptureBudget(max_spool_bytes=MAX_MACHINE_STDOUT_BYTES),stdout_receipt)
    stderr_thread=start_capture_thread(process.stderr,stderr,CaptureBudget(max_spool_bytes=MAX_MACHINE_STDERR_BYTES),stderr_receipt)
    try:
        try:return_code=process.wait(timeout=kwargs.get("timeout"))
        except subprocess.TimeoutExpired:
            process.kill();process.wait();raise
        stdout_thread.join(timeout=5);stderr_thread.join(timeout=5)
        if stdout_thread.is_alive() or stderr_thread.is_alive():raise subprocess.SubprocessError("machine result capture did not converge")
        return subprocess.CompletedProcess(command,return_code,stdout.getvalue().decode("utf-8",errors="replace"),stderr.getvalue().decode("utf-8",errors="replace"))
    finally:
        if process.poll() is None:process.kill()
        process.stdout.close();process.stderr.close()


def _result(status: str, **values: Any) -> dict[str, Any]:
    pro_state = values.pop("pro_state", None)
    if pro_state is None:
        pro_state = (
            "COMMUNITY_FALLBACK" if status == "COMMUNITY_FALLBACK"
            else "PRO_REQUIRED_BLOCKED" if status == "BLOCKED"
            else "PRO_DEGRADED"
        )
    return {"status": status, "pro_state": pro_state, **values}


def _provider_session_available(environment: Mapping[str, str]) -> bool:
    return any(
        environment.get(name, "").strip()
        for name in ("HIKER_PROVIDER_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID")
    )


def _read_runtime_locator(environment: Mapping[str, str]) -> str | None:
    configured = environment.get("HIKER_PRO_LOCATOR", "").strip()
    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    locator = Path(configured) if configured else Path(local_app_data) / "Hiker" / "pro-runtime.json" if local_app_data else None
    if locator is None or not locator.is_absolute() or not locator.is_file() or locator.is_symlink():
        return None
    try:
        if locator.stat().st_size <= 0 or locator.stat().st_size > MAX_LOCATOR_BYTES:
            return None
        payload = json.loads(locator.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("contract_version") != LOCATOR_CONTRACT_VERSION:
            return None
        home = Path(str(payload.get("hiker_home", "")))
        executable = Path(str(payload.get("executable", "")))
        if not home.is_absolute() or not executable.is_absolute() or executable.is_symlink():
            return None
        expected = home / "bin" / ("hiker.exe" if os.name == "nt" else "hiker")
        if executable.resolve() != expected.resolve() or not executable.is_file():
            return None
        return str(executable.resolve())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _resolve_pro_executable(environment: Mapping[str, str]) -> tuple[str | None, str]:
    configured = environment.get("HIKER_EXECUTABLE", "").strip()
    if configured:
        return configured, "HIKER_EXECUTABLE"
    configured_home = environment.get("HIKER_HOME", "").strip()
    if configured_home:
        home_executable = Path(configured_home) / "bin" / ("hiker.exe" if os.name == "nt" else "hiker")
        if home_executable.is_file() and not home_executable.is_symlink():
            return str(home_executable.resolve()), "HIKER_HOME"
    located = _read_runtime_locator(environment)
    if located:
        return located, "PRO_RUNTIME_LOCATOR"
    return shutil.which("hiker"), "PATH"


def _parse_semantic_version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _single_json_document(output: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    stripped = output.lstrip()
    try:
        payload, end = decoder.raw_decode(stripped)
    except (TypeError, json.JSONDecodeError):
        return None
    if stripped[end:].strip() or not isinstance(payload, dict):
        return None
    return payload


def _machine_payload(
    completed: subprocess.CompletedProcess[str],
    command: str,
) -> tuple[dict[str, Any] | None, str | None]:
    payload = _single_json_document(completed.stdout)
    if payload is None:
        return None, "STDOUT_NOT_SINGLE_JSON_DOCUMENT"
    if completed.stderr.strip() and _single_json_document(completed.stderr) is not None:
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


def _protocol_facts(payload: dict[str, Any]) -> tuple[tuple[int, int, int], tuple[int, int, int], int] | None:
    product = _parse_semantic_version(payload.get("product_version"))
    runtime = _parse_semantic_version(payload.get("runtime_api_version"))
    protocol = payload.get("live_adoption_protocol")
    if product is None or runtime is None or not isinstance(protocol, int):
        return None
    return product, runtime, protocol


def detect_pro_runtime(
    environment: Mapping[str, str] | None = None,
    runner: Any = bounded_machine_run,
) -> dict[str, Any]:
    effective_environment = os.environ if environment is None else environment
    executable, detection_source = _resolve_pro_executable(effective_environment)
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
    payload, contract_error = _machine_payload(completed, "version")
    facts = _protocol_facts(payload) if payload is not None else None
    if completed.returncode != 0 or facts is None:
        return _result(
            "COMMUNITY_FALLBACK",
            reason="PRO_MACHINE_CONTRACT_INCOMPATIBLE" if contract_error else "PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE",
            diagnostic=contract_error,
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
        pro_state="PRO_ACTIVE",
        pro_available=True,
        executable=str(Path(executable).resolve()),
        product_version=".".join(str(value) for value in product_version),
        runtime_api_version=".".join(str(value) for value in runtime_version),
        live_adoption_protocol=protocol_version,
        provider_session_available=_provider_session_available(effective_environment),
        machine_contract=MACHINE_CONTRACT_VERSION,
        detection_source=detection_source,
    )


def _run_machine_action(
    root: Path,
    command: list[str],
    command_name: str,
    environment: Mapping[str, str],
    runner: Any,
) -> tuple[dict[str, Any] | None, subprocess.CompletedProcess[str] | None, str | None]:
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
            env=dict(environment),
        )
    except subprocess.TimeoutExpired:
        return None, None, "PRO_RUNTIME_TIMEOUT"
    except OSError:
        return None, None, "PRO_RUNTIME_UNAVAILABLE"
    payload, error = _machine_payload(completed, command_name)
    return payload, completed, error


def invoke_bridge(
    root: Path,
    action: str,
    boundary_proof: str | None,
    environment: Mapping[str, str] | None = None,
    runner: Any = bounded_machine_run,
    detected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_environment = os.environ if environment is None else environment
    if not _provider_session_available(effective_environment):
        return _result("COMMUNITY_FALLBACK", reason="PROVIDER_SESSION_UNAVAILABLE", pro_available=False)
    detected = detected or detect_pro_runtime(effective_environment, runner)
    if not detected.get("pro_available"):
        return detected
    if not root.is_dir():
        return _result("BLOCKED", pro_state="PRO_REQUIRED_BLOCKED", reason="PROJECT_ROOT_NOT_FOUND", pro_available=True)
    command = [detected["executable"], action, "--root", str(root.resolve()), "--json"]
    if action in {"attach", "resume"}:
        if boundary_proof not in {"NEW_TASK", "TURN_TERMINAL", "NATURAL_CHECKPOINT", "RECOVERY_CHECKPOINT"}:
            return _result(
                "WAIT_SAFE_BOUNDARY",
                pro_state="PRO_DEGRADED",
                reason="SAFE_BOUNDARY_NOT_CONFIRMED",
                pro_available=True,
            )
        command.extend(["--boundary-proof", boundary_proof])
    payload, completed, contract_error = _run_machine_action(root, command, action, effective_environment, runner)
    if completed is None:
        if contract_error == "PRO_RUNTIME_UNAVAILABLE":
            return _result("COMMUNITY_FALLBACK", reason=contract_error, pro_available=False)
        return _result("BLOCKED", pro_state="PRO_REQUIRED_BLOCKED", reason=contract_error, pro_available=True)
    if payload is None:
        return _result(
            "BLOCKED",
            pro_state="PRO_REQUIRED_BLOCKED",
            reason="PRO_RUNTIME_RESPONSE_INVALID",
            diagnostic=contract_error,
            exit_code=completed.returncode,
            pro_available=True,
        )
    status = str(payload["status"])
    return _result(
        status,
        pro_state=str(payload["pro_state"]),
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
        machine_contract=payload.get("contract_version"),
        stderr_diagnostic=bool(completed.stderr.strip()),
    )


def query_project_facts(
    root: Path,
    environment: Mapping[str, str] | None = None,
    runner: Any = bounded_machine_run,
    detected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_environment = os.environ if environment is None else environment
    detected = detected or detect_pro_runtime(effective_environment, runner)
    if not detected.get("pro_available"):
        return detected
    if not root.is_dir():
        return _result("BLOCKED", pro_state="PRO_REQUIRED_BLOCKED", reason="PROJECT_ROOT_NOT_FOUND", pro_available=True)
    command = [detected["executable"], "project-facts", "--root", str(root.resolve()), "--json"]
    payload, completed, contract_error = _run_machine_action(root, command, "project-facts", effective_environment, runner)
    if completed is None:
        return _result(
            "PRO_DEGRADED" if contract_error != "PRO_RUNTIME_UNAVAILABLE" else "COMMUNITY_FALLBACK",
            pro_state="PRO_DEGRADED" if contract_error != "PRO_RUNTIME_UNAVAILABLE" else "COMMUNITY_FALLBACK",
            reason=contract_error,
            pro_available=contract_error != "PRO_RUNTIME_UNAVAILABLE",
        )
    if payload is None:
        return _result(
            "PRO_DEGRADED",
            pro_state="PRO_DEGRADED",
            reason="PROJECT_FACTS_RESPONSE_INVALID",
            diagnostic=contract_error,
            exit_code=completed.returncode,
            pro_available=True,
        )
    return _result(
        str(payload["status"]),
        pro_state=str(payload["pro_state"]),
        pro_available=True,
        ok=bool(payload["ok"]),
        exit_code=completed.returncode,
        facts=payload.get("facts") if isinstance(payload.get("facts"), dict) else None,
        machine_contract=payload.get("contract_version"),
        stderr_diagnostic=bool(completed.stderr.strip()),
    )


def router_boundary_adoption(
    root: Path,
    environment: Mapping[str, str] | None = None,
    runner: Any = bounded_machine_run,
    detected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adopt only at the router's existing pre-write boundary; fallback remains observable."""
    report = invoke_bridge(root, "attach", "NEW_TASK", environment, runner, detected)
    if report.get("adopted"):
        report["terminal_action"] = "checkpoint"
        report["terminal_boundary"] = "TURN_TERMINAL"
        report["authority"] = "PRO_5_19_RUNTIME"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thin Community to Pro 5.19 bridge")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--action", choices=("probe", "project-facts", "attach", "resume", "checkpoint"), default="probe")
    parser.add_argument("--boundary-proof", choices=("NEW_TASK", "TURN_TERMINAL", "NATURAL_CHECKPOINT", "RECOVERY_CHECKPOINT"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.action == "probe":
        report = detect_pro_runtime()
    elif arguments.action == "project-facts":
        report = query_project_facts(arguments.root)
    else:
        report = invoke_bridge(arguments.root, arguments.action, arguments.boundary_proof)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report.get("pro_state") in {"PRO_ACTIVE", "COMMUNITY_FALLBACK"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
