from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from technology_markers import PROJECT_MARKER_PATHS, STATE_FINGERPRINT_NAMES

PROJECT_MARKERS = PROJECT_MARKER_PATHS
STATE_MANIFEST_NAMES = STATE_FINGERPRINT_NAMES


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


def _git_layout(scope: Path) -> tuple[Path, Path, Path] | None:
    for root in (scope, *scope.parents):
        marker = root / ".git"
        if marker.is_dir():
            return root, marker.resolve(), marker.resolve()
        if marker.is_file():
            try:
                prefix, _, raw = marker.read_text(encoding="utf-8", errors="replace").strip().partition(":")
            except OSError:
                continue
            if prefix.lower() != "gitdir" or not raw.strip():
                continue
            git_dir = _resolve_git_path(root, raw)
            common_file = git_dir / "commondir"
            try:
                common_raw = common_file.read_text(encoding="utf-8").strip() if common_file.is_file() else ""
            except OSError:
                common_raw = ""
            common = _resolve_git_path(git_dir, common_raw) if common_raw else git_dir
            return root, git_dir, common
    return None


def _worktrees(repo: Path, common_dir: Path) -> list[dict[str, str]]:
    items = [{"worktree": str(repo)}]
    metadata = common_dir / "worktrees"
    try:
        candidates = sorted((item for item in metadata.iterdir() if item.is_dir()), key=lambda item: item.name)
    except OSError:
        candidates = []
    for candidate in candidates[:128]:
        try:
            git_marker = Path((candidate / "gitdir").read_text(encoding="utf-8").strip())
        except OSError:
            continue
        worktree = git_marker.parent if git_marker.name == ".git" else git_marker
        if worktree.is_dir():
            items.append({"worktree": str(worktree.resolve())})
    return items


def _origin_url(common_dir: Path) -> str:
    try:
        content = (common_dir / "config").read_text(encoding="utf-8", errors="replace")[:256 * 1024]
    except OSError:
        return ""
    match = re.search(r'^\s*\[remote\s+["\']origin["\']\]\s*$([\s\S]*?)(?=^\s*\[|\Z)', content, re.M | re.I)
    if not match:
        return ""
    url = re.search(r"^\s*url\s*=\s*(.+?)\s*$", match.group(1), re.M | re.I)
    return url.group(1).strip() if url else ""


def _head_facts(git_dir: Path, common_dir: Path) -> tuple[str | None, str | None]:
    try:
        raw = (git_dir / "HEAD").read_text(encoding="ascii", errors="replace").strip()
    except OSError:
        return None, None
    if not raw.startswith("ref:"):
        return (raw if re.fullmatch(r"[0-9a-fA-F]{40,64}", raw) else None), "HEAD"
    reference = raw.partition(":")[2].strip().replace("\\", "/")
    branch = reference.removeprefix("refs/heads/") or "HEAD"
    for base in (git_dir, common_dir):
        try:
            value = (base / Path(reference)).read_text(encoding="ascii", errors="replace").strip()
        except OSError:
            value = ""
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
            return value, branch
    try:
        packed = (common_dir / "packed-refs").read_text(encoding="ascii", errors="replace")
    except OSError:
        packed = ""
    for line in packed.splitlines():
        value, _, name = line.partition(" ")
        if name == reference and re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
            return value, branch
    return None, branch


def _tracked_inventory(repo: Path, scope: Path, marker_limit: int = 96, manifest_limit: int = 500) -> dict[str, Any]:
    markers: list[Path] = []
    manifests: list[Path] = []
    count = 0
    try:
        scope_prefix = scope.resolve().relative_to(repo.resolve()).as_posix().strip("/")
    except ValueError:
        scope_prefix = ""
    marker_names = {name.lower() for name in PROJECT_MARKERS}
    state_names = {name.lower() for name in STATE_MANIFEST_NAMES}
    try:
        records=iter_git_nul_records(repo,["ls-files","-z","--",".",":(exclude).ai/**"])
        for raw in records:
            count += 1
            rel = Path(raw)
            normalized = rel.as_posix()
            in_scope = not scope_prefix or normalized == scope_prefix or normalized.startswith(scope_prefix + "/")
            if not in_scope:
                continue
            marker_candidate = rel.name.lower() in marker_names or normalized.lower() in marker_names or rel.suffix.lower() in {".sln", ".csproj"}
            lower = normalized.lower()
            state_candidate = rel.name.lower() in state_names or "/migrations/" in f"/{lower}/"
            if not marker_candidate and not state_candidate:
                continue
            candidate = repo / rel
            if is_reserved_source_path(repo,candidate):
                continue
            if len(markers) < marker_limit and marker_candidate and candidate.is_file():
                markers.append(candidate)
            if len(manifests) < manifest_limit and state_candidate and candidate.is_file():
                manifests.append(candidate)
    except (RuntimeError,TraversalLimitReached):
        return {"count": None,"markers":[],"manifest_hash":hashlib.sha256(b"").hexdigest(),"status":"TRAVERSAL_LIMIT_REACHED"}
    digest = hashlib.sha256()
    bytes_read=0
    for path in sorted(manifests):
        digest.update(path.relative_to(repo).as_posix().encode("utf-8"))
        try:
            raw,truncated=read_bounded_bytes(path,min(256*1024,4*1024*1024-bytes_read))
            bytes_read+=len(raw);digest.update(raw)
            if truncated:digest.update(b"[TRUNCATED]")
        except OSError:
            digest.update(b"unreadable")
        if bytes_read>=4*1024*1024:break
    return {"count": count, "markers": markers, "manifest_hash": digest.hexdigest(),"status":"COMPLETE","bytes_read":bytes_read}


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


def identify(root: Path, include_untracked_dirty: bool = True) -> dict[str, Any]:
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
    layout = _git_layout(scope)
    if layout is None:
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
    repo, git_dir, common_dir = layout
    head, branch = _head_facts(git_dir, common_dir)
    remote = _origin_url(common_dir)
    repo_seed = remote or str(common_dir)
    repo_id = hashlib.sha256(repo_seed.encode("utf-8", errors="replace")).hexdigest()
    current = scope
    worktrees = _worktrees(repo, common_dir)
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
    if include_untracked_dirty:
        try:
            dirty=any(True for _ in iter_git_nul_records(scope,["status","--porcelain=v1","-z","--untracked-files=all","--",".",":(exclude).ai/**"],max_items=100_000))
        except (RuntimeError,TraversalLimitReached):
            dirty=None
    else:
        dirty = None
    return {
        "is_git": True,
        "scope": str(scope),
        "repo_root": str(repo),
        "worktree_root": str(current),
        "branch": branch,
        "head": head,
        "common_dir": str(common_dir),
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
