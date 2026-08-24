from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, locked_state, read_json, repo_root, safe_id


SCHEMA = "1.0.0"


def contract_file(root: Path) -> Path:
    return root / ".ai" / "governance" / "goal-contract.json"


def _stable_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal_id": data.get("goal_id"),
        "revision": int(data.get("revision") or 0),
        "outcome": str(data.get("outcome") or "").strip(),
        "non_goals": list(data.get("non_goals") or []),
        "acceptance_ids": list(data.get("acceptance_ids") or []),
        "behavior_invariants": list(data.get("behavior_invariants") or []),
        "constraints": list(data.get("constraints") or []),
        "priority_order": list(data.get("priority_order") or []),
    }


def fingerprint(data: dict[str, Any]) -> str:
    raw = json.dumps(_stable_payload(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def empty_contract() -> dict[str, Any]:
    data = {
        "schema_version": SCHEMA,
        "status": "UNSET",
        "goal_id": None,
        "revision": 0,
        "outcome": "",
        "non_goals": [],
        "acceptance_ids": [],
        "behavior_invariants": [],
        "constraints": [],
        "priority_order": [],
        "fingerprint": None,
    }
    return data


@locked_state
def ensure_contract(root: Path) -> dict[str, Any]:
    path = contract_file(root)
    current = read_json(path, {}) or {}
    if not current:
        current = empty_contract()
        atomic_json(path, current)
    return current


@locked_state
def set_contract(
    root: Path,
    goal_id: str,
    outcome: str,
    non_goals: list[str] | None = None,
    acceptance_ids: list[str] | None = None,
    behavior_invariants: list[str] | None = None,
    constraints: list[str] | None = None,
    priority_order: list[str] | None = None,
) -> dict[str, Any]:
    if not outcome.strip():
        raise RuntimeError("goal outcome is required")
    previous = ensure_contract(root)
    revision = int(previous.get("revision") or 0) + 1
    data = {
        "schema_version": SCHEMA,
        "status": "ACTIVE",
        "goal_id": safe_id(goal_id).upper(),
        "revision": revision,
        "outcome": outcome.strip(),
        "non_goals": list(dict.fromkeys(non_goals or [])),
        "acceptance_ids": list(dict.fromkeys(acceptance_ids or [])),
        "behavior_invariants": list(dict.fromkeys(behavior_invariants or [])),
        "constraints": list(dict.fromkeys(constraints or [])),
        "priority_order": list(dict.fromkeys(priority_order or [])),
    }
    data["fingerprint"] = fingerprint(data)
    if previous.get("status") == "ACTIVE":
        archive = root / ".ai" / "archive" / "goal-contracts" / f"{safe_id(str(previous.get('goal_id') or 'goal'))}-r{int(previous.get('revision') or 0)}.json"
        if not archive.exists():
            atomic_json(archive, previous)
    atomic_json(contract_file(root), data)
    return data


@locked_state
def task_binding(root: Path, task_id: str, task_goal: str) -> dict[str, Any]:
    contract = ensure_contract(root)
    if contract.get("status") == "ACTIVE":
        return {
            "scope": "project",
            "goal_id": contract.get("goal_id"),
            "revision": contract.get("revision"),
            "fingerprint": contract.get("fingerprint"),
        }
    local = {
        "goal_id": f"TASK-{safe_id(task_id).upper()}",
        "revision": 1,
        "outcome": task_goal,
        "non_goals": [],
        "acceptance_ids": [],
        "behavior_invariants": [],
        "constraints": [],
        "priority_order": [],
    }
    return {
        "scope": "task",
        "goal_id": local["goal_id"],
        "revision": 1,
        "fingerprint": fingerprint(local),
    }


@locked_state
def verify_binding(root: Path, binding: dict[str, Any] | None) -> dict[str, Any]:
    binding = binding or {}
    if binding.get("scope") != "project":
        return {"ok": True, "status": "TASK_LOCAL", "binding": binding}
    current = ensure_contract(root)
    ok = (
        current.get("status") == "ACTIVE"
        and binding.get("goal_id") == current.get("goal_id")
        and int(binding.get("revision") or 0) == int(current.get("revision") or 0)
        and binding.get("fingerprint") == current.get("fingerprint")
    )
    return {
        "ok": ok,
        "status": "CURRENT" if ok else "STALE",
        "binding": binding,
        "current": {
            "goal_id": current.get("goal_id"),
            "revision": current.get("revision"),
            "fingerprint": current.get("fingerprint"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="维护不可漂移的项目目标契约")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    command = sub.add_parser("set")
    command.add_argument("--goal-id", required=True)
    command.add_argument("--outcome", required=True)
    command.add_argument("--non-goal", action="append", default=[])
    command.add_argument("--acceptance-id", action="append", default=[])
    command.add_argument("--behavior-invariant", action="append", default=[])
    command.add_argument("--constraint", action="append", default=[])
    command.add_argument("--priority", action="append", default=[])
    args = parser.parse_args()
    root = repo_root(Path(args.root).resolve())
    if args.command == "set":
        result = set_contract(root, args.goal_id, args.outcome, args.non_goal, args.acceptance_id, args.behavior_invariant, args.constraint, args.priority)
    else:
        result = ensure_contract(root)
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
