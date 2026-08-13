from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from convergence_guard import assess as convergence_assess
from workspacelib import atomic_json, common_dir, read_json, repo_root, run, safe_id, state_lock, worktree_fingerprint


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_path(root: Path, task_id: str) -> Path:
    return root / ".ai" / "tasks" / f"{safe_id(task_id)}.json"


def artifact_ok(root: Path, value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} or (root / value).exists() or Path(value).is_absolute() and Path(value).exists()


def evaluate(root: Path, task: dict, phase: str) -> dict:
    failures = []; warnings = []
    git_branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "DETACHED"
    dirty_all = run(["git", "status", "--porcelain"], root, check=False).stdout.splitlines()
    dirty = []
    for row in dirty_all:
        rel = row[3:].split(" -> ")[-1].replace("\\", "/") if len(row) >= 4 else row
        if rel.startswith(".ai/") or rel in {"PROJECT_STATE.md", "CURRENT_CONTEXT.md"}: continue
        dirty.append(row)
    if phase == "merge":
        if task.get("state") != "Testing": failures.append("task must be in Testing")
        if not task.get("commits"): failures.append("no implementation commit recorded")
        if task.get("review", {}).get("status") != "PASS": failures.append("Review Agent evidence is not PASS")
        if task.get("tests", {}).get("status") != "PASS" or not task.get("tests", {}).get("records"): failures.append("Test Agent evidence is not PASS")
        artifacts = [x for x in task.get("artifacts", []) if artifact_ok(root, str(x.get("value", "")))]
        if not artifacts: failures.append("no verifiable screenshot or log artifact")
        docs = task.get("documents", [])
        if not any(str(x.get("value")) == "CHANGELOG.md" and x.get("status") == "UPDATED" for x in docs): failures.append("CHANGELOG.md update evidence missing")
        arch = [x for x in docs if str(x.get("value")) == "ARCHITECTURE.md"]
        if not arch or not any(x.get("status") in {"UPDATED", "NOT_APPLICABLE"} and (x.get("status") != "NOT_APPLICABLE" or x.get("reason")) for x in arch): failures.append("ARCHITECTURE.md update or justified NOT_APPLICABLE evidence missing")
        if git_branch != task.get("branch"): failures.append(f"current branch {git_branch} does not match task branch {task.get('branch')}")
        if dirty: failures.append("working tree is not clean")
        architecture = read_json(root / ".ai" / "evidence" / "architecture-guard" / f"{safe_id(str(task.get('task_id')))}.json", {}) or {}
        current_head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
        if architecture.get("result") not in {"PASS", "PASS_WITH_WARNINGS"}: failures.append("architecture guard evidence is missing or blocked")
        elif architecture.get("head") != current_head or architecture.get("worktree_fingerprint") != worktree_fingerprint(root): failures.append("architecture guard evidence is stale")
        locks = (read_json(common_dir(root) / "ai-engineering/file-locks.json", {}) or {}).get("locks", [])
        held = [x for x in locks if x.get("task_id") == task.get("task_id")]
        if held: failures.append("task still holds file locks")
    else:
        if task.get("state") != "Merged": failures.append("release gate requires Merged state")
        if task.get("release", {}).get("status") != "PASS": failures.append("release evidence is not PASS")
        if not task.get("merge_commit"): failures.append("merge commit is missing")
    convergence = task.get("convergence") or {}
    if convergence.get("required"):
        convergence_report = convergence_assess(convergence, phase)
        failures.extend(f"convergence: {value}" for value in convergence_report["blockers"])
        warnings.extend(f"convergence: {value}" for value in convergence_report["warnings"])
    return {"ok": not failures, "phase": phase, "task_id": task.get("task_id"), "failures": failures, "warnings": warnings, "checked_at": now(), "git_branch": git_branch}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--task-id", required=True); ap.add_argument("--phase", choices=["merge", "release"], default="merge"); ap.add_argument("--output"); args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        with state_lock(root):
            path = task_path(root, args.task_id); task = read_json(path, {}) or {}
            if not task: raise RuntimeError("unknown task")
            result = evaluate(root, task, args.phase); task.setdefault("closure", {})[args.phase] = "PASS" if result["ok"] else "FAIL"; task.setdefault("history", []).append({"at": now(), "event": f"CLOSURE:{args.phase}:{task['closure'][args.phase]}"}); task["updated_at"] = now(); atomic_json(path, task)
            output = Path(args.output).resolve() if args.output else root / ".ai" / "evidence" / f"{safe_id(args.task_id)}-{args.phase}-closure.json"; atomic_json(output, result)
        print(json.dumps({"ok": result["ok"], "output": str(output), "result": result}, ensure_ascii=False, indent=2)); return 0 if result["ok"] else 2
    except (RuntimeError, ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
