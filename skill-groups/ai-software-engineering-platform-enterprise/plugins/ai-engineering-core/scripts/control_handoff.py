from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from control_common import SCHEMA_VERSION, bounded, inside, safe_id, write_context
from control_kernel import execute_operation
from control_trace import record_event
from control_workflow import _domain_recovery, _fingerprint_paths, _intended_fingerprint
from corelib import ai_root, atomic_write_json, read_json, sha256_file, state_lock, utc_now


def handoff_path(root: Path, handoff_id: str) -> Path:
    return ai_root(root) / "runtime" / "handoffs" / f"{safe_id(handoff_id)}.json"


def create_handoff(
    root: Path,
    task_id: str,
    to_role: str,
    summary_path: str,
    evidence_paths: list[str],
    operation_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    summary_file, summary_rel = inside(root, summary_path)
    if not summary_file.is_file():
        raise RuntimeError("handoff summary file does not exist")
    if summary_file.stat().st_size > 8 * 1024:
        raise RuntimeError("handoff summary exceeds 8KiB bounded-context limit")
    evidence_input = []
    for raw in bounded(evidence_paths, 8):
        path, relative = inside(root, raw)
        evidence_input.append({"path": relative, "sha256": sha256_file(path)})
    operation_payload = {
        "task_id": safe_id(task_id).upper(),
        "to_role": to_role,
        "summary_path": summary_rel,
        "summary_sha256": sha256_file(summary_file),
        "evidence": evidence_input,
    }
    task, goal, gate = write_context(
        root, task_id, allow_version_recovery=True, allow_epoch_overrun=True
    )
    packet = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task.get("task_id"),
        "from_role": task.get("owner_agent"),
        "to_role": to_role,
        "phase": task.get("state"),
        "goal_revision": goal.get("revision"),
        "goal_fingerprint": goal.get("fingerprint"),
        "suite_fingerprint": gate.get("suite_fingerprint"),
        "repo_id": gate.get("repo_id"),
        "head": gate.get("head"),
        "summary": {
            "path": summary_rel,
            "sha256": sha256_file(summary_file),
            "bytes": summary_file.stat().st_size,
        },
        "evidence": evidence_input,
        "status": "PENDING_ACK",
        "created_at": utc_now(),
        "operation_id": operation_id,
    }
    basis = json.dumps(
        {key: value for key, value in packet.items() if key != "created_at"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    handoff_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
    packet["handoff_id"] = handoff_id
    path = handoff_path(root, handoff_id)
    packet_rel = path.relative_to(root).as_posix()
    relative_paths = [packet_rel]

    def domain_result(recovered: bool, current: dict[str, Any]) -> dict[str, Any]:
        return {
            "handoff_id": handoff_id,
            "status": current.get("status"),
            "packet": packet_rel,
            "recovered_after_interruption": recovered,
        }

    def prepare() -> dict[str, Any]:
        before = _fingerprint_paths(root, relative_paths)
        return {
            "before_fingerprint": before,
            "intended_after_fingerprint": _intended_fingerprint(
                "handoff-create", operation_payload, before
            ),
        }

    def commit_domain() -> dict[str, Any]:
        with state_lock(root):
            existing = read_json(path, {}) or {}
            if existing:
                current = existing
            else:
                atomic_write_json(path, packet)
                current = packet
        return {
            "domain_result": domain_result(False, current),
            "committed_after_fingerprint": _fingerprint_paths(root, relative_paths),
        }

    def recover_domain(entry: dict[str, Any]) -> dict[str, Any]:
        current = read_json(path, {}) or {}
        return _domain_recovery(
            root,
            entry,
            relative_paths,
            operation_proved=current.get("operation_id") == operation_id,
            domain_result=domain_result(True, current),
        )

    def commit_trace(result: dict[str, Any]) -> dict[str, Any]:
        return record_event(
            root,
            event_type="handoff-created",
            summary_code="HANDOFF_CREATED",
            task_id=task_id,
            phase=str(task.get("state") or "unknown"),
            tool="hikerctl.handoff",
            result="PENDING",
            evidence_paths=[packet_rel, summary_rel],
            operation_id=operation_id,
            operation_fingerprint=handoff_id,
            durable=True,
        )

    return execute_operation(
        root,
        operation_id=operation_id,
        command="handoff-create",
        payload=operation_payload,
        prepare=prepare,
        commit_domain=commit_domain,
        recover_domain=recover_domain,
        commit_trace=commit_trace,
    )


def acknowledge_handoff(
    root: Path,
    handoff_id: str,
    role: str,
    operation_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    path = handoff_path(root, handoff_id)
    packet_rel = path.relative_to(root).as_posix()
    relative_paths = [packet_rel]
    operation_payload = {"handoff_id": safe_id(handoff_id), "role": role}

    def domain_result(recovered: bool, packet: dict[str, Any]) -> dict[str, Any]:
        return {
            "handoff_id": handoff_id,
            "task_id": packet.get("task_id"),
            "phase": packet.get("phase"),
            "status": packet.get("status"),
            "packet": packet_rel,
            "recovered_after_interruption": recovered,
        }

    def prepare() -> dict[str, Any]:
        packet = read_json(path, {}) or {}
        if not packet:
            raise RuntimeError("handoff packet not found")
        before = _fingerprint_paths(root, relative_paths)
        return {
            "before_fingerprint": before,
            "intended_after_fingerprint": _intended_fingerprint(
                "handoff-ack", operation_payload, before
            ),
        }

    def commit_domain() -> dict[str, Any]:
        with state_lock(root):
            packet = read_json(path, {}) or {}
            if not packet:
                raise RuntimeError("handoff packet not found")
            if packet.get("to_role") != role:
                raise RuntimeError("handoff role does not match packet recipient")
            _, goal, gate = write_context(
                root,
                str(packet.get("task_id")),
                allow_version_recovery=True,
                allow_epoch_overrun=True,
            )
            if (
                packet.get("goal_revision") != goal.get("revision")
                or packet.get("goal_fingerprint") != goal.get("fingerprint")
            ):
                raise RuntimeError("handoff packet goal binding is stale")
            if (
                packet.get("suite_fingerprint") != gate.get("suite_fingerprint")
                or packet.get("repo_id") != gate.get("repo_id")
            ):
                raise RuntimeError("handoff packet suite or project identity is stale")
            summary = packet.get("summary") or {}
            summary_file, _ = inside(root, str(summary.get("path") or ""))
            if sha256_file(summary_file) != summary.get("sha256"):
                raise RuntimeError("handoff summary changed after preparation")
            for item in packet.get("evidence") or []:
                evidence_file, _ = inside(root, str(item.get("path") or ""))
                if sha256_file(evidence_file) != item.get("sha256"):
                    raise RuntimeError("handoff evidence changed after preparation")
            if packet.get("status") != "ACKNOWLEDGED":
                packet["status"] = "ACKNOWLEDGED"
                packet["acknowledged_at"] = utc_now()
                packet["ack_operation_id"] = operation_id
                atomic_write_json(path, packet)
        return {
            "domain_result": domain_result(False, packet),
            "committed_after_fingerprint": _fingerprint_paths(root, relative_paths),
        }

    def recover_domain(entry: dict[str, Any]) -> dict[str, Any]:
        packet = read_json(path, {}) or {}
        return _domain_recovery(
            root,
            entry,
            relative_paths,
            operation_proved=packet.get("ack_operation_id") == operation_id,
            domain_result=domain_result(True, packet),
        )

    def commit_trace(result: dict[str, Any]) -> dict[str, Any]:
        return record_event(
            root,
            event_type="handoff-acknowledged",
            summary_code="HANDOFF_ACKNOWLEDGED",
            task_id=result.get("task_id"),
            phase=str(result.get("phase") or "unknown"),
            tool="hikerctl.handoff",
            result="PASS",
            evidence_paths=[packet_rel],
            operation_id=operation_id,
            operation_fingerprint=handoff_id,
            durable=True,
        )

    return execute_operation(
        root,
        operation_id=operation_id,
        command="handoff-ack",
        payload=operation_payload,
        prepare=prepare,
        commit_domain=commit_domain,
        recover_domain=recover_domain,
        commit_trace=commit_trace,
    )

