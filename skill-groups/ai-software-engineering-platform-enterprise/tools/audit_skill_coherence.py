from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
from pathlib import Path
from typing import Any

from audit_specialization_maturity import audit as audit_specialization_maturity


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODES = {"router", "planning", "design", "implementation", "review", "workflow", "control-plane", "report"}
NEGATION_WORDS = ("不得", "禁止", "不自动", "不直接", "不能", "不允许", "只生成", "仅生成")
DESTRUCTIVE_PATTERN = re.compile(r"(?:自动|直接).{0,10}(?:push|merge|deploy|release|推送|合并|部署|发布|删除|清理)", re.I)
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _yaml_value(text: str, key: str) -> str:
    match = re.search(rf'^\s*{re.escape(key)}:\s*["\']?([^"\'\r\n]+)', text, re.M)
    return match.group(1).strip() if match else ""


def _trigrams(value: str) -> set[str]:
    compact = re.sub(r"\s+", "", value.lower())
    return {compact[index:index + 3] for index in range(max(0, len(compact) - 2))}


def _finding(code: str, skill: str, message: str, path: Path | None = None) -> dict[str, str]:
    item = {"code": code, "skill": skill, "message": message}
    if path is not None:
        item["path"] = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    return item


def audit(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    plugins = sorted(path for path in (root / "plugins").iterdir() if path.is_dir())
    records: dict[str, dict[str, Any]] = {}
    display_names: dict[str, str] = {}
    versions: set[str] = set()

    for plugin in plugins:
        manifest_path = plugin / ".codex-plugin" / "plugin.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            versions.add(str(manifest.get("version") or ""))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(_finding("INVALID_PLUGIN_MANIFEST", plugin.name, str(exc), manifest_path))
            continue
        prompts = manifest.get("interface", {}).get("defaultPrompt") or []
        if not isinstance(prompts, list) or len(prompts) > 3:
            errors.append(_finding("DESKTOP_DEFAULT_PROMPT_OVERFLOW", plugin.name, "defaultPrompt 必须是不超过3项的数组", manifest_path))
        hook_files = [path for path in (plugin / "hooks").rglob("*") if path.is_file()] if (plugin / "hooks").exists() else []
        if hook_files:
            errors.append(_finding("DESKTOP_LIFECYCLE_HOOK_FORBIDDEN", plugin.name, "高频生命周期Hook会放大桌面任务崩溃与重入写入风险", hook_files[0]))
        for skill_path in sorted((plugin / "skills").glob("*/SKILL.md")):
            text = skill_path.read_text(encoding="utf-8")
            meta = _frontmatter(text)
            name = skill_path.parent.name
            yaml_path = skill_path.parent / "agents" / "openai.yaml"
            yaml_text = yaml_path.read_text(encoding="utf-8") if yaml_path.is_file() else ""
            display = _yaml_value(yaml_text, "display_name")
            prompt = _yaml_value(yaml_text, "default_prompt")
            implicit = _yaml_value(yaml_text, "allow_implicit_invocation").lower()
            description = meta.get("description", "")
            records[name] = {
                "plugin": plugin.name,
                "path": skill_path,
                "text": text,
                "description": description,
                "display": display,
                "prompt": prompt,
                "implicit": implicit,
            }
            if meta.get("name") != name:
                errors.append(_finding("SKILL_NAME_MISMATCH", name, "frontmatter name 与目录名不一致", skill_path))
            if len(description) < 40:
                errors.append(_finding("DESCRIPTION_TOO_THIN", name, "description 未充分说明用途、触发条件与边界", skill_path))
            if len(text.splitlines()) > 500:
                errors.append(_finding("SKILL_BODY_TOO_LARGE", name, "SKILL.md 超过500行，违反渐进加载预算", skill_path))
            if skill_path.stat().st_size > 16 * 1024:
                errors.append(_finding("SKILL_BYTES_TOO_LARGE", name, "SKILL.md 超过16KiB，会增加桌面上下文压力", skill_path))
            if not display or re.search(r"[A-Za-z]", display):
                errors.append(_finding("INVALID_DISPLAY_NAME", name, "用户可见 Skill 名称必须是非空中文名称", yaml_path))
            elif display in display_names:
                errors.append(_finding("DUPLICATE_DISPLAY_NAME", name, f"与 {display_names[display]} 使用相同中文名称", yaml_path))
            else:
                display_names[display] = name
            if not prompt:
                errors.append(_finding("MISSING_DEFAULT_PROMPT", name, "缺少手动选择后的默认调用提示", yaml_path))
            elif f"${name}" not in prompt:
                errors.append(_finding("AMBIGUOUS_DEFAULT_PROMPT", name, "默认调用提示未绑定当前 Skill", yaml_path))
            if name == "plugin-application-receipt" and any(term in prompt for term in ("项目", "模式", "原因", "分类")):
                errors.append(_finding("RECEIPT_SCOPE_CONFLICT", name, "应用回执不得显示项目、模式、原因或组织分类", yaml_path))
            for target in LINK_PATTERN.findall(text):
                clean = target.split("#", 1)[0].strip()
                if not clean or clean.startswith(("http://", "https://", "mailto:", "#", "<")):
                    continue
                if not (skill_path.parent / clean).resolve().exists():
                    errors.append(_finding("BROKEN_LOCAL_REFERENCE", name, f"本地引用不存在：{target}", skill_path))
            for line_number, line in enumerate(text.splitlines(), 1):
                if DESTRUCTIVE_PATTERN.search(line) and not any(word in line for word in NEGATION_WORDS):
                    errors.append(_finding("UNAUTHORIZED_DESTRUCTIVE_ACTION", name, f"第{line_number}行可能自动执行高影响操作", skill_path))

    if len(plugins) != 5:
        errors.append(_finding("PLUGIN_COUNT_DRIFT", "suite", f"期望5个插件，实际{len(plugins)}"))
    if len(versions) != 1:
        errors.append(_finding("PLUGIN_VERSION_DRIFT", "suite", f"插件版本不一致：{sorted(versions)}"))

    registry_path = root / "plugins" / "ai-engineering-core" / "references" / "SKILL_REGISTRY.json"
    registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = registry_document.get("skills", {})
    registry_files = sorted(root.rglob("SKILL_REGISTRY.json"))
    if registry_document.get("authority") != "SINGLE_CAPABILITY_METADATA_AUTHORITY" or registry_files != [registry_path]:
        errors.append(_finding(
            "CAPABILITY_AUTHORITY_CONFLICT", "suite",
            f"Capability Metadata Authority必须唯一，实际{[path.relative_to(root).as_posix() for path in registry_files]}",
            registry_path,
        ))
    if (root / "plugins" / "ai-engineering-core" / "references" / "capability-registry.json").exists():
        errors.append(_finding("DUPLICATE_CAPABILITY_CATALOG", "suite", "旧Capability Catalog仍然存在", registry_path))
    if set(registry) != set(records):
        errors.append(_finding("REGISTRY_DRIFT", "suite", f"目录缺失{sorted(set(registry)-set(records))}，登记缺失{sorted(set(records)-set(registry))}", registry_path))
    for name, record in records.items():
        contract = registry.get(name) or {}
        if contract.get("plugin") != record["plugin"]:
            errors.append(_finding("PLUGIN_OWNERSHIP_CONFLICT", name, "注册表插件归属与实际目录不一致", registry_path))
        mode = str(contract.get("mode") or "")
        if mode not in ALLOWED_MODES:
            errors.append(_finding("INVALID_SKILL_MODE", name, f"未知职责类型：{mode}", registry_path))
        for field in ("capability", "domain"):
            if field not in contract:
                errors.append(_finding("INCOMPLETE_CAPABILITY_METADATA", name, f"缺少唯一注册表字段：{field}", registry_path))
        for field in ("families", "stages", "surfaces", "specializations"):
            if field in contract and not isinstance(contract.get(field), list):
                errors.append(_finding("INVALID_CAPABILITY_METADATA", name, f"唯一注册表字段必须是数组：{field}", registry_path))
        may_modify = bool(contract.get("may_modify_source"))
        if mode == "implementation" and not may_modify:
            errors.append(_finding("IMPLEMENTATION_PERMISSION_CONFLICT", name, "实现 Skill 未声明源码修改权限", registry_path))
        if mode in {"router", "planning", "design", "review"} and may_modify:
            errors.append(_finding("READ_ONLY_PERMISSION_CONFLICT", name, f"{mode} Skill 不应拥有源码修改权限", registry_path))
        if contract.get("independence_requirement") == "INDEPENDENT_REVIEW" and "只读" not in record["text"]:
            errors.append(_finding("REVIEW_NOT_INDEPENDENT", name, "独立审核 Skill 未明确只读边界", record["path"]))

    architecture_challenge = records.get("architecture-decision-challenge")
    if architecture_challenge:
        architecture_text = architecture_challenge["text"]
        required_concepts = {
            "USER_IDEA_NOT_APPROVED": "待验证假设",
            "MISSING_COUNTEREXAMPLE": "反例",
            "MISSING_ALTERNATIVES": "替代方案",
            "MISSING_AUTOMATIC_CHECKPOINT": "自动生成决策 Checkpoint",
            "MISSING_NON_BLOCKING_DECISION": "不得弹出审批",
            "MISSING_READ_ONLY_BOUNDARY": "不直接修改",
            "MISSING_BOUNDED_DEPTH": "无边界过度设计",
        }
        for code, token in required_concepts.items():
            if token not in architecture_text:
                errors.append(_finding(code, "architecture-decision-challenge", f"缺少架构挑战边界：{token}", architecture_challenge["path"]))

    non_blocking_decision_files = {
        "global-governance": ROOT / "templates" / "GLOBAL_AGENTS_AI_ENGINEERING.md",
        "greenfield-project-planning": ROOT / "plugins" / "ai-engineering-core" / "skills" / "greenfield-project-planning" / "SKILL.md",
        "architecture-decision-challenge": ROOT / "plugins" / "ai-engineering-core" / "skills" / "architecture-decision-challenge" / "SKILL.md",
        "brownfield-requirement-reconciliation": ROOT / "plugins" / "ai-engineering-core" / "skills" / "brownfield-requirement-reconciliation" / "SKILL.md",
    }
    forbidden_approval_phrases = ("人工 Checkpoint", "人工Checkpoint", "批准后才锁定", "Checkpoint通过前")
    for owner, path in non_blocking_decision_files.items():
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        for phrase in forbidden_approval_phrases:
            if phrase in text:
                errors.append(_finding("BLOCKING_DECISION_APPROVAL", owner, f"决策 Checkpoint 不得要求人工审批：{phrase}", path))

    convergence = records.get("long-chain-change-convergence")
    if convergence:
        for token in ("治理进展", "业务价值进展", "一个机器可写事实源", "证据指纹 + 影响范围", "INVALID"):
            if token not in convergence["text"]:
                errors.append(_finding("CONVERGENCE_GOVERNANCE_DRIFT", "long-chain-change-convergence", f"缺少治理收敛契约：{token}", convergence["path"]))
    governance = records.get("multi-agent-project-governance")
    if governance:
        for token in ("SETUP_PENDING", "project_id + repo root + execution family", "IDLE_REUSABLE", "ARCHIVED_RUNTIME_UNVERIFIED", "业务价值进度", "派生视图"):
            if token not in governance["text"]:
                errors.append(_finding("MULTI_AGENT_BINDING_DRIFT", "multi-agent-project-governance", f"缺少多会话防重契约：{token}", governance["path"]))

    implicit = sorted(name for name, record in records.items() if record["implicit"] == "true")
    if implicit != ["ai-engineering-router"]:
        errors.append(_finding("IMPLICIT_ROUTER_CONFLICT", "suite", f"隐式入口必须且只能是智能工程轻量路由，实际{implicit}"))

    try:
        router_path = root / "plugins" / "ai-engineering-core" / "scripts" / "suite_router.py"
        router_text = router_path.read_text(encoding="utf-8")
        for token in (
            '"max_loaded_atomic_skills": 2', '"router_counts_toward_limit": False', '"deferred":',
            '"routing_authority": "chatgpt-semantic-selection"',
            '"guard_role": "constraints-and-evidence-only"',
        ):
            if token not in router_text:
                errors.append(_finding("ROUTER_BOUNDED_LOADING_DRIFT", "ai-engineering-router", f"缺少路由有界加载契约：{token}", router_path))
        for forbidden in ("ACTION_TERMS =", "classify_intent(", "explicit_bs =", "explicit_cs =", "plugin_engineering ="):
            if forbidden in router_text:
                errors.append(_finding("KEYWORD_ROUTING_AUTHORITY", "ai-engineering-router", f"守门器仍在按关键词替代模型选择：{forbidden}", router_path))
        workspace_router_path = root / "plugins" / "ai-engineering-workspace" / "scripts" / "task_router.py"
        workspace_router_text = workspace_router_path.read_text(encoding="utf-8")
        for token in ("chatgpt-semantic-selection", "PROPOSAL_REQUIRED", "constraints-and-workflow-expansion-only"):
            if token not in workspace_router_text:
                errors.append(_finding("WORKSPACE_ROUTER_MODEL_AUTHORITY_DRIFT", "workspace-task-router", f"缺少模型选择与脚本守门契约：{token}", workspace_router_path))
        for forbidden in ("explicit_bs =", "explicit_cs =", "explicit_backend =", "request_families ="):
            if forbidden in workspace_router_text:
                errors.append(_finding("WORKSPACE_KEYWORD_ROUTING_AUTHORITY", "workspace-task-router", f"工作区守门器仍在按关键词替代模型选择：{forbidden}", workspace_router_path))
        for forbidden in (
            "PLUGIN_FOR = {", "DESIGN_SKILLS =", "IMPLEMENTATION_SKILLS =", "WEB_SKILLS =",
            "BACKEND_SKILLS =", "CLIENT_SKILLS =", "SOURCE_CONFLICT_SAFE =",
            "AI_STATE_DEPENDENT_SKILLS =", "VERSION_RECOVERY_SKILLS =",
        ):
            if forbidden in router_text:
                errors.append(_finding("DUPLICATE_STATIC_MAPPING", "ai-engineering-router", f"Router仍包含重复映射：{forbidden}", router_path))
        mapping = {
            name: str(contract.get("plugin") or "")
            for name, contract in registry.items()
            if bool(contract.get("routable", True))
        }
        expected_routable = {name for name, contract in registry.items() if bool(contract.get("routable", True))}
        if set(mapping) != expected_routable:
            errors.append(_finding("ROUTER_COVERAGE_DRIFT", "suite", f"缺少{sorted(expected_routable-set(mapping))}，多余{sorted(set(mapping)-expected_routable)}"))
        for name, plugin in mapping.items():
            if name in records and records[name]["plugin"] != plugin:
                errors.append(_finding("ROUTER_PLUGIN_CONFLICT", name, f"路由映射到 {plugin}，实际属于 {records[name]['plugin']}"))
        catalog_path = root / "plugins" / "ai-engineering-core" / "references" / "semantic-routing-catalog.md"
        catalog_text = catalog_path.read_text(encoding="utf-8")
        catalog_skills = set(re.findall(r"`([a-z0-9][a-z0-9-]+)`｜", catalog_text))
        if catalog_skills != expected_routable:
            errors.append(_finding(
                "SEMANTIC_CATALOG_DRIFT", "ai-engineering-router",
                f"语义目录缺少{sorted(expected_routable-catalog_skills)}，多余{sorted(catalog_skills-expected_routable)}",
                catalog_path,
            ))
    except (OSError, RuntimeError, SyntaxError, ValueError) as exc:
        errors.append(_finding("ROUTER_MAPPING_INVALID", "suite", str(exc)))

    positive_eval: set[str] = set()
    for csv_path in sorted((root / "plugins").glob("*/evals/prompts.csv")):
        with csv_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("should_trigger", "")).lower() == "true":
                    positive_eval.add(str(row.get("skill") or ""))
    missing_eval = (set(records) - {"ai-engineering-router"}) - positive_eval
    if missing_eval:
        errors.append(_finding("MISSING_POSITIVE_EVAL", "suite", f"缺少正向路由样例：{sorted(missing_eval)}"))

    for left, right in itertools.combinations(records.values(), 2):
        a = _trigrams(str(left["description"])); b = _trigrams(str(right["description"]))
        similarity = len(a & b) / max(1, len(a | b))
        if similarity >= 0.72:
            errors.append(_finding("AMBIGUOUS_TRIGGER_OVERLAP", str(left["path"].parent.name), f"与 {right['path'].parent.name} 的触发描述过度相似：{similarity:.3f}"))
        elif similarity >= 0.55:
            warnings.append(_finding("TRIGGER_OVERLAP_REVIEW", str(left["path"].parent.name), f"与 {right['path'].parent.name} 的触发描述相似：{similarity:.3f}"))

    specialization_maturity = audit_specialization_maturity(root)
    for item in specialization_maturity["errors"]:
        errors.append(_finding(
            "SPECIALIZATION_MATURITY_" + item["code"], item.get("profile", "suite"),
            item["message"], root / item["path"] if item.get("path") else None,
        ))

    categories = {
        "structure": sum(item["code"] in {"PLUGIN_COUNT_DRIFT", "PLUGIN_VERSION_DRIFT", "SKILL_NAME_MISMATCH", "REGISTRY_DRIFT", "BROKEN_LOCAL_REFERENCE"} for item in errors),
        "routing": sum("ROUTER" in item["code"] or "EVAL" in item["code"] or "TRIGGER" in item["code"] for item in errors),
        "ownership": sum("MODE" in item["code"] or "OWNERSHIP" in item["code"] for item in errors),
        "permissions": sum("PERMISSION" in item["code"] or "DESTRUCTIVE" in item["code"] or "INDEPENDENT" in item["code"] for item in errors),
        "usability": sum("PROMPT" in item["code"] or "DISPLAY" in item["code"] or "DESCRIPTION" in item["code"] for item in errors),
        "performance": sum("TOO_LARGE" in item["code"] or "DESKTOP_" in item["code"] for item in errors),
    }
    return {
        "ok": not errors,
        "plugin_count": len(plugins),
        "skill_count": len(records),
        "audited_skills": sorted(records),
        "checks": categories,
        "errors": errors,
        "warnings": warnings,
        "specialization_maturity": specialization_maturity,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="审核五个工程插件全部 Skill 的一致性、边界和路由契约")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    result = audit(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
