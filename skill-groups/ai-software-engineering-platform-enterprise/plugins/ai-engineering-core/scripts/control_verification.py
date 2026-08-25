from __future__ import annotations

from pathlib import Path
from typing import Any

from control_common import (
    bounded,
    capability_indexes,
    check_goal,
    check_locks,
    load_capability_registry,
    load_task,
    workspace_module,
)
from control_kernel import operation_status
from corelib import ai_root
from session_epoch import assess as assess_epoch
from state_consistency import assess as assess_state
from suite_router import PLUGIN_FOR
from suite_version import inspect_suite


def verify(
    root: Path,
    task_id: str | None = None,
    files: list[str] | None = None,
    profile: str = "quick",
) -> dict[str, Any]:
    root = root.resolve()
    suite = inspect_suite()
    consistency = assess_state(root)
    registry = load_capability_registry()
    skill_index, _ = capability_indexes(registry)
    registry_ok = set(skill_index) == {"ai-engineering-router", *PLUGIN_FOR}
    task = load_task(root, task_id)
    goal = check_goal(root, task)
    locks = check_locks(root, task_id, bounded(files, 200)) if goal["ok"] else {
        "ok": False,
        "status": "SKIPPED_GOAL_STALE",
    }
    epoch = assess_epoch(root) if (ai_root(root) / "schema.json").is_file() else {
        "risk": "NOT_REQUIRED",
        "rotation_required": False,
    }
    gate: dict[str, Any] = {"ok": True, "profile": profile, "status": "NOT_REQUIRED"}
    if profile in {"task", "merge", "release"}:
        if not task:
            raise RuntimeError(f"verify {profile} requires --task-id")
        if profile == "task":
            governance = workspace_module("governance_state")
            checks = []
            if (task.get("review") or {}).get("status") == "PASS":
                checks.append(governance.verify_quality_lineage(
                    root,
                    task,
                    "review",
                    require_live_candidate=task.get("state") in {"Review", "Testing"},
                ))
            if (task.get("tests") or {}).get("status") == "PASS":
                checks.append(governance.verify_quality_lineage(
                    root,
                    task,
                    "test",
                    require_live_candidate=task.get("state") == "Testing",
                ))
            gate = {
                "ok": all(item.get("ok") for item in checks),
                "profile": profile,
                "status": "CHECKED",
                "checks": checks,
            }
        else:
            closure = workspace_module("closure_gate")
            report = closure.evaluate(root, task, profile)
            gate = {
                "ok": bool(report.get("ok")),
                "profile": profile,
                "status": "PASS" if report.get("ok") else "BLOCKED",
                "failures": report.get("failures") or [],
                "binding": report.get("binding") or {},
            }
    ok = bool(
        suite["consistent"]
        and registry_ok
        and goal["ok"]
        and locks.get("ok")
        and consistency.get("recovery_level") in {"L0", "L1", "L2"}
        and not epoch.get("rotation_required")
        and gate.get("ok")
    )
    return {
        "ok": ok,
        "suite": {
            "consistent": suite["consistent"],
            "version": suite["version"],
            "fingerprint": suite["fingerprint"],
        },
        "state": {
            "status": consistency.get("status"),
            "recovery_level": consistency.get("recovery_level"),
            "execution_policy": (consistency.get("execution_policy") or {}).get("mode"),
        },
        "goal": goal,
        "task": task.get("task_id") if task else None,
        "locks": locks,
        "capability_registry": {"ok": registry_ok, "skill_count": len(skill_index)},
        "control_operations": operation_status(root),
        "session_epoch": {
            "risk": epoch.get("risk"),
            "epoch": epoch.get("epoch"),
            "rotation_required": bool(epoch.get("rotation_required")),
            "checkpoint_recommended": bool(epoch.get("checkpoint_recommended")),
        },
        "profile_gate": gate,
        "runtime_policy": {
            "additional_model_calls": 0,
            "external_model_api": False,
            "background_service": False,
            "network_calls": 0,
        },
    }
