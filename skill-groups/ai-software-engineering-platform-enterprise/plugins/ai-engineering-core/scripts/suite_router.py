from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any

from source_identity import context_fresh, identify
from context_budget import build_context_plan
from state_consistency import assess as assess_state_consistency


# Keep this literal mapping: the release audit uses it as the single coverage map.
PLUGIN_FOR = {
    "greenfield-project-planning": "ai-engineering-core",
    "architecture-decision-challenge": "ai-engineering-core",
    "brownfield-requirement-reconciliation": "ai-engineering-core",
    "project-bootstrap": "ai-engineering-core",
    "bounded-context-memory": "ai-engineering-core",
    "interruptible-task-control": "ai-engineering-core",
    "context-recovery": "ai-engineering-core",
    "official-standards-resolver": "ai-engineering-core",
    "web-ui-design": "ai-engineering-web",
    "web-component-implementation": "ai-engineering-web",
    "web-quality-review": "ai-engineering-web",
    "backend-technology-router": "ai-engineering-web",
    "api-event-contract-design": "ai-engineering-web",
    "backend-component-implementation": "ai-engineering-web",
    "database-migration-governance": "ai-engineering-web",
    "backend-quality-review": "ai-engineering-web",
    "cs-client-router": "ai-engineering-unity",
    "cs-ui-design": "ai-engineering-unity",
    "cs-component-implementation": "ai-engineering-unity",
    "cs-quality-review": "ai-engineering-unity",
    "unity-ui-design": "ai-engineering-unity",
    "unity-component-implementation": "ai-engineering-unity",
    "unity-quality-review": "ai-engineering-unity",
    "workspace-task-router": "ai-engineering-workspace",
    "multi-agent-project-governance": "ai-engineering-workspace",
    "change-ownership-merge": "ai-engineering-workspace",
    "regression-test-planner": "ai-engineering-quality",
    "full-change-risk-review": "ai-engineering-quality",
    "release-readiness-review": "ai-engineering-quality",
    "design-readiness-review": "ai-engineering-quality",
    "knowledge-graph-maintenance": "ai-engineering-quality",
    "interaction-conflict-governance": "ai-engineering-quality",
    "feature-acceptance-closure": "ai-engineering-workspace",
    "file-lock-manager": "ai-engineering-workspace",
    "multi-project-portfolio-manager": "ai-engineering-workspace",
    "plugin-application-receipt": "ai-engineering-workspace",
    "project-state-manager": "ai-engineering-workspace",
    "task-lifecycle-manager": "ai-engineering-workspace",
    "long-chain-change-convergence": "ai-engineering-workspace",
    "worktree-task-manager": "ai-engineering-workspace",
    "worktree-safe-convergence": "ai-engineering-workspace",
}

PLUGIN_DISPLAY = {
    "ai-engineering-core": "01 智能工程核心",
    "ai-engineering-web": "02 浏览器端与服务端工程",
    "ai-engineering-unity": "03 客户端工程",
    "ai-engineering-workspace": "04 工作区与多会话协作",
    "ai-engineering-quality": "05 质量、风险与发布",
}

PROJECT_MARKERS = (
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "Gemfile",
    "CMakeLists.txt", "Packages/manifest.json",
)
IGNORED_DIRS = {
    ".git", ".ai", "node_modules", "Library", "Temp", "obj", "bin", "dist",
    "build", ".venv", "venv", "Pods", "DerivedData",
}
FRONTEND_TOKENS = ("vue", "react", "next.js", "next", "nuxt", "angular", "svelte", "vite", "web-node")
BACKEND_TOKENS = (
    "nestjs", "express", "fastify", "koa", "@hapi/hapi", "fastapi", "django",
    "flask", "litestar", "sanic", "spring boot", "spring-boot", "quarkus",
    "micronaut", "asp.net", "microsoft.net.sdk.web", "laravel", "rails", "backend", "server",
)
CLIENT_TOKENS = (
    "unity", "wpf", "winui", "winforms", "avalonia", "maui", "qt", "qml",
    "electron", "tauri", "flutter", "android", "swiftui", "uikit", "appkit",
    "react native", "react-native", "javafx", "swing", "lvgl",
)

VALID_STAGES = {"planning", "design", "development", "review", "testing", "merge", "release", "governance", "unknown"}
VALID_ARCHITECTURES = {"bs", "cs", "backend", "hybrid", "tooling", "unknown"}
VALID_MODES = {"greenfield", "brownfield", "existing", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low"}

DESIGN_SKILLS = {"web-ui-design", "cs-ui-design", "unity-ui-design"}
IMPLEMENTATION_SKILLS = {
    "web-component-implementation", "backend-component-implementation",
    "cs-component-implementation", "unity-component-implementation",
}
QUALITY_REVIEW_SKILLS = {
    "design-readiness-review", "full-change-risk-review", "interaction-conflict-governance",
    "web-quality-review", "backend-quality-review", "cs-quality-review", "unity-quality-review",
}
PLANNING_SKILLS = {
    "greenfield-project-planning", "architecture-decision-challenge",
    "brownfield-requirement-reconciliation", "api-event-contract-design", "project-bootstrap",
}
WEB_SKILLS = {"web-ui-design", "web-component-implementation", "web-quality-review"}
BACKEND_SKILLS = {
    "backend-technology-router", "api-event-contract-design", "backend-component-implementation",
    "database-migration-governance", "backend-quality-review",
}
CLIENT_SKILLS = {
    "cs-client-router", "cs-ui-design", "cs-component-implementation", "cs-quality-review",
    "unity-ui-design", "unity-component-implementation", "unity-quality-review",
}
SOURCE_CONFLICT_SAFE = {
    "worktree-task-manager", "worktree-safe-convergence", "project-bootstrap",
    "full-change-risk-review", "project-state-manager",
}
AI_STATE_DEPENDENT_SKILLS = {
    "bounded-context-memory", "interruptible-task-control", "workspace-task-router",
    "multi-agent-project-governance", "change-ownership-merge", "feature-acceptance-closure",
    "file-lock-manager", "multi-project-portfolio-manager", "plugin-application-receipt",
    "project-state-manager", "task-lifecycle-manager", "long-chain-change-convergence",
    "worktree-task-manager", "knowledge-graph-maintenance",
    "release-readiness-review",
}


def bounded_marker_paths(root: Path, max_depth: int = 3, max_dirs: int = 160) -> list[Path]:
    """Read only shallow manifests; never scan project source during routing."""
    identity = identify(root)
    if identity["is_git"]:
        return [Path(path) for path in identity["trusted_markers"]]
    root = root.resolve()
    found: list[Path] = []
    queue = deque([(root, 0)])
    visited = 0
    while queue and visited < max_dirs:
        current, depth = queue.popleft()
        visited += 1
        for marker in PROJECT_MARKERS:
            path = current / marker
            if path.is_file():
                found.append(path)
        found.extend(sorted(current.glob("*.sln"))[:4])
        found.extend(sorted(current.glob("*.csproj"))[:8])
        if depth >= max_depth:
            continue
        try:
            children = [
                path for path in current.iterdir()
                if path.is_dir() and path.name not in IGNORED_DIRS and not (path / ".git").exists()
            ]
        except OSError:
            children = []
        queue.extend((child, depth + 1) for child in sorted(children)[:64])
    return list(dict.fromkeys(found))


def project_signals(root: Path) -> dict[str, Any]:
    """Return bounded, evidence-backed facts. Do not interpret the user's prose."""
    identity = identify(root)
    context = root / ".ai" / "context" / "tech-stack.json"
    sources: list[str] = []
    evidence_parts: list[str] = []
    context_evidence = ""
    consistency = assess_state_consistency(root)
    state_trusted = bool(consistency.get("execution_policy", {}).get("trusted_ai_state"))
    context_ready = state_trusted and (
        context_fresh(context, identity.get("branch") or "", identity.get("head") or "")
        if identity["is_git"] else context.is_file()
    )
    if context_ready:
        try:
            context_evidence = json.dumps(json.loads(context.read_text(encoding="utf-8")), ensure_ascii=False).lower()
            evidence_parts.append(context_evidence)
            sources.append(str(context))
        except (OSError, json.JSONDecodeError):
            pass
    markers = bounded_marker_paths(root)
    package_dependencies: set[str] = set()
    backend = False
    client = False
    unity = False
    for marker in markers:
        sources.append(str(marker))
        try:
            content = marker.read_text(encoding="utf-8", errors="ignore")[:120_000].lower()
        except OSError:
            content = ""
        evidence_parts.extend((marker.as_posix().lower(), content))
        if marker.name == "package.json":
            try:
                package = json.loads(content)
                package_dependencies.update(
                    str(name).lower()
                    for section in ("dependencies", "devDependencies", "peerDependencies")
                    for name in (package.get(section) or {})
                )
            except (TypeError, json.JSONDecodeError):
                pass
        if marker.suffix.lower() == ".csproj":
            backend = backend or any(token in content for token in ("microsoft.net.sdk.web", "microsoft.aspnetcore", "include=\"aspnetcore\""))
            client = client or any(token in content for token in ("<usewpf>true", "<usewindowsforms>true", "microsoft.windowsappsdk", "avalonia", "maui", "xamarin"))
        if marker.name.lower() in {"pyproject.toml", "requirements.txt", "go.mod", "cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "gemfile"}:
            backend = backend or marker.name.lower() in {"go.mod", "cargo.toml", "composer.json", "gemfile"} or any(token in content for token in BACKEND_TOKENS)
        unity = unity or marker.as_posix().lower().endswith("packages/manifest.json") or "com.unity" in content
    evidence = " ".join(evidence_parts)
    react_native = "react-native" in package_dependencies or "react-native" in evidence or "react native" in evidence
    web_packages = {"vue", "next", "nuxt", "@angular/core", "svelte", "vite"}
    client_packages = {"electron", "electron-builder", "react-native", "@tauri-apps/api", "@tauri-apps/cli", "@capacitor/core", "@ionic/react", "@ionic/vue"}
    web = bool(package_dependencies & web_packages) or ("react" in package_dependencies and not react_native)
    backend = backend or any(
        dependency == token or dependency.startswith(token)
        for dependency in package_dependencies
        for token in ("@nestjs/", "express", "fastify", "koa", "@hapi/", "hapi", "fastapi", "django", "flask", "spring-boot", "laravel", "rails")
    ) or any(token in evidence for token in BACKEND_TOKENS)
    structured_client = bool(context_evidence) and any(token in context_evidence for token in CLIENT_TOKENS)
    client = client or react_native or bool(package_dependencies & client_packages) or structured_client
    unity = unity or (bool(context_evidence) and "unity" in context_evidence)
    architectures = [name for name, present in (("bs", web), ("cs", client), ("backend", backend)) if present]
    return {
        "existing": bool(markers or context_ready),
        "architectures": architectures,
        "unity": unity,
        "context_ready": context_ready,
        "sources": sources[:12],
        "identity": identity,
        "source_conflicts": bool(identity.get("nested_worktrees")),
        "state_consistency": consistency,
    }


@lru_cache(maxsize=64)
def locate(skill: str) -> str:
    plugin = PLUGIN_FOR[skill]
    here = Path(__file__).resolve().parents[1]
    candidates = [
        here.parent / plugin / "skills" / skill / "SKILL.md",
        Path.home() / ".codex" / "plugins" / plugin / "skills" / skill / "SKILL.md",
    ]
    cache = Path.home() / ".codex" / "plugins" / "cache"
    if cache.is_dir():
        candidates.extend(sorted(cache.glob(f"*/{plugin}/*/skills/{skill}/SKILL.md"), reverse=True))
    return str(next((path.resolve() for path in candidates if path.is_file()), candidates[0].resolve()))


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


def inspect_project(root: Path) -> dict[str, Any]:
    root = root.resolve()
    signals = project_signals(root)
    identity = signals["identity"]
    return {
        "schema_version": "2.0.0",
        "routing_authority": "chatgpt-semantic-selection",
        "guard_role": "constraints-and-evidence-only",
        "project_facts": {
            "mode_hint": "existing" if signals["existing"] else "unknown",
            "architectures": signals["architectures"],
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
        },
        "proposal_contract": {
            "required": ["project_mode", "architecture", "stage", "candidates", "current_action"],
            "candidate_limit": 2,
            "deferred_limit": 8,
            "architectures": sorted(VALID_ARCHITECTURES),
            "stages": sorted(VALID_STAGES),
        },
        "context_budget": build_context_plan(root, "unknown"),
        "state_consistency": signals["state_consistency"],
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


def _validate_stage(skill: str, stage: str) -> str | None:
    if skill in DESIGN_SKILLS and stage != "design":
        return f"{skill} 只能在 design 阶段激活"
    if skill in IMPLEMENTATION_SKILLS and stage != "development":
        return f"{skill} 只能在 development 阶段激活"
    if skill in PLANNING_SKILLS and stage not in {"planning", "design", "review"}:
        return f"{skill} 与 {stage} 阶段不兼容"
    if skill in QUALITY_REVIEW_SKILLS and stage not in {"review", "testing", "release"}:
        return f"{skill} 属于独立审核能力，不能替代当前 {stage} 阶段"
    if skill == "regression-test-planner" and stage not in {"testing", "review", "release"}:
        return "regression-test-planner 只能用于测试或审核阶段"
    if skill == "release-readiness-review" and stage != "release":
        return "release-readiness-review 只能用于 release 阶段"
    if skill == "change-ownership-merge" and stage != "merge":
        return "change-ownership-merge 只能用于 merge 阶段"
    return None


def _validate_architecture(skill: str, architectures: set[str]) -> str | None:
    if not architectures:
        return None
    if skill in WEB_SKILLS and "bs" not in architectures:
        return f"{skill} 与项目清单中的架构证据冲突"
    if skill in BACKEND_SKILLS and "backend" not in architectures:
        return f"{skill} 与项目清单中的服务端证据冲突"
    if skill in CLIENT_SKILLS and "cs" not in architectures:
        return f"{skill} 与项目清单中的客户端证据冲突"
    return None


def route(root: Path, proposal: dict[str, Any] | str | None = None) -> dict[str, Any]:
    """Validate a ChatGPT proposal. Never infer a Skill from request keywords."""
    root = root.resolve()
    signals = project_signals(root)
    identity = signals["identity"]
    project_facts = {
        "mode_hint": "existing" if signals["existing"] else "unknown",
        "architectures": signals["architectures"],
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
    }
    consistency = signals["state_consistency"]
    if not isinstance(proposal, dict):
        request_hash = hashlib.sha256(str(proposal or "").encode("utf-8")).hexdigest()[:16] if proposal else None
        return {
            "schema_version": "2.0.0",
            "routing_authority": "chatgpt-semantic-selection",
            "guard_role": "constraints-and-evidence-only",
            "project_facts": project_facts,
            "context_budget": build_context_plan(root, "unknown"),
            "state_consistency": consistency,
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

    stage = str(proposal.get("stage") or "unknown").strip().lower()
    architecture = str(proposal.get("architecture") or "unknown").strip().lower()
    project_mode = str(proposal.get("project_mode") or ("existing" if signals["existing"] else "unknown")).strip().lower()
    confidence = str(proposal.get("confidence") or "medium").strip().lower()
    current_action = str(proposal.get("current_action") or "").strip()[:240]
    candidates = _candidate_items(proposal.get("candidates"))
    deferred = _candidate_items(proposal.get("deferred"))[:8]
    diagnostics: list[dict[str, str]] = []

    def error(code: str, message: str) -> None:
        diagnostics.append({"code": code, "message": message})

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

    all_ids = [item["skill"] for item in candidates + deferred]
    if len(all_ids) != len(set(all_ids)):
        error("DUPLICATE_SKILL", "活跃与待执行队列存在重复 Skill")
    for skill in all_ids:
        if skill not in PLUGIN_FOR:
            error("UNKNOWN_SKILL", f"候选 Skill 不在已发布目录中：{skill}")

    fact_architectures = set(signals["architectures"])
    if fact_architectures and architecture not in {"unknown", "tooling"}:
        if architecture == "hybrid" and len(fact_architectures) < 2:
            error("ARCHITECTURE_CONFLICT", f"项目证据仅支持 {sorted(fact_architectures)}，不支持 hybrid")
        elif architecture != "hybrid" and architecture not in fact_architectures:
            error("ARCHITECTURE_CONFLICT", f"模型提出 {architecture}，项目证据为 {sorted(fact_architectures)}")

    for item in candidates:
        skill = item["skill"]
        if skill not in PLUGIN_FOR:
            continue
        stage_problem = _validate_stage(skill, stage)
        if stage_problem:
            error("STAGE_SKILL_CONFLICT", stage_problem)
        architecture_problem = _validate_architecture(skill, fact_architectures)
        if architecture_problem:
            error("SKILL_PROJECT_EVIDENCE_CONFLICT", architecture_problem)
        if signals["source_conflicts"] and skill not in SOURCE_CONFLICT_SAFE:
            error("SOURCE_IDENTITY_CONFLICT", "检测到嵌套工作目录；只能先选择源码身份或工作目录收敛能力")
        state_policy = consistency.get("execution_policy", {})
        if (
            consistency.get("status") != "STATELESS_UNMANAGED"
            and not state_policy.get("trusted_ai_state")
            and skill in AI_STATE_DEPENDENT_SKILLS
        ):
            error(
                "STALE_AI_STATE_DEPENDENCY",
                f"{skill} 依赖可信 .ai；当前只能按最新用户请求与 Git 轻量推进，禁止恢复旧任务、旧 PASS、多会话或 Worktree",
            )

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
    basis = {
        "stage": stage,
        "architecture": architecture,
        "active": [item["skill"] for item in candidates],
        "deferred": [item["skill"] for item in deferred],
        "head": signals["identity"].get("head"),
    }
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
        "route_fingerprint": hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16],
        "next_gate": "完成当前阶段并由 ChatGPT 重新语义选择" if deferred else None,
        "confidence": confidence,
        "context_budget": build_context_plan(root, stage, signals=context_signals),
        "project_evidence": signals["sources"],
        "source_identity": project_facts,
        "state_consistency": consistency,
        "execution_policy": consistency.get("execution_policy", {}),
        "receipt_required": accepted,
        "diagnostics": diagnostics,
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
            "candidates": args.candidate,
            "deferred": args.deferred_skill,
            "negated_terms": args.negated_term,
            "future_terms": args.future_term,
            "follow_up_actions": args.follow_up_action,
        }
    return None


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
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--deferred-skill", action="append", default=[])
    parser.add_argument("--negated-term", action="append", default=[])
    parser.add_argument("--future-term", action="append", default=[])
    parser.add_argument("--follow-up-action", action="append", default=[])
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.inspect:
        result = inspect_project(root)
    else:
        proposal = _load_proposal(args)
        result = route(root, proposal if proposal is not None else args.request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("guard_decision") != "REJECT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
