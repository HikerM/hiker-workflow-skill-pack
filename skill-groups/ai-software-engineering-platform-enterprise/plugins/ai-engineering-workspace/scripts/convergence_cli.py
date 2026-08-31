from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import convergence_guard as domain
import governance_state as task_store
from implementation_guard import validate_registry
from workspacelib import repo_root, state_lock, worktree_fingerprint


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--task-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("init")
    command.add_argument("--criterion", action="append", default=[])
    command.add_argument("--strategy", default="")
    command = sub.add_parser("observe")
    command.add_argument("--kind", choices=sorted(domain.OBSERVATIONS), required=True)
    command.add_argument("--summary", required=True)
    command.add_argument("--impact", default="")
    command.add_argument("--action", default="")
    command.add_argument("--criterion-id", default="")
    command = sub.add_parser("resolve")
    command.add_argument("--contradiction-id", required=True)
    command.add_argument("--evidence", required=True)
    command = sub.add_parser("strategy-set")
    command.add_argument("--summary", required=True)
    command.add_argument("--reason", required=True)
    command = sub.add_parser("hypothesis-add")
    command.add_argument("--issue-id", required=True)
    command.add_argument("--statement", required=True)
    command.add_argument("--allowed-actions", required=True)
    command.add_argument("--forbidden-actions", required=True)
    command = sub.add_parser("hypothesis-result")
    command.add_argument("--hypothesis-id", required=True)
    command.add_argument("--result", choices=["CONFIRMED", "REJECTED"], required=True)
    command.add_argument("--evidence", required=True)
    command = sub.add_parser("route-set")
    command.add_argument("--responsibility", required=True)
    command.add_argument("--route-id", required=True)
    command.add_argument("--status", choices=["ACTIVE", "MIGRATION", "RETIRED"], required=True)
    command.add_argument("--exit-condition", default="")
    command.add_argument("--removal-evidence", default="")
    command = sub.add_parser("experiment-authorize")
    command.add_argument("--criterion-id", required=True)
    command.add_argument("--hypothesis", required=True)
    command.add_argument("--expected", required=True)
    command.add_argument("--stop-condition", required=True)
    command.add_argument("--environment", choices=["local", "production"], default="local")
    command = sub.add_parser("experiment-result")
    command.add_argument("--experiment-id", required=True)
    command.add_argument("--result", choices=["PASS", "FAIL", "CANCELLED"], required=True)
    command.add_argument("--evidence", required=True)
    command = sub.add_parser("evidence-record")
    command.add_argument("--criterion-id", required=True)
    command.add_argument("--level", choices=sorted(domain.LEVELS), required=True)
    command.add_argument("--status", choices=["PASS", "FAIL"], required=True)
    command.add_argument("--value", required=True)
    command.add_argument("--fingerprint", required=True)
    command = sub.add_parser("progress-record")
    command.add_argument("--lane", choices=["governance", "business"], required=True)
    command.add_argument("--summary", required=True)
    command.add_argument("--next-business-gate", required=True)
    command.add_argument("--override-reason", default="")
    command = sub.add_parser("verification-plan")
    command.add_argument("--gate-id", required=True)
    command.add_argument("--fingerprint", required=True)
    command.add_argument("--scope", required=True)
    command = sub.add_parser("verification-record")
    command.add_argument("--gate-id", required=True)
    command.add_argument("--fingerprint", required=True)
    command.add_argument("--scope", required=True)
    command.add_argument("--mode", choices=["targeted", "full"], required=True)
    command.add_argument("--status", choices=["PASS", "FAIL", "INVALID"], required=True)
    command.add_argument("--evidence", required=True)
    command = sub.add_parser("deployment-set")
    command.add_argument("--source-head", required=True)
    command.add_argument("--remote-head", required=True)
    command.add_argument("--deployed-head", required=True)
    command.add_argument("--post-deploy-evidence", choices=["PENDING", "PASS", "FAIL"], default="PENDING")
    command = sub.add_parser("status")
    command.add_argument("--phase", choices=["status", "experiment", "production-experiment", "merge", "release"], default="status")
    command = sub.add_parser("ack")
    command.add_argument("--fingerprint", required=True)
    return parser


def _execute(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    operation_result: dict[str, Any] | None = None
    task = task_store.load_task(root, args.task_id)
    state = task.get("convergence")
    if args.command == "init":
        state = domain.initialize(task, args.criterion, args.strategy)
        progress = state.setdefault("delivery_progress", {})
        progress.setdefault("baseline_source_fingerprint", worktree_fingerprint(root))
        progress.setdefault("last_business_fingerprint", progress["baseline_source_fingerprint"])
    elif not state or not state.get("required"):
        raise RuntimeError("convergence guard is not initialized for this task")
    elif args.command == "observe":
        domain.observe(state, args.kind, args.summary, args.impact, args.action, args.criterion_id)
    elif args.command == "resolve":
        domain.resolve_contradiction(state, args.contradiction_id, args.evidence)
    elif args.command == "strategy-set":
        domain.set_strategy(state, args.summary, args.reason)
    elif args.command == "hypothesis-add":
        operation_result = domain.register_hypothesis(state, args.issue_id, args.statement, args.allowed_actions, args.forbidden_actions)
    elif args.command == "hypothesis-result":
        operation_result = domain.resolve_hypothesis(state, args.hypothesis_id, args.result, args.evidence)
    elif args.command == "route-set":
        domain.register_route(state, args.responsibility, args.route_id, args.status, args.exit_condition, args.removal_evidence)
    elif args.command == "experiment-authorize":
        domain.authorize_experiment(state, args.criterion_id, args.hypothesis, args.expected, args.stop_condition, args.environment)
    elif args.command == "experiment-result":
        domain.finish_experiment(state, args.experiment_id, args.result, args.evidence)
    elif args.command == "evidence-record":
        domain.record_evidence(state, args.criterion_id, args.level, args.status, args.value, args.fingerprint)
    elif args.command == "progress-record":
        operation_result = domain.record_progress(state, args.lane, args.summary, args.next_business_gate, worktree_fingerprint(root), args.override_reason)
    elif args.command == "verification-plan":
        operation_result = domain.verification_plan(state, args.gate_id, args.fingerprint, args.scope)
    elif args.command == "verification-record":
        operation_result = domain.record_verification(state, args.gate_id, args.fingerprint, args.scope, args.mode, args.status, args.evidence)
    elif args.command == "deployment-set":
        domain.set_deployment(state, args.source_head, args.remote_head, args.deployed_head, args.post_deploy_evidence)
    elif args.command == "ack":
        domain.acknowledge(state, args.fingerprint)
    task["convergence"] = state
    task_store.save_task(root, task)
    phase = args.phase if args.command == "status" else "status"
    report = domain.health_report(state, phase)
    implementation_report = validate_registry(root)
    if not implementation_report["ok"]:
        report["ok"] = False
        report["severity"] = "BLOCKED"
        report["blockers"].extend(f"实现唯一性门禁：{item['message']}" for item in implementation_report["errors"])
        report["actions"].append("收敛为一个权威活动实现和一个权威状态写入者")
    return state, report, operation_result


def main() -> int:
    args = _parser().parse_args()
    root = repo_root(Path(args.root).resolve())
    try:
        with state_lock(root):
            state, report, operation_result = _execute(root, args)
        print(json.dumps({"ok": report["ok"], "result": report, "operation": operation_result, "state": state}, ensure_ascii=False, indent=2))
        return 0 if args.command != "status" or report["ok"] else 2
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
