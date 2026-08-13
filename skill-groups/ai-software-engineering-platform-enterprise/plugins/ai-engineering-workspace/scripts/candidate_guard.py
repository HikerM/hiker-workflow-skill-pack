from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, read_json, repo_root, run, safe_id, state_lock, worktree_fingerprint

SCHEMA = "1.0.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def snapshot(root: Path) -> dict[str, Any]:
    head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
    branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "DETACHED"
    index = run(["git", "ls-files", "-s", "-z"], root, check=False).stdout
    status = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root, check=False).stdout
    changed = []
    for row in status.split("\0"):
        if len(row) < 4:
            continue
        path = row[3:].split(" -> ")[-1].replace("\\", "/")
        if path == ".ai" or path.startswith(".ai/") or path in {"PROJECT_STATE.md", "CURRENT_CONTEXT.md"}:
            continue
        changed.append(path)
    source_fingerprint = worktree_fingerprint(root)
    return {
        "repo_root": str(root), "branch": branch, "candidate_commit": head,
        "index_hash": digest(index), "dirty_diff_hash": source_fingerprint,
        "file_set_hash": digest("\n".join(sorted(set(changed)))),
        "changed_files": sorted(set(changed)), "worktree_fingerprint": source_fingerprint,
    }


def manifest_path(root: Path, candidate_id: str) -> Path:
    return root / ".ai" / "evidence" / "candidates" / f"{safe_id(candidate_id)}.json"


def freeze(root: Path, candidate_id: str, task_id: str, review_source: str) -> dict[str, Any]:
    path = manifest_path(root, candidate_id)
    if path.exists():
        raise RuntimeError(f"candidate already exists: {candidate_id}")
    current = snapshot(root)
    data = {
        "schema_version": SCHEMA, "candidate_id": safe_id(candidate_id), "task_id": safe_id(task_id).upper(),
        "review_source": review_source, "writable": False, "frozen_at": now(), **current,
    }
    data["candidate_fingerprint"] = digest(json.dumps(current, ensure_ascii=False, sort_keys=True))
    atomic_json(path, data)
    return data


def verify(root: Path, candidate_id: str) -> dict[str, Any]:
    expected = read_json(manifest_path(root, candidate_id), {}) or {}
    if not expected:
        raise RuntimeError(f"unknown candidate: {candidate_id}")
    current = snapshot(root)
    fields = ("repo_root", "branch", "candidate_commit", "index_hash", "dirty_diff_hash", "file_set_hash", "worktree_fingerprint")
    mismatches = {field: {"expected": expected.get(field), "actual": current.get(field)} for field in fields if expected.get(field) != current.get(field)}
    return {
        "candidate_id": expected["candidate_id"], "task_id": expected["task_id"],
        "result": "STALE" if mismatches else "PASS", "writable": False,
        "candidate_fingerprint": expected.get("candidate_fingerprint"), "mismatches": mismatches,
        "rule": "any change requires a new candidate_id and invalidates prior review evidence",
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("freeze"); p.add_argument("--candidate-id", required=True); p.add_argument("--task-id", required=True); p.add_argument("--review-source", default="independent-review")
    p = sub.add_parser("verify"); p.add_argument("--candidate-id", required=True)
    args = parser.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        with state_lock(root):
            result = freeze(root, args.candidate_id, args.task_id, args.review_source) if args.cmd == "freeze" else verify(root, args.candidate_id)
        ok = result.get("result", "PASS") == "PASS"
        print(json.dumps({"ok": ok, "result": result}, ensure_ascii=False, indent=2))
        return 0 if ok else 2
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
