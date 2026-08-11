from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from corelib import ai_root, atomic_write_json, atomic_write_text, ensure_schema, git_info, read_json, sha256_file, utc_now
from context_memory import bounded_items, crop, enforce_checkpoint_retention, ensure_memory_policy, limit_text, memory_status


def task_path(root: Path) -> Path: return ai_root(root) / "runtime" / "task.json"
def control_path(root: Path) -> Path: return ai_root(root) / "runtime" / "control.json"


def load_task(root: Path) -> dict:
    data = read_json(task_path(root), {})
    return data if isinstance(data, dict) else {}


def save_task(root: Path, task: dict) -> None:
    task["updated_at"] = utc_now(); atomic_write_json(task_path(root), task)


def update_active(root: Path, task: dict) -> None:
    policy = ensure_memory_policy(root); limit = policy["max_items_per_section"]
    source = ".ai/runtime/task.json"
    lines = ["# 当前有效上下文", "", f"- 任务：{crop(task.get('id') or '无', 120)}", f"- 目标：{crop(task.get('goal') or '无')}", f"- 状态：{task.get('status')}", f"- 计划版本：{task.get('plan_version', 0)}", f"- 允许范围：{crop(task.get('scope') or '未定义')}", "", "## 已完成"]
    lines += bounded_items(task.get("completed"), limit, source)
    lines += ["", "## 正在进行"] + bounded_items(task.get("working"), limit, source)
    lines += ["", "## 待处理"] + bounded_items(task.get("pending"), limit, source)
    lines += ["", "## 风险"] + bounded_items(task.get("risks"), limit, source)
    lines += ["", "## 恢复规则", "- 本文件是有界工作集，不是完整历史。", "- 事实恢复顺序：项目身份 → Task/决定 → Git → 文档 → 检查点 → 聊天摘要。"]
    text = limit_text("\n".join(lines), policy["active_context_max_chars"], source)
    atomic_write_text(ai_root(root) / "runtime" / "active-context.md", text)


def checkpoint(root: Path, label: str, event: str = "manual") -> Path:
    ai = ai_root(root); cp_dir = ai / "runtime" / "checkpoints"; cp_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "-")
    key_files = ["schema.json", "context/project.json", "context/tech-stack.json", "context/architecture.json", "context/standards.json", "runtime/task.json", "runtime/control.json", "runtime/active-context.md", "governance/locked-decisions.json", "governance/ownership.json", "governance/project-state.json", "governance/task-index.json", "architecture/module-registry.json", "architecture/dependency-rules.json", "architecture/public-surface.json", "workspace/task-map.json", "quality/policy.json", "knowledge/metadata.json", "evidence/index.json"]
    task_candidates = []
    for candidate in (ai / "tasks").glob("*.json") if (ai / "tasks").is_dir() else []:
        data = read_json(candidate, {})
        if data.get("state") not in {"Merged", "Released"}: task_candidates.append(candidate)
    for candidate in sorted(task_candidates, key=lambda p: p.stat().st_mtime_ns, reverse=True)[:5]:
        key_files.append(candidate.relative_to(ai).as_posix())
    key_files = list(dict.fromkeys(key_files))
    root_files = ["PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md"]
    snapshot = {"schema_version": "1.0.0", "created_at": utc_now(), "label": label, "event": event, "git": git_info(root), "files": {}}
    for rel in key_files:
        p = ai / rel
        snapshot["files"][rel] = {"exists": p.exists(), "sha256": sha256_file(p)}
    for rel in root_files:
        p = root / rel
        snapshot["files"][f"root/{rel}"] = {"exists": p.exists(), "sha256": sha256_file(p)}
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("._-")[:80] or "checkpoint"
    path = cp_dir / f"{stamp}-{safe_label}.json"
    atomic_write_json(path, snapshot)
    # Keep a copy of mutable state for recovery without copying source code.
    state_dir = cp_dir / (path.stem + "-state")
    state_dir.mkdir(parents=True, exist_ok=True)
    for rel in key_files:
        src = ai / rel
        if src.exists():
            dst = state_dir / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    for rel in root_files:
        src = root / rel
        if src.exists():
            dst = state_dir / "root" / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    enforce_checkpoint_retention(root)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("task-start"); p.add_argument("--id", required=True); p.add_argument("--goal", required=True); p.add_argument("--scope", default="current task module")
    sub.add_parser("status")
    p = sub.add_parser("pause"); p.add_argument("--reason", default="user interruption")
    sub.add_parser("resume")
    p = sub.add_parser("adjust"); p.add_argument("--instruction", required=True)
    p = sub.add_parser("checkpoint"); p.add_argument("--label", required=True)
    sub.add_parser("complete")
    sub.add_parser("validate")
    sub.add_parser("memory-status")
    p = sub.add_parser("lock-decision"); p.add_argument("--id", required=True); p.add_argument("--content", required=True); p.add_argument("--reason", required=True)
    args = ap.parse_args(); root = Path(args.root).resolve()
    ok, version = ensure_schema(root)
    if not ok and args.cmd != "validate": raise SystemExit(f"STATE_ERROR: {version}")
    task = load_task(root)
    if args.cmd == "task-start":
        task = {"schema_version": "1.0.0", "id": args.id, "goal": args.goal, "scope": args.scope, "status": "EXECUTING", "plan_version": 1, "completed": [], "working": ["分析并执行当前计划"], "pending": [], "risks": [], "updated_at": utc_now()}; save_task(root, task); update_active(root, task); checkpoint(root, "task-start")
    elif args.cmd == "status":
        print(json.dumps({"schema_ok": ok, "schema": version, "task": task, "git": git_info(root), "control": read_json(control_path(root), {})}, ensure_ascii=False, indent=2)); return 0
    elif args.cmd == "pause":
        task["status"] = "PAUSED"; task.setdefault("risks", []).append(f"暂停原因：{args.reason}"); save_task(root, task); update_active(root, task); checkpoint(root, "paused")
    elif args.cmd == "resume":
        task["status"] = "EXECUTING"; save_task(root, task); update_active(root, task); atomic_write_json(control_path(root), {"schema_version": "1.0.0", "requested_action": None, "request_text": None, "updated_at": utc_now()})
    elif args.cmd == "adjust":
        task["status"] = "REPLANNING"; task["plan_version"] = int(task.get("plan_version", 0)) + 1; task.setdefault("plan_changes", []).append({"at": utc_now(), "instruction": args.instruction}); save_task(root, task); update_active(root, task); checkpoint(root, f"before-plan-v{task['plan_version']}")
    elif args.cmd == "checkpoint": print(checkpoint(root, args.label)); return 0
    elif args.cmd == "complete": task["status"] = "COMPLETED"; save_task(root, task); update_active(root, task); checkpoint(root, "completed")
    elif args.cmd == "validate":
        required = ["context/project.json", "context/tech-stack.json", "runtime/task.json", "runtime/active-context.md", "governance/locked-decisions.json"]
        missing = [x for x in required if not (ai_root(root) / x).exists()]
        print(json.dumps({"ok": ok and not missing, "schema": version, "missing": missing, "git": git_info(root)}, ensure_ascii=False, indent=2)); return 0 if ok and not missing else 2
    elif args.cmd == "memory-status":
        print(json.dumps({"ok": True, "memory": memory_status(root)}, ensure_ascii=False, indent=2)); return 0
    elif args.cmd == "lock-decision":
        path = ai_root(root) / "governance" / "locked-decisions.json"; data = read_json(path, {"schema_version": "1.0.0", "decisions": []}); decisions = data.setdefault("decisions", [])
        if any(d.get("id") == args.id for d in decisions): raise SystemExit("decision id already exists")
        decisions.append({"id": args.id, "status": "LOCKED", "content": args.content, "reason": args.reason, "created_at": utc_now(), "superseded_by": None}); atomic_write_json(path, data)
    if args.cmd not in {"status", "validate", "checkpoint", "memory-status"}: print(json.dumps({"ok": True, "command": args.cmd, "task": load_task(root)}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
