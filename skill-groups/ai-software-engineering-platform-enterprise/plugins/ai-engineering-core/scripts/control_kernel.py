from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from control_trace import TraceWriteError, control_root
from corelib import atomic_write_json, read_json, utc_now
from state_consistency import assess as assess_state
from session_epoch import assess as assess_epoch
from suite_version import inspect_suite
from process_identity import owner_status, process_identity


SCHEMA_VERSION = "2.0.0"
MAX_OPERATIONS = 128
MAX_RESULT_BYTES = 16 * 1024
OPERATION_STATUSES = {
    "PREPARED", "DOMAIN_COMMITTED", "TRACE_PENDING", "COMPLETE",
    "FAILED_BEFORE_COMMIT", "RECOVERY_REQUIRED",
}
UNCERTAIN_STATUSES = {"PREPARED", "DOMAIN_COMMITTED", "TRACE_PENDING", "RECOVERY_REQUIRED"}
TOKEN_RE = re.compile(r"[^A-Za-z0-9._:-]+")
FORBIDDEN_RESULT_KEYS = {
    "prompt", "message", "tail", "request_text", "instruction", "stdout", "stderr",
    "diff", "source", "source_body", "assistant_output", "last_assistant_message",
}


def _token(value: str, limit: int = 100) -> str:
    token = TOKEN_RE.sub("-", str(value or "").strip()).strip("-._:")
    if not token:
        raise ValueError("operation id is empty")
    return token[:limit]


def operation_file(root: Path) -> Path:
    return control_root(root) / "operations-v1.json"


@contextlib.contextmanager
def operation_lock(root: Path, timeout: float = 15.0, stale_after: float = 120.0) -> Iterator[None]:
    path = control_root(root) / "operation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    descriptor: int | None = None
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, json.dumps({
                "pid": os.getpid(),
                "created": time.time(),
                "runtime_identity": process_identity(os.getpid()),
            }).encode("ascii"))
            break
        except FileExistsError:
            try:
                owner = json.loads(path.read_text(encoding="ascii"))
            except (OSError, json.JSONDecodeError):
                owner = {}
            age = time.time() - float(owner.get("created") or path.stat().st_mtime)
            pid = int(owner.get("pid") or 0)
            if age > stale_after and owner_status(owner) in {"DEAD", "IDENTITY_CHANGED"}:
                try:
                    path.unlink()
                    continue
                except FileNotFoundError:
                    continue
            if time.time() - started > timeout:
                raise TimeoutError(f"control operation lock timeout; owner={pid}, age={round(age, 1)}s")
            time.sleep(0.03)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _default_operations() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "revision": 0, "operations": {}}


def _load_operations(root: Path) -> dict[str, Any]:
    path = operation_file(root)
    if not path.is_file():
        return _default_operations()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"control operation journal is damaged: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("operations"), dict):
        raise RuntimeError("control operation journal schema is invalid")
    if data.get("schema_version") == "1.0.0":
        for item in data["operations"].values():
            legacy = str(item.get("status") or "")
            item["status"] = {
                "COMPLETE": "COMPLETE",
                "FAILED": "FAILED_BEFORE_COMMIT",
            }.get(legacy, "RECOVERY_REQUIRED")
            item.setdefault("operation_type", item.get("command"))
            item.setdefault("retry_count", max(0, int(item.get("attempts") or 1) - 1))
            item.setdefault("trace_status", "COMMITTED" if legacy == "COMPLETE" else "UNKNOWN")
        data["schema_version"] = SCHEMA_VERSION
        data["migrated_from"] = "1.0.0"
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("control operation journal schema is invalid")
    return data


def _payload_hash(command: str, payload: dict[str, Any]) -> str:
    basis = {"command": command, "payload": payload}
    return hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_result(value: Any, path: str = "result") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_RESULT_KEYS:
                raise RuntimeError(f"control result contains forbidden field: {path}.{key}")
            _validate_result(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_result(item, f"{path}[{index}]")


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    _validate_result(result)
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise RuntimeError("control operation result exceeds bounded journal limit")
    return result


def _required_fingerprint(value: Any, field: str) -> str:
    token = str(value or "")
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise RuntimeError(f"{field} must be a lowercase SHA-256 fingerprint")
    return token


def _prepared_facts(value: dict[str, Any]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RuntimeError("operation prepare callback must return an object")
    return {
        "before_fingerprint": _required_fingerprint(value.get("before_fingerprint"), "before_fingerprint"),
        "intended_after_fingerprint": _required_fingerprint(
            value.get("intended_after_fingerprint"), "intended_after_fingerprint"
        ),
    }


def _committed_facts(value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict):
        raise RuntimeError("domain commit callback must return an object")
    result = _compact_result(dict(value.get("domain_result") or {}))
    fingerprint = _required_fingerprint(
        value.get("committed_after_fingerprint"), "committed_after_fingerprint"
    )
    return result, fingerprint


def _persist(root: Path, journal: dict[str, Any]) -> None:
    journal["revision"] = int(journal.get("revision") or 0) + 1
    atomic_write_json(operation_file(root), journal)


def _error_facts(exc: BaseException) -> dict[str, str]:
    return {
        "error_code": type(exc).__name__,
        "error_fingerprint": hashlib.sha256(
            str(exc).encode("utf-8", errors="replace")
        ).hexdigest(),
    }


def _operation_result(
    operation_id: str,
    domain_result: dict[str, Any],
    *,
    operation_status: str,
    trace_status: str,
    journal_status: str,
    trace: dict[str, Any] | None = None,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    result = {
        **domain_result,
        "operation_id": operation_id,
        "operation_status": operation_status,
        "business_committed": True,
        "trace_status": trace_status,
        "journal_status": journal_status,
        "retry_same_operation_id": operation_status != "COMPLETE" or journal_status != "COMMITTED",
        "idempotent_replay": idempotent_replay,
    }
    if trace is not None:
        result["trace"] = trace
    return _compact_result(result)


def write_gate(
    root: Path,
    *,
    allow_version_recovery: bool = False,
    allow_epoch_overrun: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    suite = inspect_suite()
    if not suite.get("consistent"):
        raise RuntimeError("plugin suite version is inconsistent")
    state = assess_state(root)
    if state.get("recovery_level") in {"L3", "L4"}:
        raise RuntimeError(f"project source identity is quarantined: {state.get('status')}")
    route_state = read_json(root / ".ai" / "runtime" / "skill-routing.json", {}) or {}
    prior_suite = route_state.get("suite_fingerprint")
    if prior_suite and prior_suite != suite.get("fingerprint") and not allow_version_recovery:
        raise RuntimeError("project routing state belongs to an older plugin suite; checkpoint and context recovery are required")
    epoch = assess_epoch(root)
    if epoch.get("rotation_required") and not allow_epoch_overrun:
        raise RuntimeError("session epoch budget is exhausted; checkpoint and rotate before further state transitions")
    current = state.get("current") or {}
    return {
        "suite_version": suite.get("version"),
        "suite_fingerprint": suite.get("fingerprint"),
        "state_status": state.get("status"),
        "recovery_level": state.get("recovery_level"),
        "repo_id": current.get("repo_id"),
        "head": current.get("head"),
        "branch": current.get("branch"),
        "manifest_hash": current.get("manifest_hash"),
        "session_epoch": epoch.get("epoch"),
        "session_epoch_rotation_required": bool(epoch.get("rotation_required")),
    }


def execute_operation(
    root: Path,
    *,
    operation_id: str,
    command: str,
    payload: dict[str, Any],
    prepare: Callable[[], dict[str, Any]],
    commit_domain: Callable[[], dict[str, Any]],
    recover_domain: Callable[[dict[str, Any]], dict[str, Any]],
    commit_trace: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    root = root.resolve()
    operation = _token(operation_id)
    command_token = _token(command, 80)
    fingerprint = _payload_hash(command_token, payload)
    with operation_lock(root):
        journal = _load_operations(root)
        operations = journal["operations"]
        previous = operations.get(operation)
        if previous:
            if previous.get("payload_hash") != fingerprint:
                raise RuntimeError("operation id was already used with a different payload")
            if previous.get("status") == "COMPLETE":
                return {**(previous.get("result") or {}), "idempotent_replay": True}
            if previous.get("status") == "RECOVERY_REQUIRED":
                raise RuntimeError("operation requires explicit recovery review; automatic replay is blocked")
        uncertain = [
            key for key, value in operations.items()
            if key != operation and value.get("status") in UNCERTAIN_STATUSES
        ]
        if uncertain:
            raise RuntimeError("another interrupted control operation must be recovered before a new write")
        if previous:
            entry = previous
            entry["attempts"] = int(entry.get("attempts") or 1) + 1
            entry["retry_count"] = int(entry.get("retry_count") or 0) + 1
            if entry.get("status") == "FAILED_BEFORE_COMMIT":
                entry["status"] = "PREPARED"
        else:
            facts = _prepared_facts(prepare())
            entry = operations[operation] = {
                "command": command_token,
                "operation_type": command_token,
                "task_id": payload.get("task_id"),
                "payload_hash": fingerprint,
                "status": "PREPARED",
                "started_at": utc_now(),
                "prepared_at": utc_now(),
                "attempts": 1,
                "retry_count": 0,
                "before_fingerprint": facts["before_fingerprint"],
                "intended_after_fingerprint": facts["intended_after_fingerprint"],
                "committed_after_fingerprint": None,
                "domain_commit_timestamp": None,
                "trace_status": "NOT_ATTEMPTED",
            }
            _persist(root, journal)

        domain_result = dict(entry.get("domain_result") or {})
        if entry.get("status") in {"PREPARED", "FAILED_BEFORE_COMMIT"}:
            should_commit = previous is None
            if previous is not None:
                recovery = recover_domain(entry)
                recovery_status = str(recovery.get("status") or "UNKNOWN")
                if recovery_status == "COMMITTED":
                    domain_result, committed_fingerprint = _committed_facts(recovery)
                    should_commit = False
                elif (
                    recovery_status == "NOT_COMMITTED"
                    and recovery.get("current_fingerprint") == entry.get("before_fingerprint")
                ):
                    should_commit = True
                else:
                    entry.update({
                        "status": "RECOVERY_REQUIRED",
                        "recovery_required_at": utc_now(),
                        "recovery_observed_fingerprint": recovery.get("current_fingerprint"),
                    })
                    _persist(root, journal)
                    raise RuntimeError("domain state and operation journal cannot prove a safe replay")
            if should_commit:
                try:
                    committed = commit_domain()
                    domain_result, committed_fingerprint = _committed_facts(committed)
                except Exception as exc:
                    recovery = recover_domain(entry)
                    if recovery.get("status") == "COMMITTED":
                        domain_result, committed_fingerprint = _committed_facts(recovery)
                    else:
                        safe_before = (
                            recovery.get("status") == "NOT_COMMITTED"
                            and recovery.get("current_fingerprint") == entry.get("before_fingerprint")
                        )
                        entry.update({
                            "status": "FAILED_BEFORE_COMMIT" if safe_before else "RECOVERY_REQUIRED",
                            "failed_before_commit_at" if safe_before else "recovery_required_at": utc_now(),
                            **_error_facts(exc),
                        })
                        _persist(root, journal)
                        raise
            entry.update({
                "status": "DOMAIN_COMMITTED",
                "domain_result": domain_result,
                "committed_after_fingerprint": committed_fingerprint,
                "domain_commit_timestamp": entry.get("domain_commit_timestamp") or utc_now(),
                "trace_status": "PENDING",
            })
            try:
                _persist(root, journal)
            except OSError:
                return _operation_result(
                    operation,
                    domain_result,
                    operation_status="DOMAIN_COMMITTED",
                    trace_status="NOT_ATTEMPTED",
                    journal_status="COMMIT_RECORD_PENDING",
                )
        elif entry.get("status") in {"DOMAIN_COMMITTED", "TRACE_PENDING"}:
            recovery = recover_domain(entry)
            if recovery.get("status") != "COMMITTED":
                entry.update({"status": "RECOVERY_REQUIRED", "recovery_required_at": utc_now()})
                _persist(root, journal)
                raise RuntimeError("committed domain state can no longer be verified")
            recovered_result, recovered_fingerprint = _committed_facts(recovery)
            if recovered_fingerprint != entry.get("committed_after_fingerprint"):
                entry.update({
                    "status": "RECOVERY_REQUIRED",
                    "recovery_required_at": utc_now(),
                    "recovery_observed_fingerprint": recovered_fingerprint,
                })
                _persist(root, journal)
                raise RuntimeError("committed domain fingerprint changed; automatic recovery is blocked")
            domain_result = recovered_result
        else:
            raise RuntimeError(f"unsupported operation recovery status: {entry.get('status')}")

        try:
            trace_result = _compact_result(commit_trace(domain_result))
        except TraceWriteError as exc:
            entry.update({
                "status": "TRACE_PENDING",
                "trace_status": "PENDING",
                "trace_pending_at": utc_now(),
                **_error_facts(exc),
            })
            try:
                _persist(root, journal)
                journal_status = "COMMITTED"
            except OSError:
                journal_status = "TRACE_PENDING_RECORD_PENDING"
            return _operation_result(
                operation,
                domain_result,
                operation_status="TRACE_PENDING",
                trace_status="PENDING",
                journal_status=journal_status,
            )
        except Exception as exc:
            entry.update({
                "status": "RECOVERY_REQUIRED",
                "trace_status": "UNKNOWN",
                "recovery_required_at": utc_now(),
                **_error_facts(exc),
            })
            try:
                _persist(root, journal)
                journal_status = "COMMITTED"
            except OSError:
                journal_status = "RECOVERY_RECORD_PENDING"
            return _operation_result(
                operation,
                domain_result,
                operation_status="RECOVERY_REQUIRED",
                trace_status="UNKNOWN",
                journal_status=journal_status,
            )

        result = _operation_result(
            operation,
            domain_result,
            operation_status="COMPLETE",
            trace_status="COMMITTED",
            journal_status="COMMITTED",
            trace=trace_result,
        )
        entry.update({
            "status": "COMPLETE",
            "trace_status": "COMMITTED",
            "trace_committed_at": utc_now(),
            "completed_at": utc_now(),
            "result": result,
        })
        if len(operations) > MAX_OPERATIONS:
            removable = [
                key for key, value in operations.items()
                if key != operation and value.get("status") not in UNCERTAIN_STATUSES
            ]
            for key in removable[: max(0, len(operations) - MAX_OPERATIONS)]:
                operations.pop(key, None)
        try:
            _persist(root, journal)
            return result
        except OSError:
            return _operation_result(
                operation,
                domain_result,
                operation_status="DOMAIN_COMMITTED",
                trace_status="COMMITTED",
                journal_status="FINALIZE_PENDING",
                trace=trace_result,
            )


def operation_status(root: Path) -> dict[str, Any]:
    journal = _load_operations(root.resolve())
    counts: dict[str, int] = {}
    for item in journal["operations"].values():
        status = str(item.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": journal.get("revision"),
        "counts": counts,
        "bounded_operation_count": len(journal["operations"]),
        "max_operations": MAX_OPERATIONS,
    }
