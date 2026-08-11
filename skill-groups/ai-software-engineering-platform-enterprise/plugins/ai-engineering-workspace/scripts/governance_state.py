from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, read_json, repo_root, run, safe_id, state_lock

SCHEMA = "2.0.0"
TASK_STATES = ["Created", "Planning", "Development", "Review", "Testing", "Merged", "Released"]
TRANSITIONS = {
    "Created": {"Planning"},
    "Planning": {"Development"},
    "Development": {"Review"},
    "Review": {"Development", "Testing"},
    "Testing": {"Development", "Merged"},
    "Merged": {"Released"},
    "Released": set(),
}
ROLE_TARGETS = {
    "Planning": {"Master Agent", "Planning Agent"},
    "Development": {"Master Agent", "Planning Agent", "Developer Agent", "Review Agent", "Test Agent"},
    "Review": {"Master Agent", "Developer Agent"},
    "Testing": {"Master Agent", "Review Agent", "Test Agent"},
    "Merged": {"Master Agent", "Merge Agent"},
    "Released": {"Master Agent", "Merge Agent"},
}
MANAGED_START = "<!-- AI-GOVERNANCE:START -->"
MANAGED_END = "<!-- AI-GOVERNANCE:END -->"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_snapshot(root: Path) -> dict[str, Any]:
    branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "DETACHED"
    head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
    dirty = run(["git", "status", "--porcelain"], root, check=False).stdout.splitlines()
    return {"branch": branch, "head": head, "dirty": dirty}


def state_file(root: Path) -> Path:
    return root / ".ai" / "governance" / "project-state.json"


def task_file(root: Path, task_id: str) -> Path:
    return root / ".ai" / "tasks" / f"{safe_id(task_id)}.json"


def load_project(root: Path) -> dict[str, Any]:
    data = read_json(state_file(root), {}) or {}
    if not data:
        raise RuntimeError("project governance is not initialized; run init first")
    return data


def load_task(root: Path, task_id: str) -> dict[str, Any]:
    data = read_json(task_file(root, task_id), {}) or {}
    if not data:
        raise RuntimeError(f"unknown task: {task_id}")
    return data


def save_task(root: Path, task: dict[str, Any]) -> None:
    task["updated_at"] = now()
    atomic_json(task_file(root, str(task["task_id"])), task)


def all_tasks(root: Path) -> list[dict[str, Any]]:
    folder = root / ".ai" / "tasks"
    return [read_json(path, {}) or {} for path in sorted(folder.glob("*.json"))] if folder.exists() else []


def managed_write(path: Path, title: str, body: str) -> None:
    block = f"{MANAGED_START}\n{body.rstrip()}\n{MANAGED_END}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.S)
        updated = pattern.sub(block, text) if pattern.search(text) else text.rstrip() + "\n\n" + block + "\n"
    else:
        updated = f"# {title}\n\n{block}\n"
    path.write_text(updated, encoding="utf-8", newline="\n")


def bullets(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] or ["- 无"]


def render_project_state(root: Path, project: dict[str, Any]) -> None:
    tasks = all_tasks(root)
    completed = [f"{t.get('task_id')}：{t.get('goal')}（{t.get('state')}）" for t in tasks if t.get("state") in {"Merged", "Released"}]
    developing = [f"{t.get('task_id')}：{t.get('goal')}（{t.get('state')} / {t.get('control_status')}）" for t in tasks if t.get("state") not in {"Merged", "Released"}]
    pending = list(project.get("pending_issues", []))
    risks = list(project.get("risks", []))
    git = git_snapshot(root)
    lines = [
        "## 当前版本", f"- {project.get('version') or '未设置'}", "",
        "## 当前分支", f"- {git['branch']}", "",
        "## 已完成功能", *bullets(completed), "",
        "## 开发中功能", *bullets(developing), "",
        "## 待处理问题", *bullets(pending), "",
        "## 数据库版本", f"- {project.get('database_version') or '未设置'}", "",
        "## API版本", f"- {project.get('api_version') or '未设置'}", "",
        "## 风险列表", *bullets(risks), "",
        "## 项目标识", f"- Project ID：{project.get('project_id')}", f"- Architecture：{project.get('architecture')}",
        f"- Git HEAD：{git['head'] or '无'}", f"- 更新时间：{now()}",
    ]
    managed_write(root / "PROJECT_STATE.md", "项目状态", "\n".join(lines))


def render_context(root: Path, task: dict[str, Any] | None) -> None:
    if not task:
        managed_write(root / "CURRENT_CONTEXT.md", "当前上下文", "当前没有活动任务。")
        return
    lines = [
        "## 当前目标", f"- {task.get('goal') or '未设置'}", "",
        "## 当前任务", f"- Task ID：{task.get('task_id')}", f"- 状态：{task.get('state')} / {task.get('control_status')}",
        f"- 负责人：{task.get('owner_agent')}", f"- 分支：{task.get('branch')}", "",
        "## 已完成修改", *bullets(task.get("completed_changes", [])), "",
        "## 未完成事项", *bullets(task.get("pending_items", [])), "",
        "## 关键决定", *bullets(task.get("decisions", [])), "",
        "## 禁止事项", *bullets(task.get("prohibitions", [])), "",
        "## 影响文件", *bullets(task.get("affected_files", [])), "",
        f"- 更新时间：{now()}",
    ]
    managed_write(root / "CURRENT_CONTEXT.md", "当前上下文", "\n".join(lines))


def ensure_supporting_docs(root: Path, architecture: str) -> None:
    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text("# Changelog\n\n## Unreleased\n\n- 初始化工程变更记录。\n", encoding="utf-8", newline="\n")
    architecture_file = root / "ARCHITECTURE.md"
    if not architecture_file.exists():
        frontend = "B/S Web 前端" if architecture == "bs" else "C/S 客户端" if architecture == "cs" else "B/S Web 前端与 C/S 客户端"
        architecture_file.write_text(
            "# Architecture\n\n"
            "## 系统边界\n\n- 待 Planning Agent 完成边界确认。\n\n"
            f"## 前端/客户端\n\n- {frontend}\n\n"
            "## 后端服务\n\n- API、领域服务、鉴权、任务与集成边界。\n\n"
            "## 数据与契约\n\n- 数据库版本、迁移、API/事件契约和兼容策略。\n\n"
            "## 部署与发布\n\n- 环境、构建、迁移、回滚和观测。\n",
            encoding="utf-8", newline="\n")


def init_project(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(root)
    existing = read_json(state_file(root), {}) or {}
    project = {
        "schema_version": SCHEMA,
        "project_id": safe_id(args.project_id),
        "architecture": args.architecture,
        "version": args.version,
        "database_version": args.database_version,
        "api_version": args.api_version,
        "pending_issues": existing.get("pending_issues", []),
        "risks": existing.get("risks", []),
        "created_at": existing.get("created_at", now()),
        "updated_at": now(),
    }
    atomic_json(state_file(root), project)
    (root / ".ai" / "tasks").mkdir(parents=True, exist_ok=True)
    (root / ".ai" / "runtime" / "checkpoints").mkdir(parents=True, exist_ok=True)
    ensure_supporting_docs(root, args.architecture)
    render_project_state(root, project)
    render_context(root, None)
    return project


def create_task(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    project = load_project(root)
    task_id = safe_id(args.task_id).upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d{3,}", task_id):
        raise RuntimeError("task id must look like KG-001")
    path = task_file(root, task_id)
    if path.exists():
        raise RuntimeError(f"task already exists: {task_id}")
    if args.branch in {"main", "develop", "release"}:
        raise RuntimeError("feature task cannot write a protected branch")
    task = {
        "schema_version": SCHEMA,
        "project_id": project["project_id"],
        "task_id": task_id,
        "goal": args.goal,
        "state": "Created",
        "control_status": "ACTIVE",
        "owner_agent": args.owner_agent,
        "branch": args.branch,
        "base_branch": args.base_branch,
        "affected_files": args.affected_files or [],
        "dependencies": getattr(args, "dependencies", None) or [],
        "commits": [],
        "review": {"status": "PENDING", "records": []},
        "tests": {"status": "PENDING", "records": []},
        "artifacts": [],
        "documents": [],
        "decisions": [],
        "prohibitions": ["Developer Agent 不得直接修改 main、develop 或 release", "不得修改未授权或被其他任务锁定的文件"],
        "completed_changes": [],
        "pending_items": [],
        "risks": [],
        "closure": {"merge": "PENDING", "release": "PENDING"},
        "release": {"status": "PENDING", "records": []},
        "history": [{"at": now(), "event": "CREATED", "agent_role": args.owner_agent}],
        "created_at": now(),
        "updated_at": now(),
    }
    save_task(root, task)
    render_project_state(root, project)
    render_context(root, task)
    return task


def transition(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    current, target = task["state"], args.to
    if target not in TRANSITIONS.get(current, set()):
        raise RuntimeError(f"invalid transition: {current} -> {target}")
    if args.agent_role not in ROLE_TARGETS[target]:
        raise RuntimeError(f"{args.agent_role} cannot transition a task to {target}")
    if task.get("control_status") == "PAUSED":
        raise RuntimeError("paused task must be resumed before transition")
    if target == "Review" and not task.get("commits"):
        raise RuntimeError("Development -> Review requires at least one commit")
    if target == "Testing" and task.get("review", {}).get("status") != "PASS":
        raise RuntimeError("Review -> Testing requires Review Agent PASS evidence")
    if target == "Merged":
        if task.get("tests", {}).get("status") != "PASS" or task.get("closure", {}).get("merge") != "PASS":
            raise RuntimeError("Testing -> Merged requires tests PASS and merge closure PASS")
        if not args.commit_id:
            raise RuntimeError("Merged transition requires merge commit id")
        task["merge_commit"] = args.commit_id
    if target == "Released" and task.get("release", {}).get("status") != "PASS":
        raise RuntimeError("Merged -> Released requires release evidence PASS")
    task["state"] = target
    task["history"].append({"at": now(), "event": f"STATE:{current}->{target}", "agent_role": args.agent_role, "commit_id": args.commit_id})
    save_task(root, task)
    project = load_project(root); project["updated_at"] = now(); atomic_json(state_file(root), project)
    render_project_state(root, project); render_context(root, task)
    return task


def record(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    item = {"at": now(), "value": args.value, "status": args.status, "command": args.command, "reason": args.reason}
    if args.kind == "commit":
        task["commits"].append(args.value)
    elif args.kind in {"review", "test", "release"}:
        key = "tests" if args.kind == "test" else args.kind
        task[key]["status"] = args.status or "RECORDED"; task[key]["records"].append(item)
    elif args.kind == "artifact": task["artifacts"].append(item)
    elif args.kind == "document": task["documents"].append(item)
    elif args.kind == "decision": task["decisions"].append(args.value)
    elif args.kind == "prohibition": task["prohibitions"].append(args.value)
    elif args.kind == "risk": task["risks"].append(args.value)
    elif args.kind == "completed": task["completed_changes"].append(args.value)
    elif args.kind == "pending": task["pending_items"].append(args.value)
    else: raise RuntimeError(f"unsupported record kind: {args.kind}")
    task["history"].append({"at": now(), "event": f"RECORD:{args.kind}", "agent_role": args.agent_role})
    save_task(root, task); render_context(root, task); render_project_state(root, load_project(root))
    return task


def checkpoint(root: Path, task: dict[str, Any], label: str) -> Path:
    git = git_snapshot(root)
    data = {"schema_version": SCHEMA, "created_at": now(), "label": label, "task": task, "git": git}
    stamp = now().replace(":", "-")
    path = root / ".ai" / "runtime" / "checkpoints" / f"{stamp}-{safe_id(task['task_id'])}-{safe_id(label)}.json"
    atomic_json(path, data); render_context(root, task)
    return path


def control(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    if args.action == "pause": task["control_status"] = "PAUSED"
    elif args.action == "resume": task["control_status"] = "ACTIVE"
    elif args.action == "adjust":
        task["control_status"] = "ADJUSTING"; task["pending_items"].append(f"方向调整：{args.instruction}")
    elif args.action == "insert":
        if not args.new_task_id or not args.branch or not args.instruction:
            raise RuntimeError("insert requires --new-task-id, --branch and --instruction")
        task["pending_items"].append(f"插入需求 {args.new_task_id}：{args.instruction}")
    task["history"].append({"at": now(), "event": f"CONTROL:{args.action}", "instruction": args.instruction, "agent_role": "Master Agent"})
    save_task(root, task); path = checkpoint(root, task, args.action)
    if args.action == "insert":
        inserted = create_task(root, argparse.Namespace(task_id=args.new_task_id, goal=args.instruction, owner_agent="Planning Agent", branch=args.branch, base_branch=args.base_branch, affected_files=[], dependencies=[task["task_id"]]))
        inserted["history"].append({"at": now(), "event": "INSERTED", "agent_role": "Master Agent", "parent_task": task["task_id"]}); save_task(root, inserted); render_context(root, inserted)
        return {"task": task, "inserted_task": inserted, "checkpoint": str(path)}
    return {"task": task, "checkpoint": str(path)}


def validate(root: Path) -> dict[str, Any]:
    required = ["PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md", ".ai/governance/project-state.json"]
    missing = [name for name in required if not (root / name).exists()]
    issues = []
    for task in all_tasks(root):
        if task.get("state") not in TASK_STATES: issues.append(f"{task.get('task_id')}: invalid state")
        if task.get("project_id") != (read_json(state_file(root), {}) or {}).get("project_id"): issues.append(f"{task.get('task_id')}: project context mismatch")
    git = git_snapshot(root)
    active = [t for t in all_tasks(root) if t.get("state") == "Development" and t.get("control_status") == "ACTIVE"]
    if active and git["branch"] in {"main", "develop", "release"}: issues.append("active development task is on a protected branch")
    return {"ok": not missing and not issues, "schema_version": SCHEMA, "missing": missing, "issues": issues, "git": git, "task_count": len(all_tasks(root))}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--project-id", required=True); p.add_argument("--architecture", choices=["bs", "cs", "hybrid"], required=True); p.add_argument("--version", default="0.1.0"); p.add_argument("--database-version", default="unversioned"); p.add_argument("--api-version", default="v1")
    p = sub.add_parser("task-create"); p.add_argument("--task-id", required=True); p.add_argument("--goal", required=True); p.add_argument("--owner-agent", default="Master Agent"); p.add_argument("--branch", required=True); p.add_argument("--base-branch", default="develop"); p.add_argument("--affected-files", nargs="*")
    p = sub.add_parser("transition"); p.add_argument("--task-id", required=True); p.add_argument("--to", choices=TASK_STATES, required=True); p.add_argument("--agent-role", required=True); p.add_argument("--commit-id")
    p = sub.add_parser("record"); p.add_argument("--task-id", required=True); p.add_argument("--kind", choices=["commit", "review", "test", "artifact", "document", "decision", "prohibition", "risk", "completed", "pending", "release"], required=True); p.add_argument("--value", required=True); p.add_argument("--status"); p.add_argument("--command"); p.add_argument("--reason"); p.add_argument("--agent-role", required=True)
    p = sub.add_parser("checkpoint"); p.add_argument("--task-id", required=True); p.add_argument("--label", required=True)
    p = sub.add_parser("control"); p.add_argument("--task-id", required=True); p.add_argument("--action", choices=["pause", "resume", "adjust", "insert"], required=True); p.add_argument("--instruction", default=""); p.add_argument("--new-task-id"); p.add_argument("--branch"); p.add_argument("--base-branch", default="develop")
    p = sub.add_parser("status"); p.add_argument("--task-id")
    sub.add_parser("validate")
    args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        with state_lock(root):
            if args.cmd == "init": data = init_project(root, args)
            elif args.cmd == "task-create": data = create_task(root, args)
            elif args.cmd == "transition": data = transition(root, args)
            elif args.cmd == "record": data = record(root, args)
            elif args.cmd == "checkpoint": data = {"path": str(checkpoint(root, load_task(root, args.task_id), args.label))}
            elif args.cmd == "control": data = control(root, args)
            elif args.cmd == "status": data = {"project": load_project(root), "task": load_task(root, args.task_id) if args.task_id else None, "tasks": all_tasks(root), "git": git_snapshot(root)}
            else: data = validate(root)
        print(json.dumps({"ok": data.get("ok", True) if isinstance(data, dict) else True, "result": data}, ensure_ascii=False, indent=2))
        return 0 if args.cmd != "validate" or data["ok"] else 2
    except (RuntimeError, ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
