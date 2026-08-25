from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


def run_cli(
    record_event: Callable[..., dict[str, Any]],
    status: Callable[[Path], dict[str, Any]],
    summary_messages: dict[str, str],
    archived_segment: Callable[[Path, str], list[dict[str, Any]]] | None = None,
) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="记录或查询有界控制事件；只接受枚举摘要码与相对证据路径")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    if archived_segment is not None:
        archive = sub.add_parser("archive-read")
        archive.add_argument("--segment-id", required=True)
    command = sub.add_parser("record")
    command.add_argument("--event-type", required=True)
    command.add_argument("--summary-code", choices=sorted(summary_messages), required=True)
    command.add_argument("--task-id")
    command.add_argument("--phase", default="unknown")
    command.add_argument("--skill", action="append", default=[])
    command.add_argument("--tool")
    command.add_argument("--result", default="UNKNOWN")
    command.add_argument("--gate-result")
    command.add_argument("--cache-hit", action="store_true")
    command.add_argument("--evidence", action="append", default=[])
    command.add_argument("--duration-ms", type=float, default=0.0)
    command.add_argument("--trace-id")
    command.add_argument("--parent-id")
    command.add_argument("--operation-id", required=True)
    command.add_argument("--operation-fingerprint")
    command.add_argument("--durable", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "status":
            result = status(root)
        elif args.command == "archive-read":
            result = {"segment_id": args.segment_id, "events": archived_segment(root, args.segment_id)}
        else:
            result = record_event(
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
            trace_id=args.trace_id,
            parent_id=args.parent_id,
            operation_id=args.operation_id,
            operation_fingerprint=args.operation_fingerprint,
            durable=args.durable,
            )
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, separators=(",", ":")))
        return 2
