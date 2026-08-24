from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from corelib import ai_root, atomic_write_json, read_json, state_lock, utc_now
from context_memory import ensure_memory_policy


SCHEMA = "1.1.0"
SOFT_RATIO = 0.75


def state_file(root: Path) -> Path:
    return ai_root(root) / "runtime" / "session-epoch.json"


def default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "epoch": 1,
        "substantive_turns": 0,
        "tool_calls": 0,
        "tool_output_chars": 0,
        "compactions": 0,
        "stage_transitions": 0,
        "last_checkpoint_id": None,
        "started_at": utc_now(),
        "updated_at": utc_now(),
    }


def load(root: Path) -> dict[str, Any]:
    with state_lock(root):
        data = read_json(state_file(root), {}) or {}
        if not data:
            data = default_state()
            atomic_write_json(state_file(root), data)
        return data


def assess(root: Path, state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or load(root)
    policy = ensure_memory_policy(root)
    checks = {
        "substantive_turns": (int(state.get("substantive_turns") or 0), int(policy["max_session_epoch_turns"])),
        "tool_calls": (int(state.get("tool_calls") or 0), int(policy["max_session_epoch_tool_calls"])),
        "tool_output_chars": (int(state.get("tool_output_chars") or 0), int(policy["max_session_epoch_tool_output_chars"])),
        "compactions": (int(state.get("compactions") or 0), int(policy["max_session_epoch_compactions"])),
    }
    reasons = [name for name, (value, limit) in checks.items() if value >= limit]
    soft_reasons = [
        name for name, (value, limit) in checks.items()
        if name != "compactions" and value >= max(1, math.ceil(limit * SOFT_RATIO)) and value < limit
    ]
    return {
        "schema_version": SCHEMA,
        "epoch": int(state.get("epoch") or 1),
        "rotation_required": bool(reasons),
        "checkpoint_recommended": bool(soft_reasons) and not reasons,
        "continuation_allowed": not reasons,
        "risk": "CRITICAL" if reasons else ("WARNING" if soft_reasons else "NORMAL"),
        "reasons": reasons,
        "soft_reasons": soft_reasons,
        "counters": {name: value for name, (value, _) in checks.items()},
        "limits": {name: limit for name, (_, limit) in checks.items()},
        "stage_transitions": int(state.get("stage_transitions") or 0),
        "last_checkpoint_id": state.get("last_checkpoint_id"),
        "rule": "软阈值只在自然阶段边界保存Checkpoint；硬阈值禁止继续实质执行，并由唯一新总控纪元接管",
    }


def record(root: Path, **increments: int) -> dict[str, Any]:
    with state_lock(root):
        state = load(root)
        for key in ("substantive_turns", "tool_calls", "tool_output_chars", "compactions", "stage_transitions"):
            value = int(increments.get(key) or 0)
            if value < 0:
                raise RuntimeError(f"{key} increment cannot be negative")
            state[key] = int(state.get(key) or 0) + value
        state["updated_at"] = utc_now()
        atomic_write_json(state_file(root), state)
        return assess(root, state)


def rotate(root: Path, checkpoint_id: str) -> dict[str, Any]:
    if not checkpoint_id.strip():
        raise RuntimeError("session epoch rotation requires a checkpoint id")
    with state_lock(root):
        current = load(root)
        archive = ai_root(root) / "archive" / "session-epochs" / f"epoch-{int(current.get('epoch') or 1):04d}.json"
        if not archive.exists():
            atomic_write_json(archive, current)
        next_state = default_state()
        next_state["epoch"] = int(current.get("epoch") or 1) + 1
        next_state["last_checkpoint_id"] = checkpoint_id
        atomic_write_json(state_file(root), next_state)
        return assess(root, next_state)


def main() -> int:
    parser = argparse.ArgumentParser(description="跟踪长期总控会话的有界执行纪元")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    command = sub.add_parser("record")
    command.add_argument("--substantive-turns", type=int, default=0)
    command.add_argument("--tool-calls", type=int, default=0)
    command.add_argument("--tool-output-chars", type=int, default=0)
    command.add_argument("--compactions", type=int, default=0)
    command.add_argument("--stage-transitions", type=int, default=0)
    command = sub.add_parser("rotate")
    command.add_argument("--checkpoint-id", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "record":
        result = record(root, substantive_turns=args.substantive_turns, tool_calls=args.tool_calls, tool_output_chars=args.tool_output_chars, compactions=args.compactions, stage_transitions=args.stage_transitions)
    elif args.command == "rotate":
        result = rotate(root, args.checkpoint_id)
    else:
        result = assess(root)
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
