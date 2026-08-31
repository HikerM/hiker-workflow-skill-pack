from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from workspacelib import atomic_json, common_dir, load_state, read_json, repo_root, run, safe_branch, safe_id, state_lock, state_path
from worktree_inventory import inventory
from task_router import execution_class_for

PROTECTED = {"main", "develop", "release"}
PREFIXES = ("feature/", "bugfix/", "hotfix/", "release/")


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def future(days: int): return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def worktree_list(root: Path) -> list[dict]:
    out = run(["git", "worktree", "list", "--porcelain"], root).stdout; items = []; cur = {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur: items.append(cur); cur = {}
            continue
        key, *rest = line.split(" ", 1); value = rest[0] if rest else True
        if key == "worktree": cur["path"] = value
        elif key == "HEAD": cur["head"] = value
        elif key == "branch": cur["branch"] = str(value).removeprefix("refs/heads/")
        elif key == "detached": cur["detached"] = True
        elif key == "locked": cur["locked"] = value
    return items


def branch_exists(root: Path, branch: str) -> bool: return run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], root, check=False).returncode == 0
def current_base(root: Path) -> str: return run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "HEAD"


def default_base(branch: str) -> str:
    if branch.startswith(("feature/", "bugfix/", "release/")): return "develop"
    if branch.startswith("hotfix/"): return "main"
    raise RuntimeError("worktree branch must use feature/*, bugfix/*, hotfix/*, or release/*")


def validate_branch_policy(root: Path, branch: str, base: str, agent_role: str) -> None:
    if branch in PROTECTED: raise RuntimeError("creating a task worktree on main/develop/release is forbidden")
    if not branch.startswith(PREFIXES): raise RuntimeError("invalid branch prefix")
    if branch.startswith("release/") and execution_class_for(agent_role) != "CONTROL": raise RuntimeError("CONTROL responsibility is required to create release/* worktrees")
    expected = default_base(branch)
    if base != expected: raise RuntimeError(f"{branch} must be based on {expected}")
    if not branch_exists(root, base): raise RuntimeError(f"required base branch does not exist: {base}")


def status_for(path: Path) -> dict:
    dirty = run(["git", "status", "--porcelain"], path).stdout.splitlines(); branch = run(["git", "branch", "--show-current"], path, check=False).stdout.strip() or "DETACHED"; head = run(["git", "rev-parse", "HEAD"], path).stdout.strip(); return {"path": str(path), "branch": branch, "head": head, "dirty": dirty}


def governance_task(root: Path, task: str) -> dict | None:
    state = read_json(root / ".ai" / "governance" / "project-state.json", {}) or {}
    if not state: raise RuntimeError("project governance is not initialized; create project state and task before a worktree")
    data = read_json(root / ".ai" / "tasks" / f"{task.upper()}.json", {}) or {}
    if not data: raise RuntimeError("governed projects require an existing task before worktree creation")
    if data.get("state") not in {"Planning", "Development"}: raise RuntimeError("task must be in Planning or Development")
    return data


def cmd_create(root: Path, a) -> dict:
    task = safe_id(a.task_id); branch = safe_branch(a.branch or f"feature/{task}"); base = a.base or default_base(branch); role = getattr(a, "agent_role", "Developer Agent")
    validate_branch_policy(root, branch, base, role)
    governed = governance_task(root, task)
    if governed and governed.get("branch") != branch: raise RuntimeError(f"task branch mismatch: expected {governed.get('branch')}")
    stock = inventory(root, "quick")
    if stock["summary"]["nested"]:
        raise RuntimeError("nested worktree detected inside the canonical repository; reconcile it before creating another worktree")
    if stock["summary"]["over_active_budget"]:
        raise RuntimeError(f"active worktree budget exceeded: {stock['summary']['active_managed']}/{stock['summary']['max_active_write_worktrees']}")
    default_parent = root.parent / f"{root.name}.ai-worktrees"; path = Path(a.path).expanduser().resolve() if a.path else (default_parent / task).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    worktree_id = "WT-" + hashlib.sha256(f"{root.resolve()}|{path}|{branch}".encode("utf-8")).hexdigest()[:16].upper()
    with state_lock(root):
        state = load_state(root)
        if task in state.get("worktrees", {}): raise RuntimeError(f"task already has worktree: {task}")
        if branch in state.get("leases", {}) and state["leases"][branch].get("status") in {"ACTIVE", "PAUSED"}: raise RuntimeError(f"branch already leased: {branch}")
        if path.exists() and any(path.iterdir()): raise RuntimeError(f"worktree path is not empty: {path}")
        if path in {Path(x["path"]).resolve() for x in worktree_list(root)}: raise RuntimeError("worktree already registered")
        cmd = ["git", "worktree", "add"] + ([str(path), branch] if branch_exists(root, branch) else ["-b", branch, str(path), base]); result = run(cmd, root)
        state.setdefault("worktrees", {})[task] = {"worktree_id": worktree_id, "task_id": task, "path": str(path), "branch": branch, "base": base, "agent_role": role, "status": "ACTIVE", "created_at": now(), "last_activity_at": now(), "lease_expires_at": future(14)}; state.setdefault("leases", {})[branch] = {"worktree_id": worktree_id, "task_id": task, "path": str(path), "status": "ACTIVE", "updated_at": now(), "lease_expires_at": future(14)}; atomic_json(state_path(root), state)
    return {"ok": True, "command": result.args, "worktree_id": worktree_id, "task_id": task, "path": str(path), "branch": branch, "base": base, "agent_role": role, "worktree_summary_before_create": stock["summary"]}


def cmd_list(root: Path) -> dict:
    items = []
    for x in worktree_list(root):
        p = Path(x["path"]); item = dict(x)
        if p.exists():
            try: item.update(status_for(p))
            except Exception as exc: item["status_error"] = str(exc)
        items.append(item)
    return {"ok": True, "worktrees": items, "runtime": load_state(root)}


def cmd_inventory(root: Path, a) -> dict:
    return {"ok": True, **inventory(root, getattr(a, "mode", "quick"), getattr(a, "target", None))}


def cmd_adopt(root: Path, a) -> dict:
    worktree_id = safe_id(a.worktree_id)
    target = Path(a.path).resolve()
    stock = inventory(root, "quick")
    entry = next((item for item in stock["entries"] if item.get("path") and Path(item["path"]).resolve() == target), None)
    if not entry: raise RuntimeError("path is not a registered Git worktree")
    if entry["primary"]: raise RuntimeError("the canonical worktree cannot be adopted as a task worktree")
    with state_lock(root):
        state = load_state(root)
        if worktree_id in state.get("worktrees", {}): raise RuntimeError("worktree id already exists")
        if any(Path(item.get("path", "")).resolve() == target for item in state.get("worktrees", {}).values() if item.get("path")): raise RuntimeError("worktree path is already managed")
        record = {"worktree_id": worktree_id, "task_id": getattr(a, "task_id", None), "path": str(target), "branch": entry.get("branch"), "status": "ADOPTED", "adopted_at": now(), "last_activity_at": now(), "review_due_at": future(7)}
        state.setdefault("worktrees", {})[worktree_id] = record
        if entry.get("branch"): state.setdefault("leases", {})[entry["branch"]] = {"worktree_id": worktree_id, "task_id": record.get("task_id"), "path": str(target), "status": "ADOPTED", "updated_at": now(), "review_due_at": future(7)}
        atomic_json(state_path(root), state)
    return {"ok": True, "adopted": record}


def is_merged(root: Path, branch: str, target: str) -> bool: return run(["git", "merge-base", "--is-ancestor", branch, target], root, check=False).returncode == 0


def cmd_remove(root: Path, a) -> dict:
    raise RuntimeError("remove is replaced by the two-stage plan-close and close workflow")


def cmd_pause(root: Path, a, status: str) -> dict:
    task = safe_id(a.task_id)
    with state_lock(root):
        state = load_state(root); entry = state.get("worktrees", {}).get(task)
        if not entry: raise RuntimeError("unknown task id")
        entry["status"] = status; entry["updated_at"] = now(); entry["last_activity_at"] = now(); entry["review_due_at" if status == "PAUSED" else "lease_expires_at"] = future(7 if status == "PAUSED" else 14); lease = state.get("leases", {}).get(entry["branch"], {}); lease["status"] = status; lease["updated_at"] = now(); lease["review_due_at" if status == "PAUSED" else "lease_expires_at"] = future(7 if status == "PAUSED" else 14); atomic_json(state_path(root), state)
    return {"ok": True, "task_id": task, "status": status}


def _plan_token(entry: dict, digest: str, target: str) -> str:
    raw = "|".join(str(entry.get(key, "")) for key in ("path", "branch", "head", "dirty_count", "merged", "unique_commits")) + f"|{digest}|{target}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cmd_plan_close(root: Path, a) -> dict:
    stock = inventory(root, "deep", a.target)
    target_path = Path(a.path).resolve()
    entry = next((item for item in stock["entries"] if item.get("path") and Path(item["path"]).resolve() == target_path), None)
    if not entry: raise RuntimeError("path is not a registered Git worktree")
    if entry["primary"]: raise RuntimeError("the canonical worktree cannot be closed")
    blockers = []
    if entry.get("dirty_count"): blockers.append("uncommitted changes")
    if entry.get("merged") is not True: blockers.append(f"branch is not merged into {a.target}")
    if entry.get("unique_commits") != 0: blockers.append("branch unique commit count is not proven zero")
    token = _plan_token(entry, stock["digest"], a.target)
    plan = {"schema_version": "1.0.0", "created_at": now(), "path": str(target_path), "target": a.target, "entry": entry, "inventory_digest": stock["digest"], "token": token, "approved_action": "git worktree remove", "branch_preserved": True, "blockers": blockers, "ready": not blockers}
    plan_path = common_dir(root) / "ai-engineering" / "cleanup-plans" / f"{token}.json"
    atomic_json(plan_path, plan)
    return {"ok": True, "plan": plan, "plan_path": str(plan_path)}


def cmd_close(root: Path, a) -> dict:
    token = safe_id(a.token)
    plan_path = common_dir(root) / "ai-engineering" / "cleanup-plans" / f"{token}.json"
    plan = read_json(plan_path, {}) or {}
    if not plan or plan.get("token") != token: raise RuntimeError("unknown cleanup token")
    if not plan.get("ready"): raise RuntimeError("cleanup plan contains blockers")
    stock = inventory(root, "deep", plan["target"])
    path = Path(plan["path"]).resolve()
    entry = next((item for item in stock["entries"] if item.get("path") and Path(item["path"]).resolve() == path), None)
    if not entry: raise RuntimeError("worktree changed or is no longer registered")
    if _plan_token(entry, stock["digest"], plan["target"]) != token: raise RuntimeError("worktree changed after cleanup planning; generate a new plan")
    if entry["primary"] or entry.get("dirty_count") or entry.get("merged") is not True or entry.get("unique_commits") != 0: raise RuntimeError("worktree no longer satisfies safe close conditions")
    run(["git", "worktree", "remove", str(path)], root)
    with state_lock(root):
        state = load_state(root)
        for key, record in list(state.get("worktrees", {}).items()):
            if record.get("path") and Path(record["path"]).resolve() == path:
                state["worktrees"].pop(key, None)
                if record.get("branch"): state.get("leases", {}).pop(record["branch"], None)
        atomic_json(state_path(root), state)
    plan["closed_at"] = now(); plan["status"] = "CLOSED"; atomic_json(plan_path, plan)
    return {"ok": True, "closed": str(path), "branch_preserved": True}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create"); p.add_argument("--task-id", required=True); p.add_argument("--base"); p.add_argument("--branch"); p.add_argument("--path"); p.add_argument("--agent-role", default="Developer Agent"); sub.add_parser("list")
    p = sub.add_parser("inventory"); p.add_argument("--mode", choices=("quick", "standard", "deep"), default="quick"); p.add_argument("--target")
    p = sub.add_parser("adopt"); p.add_argument("--worktree-id", required=True); p.add_argument("--path", required=True); p.add_argument("--task-id")
    p = sub.add_parser("plan-close"); p.add_argument("--path", required=True); p.add_argument("--target", default="develop")
    p = sub.add_parser("close"); p.add_argument("--token", required=True)
    p = sub.add_parser("remove"); p.add_argument("--task-id", required=True); p.add_argument("--target", default="develop"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("pause"); p.add_argument("--task-id", required=True); p = sub.add_parser("resume"); p.add_argument("--task-id", required=True); args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        result = cmd_create(root, args) if args.cmd == "create" else cmd_list(root) if args.cmd == "list" else cmd_inventory(root, args) if args.cmd == "inventory" else cmd_adopt(root, args) if args.cmd == "adopt" else cmd_plan_close(root, args) if args.cmd == "plan-close" else cmd_close(root, args) if args.cmd == "close" else cmd_remove(root, args) if args.cmd == "remove" else cmd_pause(root, args, "PAUSED" if args.cmd == "pause" else "ACTIVE"); print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (RuntimeError, subprocess.CalledProcessError, ValueError, TimeoutError) as exc:
        err = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc); print(json.dumps({"ok": False, "error": err}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__": raise SystemExit(main())
