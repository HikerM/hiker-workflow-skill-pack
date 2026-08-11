from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from workspacelib import load_state, read_json, repo_root, run


def _normalized(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def git_worktrees(root: Path) -> list[dict[str, Any]]:
    result = run(["git", "worktree", "list", "--porcelain"], root, check=False)
    items: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in result.stdout.splitlines() + [""]:
        if not line:
            if current:
                items.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in {"detached", "prunable"}:
            current[key] = value or True
        else:
            current[key] = value
    return items


def _target_exists(root: Path, target: str) -> bool:
    return run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target}"], root, check=False).returncode == 0


def _is_merged(root: Path, branch: str, target: str) -> bool | None:
    if not branch or not _target_exists(root, target):
        return None
    return run(["git", "merge-base", "--is-ancestor", branch, target], root, check=False).returncode == 0


def _unique_commits(root: Path, branch: str, target: str) -> int | None:
    if not branch or not _target_exists(root, target):
        return None
    result = run(["git", "rev-list", "--count", f"{target}..{branch}"], root, check=False)
    try:
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def inventory(path: Path, mode: str = "quick", target: str | None = None) -> dict[str, Any]:
    root = repo_root(path)
    state = load_state(root)
    project = read_json(root / ".ai" / "governance" / "project-state.json", {}) or {}
    configured = project.get("parallel_budget", {})
    max_active = int(configured.get("max_active_write_tasks", 2))
    raw = git_worktrees(root)
    primary = _normalized(root)
    managed = {_normalized(item.get("path", "")): item for item in state.get("worktrees", {}).values() if item.get("path")}
    entries: list[dict[str, Any]] = []
    for item in raw:
        raw_path = item.get("worktree", "")
        normalized = _normalized(raw_path) if raw_path else ""
        entry: dict[str, Any] = {
            "path": raw_path,
            "branch": item.get("branch"),
            "head": item.get("HEAD"),
            "primary": normalized == primary,
            "managed": normalized in managed,
            "exists": bool(raw_path and Path(raw_path).exists()),
            "detached": bool(item.get("detached")),
            "prunable": bool(item.get("prunable")),
        }
        if normalized in managed:
            entry["task_id"] = managed[normalized].get("task_id")
            entry["lease_status"] = managed[normalized].get("status")
        nested = False
        if raw_path and normalized != primary:
            try:
                Path(raw_path).resolve().relative_to(root.resolve())
                nested = True
            except ValueError:
                pass
        entry["nested"] = nested
        if mode in {"standard", "deep"} and entry["exists"]:
            untracked = "all" if mode == "deep" else "no"
            dirty = run(["git", "status", "--porcelain=v1", f"--untracked-files={untracked}"], Path(raw_path), check=False).stdout.splitlines()
            entry["dirty_count"] = len(dirty)
            if mode == "deep":
                chosen_target = target or ("main" if str(entry.get("branch") or "").startswith("hotfix/") else "develop")
                entry["target"] = chosen_target
                entry["merged"] = _is_merged(root, str(entry.get("branch") or ""), chosen_target)
                entry["unique_commits"] = _unique_commits(root, str(entry.get("branch") or ""), chosen_target)
        if entry["primary"]:
            classification = "PRIMARY"
        elif entry["nested"]:
            classification = "NESTED_BLOCKED"
        elif entry["prunable"] or not entry["exists"]:
            classification = "PRUNABLE_METADATA"
        elif entry.get("dirty_count", 0):
            classification = "BLOCKED_DIRTY"
        elif mode == "deep" and entry.get("merged") is True and entry.get("unique_commits") == 0:
            classification = "CAN_CLOSE"
        elif entry["managed"]:
            classification = str(entry.get("lease_status") or "ADOPTED")
        else:
            classification = "UNMANAGED"
        entry["classification"] = classification
        entries.append(entry)
    active = sum(1 for item in entries if item.get("managed") and item.get("lease_status") == "ACTIVE" and not item.get("primary"))
    managed_count = sum(1 for item in entries if item.get("managed") and not item.get("primary"))
    unmanaged = sum(1 for item in entries if not item.get("managed") and not item.get("primary"))
    nested_count = sum(1 for item in entries if item.get("nested"))
    prunable = sum(1 for item in entries if item.get("prunable") or not item.get("exists"))
    digest_source = "\n".join(f"{x.get('path')}|{x.get('branch')}|{x.get('HEAD')}|{x.get('prunable')}" for x in raw)
    return {
        "schema_version": "2.0.0",
        "mode": mode,
        "repo_root": str(root),
        "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "summary": {
            "total": len(entries),
            "active_managed": active,
            "managed": managed_count,
            "max_active_write_worktrees": max_active,
            "unmanaged": unmanaged,
            "nested": nested_count,
            "prunable": prunable,
            "over_active_budget": active >= max_active,
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--mode", choices=("quick", "standard", "deep"), default="quick")
    parser.add_argument("--target")
    args = parser.parse_args()
    try:
        print(json.dumps(inventory(Path(args.root), args.mode, args.target), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
