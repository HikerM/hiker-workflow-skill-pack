from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, repo_root, safe_id, state_lock, worktree_fingerprint
from implementation_guard import validate_registry


SCHEMA_VERSION = "1.0.0"
LEVELS = {"static": 1, "integration": 2, "runtime": 3, "user-visible": 4, "production": 5}
OBSERVATIONS = {
    "scope-expanded",
    "user-correction",
    "evidence-contradiction",
    "strategy-invalidated",
    "implementation-sprawl",
    "rollback",
}
MAX_EVENTS = 40
MAX_EXPERIMENTS = 20
MAX_EVIDENCE_PER_CRITERION = 12
MAX_VERIFICATION_RECORDS = 30
MAX_GOVERNANCE_ONLY_CYCLES = 2
MAX_FULL_REPLAYS_PER_FINGERPRINT = 2
MAX_REJECTED_HYPOTHESES_PER_ISSUE = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_path(root: Path, task_id: str) -> Path:
    return root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json"


def read_task(root: Path, task_id: str) -> dict[str, Any]:
    path = task_path(root, task_id)
    if not path.is_file():
        raise RuntimeError(f"task not found: {safe_id(task_id).upper()}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_task(root: Path, task: dict[str, Any]) -> None:
    task["updated_at"] = now()
    atomic_json(task_path(root, str(task["task_id"])), task)


def _bounded(values: list[Any], limit: int) -> list[Any]:
    return values[-limit:]


def _criterion(raw: str, index: int) -> dict[str, Any]:
    parts = [part.strip() for part in raw.split("|", 2)]
    if len(parts) == 1:
        criterion_id, description, level = f"AC-{index:03d}", parts[0], "runtime"
    elif len(parts) == 2:
        criterion_id, description, level = parts[0], parts[1], "runtime"
    else:
        criterion_id, description, level = parts
    criterion_id = safe_id(criterion_id).upper()
    if not criterion_id or not description:
        raise RuntimeError("criterion requires a stable id and description")
    if level not in LEVELS:
        raise RuntimeError(f"unsupported evidence level: {level}")
    return {
        "id": criterion_id,
        "description": description,
        "required_level": level,
        "status": "PENDING",
        "evidence": [],
    }


def initialize(task: dict[str, Any], criteria: list[str], strategy: str) -> dict[str, Any]:
    if task.get("convergence", {}).get("required"):
        return task["convergence"]
    if not criteria:
        contract = task.get("change_contract") or {}
        source = list(contract.get("behavior_invariants") or []) + list(contract.get("required_tests") or [])
        criteria = [f"AC-{index:03d}|{value}|runtime" for index, value in enumerate(dict.fromkeys(source), 1)]
    if not criteria:
        raise RuntimeError("long-chain convergence requires at least one acceptance criterion")
    task["convergence"] = {
        "schema_version": SCHEMA_VERSION,
        "required": True,
        "status": "STABLE",
        "acceptance_revision": 1,
        "strategy_revision": 1,
        "active_strategy": {
            "id": "STRATEGY-001",
            "summary": strategy or "按当前批准变更契约实施",
            "status": "ACTIVE",
            "created_at": now(),
        },
        "criteria": [_criterion(value, index) for index, value in enumerate(criteria, 1)],
        "signals": {
            "scope_expansions": 0,
            "user_corrections": 0,
            "strategy_invalidations": 0,
            "implementation_sprawl": 0,
            "rollbacks": 0,
        },
        "open_contradictions": [],
        "implementation_routes": [],
        "experiments": [],
        "hypotheses": [],
        "events": [],
        "deployment": {
            "source_head": "",
            "remote_head": "",
            "deployed_head": "",
            "post_deploy_evidence": "PENDING",
        },
        "notification": {"last_acknowledged_fingerprint": ""},
        "delivery_progress": {
            "business_events": 0,
            "governance_events": 0,
            "consecutive_governance_only_cycles": 0,
            "business_source_started": False,
            "last_summary": "",
            "next_business_gate": "",
        },
        "verification_budget": {
            "max_full_replays_per_fingerprint": MAX_FULL_REPLAYS_PER_FINGERPRINT,
            "records": [],
            "reused_passes": 0,
        },
        "created_at": now(),
        "updated_at": now(),
    }
    return task["convergence"]


def _find_criterion(state: dict[str, Any], criterion_id: str) -> dict[str, Any]:
    wanted = safe_id(criterion_id).upper()
    for criterion in state.get("criteria", []):
        if criterion.get("id") == wanted:
            return criterion
    raise RuntimeError(f"acceptance criterion not found: {wanted}")


def _active_route_conflicts(state: dict[str, Any]) -> list[str]:
    responsibilities: dict[str, list[str]] = {}
    for route in state.get("implementation_routes", []):
        if route.get("status") != "ACTIVE":
            continue
        responsibilities.setdefault(str(route.get("responsibility")), []).append(str(route.get("route_id")))
    return [f"{key}: {', '.join(values)}" for key, values in responsibilities.items() if len(values) > 1]


def _migration_routes(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in state.get("implementation_routes", []) if item.get("status") == "MIGRATION"]


def _unproven_retirements(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in state.get("implementation_routes", [])
        if item.get("status") == "RETIRED" and not item.get("removal_evidence")
    ]


def _unresolved_experiments(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in state.get("experiments", []) if item.get("status") == "AUTHORIZED"]


def _failed_experiments_for(state: dict[str, Any], criterion_id: str) -> int:
    count = 0
    for item in reversed(state.get("experiments", [])):
        if item.get("criterion_id") != criterion_id:
            continue
        if item.get("status") == "FAIL":
            count += 1
        elif item.get("status") == "PASS":
            break
    return count


def _deployment_drift(state: dict[str, Any]) -> bool:
    deployment = state.get("deployment") or {}
    values = [deployment.get("source_head"), deployment.get("remote_head"), deployment.get("deployed_head")]
    present = [str(value) for value in values if value]
    return len(present) >= 2 and len(set(present)) > 1


def assess(state: dict[str, Any], phase: str = "status") -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []
    route_conflicts = _active_route_conflicts(state)
    if route_conflicts:
        blockers.append("同一职责存在多个活动实现路径：" + "；".join(route_conflicts))
        actions.append("明确唯一现行路径；迁移兼容路径必须登记退出条件和删除节点")
    migration_routes = _migration_routes(state)
    if phase in {"merge", "release"} and migration_routes:
        blockers.append("仍有未收敛的迁移实现路径：" + "、".join(str(item.get("route_id")) for item in migration_routes))
        actions.append("完成切换、回归与旧路径退役后才能合并")
    unproven_retirements = _unproven_retirements(state)
    if phase in {"merge", "release"} and unproven_retirements:
        blockers.append("旧路径缺少删除或不可达证据：" + "、".join(str(item.get("route_id")) for item in unproven_retirements))
        actions.append("提供删除提交、调用图不可达结果或等价的可核验证据")
    contradictions = state.get("open_contradictions") or []
    if contradictions:
        blockers.append(f"仍有 {len(contradictions)} 个证据矛盾未关闭")
        actions.append("先用可复现证据解决矛盾，不得继续叠加补丁或宣布通过")
    if state.get("status") == "PIVOT_REQUIRED":
        blockers.append("当前方案已被证据推翻或同一验收点连续失败，必须重新定方案")
        actions.append("冻结现有方案，记录被推翻依据并建立新的策略修订")
    if state.get("status") == "DIAGNOSIS_REQUIRED":
        blockers.append("同一问题的连续根因假设已被证据否定，禁止继续猜测式改码")
        actions.append("回到首个可观测失真边界，补齐调用链、状态转换或运行时证据后再建立新假设")
    if _unresolved_experiments(state):
        blockers.append("存在尚未记录结果的真实实验")
        actions.append("先完成或明确取消当前实验，禁止重复执行")
    signals = state.get("signals") or {}
    progress = state.get("delivery_progress") or {}
    governance_cycles = int(progress.get("consecutive_governance_only_cycles", 0))
    if governance_cycles >= MAX_GOVERNANCE_ONLY_CYCLES:
        warnings.append(f"已连续 {governance_cycles} 个治理周期没有业务价值增量")
        actions.append("停止追加控制投影或全量矩阵；复用未失效证据，只修首个真实阻断并明确下一业务门禁")
    if state.get("status") == "BUSINESS_REQUIRED":
        warnings.append("治理预算已用尽；下一次有效进展必须包含可验证的业务源码变化")
        actions.append(str(progress.get("next_business_gate") or "执行当前变更契约内的最小业务切片"))
    if int(signals.get("scope_expansions", 0)):
        warnings.append(f"任务范围已扩大 {signals.get('scope_expansions')} 次")
    if int(signals.get("user_corrections", 0)):
        warnings.append(f"用户已纠正目标或验收理解 {signals.get('user_corrections')} 次")
    if int(signals.get("rollbacks", 0)):
        warnings.append(f"已发生回滚 {signals.get('rollbacks')} 次")
    if int(signals.get("implementation_sprawl", 0)):
        warnings.append(f"检测到实现路径或代码职责膨胀 {signals.get('implementation_sprawl')} 次")
    if state.get("status") == "WARNING" and not warnings:
        warnings.append("工程基线或执行策略已调整，旧结论需要按当前修订重新确认")
    drift = _deployment_drift(state)
    if drift:
        warnings.append("源码、远程主线与实际部署版本不一致")
        if phase in {"production-experiment", "release"}:
            blockers.append("生产版本漂移未收敛")
            actions.append("先确认唯一目标版本与回滚策略，再进行生产执行或发布")
    pending = [criterion for criterion in state.get("criteria", []) if criterion.get("status") != "PASS"]
    if phase in {"merge", "release"} and pending:
        blockers.append("仍有未通过的验收条件：" + "、".join(str(item.get("id")) for item in pending))
        actions.append("按验收条件补齐对应层级的当前版本证据")
    if phase == "release":
        deployment = state.get("deployment") or {}
        if deployment.get("post_deploy_evidence") != "PASS":
            blockers.append("缺少当前部署版本的上线后验证证据")
    severity = "BLOCKED" if blockers else "WARNING" if warnings else "STABLE"
    if state.get("status") in {"PIVOT_REQUIRED", "DIAGNOSIS_REQUIRED"}:
        severity = state["status"]
    latest_observations = []
    visible_kinds = OBSERVATIONS | {"acceptance-baseline-invalidated", "strategy-set", "strategy-retired"}
    for event in reversed(state.get("events", [])):
        if event.get("kind") not in visible_kinds:
            continue
        latest_observations.append({
            "kind": str(event.get("kind") or ""),
            "summary": str(event.get("summary") or "")[:240],
            "impact": str(event.get("impact") or event.get("reason") or "")[:240],
            "action": str(event.get("action") or "")[:240],
        })
        if len(latest_observations) >= 3:
            break
    return {
        "ok": not blockers,
        "severity": severity,
        "blockers": blockers,
        "warnings": warnings,
        "actions": list(dict.fromkeys(actions)),
        "next_gate": _next_gate(state, phase, blockers, pending),
        "latest_observations": latest_observations,
        "delivery_progress": {
            "business_source_started": bool(progress.get("business_source_started")),
            "business_events": int(progress.get("business_events", 0)),
            "governance_events": int(progress.get("governance_events", 0)),
            "consecutive_governance_only_cycles": governance_cycles,
            "last_summary": str(progress.get("last_summary") or "")[:240],
            "next_business_gate": str(progress.get("next_business_gate") or "")[:240],
        },
    }


def record_progress(
    state: dict[str, Any], lane: str, summary: str, next_business_gate: str,
    source_fingerprint: str = "", override_reason: str = ""
) -> dict[str, Any]:
    if lane not in {"governance", "business"}:
        raise RuntimeError("progress lane must be governance or business")
    if not summary or not next_business_gate:
        raise RuntimeError("progress requires summary and an exact next business gate")
    progress = state.setdefault("delivery_progress", {})
    if lane == "business":
        previous_fingerprint = str(progress.get("last_business_fingerprint") or progress.get("baseline_source_fingerprint") or "")
        if not source_fingerprint or source_fingerprint == previous_fingerprint:
            raise RuntimeError("business progress requires a new verifiable source fingerprint; state transition or prose is not business progress")
        progress["business_events"] = int(progress.get("business_events", 0)) + 1
        progress["business_source_started"] = True
        progress["consecutive_governance_only_cycles"] = 0
        progress["last_business_fingerprint"] = source_fingerprint
        if state.get("status") == "BUSINESS_REQUIRED":
            state["status"] = "STABLE"
    else:
        next_count = int(progress.get("consecutive_governance_only_cycles", 0)) + 1
        if next_count > MAX_GOVERNANCE_ONLY_CYCLES:
            raise RuntimeError(
                "governance-only cycle budget exceeded; an override cannot create more governance cycles—execute the recorded business gate or change strategy"
            )
        progress["governance_events"] = int(progress.get("governance_events", 0)) + 1
        progress["consecutive_governance_only_cycles"] = next_count
        if next_count == MAX_GOVERNANCE_ONLY_CYCLES:
            state["status"] = "BUSINESS_REQUIRED"
    progress["last_lane"] = lane
    progress["last_summary"] = summary
    progress["next_business_gate"] = next_business_gate
    progress["override_reason"] = override_reason
    progress["updated_at"] = now()
    return progress


def verification_plan(state: dict[str, Any], gate_id: str, fingerprint: str, scope: str) -> dict[str, Any]:
    gate = safe_id(gate_id).upper()
    records = (state.get("verification_budget") or {}).get("records") or []
    matching = [
        item for item in records
        if item.get("gate_id") == gate and item.get("fingerprint") == fingerprint and item.get("scope") == scope
    ]
    if any(item.get("status") == "PASS" for item in matching):
        return {"decision": "REUSE_PASS", "reason": "相同门禁、指纹和范围已有未失效 PASS 证据"}
    full_runs = sum(item.get("mode") == "full" for item in matching)
    limit = int((state.get("verification_budget") or {}).get("max_full_replays_per_fingerprint", MAX_FULL_REPLAYS_PER_FINGERPRINT))
    if full_runs >= limit:
        return {"decision": "TARGETED_OR_REPLAN", "reason": "相同指纹的全量重放已达到预算，必须缩小到受影响切片或重新定方案"}
    return {"decision": "FULL_ALLOWED" if not matching else "TARGETED_REQUIRED", "reason": "只验证自上次有效证据后发生变化的表面"}


def record_verification(
    state: dict[str, Any], gate_id: str, fingerprint: str, scope: str, mode: str, status: str, evidence: str
) -> dict[str, Any]:
    if mode not in {"targeted", "full"} or status not in {"PASS", "FAIL", "INVALID"}:
        raise RuntimeError("verification mode/status is invalid")
    plan = verification_plan(state, gate_id, fingerprint, scope)
    budget = state.setdefault("verification_budget", {"records": [], "reused_passes": 0})
    if plan["decision"] == "REUSE_PASS" and status == "PASS":
        budget["reused_passes"] = int(budget.get("reused_passes", 0)) + 1
        return {"reused": True, **plan}
    if mode == "full" and plan["decision"] in {"TARGETED_REQUIRED", "TARGETED_OR_REPLAN"}:
        raise RuntimeError(plan["reason"])
    item = {
        "at": now(), "gate_id": safe_id(gate_id).upper(), "fingerprint": fingerprint,
        "scope": scope, "mode": mode, "status": status, "evidence": evidence,
    }
    budget.setdefault("records", []).append(item)
    budget["records"] = _bounded(budget["records"], MAX_VERIFICATION_RECORDS)
    return {"reused": False, "record": item}


def _next_gate(
    state: dict[str, Any], phase: str, blockers: list[str], pending: list[dict[str, Any]]
) -> list[str]:
    if state.get("status") == "PIVOT_REQUIRED":
        return ["建立新的策略修订并说明旧方案为什么失效"]
    if state.get("open_contradictions"):
        return ["关闭全部证据矛盾并保存可复现依据"]
    if _unresolved_experiments(state):
        return ["记录当前实验的 PASS、FAIL 或 CANCELLED 结果"]
    if pending and phase in {"merge", "release"}:
        return ["所有验收条件达到各自要求的证据层级"]
    if blockers:
        return ["解除当前阻断项后重新评估"]
    if phase == "status":
        return ["按当前策略推进一个最小可证伪步骤"]
    return [f"{phase} 门禁已满足"]


def _fingerprint(report: dict[str, Any]) -> str:
    payload = json.dumps(
        {key: report.get(key) for key in ("severity", "blockers", "warnings", "actions", "next_gate", "latest_observations")},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def health_report(state: dict[str, Any], phase: str = "status") -> dict[str, Any]:
    report = assess(state, phase)
    fingerprint = _fingerprint(report)
    previous = (state.get("notification") or {}).get("last_acknowledged_fingerprint", "")
    report["fingerprint"] = fingerprint
    report["should_notify"] = report["severity"] != "STABLE" and fingerprint != previous
    observations = report.get("latest_observations") or []
    observed_problems = [item["summary"] for item in observations if item.get("summary")]
    observed_impacts = [item["impact"] for item in observations if item.get("impact")]
    observed_actions = [item["action"] for item in observations if item.get("action")]
    report["notice"] = {
        "title": "工程状态告警",
        "problem": list(dict.fromkeys(report["blockers"] + report["warnings"] + observed_problems)),
        "impact": list(dict.fromkeys(observed_impacts)) or ["旧的通过结论只在原证据指纹和原验收范围内有效"],
        "action": list(dict.fromkeys(report["actions"] + observed_actions)) or ["保持当前有界范围继续执行"],
        "next_gate": report["next_gate"],
    }
    return report


def observe(
    state: dict[str, Any], kind: str, summary: str, impact: str = "", action: str = "", criterion_id: str = ""
) -> None:
    if kind not in OBSERVATIONS:
        raise RuntimeError(f"unsupported observation kind: {kind}")
    if not summary:
        raise RuntimeError("observation summary is required")
    signals = state.setdefault("signals", {})
    mapping = {
        "scope-expanded": "scope_expansions",
        "user-correction": "user_corrections",
        "strategy-invalidated": "strategy_invalidations",
        "implementation-sprawl": "implementation_sprawl",
        "rollback": "rollbacks",
    }
    if kind in mapping:
        signals[mapping[kind]] = int(signals.get(mapping[kind], 0)) + 1
    event = {
        "at": now(),
        "kind": kind,
        "summary": summary,
        "impact": impact,
        "action": action,
        "criterion_id": safe_id(criterion_id).upper() if criterion_id else "",
        "acceptance_revision": state.get("acceptance_revision"),
        "strategy_revision": state.get("strategy_revision"),
    }
    state.setdefault("events", []).append(event)
    state["events"] = _bounded(state["events"], MAX_EVENTS)
    if kind in {"evidence-contradiction", "strategy-invalidated", "implementation-sprawl"}:
        contradiction_id = f"CON-{len(state.get('open_contradictions', [])) + 1:03d}"
        state.setdefault("open_contradictions", []).append({"id": contradiction_id, **event})
    if kind in {"scope-expanded", "user-correction", "rollback"}:
        state["acceptance_revision"] = int(state.get("acceptance_revision", 1)) + 1
        for criterion in state.get("criteria", []):
            if not criterion_id or criterion.get("id") == safe_id(criterion_id).upper():
                criterion["status"] = "PENDING"
    if kind in {"strategy-invalidated"}:
        state["status"] = "PIVOT_REQUIRED"
        for criterion in state.get("criteria", []):
            if not criterion_id or criterion.get("id") == safe_id(criterion_id).upper():
                criterion["status"] = "INVALIDATED"
    elif state.get("status") == "STABLE":
        state["status"] = "WARNING"
    state["updated_at"] = now()


def resolve_contradiction(state: dict[str, Any], contradiction_id: str, evidence: str) -> None:
    wanted = safe_id(contradiction_id).upper()
    remaining = []
    found = False
    for item in state.get("open_contradictions", []):
        if item.get("id") == wanted:
            found = True
            item["resolved_at"] = now()
            item["resolution_evidence"] = evidence
            state.setdefault("events", []).append({"at": now(), "kind": "contradiction-resolved", "summary": wanted, "evidence": evidence})
        else:
            remaining.append(item)
    if not found:
        raise RuntimeError(f"contradiction not found: {wanted}")
    state["open_contradictions"] = remaining
    if not remaining and state.get("status") == "BLOCKED":
        state["status"] = "WARNING"


def set_strategy(state: dict[str, Any], summary: str, reason: str) -> None:
    if not summary or not reason:
        raise RuntimeError("new strategy requires a summary and invalidation/replan reason")
    previous = state.get("active_strategy") or {}
    if previous:
        previous["status"] = "RETIRED"
        previous["retired_at"] = now()
        previous["retired_reason"] = reason
        state.setdefault("events", []).append({"at": now(), "kind": "strategy-retired", "summary": previous.get("summary"), "reason": reason})
    revision = int(state.get("strategy_revision", 0)) + 1
    state["strategy_revision"] = revision
    state["active_strategy"] = {
        "id": f"STRATEGY-{revision:03d}",
        "summary": summary,
        "status": "ACTIVE",
        "created_at": now(),
        "reason": reason,
    }
    state["open_contradictions"] = []
    for item in state.get("hypotheses", []):
        if item.get("status") == "ACTIVE":
            item["status"] = "RETIRED"
            item["retired_at"] = now()
    state["status"] = "WARNING"
    state.setdefault("events", []).append({"at": now(), "kind": "strategy-set", "summary": summary, "reason": reason})


def register_hypothesis(
    state: dict[str, Any], issue_id: str, statement: str, allowed_actions: str, forbidden_actions: str
) -> dict[str, Any]:
    issue = safe_id(issue_id).upper()
    if not issue or not statement or not allowed_actions or not forbidden_actions:
        raise RuntimeError("hypothesis requires issue id, statement, allowed actions and forbidden actions")
    if state.get("status") == "DIAGNOSIS_REQUIRED":
        raise RuntimeError("diagnosis evidence is required before another hypothesis can be registered")
    if any(item.get("issue_id") == issue and item.get("status") == "ACTIVE" for item in state.get("hypotheses", [])):
        raise RuntimeError(f"issue already has an active hypothesis: {issue}")
    item = {
        "id": f"HYP-{len(state.get('hypotheses', [])) + 1:03d}",
        "issue_id": issue,
        "statement": statement,
        "allowed_actions": allowed_actions,
        "forbidden_actions": forbidden_actions,
        "status": "ACTIVE",
        "created_at": now(),
    }
    state.setdefault("hypotheses", []).append(item)
    state["hypotheses"] = _bounded(state["hypotheses"], 20)
    return item


def resolve_hypothesis(state: dict[str, Any], hypothesis_id: str, result: str, evidence: str) -> dict[str, Any]:
    if result not in {"CONFIRMED", "REJECTED"} or not evidence:
        raise RuntimeError("hypothesis result requires CONFIRMED/REJECTED and evidence")
    item = next((value for value in state.get("hypotheses", []) if value.get("id") == hypothesis_id), None)
    if not item or item.get("status") != "ACTIVE":
        raise RuntimeError("active hypothesis not found")
    item["status"] = result
    item["evidence"] = evidence
    item["resolved_at"] = now()
    if result == "REJECTED":
        rejected = sum(
            value.get("issue_id") == item.get("issue_id") and value.get("status") == "REJECTED"
            for value in state.get("hypotheses", [])
        )
        if rejected >= MAX_REJECTED_HYPOTHESES_PER_ISSUE:
            state["status"] = "DIAGNOSIS_REQUIRED"
            state.setdefault("events", []).append({
                "at": now(), "kind": "strategy-invalidated",
                "summary": f"{item['issue_id']} 连续 {rejected} 个根因假设被否定",
                "action": "停止改码并回到首个可观测失真边界补证据",
            })
    return item


def register_route(
    state: dict[str, Any], responsibility: str, route_id: str, status: str, exit_condition: str = "",
    removal_evidence: str = "",
) -> None:
    if status not in {"ACTIVE", "RETIRED", "MIGRATION"}:
        raise RuntimeError("route status must be ACTIVE, MIGRATION or RETIRED")
    if status == "MIGRATION" and not exit_condition:
        raise RuntimeError("migration route requires an exit condition")
    if status == "RETIRED" and not removal_evidence:
        raise RuntimeError("retired route requires removal or unreachable evidence")
    routes = state.setdefault("implementation_routes", [])
    existing = next((item for item in routes if item.get("route_id") == route_id), None)
    payload = {
        "responsibility": responsibility,
        "route_id": route_id,
        "status": status,
        "exit_condition": exit_condition,
        "removal_evidence": removal_evidence,
        "updated_at": now(),
    }
    if existing:
        existing.update(payload)
    else:
        routes.append(payload)
    if _active_route_conflicts(state):
        state["status"] = "BLOCKED"
    elif state.get("status") == "BLOCKED" and not state.get("open_contradictions"):
        state["status"] = "WARNING"


def authorize_experiment(
    state: dict[str, Any], criterion_id: str, hypothesis: str, expected: str, stop_condition: str, environment: str
) -> dict[str, Any]:
    criterion = _find_criterion(state, criterion_id)
    report = assess(state, "production-experiment" if environment == "production" else "experiment")
    if not report["ok"]:
        raise RuntimeError("experiment blocked: " + "; ".join(report["blockers"]))
    if not hypothesis or not expected or not stop_condition:
        raise RuntimeError("experiment requires hypothesis, expected observation and stop condition")
    sequence = len(state.get("experiments", [])) + 1
    experiment = {
        "id": f"EXP-{sequence:03d}",
        "criterion_id": criterion["id"],
        "hypothesis": hypothesis,
        "expected": expected,
        "stop_condition": stop_condition,
        "environment": environment,
        "status": "AUTHORIZED",
        "strategy_revision": state.get("strategy_revision"),
        "acceptance_revision": state.get("acceptance_revision"),
        "authorized_at": now(),
    }
    state.setdefault("experiments", []).append(experiment)
    state["experiments"] = _bounded(state["experiments"], MAX_EXPERIMENTS)
    return experiment


def finish_experiment(state: dict[str, Any], experiment_id: str, result: str, evidence: str) -> None:
    if result not in {"PASS", "FAIL", "CANCELLED"}:
        raise RuntimeError("experiment result must be PASS, FAIL or CANCELLED")
    experiment = next((item for item in state.get("experiments", []) if item.get("id") == experiment_id), None)
    if not experiment or experiment.get("status") != "AUTHORIZED":
        raise RuntimeError("authorized experiment not found")
    experiment["status"] = result
    experiment["evidence"] = evidence
    experiment["finished_at"] = now()
    criterion_id = str(experiment.get("criterion_id"))
    if result == "FAIL":
        criterion = _find_criterion(state, criterion_id)
        criterion["status"] = "FAIL"
        failures = _failed_experiments_for(state, criterion_id)
        if failures >= 2:
            state["status"] = "PIVOT_REQUIRED"
            state.setdefault("events", []).append({
                "at": now(),
                "kind": "strategy-invalidated",
                "summary": f"{criterion_id} 连续 {failures} 次真实实验失败",
                "criterion_id": criterion_id,
            })
    elif result == "PASS" and state.get("status") == "WARNING":
        state["status"] = "STABLE"


def record_evidence(
    state: dict[str, Any], criterion_id: str, level: str, status: str, value: str, fingerprint: str
) -> None:
    if level not in LEVELS:
        raise RuntimeError(f"unsupported evidence level: {level}")
    if status not in {"PASS", "FAIL"}:
        raise RuntimeError("evidence status must be PASS or FAIL")
    criterion = _find_criterion(state, criterion_id)
    item = {
        "at": now(),
        "level": level,
        "status": status,
        "value": value,
        "fingerprint": fingerprint,
        "acceptance_revision": state.get("acceptance_revision"),
        "strategy_revision": state.get("strategy_revision"),
    }
    criterion.setdefault("evidence", []).append(item)
    criterion["evidence"] = _bounded(criterion["evidence"], MAX_EVIDENCE_PER_CRITERION)
    if status == "FAIL":
        criterion["status"] = "FAIL"
        observe(state, "evidence-contradiction", f"{criterion['id']} 的当前证据失败", value, "重新定位首个失真边界", criterion["id"])
    elif LEVELS[level] >= LEVELS[criterion["required_level"]]:
        criterion["status"] = "PASS"
    else:
        criterion["status"] = "PARTIAL"


def set_deployment(
    state: dict[str, Any], source_head: str, remote_head: str, deployed_head: str, post_deploy_evidence: str
) -> None:
    if post_deploy_evidence not in {"PENDING", "PASS", "FAIL"}:
        raise RuntimeError("post-deploy evidence must be PENDING, PASS or FAIL")
    state["deployment"] = {
        "source_head": source_head,
        "remote_head": remote_head,
        "deployed_head": deployed_head,
        "post_deploy_evidence": post_deploy_evidence,
        "updated_at": now(),
    }
    if _deployment_drift(state):
        state["status"] = "WARNING"


def acknowledge(state: dict[str, Any], fingerprint: str) -> None:
    state.setdefault("notification", {})["last_acknowledged_fingerprint"] = fingerprint
    state["notification"]["acknowledged_at"] = now()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--task-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("init")
    command.add_argument("--criterion", action="append", default=[])
    command.add_argument("--strategy", default="")
    command = sub.add_parser("observe")
    command.add_argument("--kind", choices=sorted(OBSERVATIONS), required=True)
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
    command.add_argument("--level", choices=sorted(LEVELS), required=True)
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
    args = parser.parse_args()
    root = repo_root(Path(args.root).resolve())
    operation_result: dict[str, Any] | None = None
    try:
        with state_lock(root):
            task = read_task(root, args.task_id)
            state = task.get("convergence")
            if args.command == "init":
                state = initialize(task, args.criterion, args.strategy)
                progress = state.setdefault("delivery_progress", {})
                progress.setdefault("baseline_source_fingerprint", worktree_fingerprint(root))
                progress.setdefault("last_business_fingerprint", progress["baseline_source_fingerprint"])
            elif not state or not state.get("required"):
                raise RuntimeError("convergence guard is not initialized for this task")
            elif args.command == "observe":
                observe(state, args.kind, args.summary, args.impact, args.action, args.criterion_id)
            elif args.command == "resolve":
                resolve_contradiction(state, args.contradiction_id, args.evidence)
            elif args.command == "strategy-set":
                set_strategy(state, args.summary, args.reason)
            elif args.command == "hypothesis-add":
                operation_result = register_hypothesis(
                    state, args.issue_id, args.statement, args.allowed_actions, args.forbidden_actions
                )
            elif args.command == "hypothesis-result":
                operation_result = resolve_hypothesis(state, args.hypothesis_id, args.result, args.evidence)
            elif args.command == "route-set":
                register_route(
                    state,
                    args.responsibility,
                    args.route_id,
                    args.status,
                    args.exit_condition,
                    args.removal_evidence,
                )
            elif args.command == "experiment-authorize":
                authorize_experiment(state, args.criterion_id, args.hypothesis, args.expected, args.stop_condition, args.environment)
            elif args.command == "experiment-result":
                finish_experiment(state, args.experiment_id, args.result, args.evidence)
            elif args.command == "evidence-record":
                record_evidence(state, args.criterion_id, args.level, args.status, args.value, args.fingerprint)
            elif args.command == "progress-record":
                operation_result = record_progress(
                    state, args.lane, args.summary, args.next_business_gate,
                    worktree_fingerprint(root), args.override_reason,
                )
            elif args.command == "verification-plan":
                operation_result = verification_plan(state, args.gate_id, args.fingerprint, args.scope)
            elif args.command == "verification-record":
                operation_result = record_verification(
                    state, args.gate_id, args.fingerprint, args.scope, args.mode, args.status, args.evidence
                )
            elif args.command == "deployment-set":
                set_deployment(state, args.source_head, args.remote_head, args.deployed_head, args.post_deploy_evidence)
            elif args.command == "ack":
                acknowledge(state, args.fingerprint)
            task["convergence"] = state
            save_task(root, task)
            phase = args.phase if args.command == "status" else "status"
            report = health_report(state, phase)
            implementation_report = validate_registry(root)
            if not implementation_report["ok"]:
                report["ok"] = False
                report["severity"] = "BLOCKED"
                report["blockers"].extend(
                    f"实现唯一性门禁：{item['message']}" for item in implementation_report["errors"]
                )
                report["actions"].append("收敛为一个权威活动实现和一个权威状态写入者")
        print(json.dumps({"ok": report["ok"], "result": report, "operation": operation_result, "state": state}, ensure_ascii=False, indent=2))
        return 0 if args.command != "status" or report["ok"] else 2
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
