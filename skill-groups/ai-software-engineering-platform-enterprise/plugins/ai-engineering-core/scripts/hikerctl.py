from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Public imports preserve the 5.16 Python integration surface while this file stays a thin CLI.
from control_admission import admit, capability_profile
from control_common import capability_indexes, load_capability_registry
from control_trace import record_event, status as trace_status
from control_verification import verify
from control_handoff import acknowledge_handoff, create_handoff
from control_workflow import change_goal, checkpoint, rebind_goal, transition


def _proposal(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "project_mode": args.project_mode,
        "architecture": args.architecture,
        "stage": args.stage,
        "current_action": args.current_action,
        "goal_revision": args.goal_revision,
        "confidence": args.confidence,
        "candidates": args.candidate,
        "deferred": args.deferred,
        "risk_signals": args.risk_signal,
        "negated_terms": args.negated_term,
        "future_terms": args.future_term,
        "follow_up_actions": args.follow_up_action,
    }


def _admit_parser(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("admit")
    command.add_argument("--project-mode", choices=["greenfield", "brownfield", "existing", "unknown"], required=True)
    command.add_argument("--architecture", choices=["bs", "cs", "backend", "hybrid", "tooling", "unknown"], required=True)
    command.add_argument("--stage", choices=["planning", "design", "development", "review", "testing", "governance", "merge", "release", "unknown"], required=True)
    command.add_argument("--current-action", required=True)
    command.add_argument("--goal-revision", default="current")
    command.add_argument("--confidence", choices=["low", "medium", "high"], default="medium")
    for name in ["candidate", "deferred", "focus", "focus-evidence", "risk-signal", "negated-term", "future-term", "follow-up-action", "changed"]:
        command.add_argument(f"--{name}", action="append", default=[])
    command.add_argument("--task-id")
    command.add_argument("--trace", action="store_true")
    command.add_argument("--operation-id")


def _workflow_parsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("transition")
    command.add_argument("--task-id", required=True)
    command.add_argument("--to")
    command.add_argument("--agent-role", default="Master Agent")
    command.add_argument("--commit-id")
    command.add_argument("--control-action", choices=["pause", "resume", "adjust", "insert"])
    command.add_argument("--instruction", default="")
    command.add_argument("--new-task-id")
    command.add_argument("--branch")
    command.add_argument("--base-branch", default="develop")
    command.add_argument("--operation-id", required=True)

    command = sub.add_parser("goal-rebind", help="deprecated and blocked; use goal-change")
    command.add_argument("--task-id", required=True)
    command.add_argument("--agent-role", choices=["Master Agent", "Planning Agent"], default="Master Agent")
    command.add_argument("--impact", choices=["affected", "unaffected"], required=True)
    command.add_argument("--impact-summary", required=True)
    command.add_argument("--retain-change", action="append", default=[])
    command.add_argument("--revise-change", action="append", default=[])
    command.add_argument("--retire-change", action="append", default=[])
    command.add_argument("--operation-id", required=True)

    command = sub.add_parser("goal-change", help="atomically revise a goal from a structured impact plan")
    command.add_argument("--plan-file", required=True)
    command.add_argument("--operation-id", required=True)

    command = sub.add_parser("checkpoint")
    command.add_argument("--task-id", required=True)
    command.add_argument("--label", required=True)
    command.add_argument("--operation-id", required=True)

    command = sub.add_parser("handoff")
    mode = command.add_mutually_exclusive_group(required=True)
    mode.add_argument("--task-id")
    mode.add_argument("--ack")
    command.add_argument("--to-role")
    command.add_argument("--role")
    command.add_argument("--summary-path")
    command.add_argument("--evidence", action="append", default=[])
    command.add_argument("--operation-id", required=True)


def _observability_parsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("trace")
    command.add_argument("--status", action="store_true")
    command.add_argument("--event-type")
    command.add_argument("--task-id")
    command.add_argument("--phase", default="unknown")
    command.add_argument("--skill", action="append", default=[])
    command.add_argument("--tool")
    command.add_argument("--result", default="UNKNOWN")
    command.add_argument("--gate-result")
    command.add_argument("--cache-hit", action="store_true")
    command.add_argument("--summary-code", choices=[
        "ADMISSION_ACCEPTED", "ADMISSION_BLOCKED", "STATE_TRANSITIONED", "STATE_TRANSITION_BLOCKED",
        "CHECKPOINT_SAVED", "HANDOFF_CREATED", "HANDOFF_ACKNOWLEDGED", "GOAL_REBOUND", "GATE_PASSED", "GATE_BLOCKED",
        "RUNTIME_RELEASE_UNVERIFIED", "CONTROL_EVENT",
    ])
    command.add_argument("--evidence", action="append", default=[])
    command.add_argument("--duration-ms", type=float, default=0.0)
    command.add_argument("--operation-id")

    command = sub.add_parser("verify")
    command.add_argument("--profile", choices=["quick", "task", "merge", "release"], default="quick")
    command.add_argument("--task-id")
    command.add_argument("--file", action="append", default=[])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hiker工程能力系统本地确定性控制入口；不调用外部模型API或后台服务")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    _admit_parser(sub)
    _workflow_parsers(sub)
    _observability_parsers(sub)
    return parser


def _dispatch(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    if args.command == "admit":
        result = admit(
            root,
            _proposal(args),
            task_id=args.task_id,
            changed_paths=args.changed,
            focuses=args.focus,
            focus_evidence=args.focus_evidence,
            force_trace=args.trace,
            operation_id=args.operation_id,
        )
        return result, result["decision"] == "ACCEPT"
    if args.command == "transition":
        return transition(root, args), True
    if args.command == "goal-rebind":
        return rebind_goal(root, args), True
    if args.command == "goal-change":
        return change_goal(root, args), True
    if args.command == "checkpoint":
        return checkpoint(root, args.task_id, args.label, args.operation_id), True
    if args.command == "handoff":
        if args.ack:
            if not args.role:
                raise ValueError("handoff --ack requires --role")
            return acknowledge_handoff(root, args.ack, args.role, args.operation_id), True
        if not args.to_role or not args.summary_path:
            raise ValueError("handoff --task-id requires --to-role and --summary-path")
        return create_handoff(root, args.task_id, args.to_role, args.summary_path, args.evidence, args.operation_id), True
    if args.command == "trace":
        if args.status or not args.event_type:
            return trace_status(root), True
        if not args.summary_code or not args.operation_id:
            raise ValueError("trace record requires --summary-code and --operation-id")
        return record_event(
            root,
            event_type=args.event_type,
            summary_code=args.summary_code,
            task_id=args.task_id,
            phase=args.phase,
            skills=args.skill,
            tool=args.tool,
            result=args.result,
            gate_result=args.gate_result,
            cache_hit=args.cache_hit,
            evidence_paths=args.evidence,
            duration_ms=args.duration_ms,
            operation_id=args.operation_id,
        ), True
    result = verify(root, args.task_id, args.file, args.profile)
    return result, bool(result["ok"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        result, ok = _dispatch(Path(args.root).resolve(), args)
        print(json.dumps({"ok": ok, "result": result}, ensure_ascii=False, separators=(",", ":")))
        return 0 if ok else 2
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
