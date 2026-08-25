from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path
from typing import Any

from control_kernel import write_gate
from corelib import ai_root, read_json
from suite_version import plugin_root


SCHEMA_VERSION = "1.0.0"
GOVERNED_STAGES = {"governance", "merge", "release"}
MAX_ADMISSION_OUTPUT_CHARS = 4000
CAPABILITY_REGISTRY = Path(__file__).resolve().parents[1] / "references" / "capability-registry.json"


def safe_id(value: str, limit: int = 100) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    if not result:
        raise ValueError("empty id")
    return result[:limit]


def bounded(values: list[str] | None, limit: int) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in (values or []) if str(item).strip()))[:limit]


def inside(root: Path, value: str) -> tuple[Path, str]:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside project: {value}") from exc
    return resolved, relative


def load_capability_registry() -> dict[str, Any]:
    data = read_json(CAPABILITY_REGISTRY, {}) or {}
    if not isinstance(data.get("capabilities"), list) or not isinstance(data.get("specializations"), list):
        raise RuntimeError("capability registry is invalid")
    return data


def capability_indexes(
    registry: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, Any]]]:
    skills: dict[str, dict[str, str]] = {}
    for capability in registry["capabilities"]:
        for domain in capability.get("domains", []):
            for skill in domain.get("skills", []):
                if skill in skills:
                    raise RuntimeError(f"capability registry duplicates skill: {skill}")
                skills[str(skill)] = {
                    "capability": str(capability.get("id") or ""),
                    "capability_name": str(capability.get("display_name") or ""),
                    "domain": str(domain.get("id") or ""),
                    "domain_name": str(domain.get("display_name") or ""),
                }
    focuses = {str(item.get("id")): item for item in registry["specializations"] if item.get("id")}
    return skills, focuses


def load_task(root: Path, task_id: str | None) -> dict[str, Any]:
    if not task_id:
        return {}
    path = ai_root(root) / "tasks" / f"{safe_id(task_id).upper()}.json"
    data = read_json(path, {}) or {}
    if not data:
        raise RuntimeError(f"unknown governed task: {task_id}")
    return data


def check_goal(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    current = read_json(ai_root(root) / "governance" / "goal-contract.json", {}) or {}
    change_path = ai_root(root) / "governance" / "goal-change-active.json"
    change = read_json(change_path, {}) or {}
    if change_path.exists() and not change:
        return {
            "ok": False,
            "status": "GOAL_CHANGE_STATE_DAMAGED",
            "goal_id": current.get("goal_id"),
            "revision": current.get("revision"),
            "fingerprint": current.get("fingerprint"),
        }
    if change.get("status") in {"PREPARED", "APPLYING", "PROJECTED"}:
        return {
            "ok": False,
            "status": "GOAL_CHANGE_IN_PROGRESS",
            "goal_id": current.get("goal_id"),
            "revision": current.get("revision"),
            "fingerprint": current.get("fingerprint"),
            "operation_id": change.get("operation_id"),
            "target_revision": change.get("new_goal_revision"),
        }
    if not task:
        return {
            "ok": True,
            "status": "ACTIVE" if current.get("status") == "ACTIVE" else "UNBOUND",
            "goal_id": current.get("goal_id"),
            "revision": current.get("revision"),
            "fingerprint": current.get("fingerprint"),
        }
    binding = task.get("goal_binding") or {}
    if binding.get("scope") != "project":
        return {"ok": True, "status": "TASK_LOCAL", **binding}
    ok = bool(
        current.get("status") == "ACTIVE"
        and binding.get("goal_id") == current.get("goal_id")
        and int(binding.get("revision") or 0) == int(current.get("revision") or 0)
        and binding.get("fingerprint") == current.get("fingerprint")
    )
    return {
        "ok": ok,
        "status": "CURRENT" if ok else "STALE",
        "goal_id": current.get("goal_id"),
        "revision": current.get("revision"),
        "fingerprint": current.get("fingerprint"),
    }


def workspace_module(name: str):
    scripts = plugin_root("ai-engineering-workspace") / "scripts"
    if not scripts.is_dir():
        raise RuntimeError("workspace plugin is unavailable")
    text = str(scripts)
    if text not in sys.path:
        sys.path.insert(0, text)
    return importlib.import_module(name)


def check_locks(root: Path, task_id: str | None, changed_paths: list[str]) -> dict[str, Any]:
    if not task_id or not changed_paths:
        return {"ok": True, "status": "NOT_REQUIRED"}
    module = workspace_module("file_lock")
    return {"status": "CHECKED", **module.check(root, argparse.Namespace(task_id=task_id, files=changed_paths))}


def file_scope(task: dict[str, Any], changed_paths: list[str]) -> dict[str, Any]:
    contract = task.get("change_contract") or {}
    return {
        "allowed_files": bounded(contract.get("allowed_files") or changed_paths, 12),
        "allowed_modules": bounded(contract.get("allowed_modules"), 8),
        "protected_modules": bounded(contract.get("protected_modules"), 8),
        "changed_count": len(changed_paths),
    }


def write_context(
    root: Path,
    task_id: str,
    *,
    allow_version_recovery: bool = False,
    allow_epoch_overrun: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not (ai_root(root) / "schema.json").is_file():
        raise RuntimeError("governed state is not initialized")
    task = load_task(root, task_id)
    goal = check_goal(root, task)
    if not goal.get("ok"):
        raise RuntimeError("task goal binding is stale")
    gate = write_gate(
        root,
        allow_version_recovery=allow_version_recovery,
        allow_epoch_overrun=allow_epoch_overrun,
    )
    return task, goal, gate
