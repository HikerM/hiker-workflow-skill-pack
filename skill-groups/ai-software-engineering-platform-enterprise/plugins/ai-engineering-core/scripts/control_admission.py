from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from control_common import (
    GOVERNED_STAGES,
    MAX_ADMISSION_OUTPUT_CHARS,
    bounded,
    capability_indexes,
    check_goal,
    check_locks,
    file_scope,
    inside,
    load_capability_registry,
    load_task,
)
from control_trace import record_event
from corelib import ai_root, sha256_file
from session_epoch import assess as assess_epoch
from suite_router import PLUGIN_FOR, route


def capability_profile(
    root: Path,
    selected: list[str],
    requested_focuses: list[str],
    focus_evidence: list[str],
    trusted_evidence: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    registry = load_capability_registry()
    skill_index, focus_index = capability_indexes(registry)
    if set(skill_index) != {"ai-engineering-router", *PLUGIN_FOR}:
        raise RuntimeError("capability registry does not cover the published Skill set")
    diagnostics: list[dict[str, str]] = []
    active_focuses: list[dict[str, Any]] = []
    selected_set = set(selected)
    requested = bounded(requested_focuses, 4)
    if len(requested) > 2:
        diagnostics.append({"code": "SPECIALIZATION_LIMIT", "message": "每阶段最多激活两个专项焦点"})
        requested = requested[:2]
    trusted = set()
    for value in bounded(trusted_evidence, 12):
        try:
            trusted.add(str(Path(value).resolve()).casefold())
        except OSError:
            continue
    verified_evidence: list[dict[str, str | None]] = []
    for value in bounded(focus_evidence, 2):
        path, relative = inside(root, value)
        if str(path).casefold() not in trusted:
            diagnostics.append({
                "code": "UNTRUSTED_SPECIALIZATION_EVIDENCE",
                "message": f"专项证据不在有界可信清单中：{relative}",
            })
            continue
        verified_evidence.append({"path": relative, "sha256": sha256_file(path)})
    for focus_id in requested:
        focus = focus_index.get(focus_id)
        if not focus:
            diagnostics.append({"code": "UNKNOWN_SPECIALIZATION", "message": f"未知专项：{focus_id}"})
            continue
        owners = set(str(item) for item in focus.get("skills", []))
        if not owners & selected_set:
            diagnostics.append({
                "code": "SPECIALIZATION_SKILL_CONFLICT",
                "message": f"专项 {focus_id} 不属于当前原子 Skill",
            })
            continue
        if focus.get("evidence_required") and not verified_evidence:
            diagnostics.append({
                "code": "SPECIALIZATION_EVIDENCE_REQUIRED",
                "message": f"专项 {focus_id} 需要当前技术清单或版本证据",
            })
            continue
        active_focuses.append({
            "id": focus_id,
            "name": str(focus.get("display_name") or focus_id),
            "checks": bounded(focus.get("checks"), 6),
            "evidence": verified_evidence if focus.get("evidence_required") else [],
        })
    profile = [
        {
            "skill": skill,
            "capability": skill_index[skill]["capability_name"],
            "domain": skill_index[skill]["domain_name"],
        }
        for skill in selected
    ]
    for item in profile:
        item["focuses"] = [
            focus
            for focus in active_focuses
            if item["skill"] in set(focus_index[focus["id"]].get("skills", []))
        ]
    return profile, diagnostics


def _trim_result(result: dict[str, Any]) -> None:
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= MAX_ADMISSION_OUTPUT_CHARS:
        return
    result["load"] = result["load"][:2]
    scope = result["file_scope"]
    result["file_scope"] = {
        "allowed_files": scope["allowed_files"][:4],
        "allowed_modules": scope["allowed_modules"][:4],
        "protected_modules": scope["protected_modules"][:4],
        "changed_count": scope["changed_count"],
        "truncated": True,
    }
    for item in result.get("capability_profile", []):
        for focus in item.get("focuses", []):
            focus["checks"] = (focus.get("checks") or [])[:3]
            focus["evidence"] = [
                {"path": evidence.get("path"), "sha256": evidence.get("sha256")}
                for evidence in (focus.get("evidence") or [])[:1]
            ]
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_ADMISSION_OUTPUT_CHARS:
        result["diagnostics"] = [{"code": item.get("code")} for item in result.get("diagnostics", [])[:8]]


def admit(
    root: Path,
    proposal: dict[str, Any],
    *,
    task_id: str | None = None,
    changed_paths: list[str] | None = None,
    focuses: list[str] | None = None,
    focus_evidence: list[str] | None = None,
    force_trace: bool = False,
    operation_id: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = root.resolve()
    changed = bounded(changed_paths, 200)
    routed = route(root, proposal)
    selected_ids = [str(item.get("id")) for item in routed.get("selected", [])]
    profile, diagnostics = capability_profile(
        root,
        selected_ids,
        focuses or [],
        focus_evidence or [],
        routed.get("project_evidence") or [],
    ) if routed.get("accepted") else ([], [])
    task = load_task(root, task_id)
    goal = check_goal(root, task)
    coordination = {"ok": True, "status": "NOT_REQUIRED", "blockers": [], "warnings": []}
    stage = str(proposal.get("stage") or "unknown").lower()
    if task_id or stage in GOVERNED_STAGES:
        coordination = workspace_module("goal_coordination").evaluate(
            root, task_id=task_id, changed_paths=changed
        )
    locks = check_locks(root, task_id, changed) if goal["ok"] else {
        "ok": False,
        "status": "SKIPPED_GOAL_STALE",
    }
    all_diagnostics = list(routed.get("diagnostics", [])) + diagnostics
    if not goal["ok"]:
        all_diagnostics.append({"code": "GOAL_BINDING_STALE", "message": "Task绑定的目标修订或指纹已过期"})
    if not coordination.get("ok"):
        for item in coordination.get("blockers", []):
            all_diagnostics.append({"code": item.get("code", "GOAL_COORDINATION_BLOCKED"), "message": "活动目标或项目变动存在冲突，必须等待收敛"})
    if not locks.get("ok"):
        all_diagnostics.append({"code": "FILE_LOCK_GATE", "message": "变更文件存在缺失锁或所有权冲突"})
    epoch = {"status": "NOT_REQUIRED", "rotation_required": False}
    if (ai_root(root) / "schema.json").is_file() and (task_id or stage in GOVERNED_STAGES):
        epoch_report = assess_epoch(root)
        epoch = {
            "status": epoch_report.get("risk"),
            "epoch": epoch_report.get("epoch"),
            "rotation_required": bool(epoch_report.get("rotation_required")),
            "checkpoint_recommended": bool(epoch_report.get("checkpoint_recommended")),
            "reasons": epoch_report.get("reasons") or [],
        }
        recovery_skills = {"bounded-context-memory", "context-recovery", "interruptible-task-control"}
        if epoch["rotation_required"] and not set(selected_ids).issubset(recovery_skills):
            all_diagnostics.append({
                "code": "SESSION_EPOCH_ROTATION_REQUIRED",
                "message": "长会话预算已耗尽；先保存Checkpoint并轮换唯一总控纪元",
            })
    accepted = bool(routed.get("accepted") and not all_diagnostics)
    risk_signals = {str(item).strip().lower() for item in proposal.get("risk_signals", []) if str(item).strip()}
    governed = bool(
        stage in GOVERNED_STAGES
        or (task.get("convergence") or {}).get("required")
        or risk_signals & {"multiple-writers", "cross-repository", "long-running", "multi-session"}
    )
    context = routed.get("context_budget", {})
    budget = context.get("budget", {})
    current = (routed.get("state_consistency") or {}).get("current", {})
    result = {
        "schema_version": "1.0.0",
        "decision": "ACCEPT" if accepted else "REJECT",
        "execution_tier": "GOVERNED" if governed else "PROJECT",
        "project_identity": {
            "repo_id": current.get("repo_id"),
            "head": current.get("head"),
            "branch": current.get("branch"),
            "dirty": current.get("dirty"),
        },
        "plugin_version": (routed.get("plugin_suite") or {}).get("version"),
        "plugin_fingerprint": (routed.get("plugin_suite") or {}).get("fingerprint"),
        "goal": {
            "status": goal.get("status"),
            "id": goal.get("goal_id"),
            "revision": goal.get("revision"),
            "fingerprint": goal.get("fingerprint"),
        },
        "goal_coordination": coordination,
        "task": task.get("task_id") if task else None,
        "phase": stage,
        "allowed_skills": [
            {"id": item.get("id"), "name": item.get("skill"), "plugin": item.get("plugin")}
            for item in routed.get("selected", [])
        ],
        "load": routed.get("load", []),
        "capability_profile": profile,
        "context_budget": {
            "scale": (context.get("scale") or {}).get("mode"),
            "max_active_skills": budget.get("max_active_skills"),
            "max_reference_files": budget.get("max_reference_files"),
            "max_source_files": budget.get("max_source_files"),
            "max_tool_output_chars": budget.get("max_tool_output_chars"),
        },
        "file_scope": file_scope(task, changed),
        "lock_gate": locks,
        "session_epoch_gate": epoch,
        "route_fingerprint": routed.get("route_fingerprint"),
        "cache_hit": bool((routed.get("admission_cache") or {}).get("hit")),
        "next_gate": routed.get("next_gate") or "完成当前阶段后重新语义选择",
        "runtime_policy": {
            "host_runtime": "ChatGPT Desktop / Codex",
            "additional_model_calls": 0,
            "external_model_api": False,
            "background_service": False,
            "network_calls": 0,
        },
        "diagnostics": all_diagnostics,
        "trace": None,
    }
    should_trace = (governed or force_trace) and (ai_root(root) / "schema.json").is_file()
    if should_trace:
        result["trace"] = record_event(
            root,
            event_type="admission",
            summary_code="ADMISSION_ACCEPTED" if accepted else "ADMISSION_BLOCKED",
            task_id=task.get("task_id") if task else task_id,
            phase=stage,
            skills=selected_ids,
            tool="hikerctl.admit",
            result="PASS" if accepted else "BLOCKED",
            gate_result=result["decision"],
            cache_hit=result["cache_hit"],
            duration_ms=(time.perf_counter() - started) * 1000,
            operation_id=operation_id or f"admit-{result.get('route_fingerprint') or 'unknown'}",
            operation_fingerprint=result.get("route_fingerprint"),
        )
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    _trim_result(result)
    return result
