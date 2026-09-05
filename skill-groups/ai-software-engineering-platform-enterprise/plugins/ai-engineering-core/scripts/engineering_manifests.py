from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from technology_markers import ENGINEERING_MANIFEST_NAMES, is_engineering_manifest as marker_is_engineering_manifest
from resource_budget import DEFAULT_BUDGETS as RESOURCE_DEFAULT_BUDGETS, effective_budget
from source_surface import is_reserved_source_path

EXACT_MANIFESTS = ENGINEERING_MANIFEST_NAMES

IGNORED_DIRECTORIES = {
    ".git",
    ".ai",
    ".cache",
    ".idea",
    ".next",
    ".nuxt",
    ".output",
    ".turbo",
    ".venv",
    "backup",
    "backups",
    "bin",
    "build",
    "cache",
    "coverage",
    "deriveddata",
    "dist",
    "generated",
    "library",
    "node_modules",
    "obj",
    "pods",
    "temp",
    "tmp",
    "vendor",
    "venv",
    "__web_assist_stage",
    ".codex-tmp",
    ".playwright-cli",
}


@dataclass(frozen=True)
class DiscoveryBudget:
    max_depth: int = RESOURCE_DEFAULT_BUDGETS["manifest_scan"]["max_depth"]
    max_dirs: int = RESOURCE_DEFAULT_BUDGETS["manifest_scan"]["max_dirs"]
    max_manifests: int = RESOURCE_DEFAULT_BUDGETS["manifest_scan"]["max_manifests"]
    max_bytes: int = RESOURCE_DEFAULT_BUDGETS["manifest_scan"]["max_bytes"]
    max_entries_per_dir: int = RESOURCE_DEFAULT_BUDGETS["manifest_scan"]["max_entries_per_dir"]


def is_engineering_manifest(path: Path) -> bool:
    return marker_is_engineering_manifest(path)


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _relative(root: Path, path: Path) -> str | None:
    if is_reserved_source_path(root, path):
        return None
    try:
        return Path(os.path.abspath(path)).relative_to(root).as_posix()
    except ValueError:
        return None


@lru_cache(maxsize=256)
def _read_snapshot(path: str, modified_ns: int, size: int, per_file_limit: int) -> bytes:
    del modified_ns, size
    try:
        with Path(path).open("rb") as stream:
            return stream.read(per_file_limit + 1)
    except OSError:
        return b""


def _read_bounded(path: Path, remaining: int, per_file_limit: int = 96 * 1024) -> tuple[str, int, bool]:
    allowed = max(0, min(remaining, per_file_limit))
    if not allowed:
        return "", 0, True
    try:
        info = path.stat()
        snapshot = _read_snapshot(str(path.resolve()), info.st_mtime_ns, info.st_size, per_file_limit)
    except OSError:
        return "", 0, False
    raw = snapshot[: allowed + 1]
    truncated = len(raw) > allowed
    raw = raw[:allowed]
    return raw.decode("utf-8", errors="replace"), len(raw), truncated


def _workspace_patterns(path: Path, content: str) -> list[str]:
    patterns: list[str] = []
    if path.name == "package.json":
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        workspaces = payload.get("workspaces") if isinstance(payload, dict) else None
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages")
        if isinstance(workspaces, list):
            patterns.extend(str(item).strip() for item in workspaces if str(item).strip())
    elif path.name.lower() in {"pnpm-workspace.yaml", "pnpm-workspace.yml"}:
        in_packages = False
        for raw in content.splitlines()[:256]:
            stripped = raw.strip()
            if stripped == "packages:":
                in_packages = True
                continue
            if in_packages and stripped.startswith("-"):
                patterns.append(stripped[1:].strip().strip("'\"")[:160])
            elif in_packages and stripped and not raw.startswith((" ", "\t")):
                break
    return patterns[:32]


def _declared_roots(root: Path, manifest: Path, content: str) -> list[Path]:
    results: list[Path] = []
    for pattern in _workspace_patterns(manifest, content):
        normalized = pattern.replace("\\", "/").strip("/")
        if not normalized or normalized.startswith(("../", "/")) or "**" in normalized:
            continue
        parts = normalized.split("/")
        if parts.count("*") > 1 or any("*" in part and part != "*" for part in parts):
            continue
        base = manifest.parent
        if "*" not in parts:
            candidates = [base.joinpath(*parts)]
        else:
            star = parts.index("*")
            prefix = base.joinpath(*parts[:star])
            suffix = parts[star + 1 :]
            try:
                children = sorted(
                    (item for item in prefix.iterdir() if item.is_dir() and not _is_reparse_or_symlink(item)),
                    key=lambda item: item.name.lower(),
                )[:64]
            except OSError:
                children = []
            candidates = [child.joinpath(*suffix) for child in children]
        for candidate in candidates:
            relative = _relative(root, candidate)
            if relative is not None and candidate.is_dir() and not _is_reparse_or_symlink(candidate):
                results.append(candidate.resolve())
    return list(dict.fromkeys(results))[:64]


def discover_engineering_manifests(
    root: Path,
    tracked_paths: Iterable[str | Path] = (),
    declared_roots: Iterable[str | Path] = (),
    excluded_roots: Iterable[str | Path] = (),
    budget: DiscoveryBudget | None = None,
) -> dict[str, Any]:
    """Discover only engineering manifests under hard budgets; never inspect source files."""
    root = root.resolve()
    requested = budget or DiscoveryBudget()
    limits = DiscoveryBudget(**effective_budget("manifest_scan", vars(requested)))
    tracked: list[Path] = []
    tracked_set: set[Path] = set()
    excluded: list[Path] = []
    for raw in excluded_roots:
        candidate = Path(raw)
        candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if _relative(root, candidate) is not None:
            excluded.append(candidate)

    def is_excluded(path: Path) -> bool:
        resolved = Path(os.path.abspath(path))
        return any(resolved == item or resolved.is_relative_to(item) for item in excluded)

    for raw in tracked_paths:
        candidate = Path(raw)
        candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if _relative(root, candidate) is None or is_excluded(candidate) or not candidate.is_file() or not is_engineering_manifest(candidate):
            continue
        tracked.append(candidate)
        tracked_set.add(candidate)

    manifests: list[dict[str, Any]] = []
    discovered: set[Path] = set()
    bytes_read = 0
    truncated = False
    declared: list[Path] = []

    def add_manifest(path: Path, authority: str) -> None:
        nonlocal bytes_read, truncated
        path = path.resolve()
        if path in discovered or len(manifests) >= limits.max_manifests:
            truncated = truncated or len(manifests) >= limits.max_manifests
            return
        relative = _relative(root, path)
        if relative is None or is_excluded(path) or _is_reparse_or_symlink(path):
            return
        content, consumed, file_truncated = _read_bounded(path, limits.max_bytes - bytes_read)
        bytes_read += consumed
        truncated = truncated or file_truncated
        digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        manifests.append({
            "path": relative,
            "authority": authority,
            "content": content,
            "bytes": consumed,
            "sha256": digest,
        })
        discovered.add(path)
        declared.extend(_declared_roots(root, path, content))

    for path in sorted(tracked, key=lambda item: item.as_posix().lower()):
        add_manifest(path, "GIT_TRACKED_AUTHORITATIVE")

    for name in sorted(EXACT_MANIFESTS, key=str.lower):
        candidate = root / name
        if candidate.is_file():
            add_manifest(
                candidate,
                "GIT_TRACKED_AUTHORITATIVE" if candidate.resolve() in tracked_set else "CURRENT_WORKSPACE_MANIFEST",
            )

    seeds: list[Path] = []
    for raw in declared_roots:
        candidate = Path(raw)
        candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if _relative(root, candidate) is not None and candidate.is_dir() and not _is_reparse_or_symlink(candidate):
            seeds.append(candidate)
    seeds.extend(declared)
    seeds.append(root)
    controlled_top_levels = {
        Path(relative).parts[0].lower()
        for relative in (_relative(root, item) for item in declared)
        if relative and relative != "."
    }
    controlled_top_levels.update({"apps", "packages", "services", "server", "backend", "api", "src", "client"})
    queue: deque[tuple[Path, int]] = deque((item, 0) for item in dict.fromkeys(seeds))
    visited: set[Path] = set()
    entries_seen = 0
    while queue and len(visited) < limits.max_dirs and len(manifests) < limits.max_manifests and bytes_read < limits.max_bytes:
        current, depth = queue.popleft()
        current = Path(os.path.abspath(current))
        if current in visited or _relative(root, current) is None or is_excluded(current) or _is_reparse_or_symlink(current):
            continue
        visited.add(current)
        try:
            entries = []
            with os.scandir(current) as iterator:
                for index, entry in enumerate(iterator):
                    if index >= limits.max_entries_per_dir:
                        truncated = True
                        break
                    entries.append(entry)
                    entries_seen += 1
        except OSError:
            continue
        for entry in sorted(entries, key=lambda item: item.name.lower()):
            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False) and is_engineering_manifest(path):
                    add_manifest(path, "GIT_TRACKED_AUTHORITATIVE" if path.resolve() in tracked_set else "CURRENT_WORKSPACE_MANIFEST")
                elif (
                    depth < limits.max_depth
                    and entry.is_dir(follow_symlinks=False)
                    and entry.name.lower() not in IGNORED_DIRECTORIES
                    and (current != root or not declared or entry.name.lower() in controlled_top_levels)
                ):
                    queue.append((path, depth + 1))
            except OSError:
                continue
    truncated = truncated or bool(queue) or len(visited) >= limits.max_dirs or bytes_read >= limits.max_bytes
    fingerprint = hashlib.sha256()
    for item in manifests:
        fingerprint.update(item["path"].encode("utf-8"))
        fingerprint.update(item["sha256"].encode("ascii"))
        fingerprint.update(item["authority"].encode("ascii"))
    return {
        "schema_version": "1.0.0",
        "manifests": manifests,
        "declared_roots": sorted({_relative(root, item) or "." for item in declared}),
        "fingerprint": fingerprint.hexdigest(),
        "budget": {
            "max_depth": limits.max_depth,
            "max_dirs": limits.max_dirs,
            "max_manifests": limits.max_manifests,
            "max_bytes": limits.max_bytes,
            "max_entries_per_dir": limits.max_entries_per_dir,
        },
        "metrics": {
            "directories_read": len(visited),
            "directory_entries_seen": entries_seen,
            "manifests_read": len(manifests),
            "bytes_read": bytes_read,
            "controlled_untracked_manifests": sum(1 for item in manifests if item["authority"] == "CURRENT_WORKSPACE_MANIFEST"),
            "full_scan_count": 0,
            "truncated": truncated,
        },
    }
