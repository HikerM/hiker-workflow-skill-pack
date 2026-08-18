from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from corelib import ai_root, atomic_write_json, read_json


MANIFEST_NAMES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "poetry.lock", "requirements.txt", "pom.xml",
    "build.gradle", "build.gradle.kts", "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum", "manifest.json", "ProjectVersion.txt",
}
MATERIAL_HINTS = (
    "migration", "schema", "openapi", "asyncapi", "proto", "contract",
    "routes", "router", "projectsettings", "packages/manifest",
)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=root, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = _run(root, "git", *args)
    return result.stdout.strip() if result.returncode == 0 else ""


def _repo_id(root: Path) -> str:
    remote = _git(root, "config", "--get", "remote.origin.url")
    common = _git(root, "rev-parse", "--git-common-dir")
    if remote:
        seed = remote
    elif common:
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = root / common_path
        seed = str(common_path.resolve())
    else:
        seed = str(root.resolve())
    return _sha(seed)


def _tracked_manifests(root: Path) -> list[Path]:
    output = _git(root, "ls-files", "-z")
    found: list[Path] = []
    for raw in output.split("\0"):
        if not raw:
            continue
        path = Path(raw)
        normalized = raw.replace("\\", "/").lower()
        if path.name.lower() in {name.lower() for name in MANIFEST_NAMES} or "/migrations/" in f"/{normalized}/":
            target = root / path
            if target.is_file():
                found.append(target)
        if len(found) >= 500:
            break
    return found


def _manifest_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(_tracked_manifests(root)):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"unreadable")
    return digest.hexdigest()


def current_snapshot(root: Path) -> dict[str, Any]:
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current") or "DETACHED"
    raw_status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    dirty = any(
        not item[3:].replace("\\", "/").startswith(".ai/")
        for item in raw_status.split("\0")
        if len(item) >= 4
    )
    return {
        "schema_version": "1.0.0",
        "repo_id": _repo_id(root),
        "head": head or None,
        "branch": branch,
        "dirty": dirty,
        "manifest_hash": _manifest_hash(root),
    }


def provenance_path(root: Path) -> Path:
    return ai_root(root) / "governance" / "source-provenance.json"


def _changed_paths(root: Path, old_head: str, new_head: str) -> tuple[list[str], bool]:
    if not old_head or not new_head or old_head == new_head:
        return [], True
    check = _run(root, "git", "cat-file", "-e", f"{old_head}^{{commit}}")
    if check.returncode != 0:
        return [], False
    raw = _git(root, "diff", "--name-only", "-z", old_head, new_head)
    paths = [item.replace("\\", "/") for item in raw.split("\0") if item]
    return paths[:1000], True


def assess(root: Path) -> dict[str, Any]:
    current = current_snapshot(root)
    stored = read_json(provenance_path(root), None)
    if not isinstance(stored, dict):
        return {
            "ok": False,
            "status": "UNINITIALIZED_OR_INVALID",
            "recovery_level": "L1",
            "current": current,
            "stored": None,
            "invalidated": ["derived-ai-state"],
        }
    if stored.get("repo_id") != current["repo_id"]:
        return {
            "ok": False,
            "status": "PROJECT_IDENTITY_DRIFT",
            "recovery_level": "L4",
            "current": current,
            "stored": stored,
            "invalidated": ["all-derived-ai-state", "review-evidence", "test-evidence"],
        }
    paths, reachable = _changed_paths(root, str(stored.get("head") or ""), str(current.get("head") or ""))
    material = stored.get("manifest_hash") != current["manifest_hash"] or any(
        Path(path).name.lower() in {name.lower() for name in MANIFEST_NAMES}
        or any(hint in path.lower() for hint in MATERIAL_HINTS)
        for path in paths
    )
    if not reachable:
        return {
            "ok": False,
            "status": "HISTORY_DIVERGED",
            "recovery_level": "L3",
            "current": current,
            "stored": stored,
            "changed_paths": [],
            "invalidated": ["candidate-binding", "derived-graph", "review-evidence", "test-evidence"],
        }
    if material:
        return {
            "ok": False,
            "status": "MATERIAL_DRIFT",
            "recovery_level": "L2",
            "current": current,
            "stored": stored,
            "changed_paths": paths,
            "invalidated": ["affected-module-baseline", "affected-contract-evidence"],
        }
    if paths or stored.get("dirty") != current["dirty"] or stored.get("branch") != current["branch"]:
        return {
            "ok": False,
            "status": "INCREMENTAL_DRIFT",
            "recovery_level": "L1",
            "current": current,
            "stored": stored,
            "changed_paths": paths,
            "invalidated": ["affected-hot-index"],
        }
    return {
        "ok": True,
        "status": "CONSISTENT",
        "recovery_level": "L0",
        "current": current,
        "stored": stored,
        "changed_paths": [],
        "invalidated": [],
    }


def repair(root: Path) -> dict[str, Any]:
    report = assess(root)
    path = provenance_path(root)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = ai_root(root) / "archive" / "consistency" / f"source-provenance-{stamp}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archive)
    atomic_write_json(path, report["current"])
    return {**report, "repaired": True, "new_status": "CONSISTENT", "provenance": path.relative_to(root).as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 .ai 与当前源码身份和候选的一致性")
    parser.add_argument("--root", default=".")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = repair(root) if args.repair else assess(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") or result.get("repaired") else 2


if __name__ == "__main__":
    raise SystemExit(main())
