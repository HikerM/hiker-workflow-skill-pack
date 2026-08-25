from __future__ import annotations

import hashlib
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

STATE_MANIFEST_NAMES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "poetry.lock", "requirements.txt", "pom.xml",
    "build.gradle", "build.gradle.kts", "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum", "manifest.json", "ProjectVersion.txt",
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


def _tracked_inventory(repo: Path, scope: Path, marker_limit: int = 96, manifest_limit: int = 500) -> dict[str, Any]:
    result = _git(repo, "ls-files", "-z")
    if result.returncode:
        return {"count": None, "markers": [], "manifest_hash": hashlib.sha256(b"").hexdigest()}
    markers: list[Path] = []
    manifests: list[Path] = []
    count = 0
    for raw in result.stdout.split("\0"):
        if not raw:
            continue
        count += 1
        rel = Path(raw)
        normalized = rel.as_posix()
        candidate = (repo / rel).resolve()
        try:
            candidate.relative_to(scope)
        except ValueError:
            continue
        if (
            len(markers) < marker_limit
            and (rel.name in PROJECT_MARKERS or normalized in PROJECT_MARKERS or rel.suffix.lower() in {".sln", ".csproj"})
            and candidate.is_file()
        ):
            markers.append(candidate)
        lower = normalized.lower()
        if (
            len(manifests) < manifest_limit
            and (rel.name.lower() in {name.lower() for name in STATE_MANIFEST_NAMES} or "/migrations/" in f"/{lower}/")
            and candidate.is_file()
        ):
            manifests.append(candidate)
    digest = hashlib.sha256()
    for path in sorted(manifests):
        digest.update(path.relative_to(repo).as_posix().encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"unreadable")
    return {"count": count, "markers": markers, "manifest_hash": digest.hexdigest()}


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
            "tracked_file_count": None,
            "dirty": None,
            "manifest_hash": hashlib.sha256(b"").hexdigest(),
            "repo_id": hashlib.sha256(str(scope).encode("utf-8", errors="replace")).hexdigest(),
        }
    revision = _git(scope, "rev-parse", "--show-toplevel", "--git-common-dir", "HEAD", "--abbrev-ref", "HEAD")
    values = revision.stdout.splitlines()
    if revision.returncode or len(values) < 4:
        return {
            "is_git": False,
            "scope": str(scope),
            "repo_root": None,
            "branch": None,
            "head": None,
            "common_dir": None,
            "trusted_markers": [],
            "nested_worktrees": [],
            "tracked_file_count": None,
            "dirty": None,
            "manifest_hash": hashlib.sha256(b"").hexdigest(),
            "repo_id": hashlib.sha256(str(scope).encode("utf-8", errors="replace")).hexdigest(),
        }
    repo = Path(values[0].strip()).resolve()
    common_raw = values[1].strip()
    head = values[2].strip()
    branch = values[3].strip()
    common_dir = _resolve_git_path(repo, common_raw) if common_raw else None
    remote = _git(scope, "config", "--get", "remote.origin.url").stdout.strip()
    repo_seed = remote or str(common_dir or repo)
    repo_id = hashlib.sha256(repo_seed.encode("utf-8", errors="replace")).hexdigest()
    current = scope
    worktrees = _worktrees(repo)
    for item in worktrees:
        path = Path(item.get("worktree", "")).resolve() if item.get("worktree") else None
        if path and (scope == path or scope.is_relative_to(path)):
            current = path
            break
    nested: list[str] = []
    for item in worktrees:
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
    inventory = _tracked_inventory(repo, scope)
    raw_status = _git(scope, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    dirty = any(
        not item[3:].replace("\\", "/").startswith(".ai/")
        for item in raw_status.split("\0")
        if len(item) >= 4
    )
    return {
        "is_git": True,
        "scope": str(scope),
        "repo_root": str(repo),
        "worktree_root": str(current),
        "branch": branch or None,
        "head": head or None,
        "common_dir": str(common_dir) if common_dir else None,
        "trusted_markers": [str(path) for path in inventory["markers"]],
        "nested_worktrees": nested,
        "tracked_file_count": inventory["count"],
        "dirty": dirty,
        "manifest_hash": inventory["manifest_hash"],
        "repo_id": repo_id,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    print(json.dumps(identify(Path(args.root)), ensure_ascii=False, indent=2))
