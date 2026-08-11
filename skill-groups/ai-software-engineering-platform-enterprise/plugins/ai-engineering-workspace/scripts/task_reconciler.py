from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, common_dir, read_json, repo_root, run
from worktree_inventory import inventory


CLOSED = {"Merged", "Released"}
ACTIVE = {"Planning", "Development", "Review", "Testing", "MergedPendingCleanup"}


def git_branches(root: Path) -> set[str]:
    result = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], root, check=False)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def git_worktrees(root: Path) -> list[dict[str, str]]:
    result = run(["git", "worktree", "list", "--porcelain"], root, check=False)
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


def tasks(root: Path) -> list[dict[str, Any]]:
    return [data for path in sorted((root / ".ai" / "tasks").glob("*.json")) if (data := read_json(path, {}))]


def _expired(value: Any) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) < datetime.now(timezone.utc)
    except ValueError:
        return False


def reconcile(path: Path, write_report: bool = False, mode: str = "quick", phase: str = "development") -> dict[str, Any]:
    root = repo_root(path)
    project = read_json(root / ".ai" / "governance" / "project-state.json", {}) or {}
    records = tasks(root)
    branches = git_branches(root)
    stock = inventory(root, mode)
    worktrees = [{"worktree": item.get("path", ""), "branch": f"refs/heads/{item.get('branch')}" if item.get("branch") else "", **item} for item in stock["entries"]]
    task_by_branch = {item.get("branch"): item for item in records if item.get("branch") and item.get("state") not in CLOSED}
    branch_worktrees = {item.get("branch", "").removeprefix("refs/heads/"): item.get("worktree") for item in worktrees if item.get("branch")}
    findings: list[dict[str, str]] = []

    for item in records:
        task_id, branch, state = str(item.get("task_id", "unknown")), str(item.get("branch", "")), str(item.get("state", ""))
        if state in ACTIVE and branch and branch not in branches:
            findings.append({"severity": "BLOCK", "type": "TASK_BRANCH_MISSING", "task_id": task_id, "detail": branch})
        elif state == "Development" and branch and branch not in branch_worktrees:
            findings.append({"severity": "WARN", "type": "DEVELOPMENT_WORKTREE_MISSING", "task_id": task_id, "detail": branch})
        if state in CLOSED and branch and branch in branch_worktrees:
            severity = "BLOCK" if phase in {"merge", "release"} else "WARN"
            findings.append({"severity": severity, "type": "CLOSED_TASK_WORKTREE", "task_id": task_id, "detail": f"{branch} -> {branch_worktrees[branch]}"})

    primary = str(root.resolve()).casefold()
    for item in worktrees:
        branch = item.get("branch", "").removeprefix("refs/heads/")
        worktree = str(Path(item.get("worktree", "")).resolve()).casefold() if item.get("worktree") else ""
        if item.get("nested"):
            findings.append({"severity": "BLOCK", "type": "NESTED_WORKTREE", "task_id": "", "detail": f"{branch} -> {item.get('worktree', '')}"})
        if worktree != primary and branch and branch not in task_by_branch:
            severity = "BLOCK" if phase in {"create", "release"} else "WARN"
            findings.append({"severity": severity, "type": "ORPHAN_WORKTREE", "task_id": "", "detail": f"{branch} -> {item.get('worktree', '')}"})

    lock_path = common_dir(root) / "ai-engineering" / "file-locks.json"
    task_ids = {str(item.get("task_id")) for item in records if item.get("state") not in CLOSED}
    for lock in (read_json(lock_path, {}) or {}).get("locks", []):
        lock_task = str(lock.get("task_id", ""))
        if lock_task and lock_task not in task_ids:
            findings.append({"severity": "BLOCK", "type": "STALE_FILE_LOCK", "task_id": lock_task, "detail": str(lock.get("path", ""))})

    active_writes = [item for item in records if item.get("state") == "Development" and item.get("control_status") == "ACTIVE"]
    merge_debt = [item for item in records if item.get("state") in {"Review", "Testing", "MergedPendingCleanup"}]
    budget = project.get("parallel_budget", {})
    max_writes = int(budget.get("max_active_write_tasks", 2))
    max_debt = int(budget.get("max_merge_debt", 2))
    open_tasks = [item for item in records if item.get("state") not in CLOSED]
    max_open = int(budget.get("max_total_active_tasks", 5))
    if len(active_writes) > max_writes:
        findings.append({"severity": "BLOCK", "type": "PARALLEL_WRITE_BUDGET", "task_id": "", "detail": f"{len(active_writes)}/{max_writes}"})
    if len(merge_debt) > max_debt:
        findings.append({"severity": "BLOCK", "type": "MERGE_DEBT_BUDGET", "task_id": "", "detail": f"{len(merge_debt)}/{max_debt}"})
    if len(open_tasks) > max_open:
        findings.append({"severity": "BLOCK", "type": "OPEN_TASK_BUDGET", "task_id": "", "detail": f"{len(open_tasks)}/{max_open}"})
    if stock["summary"]["active_managed"] > stock["summary"]["max_active_write_worktrees"]:
        findings.append({"severity": "BLOCK", "type": "ACTIVE_WORKTREE_BUDGET", "task_id": "", "detail": f"{stock['summary']['active_managed']}/{stock['summary']['max_active_write_worktrees']}"})
    runtime = read_json(common_dir(root) / "ai-engineering" / "workspace.json", {}) or {}
    for branch, lease in runtime.get("leases", {}).items():
        expires = lease.get("lease_expires_at") or lease.get("review_due_at")
        if _expired(expires):
            severity = "BLOCK" if phase == "create" else "WARN"
            findings.append({"severity": severity, "type": "STALE_WORKTREE_LEASE", "task_id": str(lease.get("task_id") or lease.get("worktree_id") or ""), "detail": f"{branch} expired {expires}"})

    report = {
        "schema_version": "1.0.0",
        "project_id": project.get("project_id"),
        "summary": {
            "tasks": len(records),
            "active_write_tasks": len(active_writes),
            "merge_debt": len(merge_debt),
            "open_tasks": len(open_tasks),
            "worktrees": len(worktrees),
            "managed_worktrees": stock["summary"]["managed"],
            "unmanaged_worktrees": stock["summary"]["unmanaged"],
            "nested_worktrees": stock["summary"]["nested"],
            "prunable_worktrees": stock["summary"]["prunable"],
            "blockers": sum(1 for item in findings if item["severity"] == "BLOCK"),
            "warnings": sum(1 for item in findings if item["severity"] == "WARN"),
        },
        "findings": findings,
        "inventory_digest": stock["digest"],
        "mode": mode,
        "phase": phase,
        "ok": not any(item["severity"] == "BLOCK" for item in findings),
    }
    if write_report:
        atomic_json(root / ".ai" / "evidence" / "task-reconciliation.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--mode", choices=("quick", "standard", "deep"), default="quick")
    parser.add_argument("--phase", choices=("development", "create", "merge", "release"), default="development")
    args = parser.parse_args()
    try:
        report = reconcile(Path(args.root).resolve(), args.write_report, args.mode, args.phase)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
