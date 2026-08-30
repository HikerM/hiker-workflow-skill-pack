from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from control_common import SCHEMA_VERSION, bounded, inside, safe_id, workspace_module, write_context
from control_kernel import execute_operation, write_gate
from control_trace import record_event
from corelib import atomic_write_json, read_json, sha256_file


def _fingerprint_paths(root: Path, relative_paths: list[str]) -> str:
    facts = []
    for relative in sorted(dict.fromkeys(relative_paths)):
        path, normalized = inside(root, relative)
        facts.append({"path": normalized, "sha256": sha256_file(path) if path.is_file() else None})
    raw = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _intended_fingerprint(command: str, payload: dict[str, Any], before_fingerprint: str) -> str:
    raw = json.dumps(
        {"command": command, "payload": payload, "before_fingerprint": before_fingerprint},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _task_path(task_id: str) -> str:
    return f".ai/tasks/{safe_id(task_id).upper()}.json"


def _domain_recovery(
    root: Path,
    entry: dict[str, Any],
    relative_paths: list[str],
    *,
    operation_proved: bool,
    domain_result: dict[str, Any],
) -> dict[str, Any]:
    current = _fingerprint_paths(root, relative_paths)
    committed = entry.get("committed_after_fingerprint")
    if operation_proved or (
        entry.get("status") in {"DOMAIN_COMMITTED", "TRACE_PENDING"}
        and committed
        and current == committed
    ):
        return {
            "status": "COMMITTED",
            "domain_result": domain_result,
            "committed_after_fingerprint": current,
        }
    return {"status": "NOT_COMMITTED", "current_fingerprint": current}


def transition(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    module = workspace_module("governance_state")
    root = root.resolve()
    if not args.control_action and not args.to:
        raise ValueError("transition requires --to or --control-action")
    target = f"CONTROL:{args.control_action}" if args.control_action else str(args.to)
    payload = {
        "task_id": safe_id(args.task_id).upper(),
        "target": target,
        "agent_role": args.agent_role,
        "commit_id": args.commit_id,
        "instruction_hash": hashlib.sha256(
            str(args.instruction or "").encode("utf-8", errors="replace")
        ).hexdigest() if args.instruction else None,
        "instruction_chars": len(str(args.instruction or "")),
        "new_task_id": args.new_task_id,
        "branch": args.branch,
        "base_branch": args.base_branch,
    }

    relative_paths = [_task_path(args.task_id)]
    prepared_context: dict[str, Any] = {}

    def task_result(task: dict[str, Any], gate: dict[str, Any], recovered: bool) -> dict[str, Any]:
        return {
            "task_id": args.task_id,
            "state": task.get("state"),
            "control_status": task.get("control_status"),
            "target": target,
            "recovered_after_interruption": recovered,
            "suite_fingerprint": gate.get("suite_fingerprint"),
        }

    def prepare() -> dict[str, Any]:
        task, goal, gate = write_context(
            root,
            args.task_id,
            allow_version_recovery=args.control_action == "pause",
            allow_epoch_overrun=args.control_action == "pause",
        )
        prepared_context.update({"task": task, "goal": goal, "gate": gate})
        before = _fingerprint_paths(root, relative_paths)
        return {
            "before_fingerprint": before,
            "intended_after_fingerprint": _intended_fingerprint("transition", payload, before),
        }

    def commit_domain() -> dict[str, Any]:
        if prepared_context:
            before = prepared_context["task"]
            gate = prepared_context["gate"]
        else:
            before, _, gate = write_context(
                root,
                args.task_id,
                allow_version_recovery=args.control_action == "pause",
                allow_epoch_overrun=args.control_action == "pause",
            )
        if args.control_action:
            already = (
                args.control_action == "pause" and before.get("control_status") == "PAUSED"
            ) or (
                args.control_action == "resume" and before.get("control_status") == "ACTIVE"
            )
            if recovered or already:
                data = before
            else:
                data = module.control(root, argparse.Namespace(
                    task_id=args.task_id,
                    action=args.control_action,
                    instruction=args.instruction or "",
                    new_task_id=args.new_task_id,
                    branch=args.branch,
                    base_branch=args.base_branch,
                    operation_id=args.operation_id,
                ))
        elif before.get("state") == args.to:
            data = before
        else:
            data = module.transition(root, argparse.Namespace(
                task_id=args.task_id,
                to=args.to,
                agent_role=args.agent_role,
                commit_id=args.commit_id,
                operation_id=args.operation_id,
            ))
        task = data.get("task") if isinstance(data, dict) and isinstance(data.get("task"), dict) else data
        return {
            "domain_result": task_result(task, gate, False),
            "committed_after_fingerprint": _fingerprint_paths(root, relative_paths),
        }

    def recover_domain(entry: dict[str, Any]) -> dict[str, Any]:
        task = module.load_task(root, args.task_id)
        gate = write_gate(
            root,
            allow_version_recovery=args.control_action == "pause",
            allow_epoch_overrun=args.control_action == "pause",
        )
        proved = any(item.get("operation_id") == args.operation_id for item in task.get("history", []))
        return _domain_recovery(
            root,
            entry,
            relative_paths,
            operation_proved=proved,
            domain_result=task_result(task, gate, True),
        )

    def commit_trace(domain_result: dict[str, Any]) -> dict[str, Any]:
        return record_event(
            root,
            event_type="state-transition",
            summary_code="STATE_TRANSITIONED",
            task_id=args.task_id,
            phase=target,
            tool="hikerctl.transition",
            result="PASS",
            gate_result=target,
            evidence_paths=[f".ai/tasks/{safe_id(args.task_id).upper()}.json"],
            operation_id=args.operation_id,
            operation_fingerprint=domain_result.get("suite_fingerprint"),
            durable=True,
        )

    return execute_operation(
        root,
        operation_id=args.operation_id,
        command="transition",
        payload=payload,
        prepare=prepare,
        commit_domain=commit_domain,
        recover_domain=recover_domain,
        commit_trace=commit_trace,
    )


def rebind_goal(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    raise RuntimeError(
        "goal-rebind is deprecated because it can create a partial goal revision; use hikerctl goal-change"
    )


def change_goal(
    root: Path,
    args: argparse.Namespace,
    *,
    fault_injector=None,
) -> dict[str, Any]:
    transaction = workspace_module("goal_change_transaction")
    root = root.resolve()
    raw_plan = getattr(args, "plan", None)
    if raw_plan is None:
        raw_plan = transaction.load_plan(Path(args.plan_file).resolve())
    normalized = transaction.inspect_goal_change(root, raw_plan, args.operation_id)
    task_ids = [item["task_id"] for item in normalized["tasks"]]
    relative_paths = [
        path.relative_to(root).as_posix()
        for path in transaction.transaction_paths(root, args.operation_id, task_ids)
    ]
    counts = {
        name: sum(1 for item in normalized["tasks"] if item["classification"] == name)
        for name in ("AFFECTED", "UNAFFECTED", "SUPERSEDED", "REQUIRES_REVIEW")
    }
    payload = {
        "goal_id": normalized["new_goal"]["goal_id"],
        "base_revision": normalized["base_goal"]["revision"],
        "target_revision": normalized["new_goal"]["revision"],
        "plan_fingerprint": normalized["plan_fingerprint"],
        "task_ids": task_ids,
        "classifications": counts,
    }
    prepared_gate: dict[str, Any] = {}

    def prepare() -> dict[str, Any]:
        prepared_gate.update(write_gate(
            root, allow_version_recovery=True, allow_epoch_overrun=True
        ))
        before = _fingerprint_paths(root, relative_paths)
        return {
            "before_fingerprint": before,
            "intended_after_fingerprint": _intended_fingerprint("goal-change", payload, before),
        }

    def commit_domain() -> dict[str, Any]:
        result = transaction.apply_goal_change(
            root,
            raw_plan,
            args.operation_id,
            fault_injector=fault_injector,
        )
        gate = prepared_gate or write_gate(
            root, allow_version_recovery=True, allow_epoch_overrun=True
        )
        result["suite_fingerprint"] = gate.get("suite_fingerprint")
        return {
            "domain_result": result,
            "committed_after_fingerprint": _fingerprint_paths(root, relative_paths),
        }

    def recover_domain(entry: dict[str, Any]) -> dict[str, Any]:
        recovered = transaction.recover_goal_change(root, raw_plan, args.operation_id)
        current = _fingerprint_paths(root, relative_paths)
        if recovered.get("status") != "COMMITTED":
            return {"status": "NOT_COMMITTED", "current_fingerprint": current}
        result = dict(recovered.get("domain_result") or {})
        gate = write_gate(root, allow_version_recovery=True, allow_epoch_overrun=True)
        result["suite_fingerprint"] = gate.get("suite_fingerprint")
        return {
            "status": "COMMITTED",
            "domain_result": result,
            "committed_after_fingerprint": current,
        }

    def commit_trace(domain_result: dict[str, Any]) -> dict[str, Any]:
        return record_event(
            root,
            event_type="goal-revision-committed",
            summary_code="GOAL_REBOUND",
            task_id=normalized["new_goal"]["goal_id"],
            phase="goal-change",
            tool="hikerctl.goal-change",
            result="PASS",
            gate_result="COMPLETE",
            evidence_paths=[
                ".ai/governance/goal-contract.json",
                f".ai/archive/goal-changes/{safe_id(args.operation_id)}.json",
            ],
            operation_id=args.operation_id,
            operation_fingerprint=normalized["plan_fingerprint"],
            durable=True,
        )

    return execute_operation(
        root,
        operation_id=args.operation_id,
        command="goal-change",
        payload=payload,
        prepare=prepare,
        commit_domain=commit_domain,
        recover_domain=recover_domain,
        commit_trace=commit_trace,
    )


def checkpoint(root: Path, task_id: str, label: str, operation_id: str) -> dict[str, Any]:
    module = workspace_module("governance_state")
    root = root.resolve()
    payload = {"task_id": safe_id(task_id).upper(), "label": safe_id(label)}

    checkpoint_rel = (
        f".ai/runtime/checkpoints/control-{safe_id(operation_id)}-"
        f"{safe_id(task_id).upper()}-{safe_id(label)}.json"
    )
    relative_paths = [checkpoint_rel]
    prepared_context: dict[str, Any] = {}

    def prepare() -> dict[str, Any]:
        task, goal, gate = write_context(
            root, task_id, allow_version_recovery=True, allow_epoch_overrun=True
        )
        prepared_context.update({"task": task, "goal": goal, "gate": gate})
        before = _fingerprint_paths(root, relative_paths)
        return {
            "before_fingerprint": before,
            "intended_after_fingerprint": _intended_fingerprint("checkpoint", payload, before),
        }

    def commit_domain() -> dict[str, Any]:
        if prepared_context:
            task = prepared_context["task"]
            goal = prepared_context["goal"]
            gate = prepared_context["gate"]
        else:
            task, goal, gate = write_context(
                root,
                task_id,
                allow_version_recovery=True,
                allow_epoch_overrun=True,
            )
        path = module.checkpoint(root, task, label, operation_id=operation_id)
        digest = sha256_file(path)
        domain_result = {
            "task_id": task_id,
            "checkpoint": path.relative_to(root).as_posix(),
            "checkpoint_sha256": digest,
            "goal_revision": goal.get("revision"),
            "goal_fingerprint": goal.get("fingerprint"),
            "suite_fingerprint": gate.get("suite_fingerprint"),
            "repo_id": gate.get("repo_id"),
            "head": gate.get("head"),
            "recovered_after_interruption": False,
        }
        return {
            "domain_result": domain_result,
            "committed_after_fingerprint": _fingerprint_paths(root, relative_paths),
        }

    def recover_domain(entry: dict[str, Any]) -> dict[str, Any]:
        path, _ = inside(root, checkpoint_rel)
        data = read_json(path, {}) or {}
        task, goal, gate = write_context(
            root, task_id, allow_version_recovery=True, allow_epoch_overrun=True
        )
        domain_result = {
            "task_id": task_id,
            "checkpoint": checkpoint_rel,
            "checkpoint_sha256": sha256_file(path),
            "goal_revision": goal.get("revision"),
            "goal_fingerprint": goal.get("fingerprint"),
            "suite_fingerprint": gate.get("suite_fingerprint"),
            "repo_id": gate.get("repo_id"),
            "head": gate.get("head"),
            "recovered_after_interruption": True,
        }
        return _domain_recovery(
            root,
            entry,
            relative_paths,
            operation_proved=data.get("operation_id") == safe_id(operation_id),
            domain_result=domain_result,
        )

    def commit_trace(domain_result: dict[str, Any]) -> dict[str, Any]:
        return record_event(
            root,
            event_type="checkpoint",
            summary_code="CHECKPOINT_SAVED",
            task_id=task_id,
            phase="checkpoint",
            tool="hikerctl.checkpoint",
            result="PASS",
            evidence_paths=[str(domain_result.get("checkpoint"))],
            operation_id=operation_id,
            operation_fingerprint=domain_result.get("checkpoint_sha256"),
            durable=True,
        )

    return execute_operation(
        root,
        operation_id=operation_id,
        command="checkpoint",
        payload=payload,
        prepare=prepare,
        commit_domain=commit_domain,
        recover_domain=recover_domain,
        commit_trace=commit_trace,
    )


def record_closure(root: Path, task_id: str, phase: str, operation_id: str) -> dict[str, Any]:
    governance = workspace_module("governance_state")
    closure = workspace_module("closure_gate")
    root = root.resolve()
    if phase not in {"merge", "release"}:
        raise ValueError("closure phase must be merge or release")
    task_key = safe_id(task_id).upper()
    evidence_rel = f".ai/evidence/{task_key}-{phase}-closure.json"
    relative_paths = [_task_path(task_key), evidence_rel]
    payload = {"task_id": task_key, "phase": phase}
    def prepare() -> dict[str, Any]:
        governance.load_task(root, task_key)
        before = _fingerprint_paths(root, relative_paths)
        return {
            "before_fingerprint": before,
            "intended_after_fingerprint": _intended_fingerprint("closure", payload, before),
        }

    def domain_result(task: dict[str, Any], report: dict[str, Any], recovered: bool) -> dict[str, Any]:
        evidence_path, _ = inside(root, evidence_rel)
        return {
            "task_id": task_key,
            "phase": phase,
            "closure_status": (task.get("closure") or {}).get(phase),
            "closure_ok": bool(report.get("ok")),
            "evidence": evidence_rel,
            "evidence_sha256": sha256_file(evidence_path),
            "recovered_after_interruption": recovered,
        }

    def commit_domain() -> dict[str, Any]:
        task = governance.load_task(root, task_key)
        report = closure.evaluate(root, task, phase)
        evidence_path, _ = inside(root, evidence_rel)
        atomic_write_json(evidence_path, report)
        task.setdefault("closure", {})[phase] = "PASS" if report["ok"] else "FAIL"
        if report["ok"]:
            task.setdefault("closure_bindings", {})[phase] = report.get("binding") or {}
        if not any(item.get("operation_id") == operation_id for item in task.get("history", [])):
            task.setdefault("history", []).append({
                "at": closure.now(), "event": f"CLOSURE:{phase}:{task['closure'][phase]}",
                "operation_id": operation_id,
            })
        governance.save_task(root, task)
        return {
            "domain_result": domain_result(task, report, False),
            "committed_after_fingerprint": _fingerprint_paths(root, relative_paths),
        }

    def recover_domain(entry: dict[str, Any]) -> dict[str, Any]:
        task = governance.load_task(root, task_key)
        evidence_path, _ = inside(root, evidence_rel)
        report = read_json(evidence_path, {}) or {}
        proved = any(item.get("operation_id") == operation_id for item in task.get("history", []))
        return _domain_recovery(
            root, entry, relative_paths, operation_proved=proved,
            domain_result=domain_result(task, report, True),
        )

    def commit_trace(result: dict[str, Any]) -> dict[str, Any]:
        return record_event(
            root,
            event_type="closure",
            summary_code="GATE_PASSED" if result.get("closure_ok") else "GATE_BLOCKED",
            task_id=task_key,
            phase=phase,
            tool="closure_gate",
            result="PASS" if result.get("closure_ok") else "FAIL",
            evidence_paths=[evidence_rel],
            operation_id=operation_id,
            operation_fingerprint=result.get("evidence_sha256"),
            durable=True,
        )

    return execute_operation(
        root,
        operation_id=operation_id,
        command="closure",
        payload=payload,
        prepare=prepare,
        commit_domain=commit_domain,
        recover_domain=recover_domain,
        commit_trace=commit_trace,
    )
