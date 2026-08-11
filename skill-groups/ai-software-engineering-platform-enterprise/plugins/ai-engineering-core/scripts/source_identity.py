from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


PROJECT_MARKERS = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "CMakeLists.txt",
    "Packages/manifest.json",
}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _resolve_git_path(base: Path, raw: str) -> Path:
    path = Path(raw.strip())
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _worktrees(repo: Path) -> list[dict[str, str]]:
    result = _git(repo, "worktree", "list", "--porcelain")
    if result.returncode:
        return []
    items: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines() + [""]:
        if not line:
            if current:
                items.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return items


def _tracked_markers(repo: Path, scope: Path, limit: int = 96) -> list[Path]:
    result = _git(repo, "ls-files", "-z")
    if result.returncode:
        return []
    found: list[Path] = []
    for raw in result.stdout.split("\0"):
        if not raw:
            continue
        rel = Path(raw)
        normalized = rel.as_posix()
        if rel.name not in PROJECT_MARKERS and normalized not in PROJECT_MARKERS and rel.suffix.lower() not in {".sln", ".csproj"}:
            continue
        candidate = (repo / rel).resolve()
        try:
            candidate.relative_to(scope)
        except ValueError:
            continue
        if candidate.is_file():
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


def _values_for_keys(value: Any, keys: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in keys and isinstance(item, (str, int)):
                found.append(str(item))
            found.extend(_values_for_keys(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(_values_for_keys(item, keys))
    return found


def context_fresh(context: Path, branch: str, head: str) -> bool:
    if not context.is_file():
        return False
    try:
        data = json.loads(context.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    recorded_heads = _values_for_keys(data, {"head", "commit", "commit_id", "git_head"})
    recorded_branches = _values_for_keys(data, {"branch", "git_branch"})
    if recorded_heads and head and not any(head.startswith(value) or value.startswith(head) for value in recorded_heads):
        return False
    if recorded_branches and branch and branch not in recorded_branches:
        return False
    return True


def identify(root: Path) -> dict[str, Any]:
    scope = root.resolve()
    git_hint = any((candidate / ".git").exists() for candidate in (scope, *scope.parents)) or bool(os.environ.get("GIT_DIR"))
    if not scope.is_dir() or not git_hint:
        return {
            "is_git": False,
            "scope": str(scope),
            "repo_root": None,
            "branch": None,
            "head": None,
            "common_dir": None,
            "trusted_markers": [],
            "nested_worktrees": [],
        }
    top = _git(scope, "rev-parse", "--show-toplevel")
    if top.returncode:
        return {
            "is_git": False,
            "scope": str(scope),
            "repo_root": None,
            "branch": None,
            "head": None,
            "common_dir": None,
            "trusted_markers": [],
            "nested_worktrees": [],
        }
    repo = Path(top.stdout.strip()).resolve()
    branch = _git(scope, "branch", "--show-current").stdout.strip()
    head = _git(scope, "rev-parse", "HEAD").stdout.strip()
    common_raw = _git(scope, "rev-parse", "--git-common-dir").stdout.strip()
    common_dir = _resolve_git_path(repo, common_raw) if common_raw else None
    current = scope
    for item in _worktrees(repo):
        path = Path(item.get("worktree", "")).resolve() if item.get("worktree") else None
        if path and (scope == path or scope.is_relative_to(path)):
            current = path
            break
    nested: list[str] = []
    for item in _worktrees(repo):
        if not item.get("worktree"):
            continue
        path = Path(item["worktree"]).resolve()
        if path == current:
            continue
        try:
            path.relative_to(current)
        except ValueError:
            continue
        nested.append(str(path))
    markers = _tracked_markers(repo, scope)
    return {
        "is_git": True,
        "scope": str(scope),
        "repo_root": str(repo),
        "worktree_root": str(current),
        "branch": branch or None,
        "head": head or None,
        "common_dir": str(common_dir) if common_dir else None,
        "trusted_markers": [str(path) for path in markers],
        "nested_worktrees": nested,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    print(json.dumps(identify(Path(args.root)), ensure_ascii=False, indent=2))
