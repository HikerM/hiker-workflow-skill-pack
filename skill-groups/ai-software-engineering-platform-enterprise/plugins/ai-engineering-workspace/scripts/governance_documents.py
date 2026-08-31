from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bounded_context import bounded_bullets, crop, ensure_policy, limit_text
from goal_contract import ensure_contract as ensure_goal_contract
from workspacelib import atomic_json, read_json, run, safe_id


MANAGED_START = "<!-- AI-GOVERNANCE:START -->"
MANAGED_END = "<!-- AI-GOVERNANCE:END -->"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_snapshot(root: Path) -> dict[str, Any]:
    branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "DETACHED"
    head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
    return {"branch": branch, "head": head}


def _task_index(root: Path) -> dict[str, Any]:
    return read_json(root / ".ai" / "governance" / "task-index.json", {}) or {}


def managed_write(path: Path, title: str, body: str) -> None:
    block = f"{MANAGED_START}\n{body.rstrip()}\n{MANAGED_END}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.S)
        updated = pattern.sub(block, text) if pattern.search(text) else text.rstrip() + "\n\n" + block + "\n"
    else:
        updated = f"# {title}\n\n{block}\n"
    path.write_text(updated, encoding="utf-8", newline="\n")


def _bullets(values: list[str], limit: int = 20, source: str = ".ai/tasks/") -> list[str]:
    return bounded_bullets(values, limit, source)


def render_project_state(root: Path, project: dict[str, Any]) -> None:
    index = _task_index(root)
    tasks = index.get("tasks", []) if isinstance(index.get("tasks"), list) else []
    completed = [f"{t.get('task_id')}：{t.get('goal')}（{t.get('state')}）" for t in tasks if t.get("state") in {"Merged", "Released"}]
    developing = [f"{t.get('task_id')}：{t.get('goal')}（{t.get('state')} / {t.get('control_status')}）" for t in tasks if t.get("state") not in {"Merged", "Released"}]
    git = _git_snapshot(root)
    lines = [
        "## 当前版本", f"- {project.get('version') or '未设置'}", "",
        "## 当前分支", f"- {git['branch']}", "",
        "## 已完成功能", *_bullets(completed, 20, ".ai/tasks/"), "",
        "## 开发中功能", *_bullets(developing, 20, ".ai/tasks/"), "",
        "## 待处理问题", *_bullets(list(project.get("pending_issues", [])), 20, ".ai/governance/project-state.json"), "",
        "## 数据库版本", f"- {project.get('database_version') or '未设置'}", "",
        "## API版本", f"- {project.get('api_version') or '未设置'}", "",
        "## 风险列表", *_bullets(list(project.get("risks", [])), 20, ".ai/governance/project-state.json"), "",
        "## 项目标识", f"- Project ID：{project.get('project_id')}", f"- Architecture：{project.get('architecture')}",
        f"- Git HEAD：{git['head'] or '无'}", f"- 已收敛历史任务索引：{index.get('compacted_closed_count', 0)}（完整事实仍在 `.ai/tasks/`）", f"- 更新时间：{_now()}",
    ]
    managed_write(root / "PROJECT_STATE.md", "项目状态", "\n".join(lines))


def _task_context_body(root: Path, task: dict[str, Any]) -> str:
    policy = ensure_policy(root)
    section_limit = policy["max_items_per_section"]
    source = f".ai/tasks/{safe_id(str(task.get('task_id')))}.json"
    binding = task.get("goal_binding") or {}
    lines = [
        "## 当前目标", f"- {crop(task.get('goal') or '未设置')}",
        f"- 目标绑定：{binding.get('goal_id') or '未设置'} r{binding.get('revision') or 0} / {str(binding.get('fingerprint') or '')[:12]}", "",
        "## 当前任务", f"- Task ID：{task.get('task_id')}", f"- 状态：{task.get('state')} / {task.get('control_status')}",
        f"- 负责人：{task.get('owner_agent')}", f"- 所有权通道：{task.get('ownership_lane') or 'default'}", f"- 分支：{task.get('branch')}", "",
        "## 已完成修改", *_bullets(task.get("completed_changes", []), section_limit, source), "",
        "## 未完成事项", *_bullets(task.get("pending_items", []), section_limit, source), "",
        "## 关键决定", *_bullets(task.get("decisions", []), section_limit, source), "",
        "## 禁止事项", *_bullets(task.get("prohibitions", []), section_limit, source), "",
        "## 影响文件", *_bullets(task.get("affected_files", []), section_limit, source), "",
        "## 上下文策略", "- 本文件只服务绑定Task与所有权通道，不代表其他并行任务。",
        "- 完整任务事实保存在机器状态、Git和正式证据中。", "", f"- 更新时间：{_now()}",
    ]
    return limit_text("\n".join(lines), policy["active_context_max_chars"], source)


def render_master_context(root: Path) -> None:
    policy = ensure_policy(root)
    limit = policy["max_items_per_section"]
    summaries = [item for item in _task_index(root).get("tasks", []) if isinstance(item, dict) and item.get("state") not in {"Merged", "Released"}][:limit]
    goal = ensure_goal_contract(root)
    goal_text = goal.get("outcome") if goal.get("status") == "ACTIVE" else "项目级目标尚未锁定；各Task按自己的稳定目标指纹执行。"
    active = [f"{item.get('task_id')}｜{item.get('ownership_lane') or 'default'}｜{item.get('state')}｜{item.get('goal')}" for item in summaries]
    lines = [
        "## 当前目标", f"- {crop(goal_text)}", f"- 目标契约：{goal.get('goal_id') or 'UNSET'} r{goal.get('revision') or 0} / {str(goal.get('fingerprint') or '')[:12]}", "",
        "## 当前任务", *_bullets(active, limit, ".ai/governance/task-index.json"), "",
        "## 已完成修改", "- 由各Task上下文与证据索引提供；总控不注入完整实现日志。", "",
        "## 未完成事项", *_bullets([f"{item.get('task_id')}：{item.get('state')}" for item in summaries], limit, ".ai/governance/task-index.json"), "",
        "## 关键决定", "- 读取锁定决定与当前目标契约，不复制完整历史。", "",
        "## 禁止事项", "- 不跨Task或所有权通道写文件；不以治理进展冒充业务进展；不把完整工具日志注入总控。", "",
        "## 上下文策略", "- 本文件是总控摘要。执行角色必须读取 `.ai/runtime/task-contexts/<Task-ID>.md`。",
        "- 新会话按项目身份 → 目标契约 → 绑定Task → Git → 证据 → checkpoint恢复。", "", f"- 更新时间：{_now()}",
    ]
    managed_write(root / "CURRENT_CONTEXT.md", "当前上下文", limit_text("\n".join(lines), policy["active_context_max_chars"], ".ai/"))


def render_context(root: Path, task: dict[str, Any] | None) -> None:
    if task:
        path = root / ".ai" / "runtime" / "task-contexts" / f"{safe_id(str(task.get('task_id')))}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 任务上下文\n\n" + _task_context_body(root, task) + "\n", encoding="utf-8", newline="\n")
    render_master_context(root)


def ensure_supporting_docs(root: Path, architecture: str) -> None:
    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text("# Changelog\n\n## Unreleased\n\n- 初始化工程变更记录。\n", encoding="utf-8", newline="\n")
    architecture_file = root / "ARCHITECTURE.md"
    if not architecture_file.exists():
        frontend = "B/S Web 前端" if architecture == "bs" else "C/S 客户端" if architecture == "cs" else "B/S Web 前端与 C/S 客户端"
        architecture_file.write_text(
            "# Architecture\n\n## 系统边界\n\n- 待当前模型提出边界并由 CONTROL responsibility 记录。\n\n"
            f"## 前端/客户端\n\n- {frontend}\n\n"
            "## 后端服务\n\n- API、领域服务、鉴权、任务与集成边界。\n\n"
            "## 数据与契约\n\n- 数据库版本、迁移、API/事件契约和兼容策略。\n\n"
            "## 部署与发布\n\n- 环境、构建、迁移、回滚和观测。\n",
            encoding="utf-8", newline="\n",
        )
    architecture_dir = root / ".ai" / "architecture"
    architecture_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "module-registry.json": {"schema_version": "1.0.0", "mode": "auto-discovery", "modules": [], "note": "零配置时按目录和依赖自动识别；仅为受保护或边界敏感模块补充显式条目。"},
        "dependency-rules.json": {"schema_version": "1.0.0", "mode": "advisory-until-configured", "rules": [], "note": "空规则不阻塞普通开发；发现跨层、循环或受保护边界风险时再渐进配置。"},
        "public-surface.json": {"schema_version": "1.0.0", "surfaces": [], "note": "只登记跨模块公共接口、协议、迁移和共享资产，避免全量登记造成配置耦合。"},
        "runtime-topology.json": {"schema_version": "1.0.0", "nodes": [], "edges": [], "note": "仅在运行时调用关系无法由源码和清单推断时补充。"},
    }
    for filename, payload in defaults.items():
        path = architecture_dir / filename
        if not path.exists():
            atomic_json(path, payload)
