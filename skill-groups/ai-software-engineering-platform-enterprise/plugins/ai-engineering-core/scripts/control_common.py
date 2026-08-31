from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path
from typing import Any

from capability_metadata import load_registry
from control_kernel import write_gate
from corelib import ai_root, read_json
from suite_version import plugin_root
from resource_budget import HARD_MAX as RESOURCE_HARD_MAX


SCHEMA_VERSION = "1.0.0"
GOVERNED_STAGES = {"governance", "merge", "release"}
MAX_ADMISSION_OUTPUT_CHARS = RESOURCE_HARD_MAX["output"]["admission_output_chars"]
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
    data = load_registry()
    if not isinstance(data.get("capability_groups"), list) or not isinstance(data.get("specializations"), list):
        raise RuntimeError("capability registry is invalid")
    return data


def capability_indexes(
    registry: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, Any]]]:
    capability_names: dict[str, str] = {}
    domain_names: dict[tuple[str, str], str] = {}
    for capability in registry["capability_groups"]:
        capability_id = str(capability.get("id") or "")
        capability_names[capability_id] = str(capability.get("display_name") or capability_id)
        for domain in capability.get("domains", []):
            domain_id = str(domain.get("id") or "")
            domain_names[(capability_id, domain_id)] = str(domain.get("display_name") or domain_id)
    skills: dict[str, dict[str, str]] = {}
    for skill, metadata in registry["skills"].items():
        capability_id = str(metadata.get("capability") or "")
        domain_id = str(metadata.get("domain") or "")
        if capability_id not in capability_names or (capability_id, domain_id) not in domain_names:
            raise RuntimeError(f"capability registry references unknown ownership: {skill}")
        skills[str(skill)] = {
            "capability": capability_id,
            "capability_name": capability_names[capability_id],
            "domain": domain_id,
            "domain_name": domain_names[(capability_id, domain_id)],
        }
    focuses = {
        str(item.get("id")): {**item, "skills": []}
        for item in registry["specializations"]
        if item.get("id")
    }
    for skill, metadata in registry["skills"].items():
        for focus_id in metadata.get("specializations", []):
            if focus_id not in focuses:
                raise RuntimeError(f"capability registry references unknown specialization: {skill}/{focus_id}")
            focuses[focus_id]["skills"].append(skill)
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
