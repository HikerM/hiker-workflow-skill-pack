from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, common_dir, locked_state, read_json, repo_root, safe_id, state_lock

SCHEMA = "2.0.0"
GLOBAL_EXCLUSIVE = {"unity-projectsettings", "database-migration", "api-contract"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lock_file(root: Path) -> Path:
    return common_dir(root) / "ai-engineering" / "file-locks.json"


def load_locks(root: Path) -> dict[str, Any]:
    return read_json(lock_file(root), {"schema_version": SCHEMA, "locks": []}) or {"schema_version": SCHEMA, "locks": []}


def normalize(root: Path, value: str) -> str:
    path = Path(value)
    root_text = os.path.realpath(str(root))
    absolute_text = os.path.realpath(str(path if path.is_absolute() else root / path))
    try: common = os.path.commonpath([os.path.normcase(root_text), os.path.normcase(absolute_text)])
    except ValueError: raise RuntimeError(f"lock path is outside repository: {value}")
    if common != os.path.normcase(root_text): raise RuntimeError(f"lock path is outside repository: {value}")
    return Path(os.path.relpath(absolute_text, root_text)).as_posix()


def category(path: str) -> str:
    low = path.lower()
    parts = [part.lower() for part in Path(path).parts]
    if "projectsettings" in parts: return "unity-projectsettings"
    if low.endswith(".unity"): return "unity-scene"
    if low.endswith(".prefab"): return "unity-prefab"
    if low.endswith(".meta"): return "unity-meta"
    if "migration" in low or "/migrations/" in f"/{low}": return "database-migration"
    if any(token in low for token in ("openapi", "swagger", "api-contract", "/contracts/", "/dto/")): return "api-contract"
    if ("/service" in f"/{low}" or Path(low).stem.endswith("service")) and low.endswith((".ts", ".tsx", ".cs", ".java", ".kt", ".py")): return "core-service"
    return "source-file"


def asset_key(path: str) -> str:
    return path[:-5] if path.lower().endswith(".meta") else path


def conflicts(left: dict[str, Any], right_path: str, right_category: str, task_id: str) -> bool:
    if left.get("task_id") == task_id: return False
    if left.get("path") == right_path: return True
    if left.get("category") in GLOBAL_EXCLUSIVE and left.get("category") == right_category: return True
    if asset_key(str(left.get("path"))) == asset_key(right_path): return True
    return False


def ensure_task(root: Path, task_id: str) -> dict[str, Any]:
    task = read_json(root / ".ai" / "tasks" / f"{safe_id(task_id)}.json", {}) or {}
    if not task: raise RuntimeError(f"unknown task: {task_id}")
    if task.get("control_status") != "ACTIVE": raise RuntimeError("task is not ACTIVE")
    if task.get("state") not in {"Development", "Review", "Testing"}: raise RuntimeError("locks are allowed only during Development, Review, or Testing")
    return task


@locked_state
def acquire(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task_id = safe_id(args.task_id).upper(); ensure_task(root, task_id)
    paths = [normalize(root, item) for item in args.paths]
    data = load_locks(root); blocked = []
    for path in paths:
        cat = category(path)
        for existing in data["locks"]:
            if conflicts(existing, path, cat, task_id): blocked.append({"path": path, "category": cat, "conflict": existing})
    if blocked: raise RuntimeError("lock conflict: " + json.dumps(blocked, ensure_ascii=False))
    existing_paths = {(x.get("task_id"), x.get("path")) for x in data["locks"]}
    for path in paths:
        if (task_id, path) not in existing_paths:
            data["locks"].append({"path": path, "category": category(path), "task_id": task_id, "agent_role": args.agent_role, "owner": args.owner, "acquired_at": now(), "heartbeat_at": now()})
    atomic_json(lock_file(root), data)
    return {"acquired": paths, "locks": data["locks"]}


@locked_state
def release(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task_id = safe_id(args.task_id).upper(); data = load_locks(root); wanted = {normalize(root, x) for x in args.paths} if args.paths else None
    before = list(data["locks"]); removed = []; kept = []
    for item in before:
        match = item.get("task_id") == task_id and (wanted is None or item.get("path") in wanted)
        if match: removed.append(item)
        else: kept.append(item)
    data["locks"] = kept; atomic_json(lock_file(root), data)
    return {"released": removed, "remaining": kept}


@locked_state
def heartbeat(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task_id = safe_id(args.task_id).upper(); data = load_locks(root); count = 0
    for item in data["locks"]:
        if item.get("task_id") == task_id: item["heartbeat_at"] = now(); count += 1
    atomic_json(lock_file(root), data); return {"updated": count}


def check(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task_id = safe_id(args.task_id).upper(); paths = [normalize(root, x) for x in args.files]; data = load_locks(root); missing = []; blocked = []
    owned = {(x.get("task_id"), x.get("path")) for x in data["locks"]}
    owned_assets = {(x.get("task_id"), asset_key(str(x.get("path")))) for x in data["locks"]}
    for path in paths:
        cat = category(path)
        if cat != "source-file" and (task_id, path) not in owned and (task_id, asset_key(path)) not in owned_assets: missing.append({"path": path, "category": cat})
        for existing in data["locks"]:
            if conflicts(existing, path, cat, task_id): blocked.append({"path": path, "conflict": existing})
    return {"ok": not missing and not blocked, "missing_required_locks": missing, "conflicts": blocked}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("acquire"); p.add_argument("--task-id", required=True); p.add_argument("--agent-role", required=True); p.add_argument("--owner", required=True); p.add_argument("--paths", nargs="+", required=True)
    p = sub.add_parser("release"); p.add_argument("--task-id", required=True); p.add_argument("--paths", nargs="*")
    p = sub.add_parser("heartbeat"); p.add_argument("--task-id", required=True)
    p = sub.add_parser("check"); p.add_argument("--task-id", required=True); p.add_argument("--files", nargs="+", required=True)
    sub.add_parser("list")
    args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        with state_lock(root):
            if args.cmd == "acquire": data = acquire(root, args)
            elif args.cmd == "release": data = release(root, args)
            elif args.cmd == "heartbeat": data = heartbeat(root, args)
            elif args.cmd == "check": data = check(root, args)
            else: data = load_locks(root)
        print(json.dumps({"ok": data.get("ok", True), "result": data}, ensure_ascii=False, indent=2)); return 0 if data.get("ok", True) else 2
    except (RuntimeError, ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
