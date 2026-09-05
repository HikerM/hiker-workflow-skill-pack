from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from pro_machine_contract import MACHINE_CONTRACT_VERSION, machine_payload, protocol_facts
from machine_runner import bounded_machine_run
from resource_budget import HARD_MAX as RESOURCE_HARD_MAX


MINIMUM_RUNTIME_API_VERSION = (0, 1, 0)
REQUIRED_LIVE_ADOPTION_PROTOCOL = 2
PROBE_TIMEOUT_SECONDS = 5
ACTION_TIMEOUT_SECONDS = 30
LOCATOR_CONTRACT_VERSION = "hiker-pro-locator/v1"
MAX_LOCATOR_BYTES = RESOURCE_HARD_MAX["input"]["runtime_locator_bytes"]
MAX_AUTHORITY_FACT_BYTES = RESOURCE_HARD_MAX["input"]["project_fact_file_bytes"]
AUTHORITY_REQUIRED_STATUSES = {"GOAL_ADOPTION_REQUIRED", "TASK_ADOPTION_REQUIRED"}
AUTHORITY_ESTABLISHED_STATUSES = {"ESTABLISHED", "ALREADY_ESTABLISHED", "ADOPT_EXISTING_AUTHORITY"}
TRUSTED_GOAL_AUTHORITY_SOURCES = {
    "CONTROLLER_CURRENT_GOAL",
    "PROVIDER_CURRENT_GOAL",
    "RUNTIME_CURRENT_GOAL_CONTRACT",
}
TRUSTED_TASK_AUTHORITY_SOURCES = {
    "CONTROLLER_CURRENT_ACTIVE_TASK",
    "PROVIDER_CURRENT_ACTIVE_TASK",
    "RUNTIME_CURRENT_TASK_CONTRACT",
}


def _result(status: str, **values: Any) -> dict[str, Any]:
    pro_state = values.pop("pro_state", None)
    if pro_state is None:
        pro_state = (
            "COMMUNITY_FALLBACK" if status == "COMMUNITY_FALLBACK"
            else "PRO_REQUIRED_BLOCKED" if status == "BLOCKED"
            else "PRO_DEGRADED"
        )
    manual_recovery = values.pop("manual_recovery_prompt_required", bool(values.get("ask_required", False)))
    return {"status": status, "pro_state": pro_state, "manual_recovery_prompt_required": manual_recovery, **values}


def _prepare_new_session_project(root: Path) -> dict[str, Any]:
    try:
        from bootstrap_project import prepare_for_new_session

        return prepare_for_new_session(root)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "classification": "RECOVERY_OPERATION_FAILED",
            "affected_capability": "AUTOMATIC_STATE_RECOVERY",
            "automatic_action_taken": ["PRESERVE_EXISTING_STATE"],
            "recovery_status": "CURRENT_PROJECT_USABLE_FROM_REQUEST_AND_GIT",
            "diagnostic_ref": f"{type(error).__name__}",
            "user_action_required": "NONE",
            "project_usability": "READY",
            "old_state_resumability": "UNKNOWN",
            "bootstrap_required": False,
            "state_reads": 0,
            "state_writes": 0,
            "full_ai_scan": False,
            "cold_history_scanned": False,
        }


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
    payload, contract_error = machine_payload(completed, "version")
    facts = protocol_facts(payload) if payload is not None else None
    if completed.returncode != 0 or facts is None:
        return _result(
            "COMMUNITY_FALLBACK",
            reason="PRO_MACHINE_CONTRACT_INCOMPATIBLE" if contract_error else "PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE",
            diagnostic=contract_error,
            pro_available=False,
        )
    product_version, runtime_version, protocol_version, state_schema_version = facts
    if runtime_version < MINIMUM_RUNTIME_API_VERSION or protocol_version != REQUIRED_LIVE_ADOPTION_PROTOCOL:
        return _result(
            "COMMUNITY_FALLBACK",
            reason="PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE",
            pro_available=False,
            product_version=product_version,
            runtime_api_version=".".join(str(value) for value in runtime_version),
            live_adoption_protocol=protocol_version,
            state_schema_version=state_schema_version,
        )
    return _result(
        "PRO_RUNTIME_DETECTED",
        pro_state="PRO_ACTIVE",
        pro_available=True,
        executable=str(Path(executable).resolve()),
        product_version=product_version,
        runtime_api_version=".".join(str(value) for value in runtime_version),
        live_adoption_protocol=protocol_version,
        state_schema_version=state_schema_version,
        feature_availability={"machine_json": True, "live_adoption": True},
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
    payload, error = machine_payload(completed, command_name)
    return payload, completed, error


def _authority_fact(
    value: Any,
    kind: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, Mapping):
        return None, f"{kind.upper()}_AUTHORITY_MISSING"
    statement = str(value.get("statement", "")).strip()
    state = str(value.get("state", "")).strip().upper()
    source = str(value.get("authority_source", "")).strip().upper()
    generation = value.get("authority_generation", 0)
    accepted_states = {"ACTIVE", "CURRENT", "IN_PROGRESS"} if kind == "goal" else {"ACTIVE", "CURRENT", "IN_PROGRESS", "RUNNING"}
    accepted_sources = TRUSTED_GOAL_AUTHORITY_SOURCES if kind == "goal" else TRUSTED_TASK_AUTHORITY_SOURCES
    if not statement or len(statement) > 4096:
        return None, f"{kind.upper()}_STATEMENT_INVALID"
    if state not in accepted_states:
        return None, f"{kind.upper()}_STATE_NOT_ACTIVE"
    if source not in accepted_sources:
        return None, f"{kind.upper()}_AUTHORITY_SOURCE_UNTRUSTED"
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        return None, f"{kind.upper()}_AUTHORITY_GENERATION_INVALID"
    supplied_fingerprint = str(value.get("source_fingerprint", "")).strip().lower()
    canonical = json.dumps(
        {
            "contract_version": "hiker-controller-current-authority/v1",
            "kind": kind.upper(),
            "statement": statement,
            "state": state,
            "authority_source": source,
            "authority_generation": generation,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    computed_fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if supplied_fingerprint and supplied_fingerprint != computed_fingerprint:
        return None, f"{kind.upper()}_SOURCE_FINGERPRINT_MISMATCH"
    return {
        "statement": statement,
        "state": state,
        "authority_source": source,
        "source_fingerprint": computed_fingerprint,
        "authority_generation": generation,
    }, None


def normalize_current_authority_facts(
    authority_facts: Mapping[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    if not isinstance(authority_facts, Mapping):
        return None, "CURRENT_AUTHORITY_FACTS_REQUIRED"
    goal, goal_error = _authority_fact(authority_facts.get("goal"), "goal")
    if goal_error:
        return None, goal_error
    task, task_error = _authority_fact(authority_facts.get("task"), "task")
    if task_error:
        return None, task_error
    return {"goal": goal, "task": task}, None


def _bounded_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= MAX_AUTHORITY_FACT_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def resolve_local_current_authority(root: Path) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    ai = root / ".ai"
    recovery_relative = "governance/new-session-recovery.json"
    reads = [recovery_relative, "governance/goal-contract.json", "governance/task-index.json", "runtime/task.json"]
    recovery = _bounded_json(ai / recovery_relative)
    if isinstance(recovery, dict):
        resumability = recovery.get("old_state_resumability")
        candidate_relative = str(recovery.get("authority_candidate_ref") or "")
        if resumability == "REBINDABLE" and candidate_relative:
            reads.append(candidate_relative)
            candidate = _bounded_json(ai / candidate_relative)
            if isinstance(candidate, dict) and isinstance(candidate.get("goal"), dict) and isinstance(candidate.get("task"), dict):
                return {"goal": candidate["goal"], "task": candidate["task"]}, None, reads
        if resumability in {"QUARANTINED", "AMBIGUOUS", "REBINDABLE"}:
            return None, "OLD_STATE_AUTHORITY_QUARANTINED", reads
    goal = _bounded_json(ai / reads[1])
    index = _bounded_json(ai / reads[2])
    runtime_task = _bounded_json(ai / reads[3])
    summaries = [
        item for item in ((index or {}).get("tasks") or [])
        if isinstance(item, dict) and item.get("task_id") and item.get("state") not in {"Merged", "Released"}
    ][:8]
    runtime_id = str((runtime_task or {}).get("id") or (runtime_task or {}).get("task_id") or "")
    candidates = [str(item["task_id"]) for item in summaries]
    task_id = runtime_id if runtime_id in candidates else candidates[0] if len(candidates) == 1 else ""
    if len(candidates) > 1 and not task_id:
        return None, "MULTIPLE_CURRENT_TASK_AUTHORITIES", reads
    task = None
    if task_id:
        safe_task = re.sub(r"[^A-Za-z0-9._-]+", "-", task_id).strip("._-")
        relative = f"tasks/{safe_task}.json"
        reads.append(relative)
        task = _bounded_json(ai / relative)
    elif isinstance(runtime_task, dict) and runtime_task:
        task = runtime_task
    if not isinstance(task, dict) or not task:
        return None, "CURRENT_TASK_AUTHORITY_MISSING", reads
    task_statement = str(task.get("goal") or task.get("scope") or "").strip()
    if not task_statement:
        return None, "CURRENT_TASK_STATEMENT_MISSING", reads
    binding = task.get("goal_binding") if isinstance(task.get("goal_binding"), dict) else {}
    if isinstance(goal, dict) and goal.get("status") == "ACTIVE":
        goal_statement = str(goal.get("outcome") or "").strip()
        goal_id = str(goal.get("goal_id") or "")
        revision = goal.get("revision")
        fingerprint = str(goal.get("fingerprint") or "")
        if not goal_statement or not goal_id or not isinstance(revision, int) or revision < 1 or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            return None, "CURRENT_GOAL_CONTRACT_INVALID", reads
        if binding and (
            binding.get("scope") != "project"
            or binding.get("goal_id") != goal_id
            or binding.get("revision") != revision
            or binding.get("fingerprint") != fingerprint
        ):
            return None, "CURRENT_GOAL_TASK_BINDING_MISMATCH", reads
    elif binding.get("scope") == "task" and task_statement:
        goal_statement = task_statement
        revision = int(binding.get("revision") or 1)
    else:
        return None, "CURRENT_GOAL_AUTHORITY_MISSING", reads
    history = task.get("history") if isinstance(task.get("history"), list) else []
    facts = {
        "goal": {
            "statement": goal_statement,
            "state": "ACTIVE",
            "authority_source": "RUNTIME_CURRENT_GOAL_CONTRACT",
            "authority_generation": revision,
        },
        "task": {
            "statement": task_statement,
            "state": "IN_PROGRESS",
            "authority_source": "RUNTIME_CURRENT_TASK_CONTRACT",
            "authority_generation": len(history),
        },
    }
    return facts, None, reads


def establish_current_authority(
    root: Path,
    boundary_proof: str | None,
    authority_facts: Mapping[str, Any] | None,
    environment: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
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
    if boundary_proof not in {"NEW_TASK", "TURN_TERMINAL", "NATURAL_CHECKPOINT", "RECOVERY_CHECKPOINT"}:
        return _result(
            "WAIT_SAFE_BOUNDARY",
            pro_state="PRO_DEGRADED",
            reason="SAFE_BOUNDARY_NOT_CONFIRMED",
            pro_available=True,
        )
    normalized, authority_error = normalize_current_authority_facts(authority_facts)
    if authority_error:
        return _result(
            "AUTHORITY_AMBIGUOUS",
            pro_state="PRO_REQUIRED_BLOCKED",
            reason=authority_error,
            ask_required=True,
            pro_available=True,
        )
    goal = normalized["goal"]
    task = normalized["task"]
    command = [
        detected["executable"],
        "establish-current-authority",
        "--root", str(root.resolve()),
        "--json",
        "--boundary-proof", boundary_proof,
        "--goal-statement", goal["statement"],
        "--goal-state", goal["state"],
        "--goal-authority-source", goal["authority_source"],
        "--goal-source-fingerprint", goal["source_fingerprint"],
        "--goal-authority-generation", str(goal["authority_generation"]),
        "--task-statement", task["statement"],
        "--task-state", task["state"],
        "--task-authority-source", task["authority_source"],
        "--task-source-fingerprint", task["source_fingerprint"],
        "--task-authority-generation", str(task["authority_generation"]),
    ]
    payload, completed, contract_error = _run_machine_action(
        root, command, "establish-current-authority", effective_environment, runner
    )
    if completed is None:
        return _result(
            "BLOCKED",
            pro_state="PRO_REQUIRED_BLOCKED",
            reason=contract_error,
            pro_available=True,
        )
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
        authority_established=status in AUTHORITY_ESTABLISHED_STATUSES,
        exit_code=completed.returncode,
        project_id=payload.get("project_id"),
        goal_id=payload.get("goal_id"),
        task_id=payload.get("task_id"),
        goal_authority_source=payload.get("goal_authority_source"),
        task_authority_source=payload.get("task_authority_source"),
        provider_session_fingerprint=payload.get("provider_session_fingerprint"),
        operation_id=payload.get("operation_id"),
        safe_boundary=payload.get("safe_boundary", False),
        state_generation_before=payload.get("state_generation_before", 0),
        state_generation_after=payload.get("state_generation_after", 0),
        state_reads=payload.get("state_reads", 0),
        state_writes=payload.get("state_writes", 0),
        idempotent_replay=payload.get("idempotent_replay", False),
        reasons=payload.get("reasons", []),
        machine_contract=payload.get("contract_version"),
        stderr_diagnostic=bool(completed.stderr.strip()),
    )


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
    authority_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Adopt only at the router's existing pre-write boundary; fallback remains observable."""
    effective_environment = os.environ if environment is None else environment
    recovery = _prepare_new_session_project(root)
    resolved = detected
    if resolved is None and _provider_session_available(effective_environment):
        resolved = detect_pro_runtime(effective_environment, runner)
    report = invoke_bridge(root, "attach", "NEW_TASK", effective_environment, runner, resolved)
    report["new_session_recovery"] = recovery
    report["project_ready"] = recovery.get("project_usability") == "READY"
    if report.get("pro_state") == "COMMUNITY_FALLBACK":
        report["community_safe_mode"] = True
        report["recovery_status"] = recovery.get("recovery_status")
        report["user_action_required"] = "NONE"
    if report.get("status") in AUTHORITY_REQUIRED_STATUSES:
        authority_resolution = None
        if authority_facts is None:
            authority_facts, resolution_error, resolution_reads = resolve_local_current_authority(root)
            authority_resolution = {
                "status": "RESOLVED" if authority_facts else "AMBIGUOUS",
                "reason": resolution_error,
                "reads": resolution_reads,
                "cold_history_scanned": False,
                "writes": 0,
            }
        establishment = establish_current_authority(
            root,
            "NEW_TASK",
            authority_facts,
            effective_environment,
            runner,
            resolved,
        )
        if not establishment.get("authority_established"):
            if authority_facts is None and recovery.get("project_usability") == "READY":
                return _result(
                    "COMMUNITY_SAFE_MODE",
                    pro_state="PRO_DEGRADED",
                    reason=establishment.get("reason") or establishment.get("status"),
                    pro_available=True,
                    community_safe_mode=True,
                    project_ready=True,
                    new_session_recovery=recovery,
                    authority_resolution=authority_resolution,
                    old_state_resume_status=recovery.get("old_state_resumability"),
                    old_state_resume_user_action=(
                        "SELECT_AUTHORITY" if recovery.get("old_state_resumability") == "AMBIGUOUS" else "NONE"
                    ),
                    recovery_status=recovery.get("recovery_status"),
                    user_action_required="NONE",
                    manual_recovery_prompt_required=False,
                )
            establishment["initial_attach"] = report
            if authority_resolution is not None:
                establishment["authority_resolution"] = authority_resolution
            return establishment
        report = invoke_bridge(root, "attach", "NEW_TASK", effective_environment, runner, resolved)
        report["new_session_recovery"] = recovery
        report["project_ready"] = recovery.get("project_usability") == "READY"
        report["authority_establishment"] = establishment
        if authority_resolution is not None:
            report["authority_resolution"] = authority_resolution
    if report.get("adopted"):
        report["terminal_action"] = "checkpoint"
        report["terminal_boundary"] = "TURN_TERMINAL"
        report["authority"] = "PRO_5_19_RUNTIME"
        report["adoption_flow"] = ["DETECT", "CLASSIFY", "RECONCILE", "ESTABLISH_AUTHORITY", "ATTACH", "ADOPT", "RESUME"]
        report["manual_recovery_prompt_required"] = False
        report["user_action_required"] = "NONE"
        report["terminal_contract"] = {
            "required": True,
            "execute_at": "BEFORE_FINAL_RESPONSE",
            "action": "checkpoint",
            "success_statuses": ["TURN_CHECKPOINTED", "ALREADY_CHECKPOINTED"],
            "command": [
                sys.executable,
                str(Path(__file__).resolve()),
                "--root",
                str(root.resolve()),
                "--action",
                "checkpoint",
            ],
        }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thin Community to compatible Pro runtime bridge")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--action", choices=("probe", "project-facts", "establish-current-authority", "attach", "resume", "checkpoint"), default="probe")
    parser.add_argument("--boundary-proof", choices=("NEW_TASK", "TURN_TERMINAL", "NATURAL_CHECKPOINT", "RECOVERY_CHECKPOINT"))
    parser.add_argument("--authority-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.action == "probe":
        report = detect_pro_runtime()
    elif arguments.action == "project-facts":
        report = query_project_facts(arguments.root)
    elif arguments.action == "establish-current-authority":
        facts = json.loads(arguments.authority_json) if arguments.authority_json else None
        report = establish_current_authority(arguments.root, arguments.boundary_proof, facts)
    else:
        report = invoke_bridge(arguments.root, arguments.action, arguments.boundary_proof)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report.get("pro_state") in {"PRO_ACTIVE", "COMMUNITY_FALLBACK"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
