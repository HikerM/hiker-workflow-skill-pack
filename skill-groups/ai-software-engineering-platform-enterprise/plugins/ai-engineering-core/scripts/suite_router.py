from __future__ import annotations

import argparse
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from community_pro_bridge import detect_pro_runtime, query_project_facts, router_boundary_adoption
from capability_metadata import policy_enabled, routable_plugin_map, supports_stage, supports_surface
from source_identity import identify
from context_budget import build_context_plan
from project_fact_plane import build_project_fact_plane
from route_contract import normalize_route_contract
from state_consistency import assess as assess_state_consistency, current_snapshot
from suite_version import inspect_suite, skill_path


PLUGIN_FOR = routable_plugin_map()

PLUGIN_DISPLAY = {
    "ai-engineering-core": "01 智能工程核心",
    "ai-engineering-web": "02 浏览器端与服务端工程",
    "ai-engineering-unity": "03 客户端工程",
    "ai-engineering-workspace": "04 工作区与多会话协作",
    "ai-engineering-quality": "05 质量、风险与发布",
}

VALID_STAGES = {"planning", "design", "development", "review", "testing", "merge", "release", "governance", "unknown"}
VALID_ARCHITECTURES = {"bs", "cs", "backend", "hybrid", "tooling", "unknown"}
VALID_MODES = {"greenfield", "brownfield", "existing", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low"}

def bounded_marker_paths(
    root: Path,
    max_depth: int = 3,
    max_dirs: int = 160,
    identity: dict[str, Any] | None = None,
) -> list[Path]:
    """Compatibility view backed by the single bounded Project Fact Plane discovery."""
    identity = identity or identify(root)
    plane = build_project_fact_plane(root, identity=identity)
    return [root.resolve() / path for path in plane["manifest_discovery"]["sources"]]


def project_signals(root: Path, pro_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one bounded Project Fact Plane; never interpret the user's prose."""
    identity = identify(root, include_untracked_dirty=False)
    consistency = assess_state_consistency(root, current_snapshot(root, identity))
    plane = build_project_fact_plane(root, identity, consistency, pro_payload)
    topology = (plane.get("project_topology") or {}).get("value") or {}
    architecture = str((plane.get("project_architecture") or {}).get("value") or "")
    architectures: list[str] = []
    if architecture:
        architectures.append(architecture)
    if topology.get("backend_roots") and "backend" not in architectures:
        architectures.append("backend")
    if topology.get("client_roots") and "cs" not in architectures:
        architectures.append("cs")
    frameworks = set((plane.get("framework_facts") or {}).get("value") or [])
    sources = [str(root.resolve() / path) for path in plane["manifest_discovery"]["sources"]]
    return {
        "existing": bool(sources or plane.get("current_goal") or plane.get("current_task")),
        "architectures": architectures,
        "project_architecture": architecture or None,
        "unity": "unity" in frameworks,
        "context_ready": bool(plane.get("context_source_trusted")),
        "sources": sources[:48],
        "identity": identity,
        "source_conflicts": bool(identity.get("nested_worktrees")),
        "state_consistency": consistency,
        "project_fact_plane": plane,
    }


@lru_cache(maxsize=64)
def locate(skill: str) -> str:
    plugin = PLUGIN_FOR[skill]
    exact = skill_path(plugin, skill)
    if exact.is_file():
        return str(exact.resolve())
    here = Path(__file__).resolve().parents[1]
    candidates = [
        here.parent / plugin / "skills" / skill / "SKILL.md",
        Path.home() / ".codex" / "plugins" / plugin / "skills" / skill / "SKILL.md",
    ]
    cache = Path.home() / ".codex" / "plugins" / "cache"
    if cache.is_dir():
        candidates.extend(sorted(cache.glob(f"*/{plugin}/*/skills/{skill}/SKILL.md"), reverse=True))
    return str(candidates[0].resolve())


@lru_cache(maxsize=64)
def skill_display(skill: str) -> str:
    yaml_file = Path(locate(skill)).parent / "agents" / "openai.yaml"
    if yaml_file.is_file():
        try:
            match = re.search(r'^\s*display_name:\s*["\']?([^"\'\r\n]+)', yaml_file.read_text(encoding="utf-8"), re.M)
            if match:
                return match.group(1).strip()
        except OSError:
            pass
    return "未命名工程能力"


def inspect_project(root: Path, pro_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root.resolve()
    signals = project_signals(root, pro_payload)
    identity = signals["identity"]
    suite = inspect_suite()
    return {
        "schema_version": "2.0.0",
        "routing_authority": "chatgpt-semantic-selection",
        "guard_role": "constraints-and-evidence-only",
        "project_facts": {
            "mode_hint": "existing" if signals["existing"] else "unknown",
            "architectures": signals["architectures"],
            "project_architecture": signals["project_architecture"],
            "unity": signals["unity"],
            "context_ready": signals["context_ready"],
            "source_conflicts": signals["source_conflicts"],
            "sources": signals["sources"],
            "repo_root": identity.get("repo_root"),
            "worktree_root": identity.get("worktree_root"),
            "branch": identity.get("branch"),
            "head": identity.get("head"),
            "trusted_manifest_count": len(identity.get("trusted_markers", [])),
            "tracked_file_count": identity.get("tracked_file_count"),
            "nested_worktree_count": len(identity.get("nested_worktrees", [])),
            "fact_plane": signals["project_fact_plane"],
        },
        "proposal_contract": {
            "required": ["project_mode", "architecture", "stage", "candidates", "current_action"],
            "candidate_limit": 2,
            "deferred_limit": 8,
            "architectures": sorted(VALID_ARCHITECTURES),
            "stages": sorted(VALID_STAGES),
        },
        "latency_policy": {
            "fast": "简单解释、状态查询或无项目动作时不调用本脚本",
            "project": "证据充分时直接一次守门；证据不足时最多一次检查加一次守门",
            "governed": "仅多会话、合并、发布或长链路任务启用完整治理",
        },
        "context_budget": _context_plan(root, "unknown", signals),
        "state_consistency": signals["state_consistency"],
        "plugin_suite": suite,
        "catalog": str((Path(__file__).resolve().parents[1] / "references" / "semantic-routing-catalog.md").resolve()),
    }


def _bounded_text_list(raw: Any, limit: int = 8, max_chars: int = 160) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip()[:max_chars] for item in raw[:limit] if str(item).strip()]


def _candidate_items(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append({"skill": item.strip(), "reason": "ChatGPT 根据当前目标与工程证据选择"})
        elif isinstance(item, dict):
            result.append({
                "skill": str(item.get("skill") or "").strip(),
                "reason": str(item.get("reason") or "ChatGPT 根据当前目标与工程证据选择").strip()[:240],
            })
    return [item for item in result if item["skill"]]


def _context_plan(root: Path, stage: str, signals: dict[str, Any], risk_signals: set[str] | None = None) -> dict[str, Any]:
    identity = signals["identity"]
    plane = signals["project_fact_plane"]
    changed_scope = plane.get("current_changed_scope") if isinstance(plane.get("current_changed_scope"), list) else []
    return build_context_plan(
        root,
        stage,
        changed_paths=changed_scope,
        signals=risk_signals,
        tracked_files=identity.get("tracked_file_count"),
        active_facts={
            "current_goal": plane.get("current_goal"),
            "current_task": plane.get("current_task"),
            "direct_dependencies": plane.get("current_direct_dependencies"),
            "relevant_contracts": plane.get("current_contracts"),
            "relevant_evidence": plane.get("current_evidence_refs"),
        },
    )


def _validate_stage(skill: str, stage: str) -> str | None:
    return None if supports_stage(skill, stage) else f"{skill} 与 {stage} 阶段不兼容"


def _validate_architecture(skill: str, project_architecture: str) -> str | None:
    if not project_architecture or project_architecture == "unknown":
        return None
    return None if supports_surface(skill, project_architecture) else f"{skill} 与项目清单中的架构证据冲突"


def route(
    root: Path,
    proposal: dict[str, Any] | str | None = None,
    pro_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a ChatGPT proposal. Never infer a Skill from request keywords."""
    root = root.resolve()
    signals = project_signals(root, pro_payload)
    identity = signals["identity"]
    project_facts = {
        "mode_hint": "existing" if signals["existing"] else "unknown",
        "architectures": signals["architectures"],
        "project_architecture": signals["project_architecture"],
        "unity": signals["unity"],
        "context_ready": signals["context_ready"],
        "source_conflicts": signals["source_conflicts"],
        "sources": signals["sources"],
        "repo_root": identity.get("repo_root"),
        "worktree_root": identity.get("worktree_root"),
        "branch": identity.get("branch"),
        "head": identity.get("head"),
        "trusted_manifest_count": len(identity.get("trusted_markers", [])),
        "nested_worktree_count": len(identity.get("nested_worktrees", [])),
        "fact_plane": signals["project_fact_plane"],
    }
    consistency = signals["state_consistency"]
    suite = inspect_suite()
    if not isinstance(proposal, dict):
        request_hash = hashlib.sha256(str(proposal or "").encode("utf-8")).hexdigest()[:16] if proposal else None
        return {
            "schema_version": "2.0.0",
            "routing_authority": "chatgpt-semantic-selection",
            "guard_role": "constraints-and-evidence-only",
            "project_facts": project_facts,
            "context_budget": _context_plan(root, "unknown", signals),
            "state_consistency": consistency,
            "plugin_suite": suite,
            "catalog": str((Path(__file__).resolve().parents[1] / "references" / "semantic-routing-catalog.md").resolve()),
            "guard_decision": "PROPOSAL_REQUIRED",
            "accepted": False,
            "reselect_required": True,
            "selected": [],
            "deferred": [],
            "load": [],
            "max_loaded_atomic_skills": 2,
            "router_counts_toward_limit": False,
            "receipt_required": False,
            "request_fingerprint": request_hash,
            "diagnostics": [{"code": "MODEL_PROPOSAL_REQUIRED", "message": "由 ChatGPT 先做语义选择，再提交候选给守门器"}],
        }

    normalized = normalize_route_contract(proposal, signals["project_fact_plane"], PLUGIN_FOR)
    contract = normalized["contract"]
    stage = contract["stage"]
    architecture = contract["project_architecture"]
    task_scope = contract["task_scope"]
    project_mode = str(proposal.get("project_mode") or ("existing" if signals["existing"] else "unknown")).strip().lower()
    confidence = str(proposal.get("confidence") or "medium").strip().lower()
    goal_revision = str(proposal.get("goal_revision") or "current").strip()[:80] or "current"
    current_action = str(proposal.get("current_action") or "").strip()[:240]
    candidates = _candidate_items(proposal.get("candidates"))
    deferred = _candidate_items(proposal.get("deferred"))[:8]
    diagnostics: list[dict[str, str]] = list(normalized["diagnostics"])
    warnings: list[dict[str, str]] = []

    def error(code: str, message: str) -> None:
        diagnostics.append({"code": code, "message": message})

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    if not suite["consistent"]:
        error("PLUGIN_SUITE_VERSION_CONFLICT", "五个插件不是同一完整版本；禁止加载混合版本Skill")

    if stage not in VALID_STAGES:
        error("INVALID_STAGE", f"未知阶段：{stage}")
    if architecture not in VALID_ARCHITECTURES:
        error("INVALID_ARCHITECTURE", f"未知架构：{architecture}")
    if project_mode not in VALID_MODES:
        error("INVALID_PROJECT_MODE", f"未知项目模式：{project_mode}")
    if confidence not in VALID_CONFIDENCE:
        error("INVALID_CONFIDENCE", f"未知置信度：{confidence}")
    if not current_action:
        error("MISSING_CURRENT_ACTION", "必须说明当前动作，不能用完整生命周期代替当前阶段")
    if not candidates:
        error("EMPTY_CANDIDATES", "ChatGPT 未选择当前阶段的原子 Skill")
    if len(candidates) > 2:
        error("ATOMIC_SKILL_LIMIT", "当前阶段最多激活两个原子 Skill")
    if contract["ambiguity_policy"] == "BLOCK":
        error("AMBIGUITY_BLOCKED", "存在会导致高风险工程动作分歧的正向冲突，必须阻断")
    elif contract["ambiguity_policy"] == "ASK_REQUIRED":
        error("AMBIGUITY_REQUIRES_USER", "高风险动作方向无法由证据安全确定，需要用户确认")
    for fact_conflict in signals["project_fact_plane"].get("authority_conflicts") or []:
        if fact_conflict.get("severity") == "BLOCK":
            error("FACT_AUTHORITY_CONFLICT", f"{fact_conflict.get('fact')} 存在当前权威冲突，必须先完成确定性对账")

    all_ids = [item["skill"] for item in candidates + deferred]
    if len(all_ids) != len(set(all_ids)):
        error("DUPLICATE_SKILL", "活跃与待执行队列存在重复 Skill")
    for skill in all_ids:
        if skill not in PLUGIN_FOR:
            error("UNKNOWN_SKILL", f"候选 Skill 不在已发布目录中：{skill}")

    conflict = contract["conflict_receipt"]
    if conflict["is_positive_contradiction"]:
        error(
            "ARCHITECTURE_CONFLICT",
            f"项目架构存在正向互斥证据：{conflict['expected_fact']} != {conflict['observed_fact']}",
        )

    for item in candidates:
        skill = item["skill"]
        if skill not in PLUGIN_FOR:
            continue
        stage_problem = _validate_stage(skill, stage)
        if stage_problem:
            error("STAGE_SKILL_CONFLICT", stage_problem)
        architecture_problem = _validate_architecture(skill, signals["project_architecture"] or architecture)
        if architecture_problem:
            error("ARCHITECTURE_CONFLICT", architecture_problem)
        if signals["source_conflicts"] and not policy_enabled(skill, "source_conflict_safe"):
            error("SOURCE_IDENTITY_CONFLICT", "检测到嵌套工作目录；只能先选择源码身份或工作目录收敛能力")
        state_policy = consistency.get("execution_policy", {})
        if (
            consistency.get("status") != "STATELESS_UNMANAGED"
            and not state_policy.get("trusted_ai_state")
            and policy_enabled(skill, "requires_trusted_ai_state")
        ):
            error(
                "STALE_AI_STATE_DEPENDENCY",
                f"{skill} 依赖可信 .ai；当前只能按最新用户请求与 Git 轻量推进，禁止恢复旧任务、旧 PASS、多会话或 Worktree",
            )

    basis = {
        "stage": stage,
        "architecture": architecture,
        "task_scope": task_scope,
        "active": [item["skill"] for item in candidates],
        "deferred": [item["skill"] for item in deferred],
        "current_action": current_action,
        "goal_revision": goal_revision,
        "repo_id": consistency.get("current", {}).get("repo_id"),
        "head": consistency.get("current", {}).get("head"),
        "dirty": consistency.get("current", {}).get("dirty"),
        "manifest_hash": consistency.get("current", {}).get("manifest_hash"),
        "suite_fingerprint": suite["fingerprint"],
        "project_fact_fingerprint": signals["project_fact_plane"]["source_fingerprint"],
        "route_contract_fingerprint": contract["route_contract_fingerprint"],
    }
    route_fingerprint = hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    previous_route = {}
    if consistency.get("execution_policy", {}).get("trusted_ai_state"):
        route_state = root / ".ai" / "runtime" / "skill-routing.json"
        try:
            previous_route = json.loads(route_state.read_text(encoding="utf-8")) if route_state.is_file() else {}
        except (OSError, json.JSONDecodeError):
            previous_route = {}
    previous_suite = previous_route.get("suite_fingerprint") if previous_route else None
    version_drift = bool(previous_route and previous_suite != suite["fingerprint"])
    if version_drift and not all(policy_enabled(item["skill"], "version_recovery") for item in candidates):
        warn("PLUGIN_VERSION_DRIFT_QUARANTINED", "旧插件路由缓存已隔离；当前请求与Git事实继续，Pro在安全边界完成接管")
    accepted = not diagnostics
    selected_output = [
        {
            "id": item["skill"],
            "skill": skill_display(item["skill"]),
            "plugin": PLUGIN_DISPLAY[PLUGIN_FOR[item["skill"]]],
            "reason": item["reason"],
        }
        for item in candidates if accepted
    ]
    deferred_output = [
        {
            "id": item["skill"],
            "skill": skill_display(item["skill"]),
            "plugin": PLUGIN_DISPLAY[PLUGIN_FOR[item["skill"]]],
            "reason": item["reason"],
        }
        for item in deferred if item["skill"] in PLUGIN_FOR
    ] if accepted else []
    context_signals = set(_bounded_text_list(proposal.get("risk_signals")))
    return {
        "schema_version": "2.0.0",
        "routing_authority": "chatgpt-semantic-selection",
        "guard_role": "constraints-and-evidence-only",
        "guard_decision": "ACCEPT" if accepted else "REJECT",
        "accepted": accepted,
        "reselect_required": not accepted,
        "project_mode": project_mode,
        "architecture": architecture,
        "project_architecture": architecture,
        "task_scope": task_scope,
        "stage": stage,
        "current_action": current_action,
        "selected": selected_output,
        "deferred": deferred_output,
        "load": [locate(item["skill"]) for item in candidates] if accepted else [],
        "max_loaded_atomic_skills": 2,
        "router_counts_toward_limit": False,
        "intent": {
            "negated_terms": _bounded_text_list(proposal.get("negated_terms")),
            "future_terms": _bounded_text_list(proposal.get("future_terms")),
            "follow_up_actions": _bounded_text_list(proposal.get("follow_up_actions")),
        },
        "phase_transition_required": bool(deferred or proposal.get("future_terms") or proposal.get("follow_up_actions")),
        "receipt_source": "skill-loader-telemetry",
        "route_fingerprint": route_fingerprint,
        "route_contract": contract,
        "intent_dag": {
            "nodes": contract["intent_atoms"],
            "edges": contract["dependencies"],
        },
        "ambiguity_policy": contract["ambiguity_policy"],
        "routing_cost": contract["routing_cost"],
        "capability_prefilter": contract["capability_prefilter"],
        "conflict_receipt": contract["conflict_receipt"],
        "route_receipt": {
            "candidate": contract["candidate_capabilities"],
            "selected": [item["skill"] for item in candidates] if accepted else [],
            "loaded": [],
            "applied": [],
            "completed": [],
            "deferred": [item["skill"] for item in deferred] if accepted else [],
            "rejected": [] if accepted else [item["code"] for item in diagnostics],
            "fingerprint": route_fingerprint,
        },
        "admission_cache": {
            "hit": bool(accepted and previous_route.get("route_fingerprint") == route_fingerprint),
            "key_fields": ["goal_revision", "repo_id", "head", "dirty", "manifest_hash", "stage", "current_action", "active", "deferred"],
            "reuse": "命中时复用已加载能力与回执，不重复读取目录或Skill正文",
        },
        "version_gate": {
            "suite_version": suite["version"],
            "suite_fingerprint": suite["fingerprint"],
            "consistent": suite["consistent"],
            "drift": version_drift,
            "old_task_policy": "隔离旧路由/PASS缓存；当前请求与Git继续，禁止恢复旧Lease/Agent/Writer",
        },
        "next_gate": "完成当前阶段并由 ChatGPT 重新语义选择" if deferred else None,
        "confidence": confidence,
        "context_budget": _context_plan(root, stage, signals, context_signals),
        "project_evidence": signals["sources"],
        "project_fact_plane": signals["project_fact_plane"],
        "source_identity": project_facts,
        "state_consistency": consistency,
        "plugin_suite": suite,
        "execution_policy": consistency.get("execution_policy", {}),
        "receipt_required": accepted,
        "diagnostics": diagnostics,
        "warnings": warnings,
    }


def _load_proposal(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.proposal_file:
        return json.loads(Path(args.proposal_file).read_text(encoding="utf-8"))
    if args.proposal_json:
        return json.loads(args.proposal_json)
    if args.candidate:
        return {
            "project_mode": args.project_mode,
            "architecture": args.architecture,
            "stage": args.stage,
            "current_action": args.current_action,
            "confidence": args.confidence,
            "goal_revision": args.goal_revision,
            "candidates": args.candidate,
            "deferred": args.deferred_skill,
            "negated_terms": args.negated_term,
            "future_terms": args.future_term,
            "follow_up_actions": args.follow_up_action,
        }
    return None


def _apply_route_boundary_adoption(
    root: Path,
    result: dict[str, Any],
    detected: dict[str, Any] | None = None,
    authority_facts: dict[str, Any] | None = None,
) -> None:
    """Adopt at accepted admission, before any selected Skill can be loaded."""
    if result.get("guard_decision") != "ACCEPT":
        return
    adoption = router_boundary_adoption(root, detected=detected, authority_facts=authority_facts)
    result["pro_live_adoption"] = adoption
    result["pro_state"] = adoption.get("pro_state", "COMMUNITY_FALLBACK")
    if adoption.get("adopted") or adoption.get("pro_state") == "COMMUNITY_FALLBACK":
        return
    result["guard_decision"] = "REJECT"
    result["accepted"] = False
    result["reselect_required"] = False
    result["load"] = []
    result["receipt_required"] = False
    result.setdefault("diagnostics", []).append(
        {
            "code": "PRO_LIVE_ADOPTION_REQUIRED",
            "message": "Pro Runtime存在但未完成安全接管；已明确进入DEGRADED/BLOCKED，禁止伪装为Pro已生效",
        }
    )


def _current_authority_facts(args: argparse.Namespace) -> dict[str, Any] | None:
    values = (
        args.current_goal_statement,
        args.goal_authority_source,
        args.current_task_statement,
        args.task_authority_source,
    )
    if not any(values):
        return None
    return {
        "goal": {
            "statement": args.current_goal_statement,
            "state": args.current_goal_state,
            "authority_source": args.goal_authority_source,
            "authority_generation": args.goal_authority_generation,
        },
        "task": {
            "statement": args.current_task_statement,
            "state": args.current_task_state,
            "authority_source": args.task_authority_source,
            "authority_generation": args.task_authority_generation,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 ChatGPT 的原子 Skill 语义选择；不按关键词代替模型选 Skill")
    parser.add_argument("--root", default=".")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--proposal-file")
    parser.add_argument("--proposal-json")
    parser.add_argument("--request", help="兼容旧调用；仅生成指纹，不参与 Skill 选择")
    parser.add_argument("--project-mode", default="unknown")
    parser.add_argument("--architecture", default="unknown")
    parser.add_argument("--stage", default="unknown")
    parser.add_argument("--current-action", default="")
    parser.add_argument("--confidence", default="medium")
    parser.add_argument("--goal-revision", default="current")
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--deferred-skill", action="append", default=[])
    parser.add_argument("--negated-term", action="append", default=[])
    parser.add_argument("--future-term", action="append", default=[])
    parser.add_argument("--follow-up-action", action="append", default=[])
    parser.add_argument("--current-goal-statement")
    parser.add_argument("--current-goal-state", default="ACTIVE")
    parser.add_argument("--goal-authority-source")
    parser.add_argument("--goal-authority-generation", type=int, default=0)
    parser.add_argument("--current-task-statement")
    parser.add_argument("--current-task-state", default="IN_PROGRESS")
    parser.add_argument("--task-authority-source")
    parser.add_argument("--task-authority-generation", type=int, default=0)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.inspect:
        result = inspect_project(root)
    else:
        proposal = _load_proposal(args)
        detected: dict[str, Any] | None = None
        pro_facts: dict[str, Any] | None = None
        if (root / ".ai" / "state" / "hiker-state.db").is_file():
            detected = detect_pro_runtime()
            if detected.get("pro_available"):
                facts_report = query_project_facts(root, detected=detected)
                if isinstance(facts_report.get("facts"), dict):
                    pro_facts = facts_report
        result = route(root, proposal if proposal is not None else args.request, pro_facts)
        _apply_route_boundary_adoption(root, result, detected, _current_authority_facts(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("guard_decision") != "REJECT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
