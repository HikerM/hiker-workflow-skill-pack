from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from workspacelib import atomic_json, load_state, read_json, repo_root, run, safe_branch, safe_id, state_lock, state_path

PROTECTED = {"main", "develop", "release"}
PREFIXES = ("feature/", "bugfix/", "hotfix/", "release/")


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    if branch.startswith("release/") and agent_role != "Merge Agent": raise RuntimeError("only Merge Agent may create release/* worktrees")
    expected = default_base(branch)
    if base != expected: raise RuntimeError(f"{branch} must be based on {expected}")
    if not branch_exists(root, base): raise RuntimeError(f"required base branch does not exist: {base}")


def status_for(path: Path) -> dict:
    dirty = run(["git", "status", "--porcelain"], path).stdout.splitlines(); branch = run(["git", "branch", "--show-current"], path, check=False).stdout.strip() or "DETACHED"; head = run(["git", "rev-parse", "HEAD"], path).stdout.strip(); return {"path": str(path), "branch": branch, "head": head, "dirty": dirty}


def governance_task(root: Path, task: str) -> dict | None:
    state = read_json(root / ".ai" / "governance" / "project-state.json", {}) or {}
    if not state: return None
    data = read_json(root / ".ai" / "tasks" / f"{task.upper()}.json", {}) or {}
    if not data: raise RuntimeError("governed projects require an existing task before worktree creation")
    if data.get("state") not in {"Planning", "Development"}: raise RuntimeError("task must be in Planning or Development")
    return data


def cmd_create(root: Path, a) -> dict:
    task = safe_id(a.task_id); branch = safe_branch(a.branch or f"feature/{task}"); base = a.base or default_base(branch); role = getattr(a, "agent_role", "Developer Agent")
    validate_branch_policy(root, branch, base, role)
    governed = governance_task(root, task)
    if governed and governed.get("branch") != branch: raise RuntimeError(f"task branch mismatch: expected {governed.get('branch')}")
    default_parent = root.parent / f"{root.name}.ai-worktrees"; path = Path(a.path).expanduser().resolve() if a.path else (default_parent / task).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    with state_lock(root):
        state = load_state(root)
        if task in state.get("worktrees", {}): raise RuntimeError(f"task already has worktree: {task}")
        if branch in state.get("leases", {}) and state["leases"][branch].get("status") in {"ACTIVE", "PAUSED"}: raise RuntimeError(f"branch already leased: {branch}")
        if path.exists() and any(path.iterdir()): raise RuntimeError(f"worktree path is not empty: {path}")
        if path in {Path(x["path"]).resolve() for x in worktree_list(root)}: raise RuntimeError("worktree already registered")
        cmd = ["git", "worktree", "add"] + ([str(path), branch] if branch_exists(root, branch) else ["-b", branch, str(path), base]); result = run(cmd, root)
        state.setdefault("worktrees", {})[task] = {"task_id": task, "path": str(path), "branch": branch, "base": base, "agent_role": role, "status": "ACTIVE", "created_at": now()}; state.setdefault("leases", {})[branch] = {"task_id": task, "path": str(path), "status": "ACTIVE", "updated_at": now()}; atomic_json(state_path(root), state)
    return {"ok": True, "command": result.args, "task_id": task, "path": str(path), "branch": branch, "base": base, "agent_role": role}


def cmd_list(root: Path) -> dict:
    items = []
    for x in worktree_list(root):
        p = Path(x["path"]); item = dict(x)
        if p.exists():
            try: item.update(status_for(p))
            except Exception as exc: item["status_error"] = str(exc)
        items.append(item)
    return {"ok": True, "worktrees": items, "runtime": load_state(root)}


def is_merged(root: Path, branch: str, target: str) -> bool: return run(["git", "merge-base", "--is-ancestor", branch, target], root, check=False).returncode == 0


def cmd_remove(root: Path, a) -> dict:
    task = safe_id(a.task_id)
    with state_lock(root):
        state = load_state(root); entry = state.get("worktrees", {}).get(task)
        if not entry: raise RuntimeError("unknown task id")
        path = Path(entry["path"]); branch = entry["branch"]
        if path.exists() and status_for(path)["dirty"] and not a.force: raise RuntimeError("worktree has uncommitted changes; use --force only after explicit review")
        if not is_merged(root, branch, a.target) and not a.force: raise RuntimeError(f"branch {branch} is not merged into {a.target}")
        if path.exists(): run(["git", "worktree", "remove"] + (["--force"] if a.force else []) + [str(path)], root)
        state.get("worktrees", {}).pop(task, None); state.get("leases", {}).pop(branch, None); atomic_json(state_path(root), state)
    return {"ok": True, "removed": str(path), "branch_preserved": branch, "note": "branch is not deleted automatically"}


def cmd_pause(root: Path, a, status: str) -> dict:
    task = safe_id(a.task_id)
    with state_lock(root):
        state = load_state(root); entry = state.get("worktrees", {}).get(task)
        if not entry: raise RuntimeError("unknown task id")
        entry["status"] = status; entry["updated_at"] = now(); lease = state.get("leases", {}).get(entry["branch"], {}); lease["status"] = status; lease["updated_at"] = now(); atomic_json(state_path(root), state)
    return {"ok": True, "task_id": task, "status": status}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create"); p.add_argument("--task-id", required=True); p.add_argument("--base"); p.add_argument("--branch"); p.add_argument("--path"); p.add_argument("--agent-role", default="Developer Agent"); sub.add_parser("list")
    p = sub.add_parser("remove"); p.add_argument("--task-id", required=True); p.add_argument("--target", default="develop"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("pause"); p.add_argument("--task-id", required=True); p = sub.add_parser("resume"); p.add_argument("--task-id", required=True); args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        result = cmd_create(root, args) if args.cmd == "create" else cmd_list(root) if args.cmd == "list" else cmd_remove(root, args) if args.cmd == "remove" else cmd_pause(root, args, "PAUSED" if args.cmd == "pause" else "ACTIVE"); print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (RuntimeError, subprocess.CalledProcessError, ValueError, TimeoutError) as exc:
        err = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc); print(json.dumps({"ok": False, "error": err}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__": raise SystemExit(main())
