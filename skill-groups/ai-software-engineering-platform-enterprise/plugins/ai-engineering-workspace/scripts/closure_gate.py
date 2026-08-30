from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from convergence_guard import assess as convergence_assess
from gate_applicability import gate_required, last_applicable_state
from governance_state import verify_quality_lineage
from workspacelib import common_dir, read_json, repo_root, run, safe_id, worktree_fingerprint


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_path(root: Path, task_id: str) -> Path:
    return root / ".ai" / "tasks" / f"{safe_id(task_id)}.json"


def artifact_ok(root: Path, value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} or (root / value).exists() or Path(value).is_absolute() and Path(value).exists()


def evaluate(root: Path, task: dict, phase: str) -> dict:
    failures = []; warnings = []
    binding: dict = {}
    lineage: dict = {}
    git_branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "DETACHED"
    dirty_all = run(["git", "status", "--porcelain"], root, check=False).stdout.splitlines()
    dirty = []
    for row in dirty_all:
        rel = row[3:].split(" -> ")[-1].replace("\\", "/") if len(row) >= 4 else row
        if rel.startswith(".ai/") or rel in {"PROJECT_STATE.md", "CURRENT_CONTEXT.md"}: continue
        dirty.append(row)
    if phase == "merge":
        expected_state = last_applicable_state(task, "merge")
        if task.get("state") != expected_state: failures.append(f"task must be in its last applicable pre-merge state: {expected_state}")
        if not task.get("commits"): failures.append("no implementation commit recorded")
        review_required = gate_required(task, "review")
        testing_required = gate_required(task, "testing")
        if review_required and task.get("review", {}).get("status") != "PASS": failures.append("Review evidence is not PASS")
        if testing_required and (task.get("tests", {}).get("status") != "PASS" or not task.get("tests", {}).get("records")): failures.append("Test evidence is not PASS")
        review_lineage = verify_quality_lineage(root, task, "review", require_live_candidate=True) if review_required else {"ok": True, "binding": {}}
        test_lineage = verify_quality_lineage(root, task, "test", require_live_candidate=True) if testing_required else {"ok": True, "binding": {}}
        lineage = {"review": review_lineage, "test": test_lineage}
        if not review_lineage["ok"]: failures.append("Review evidence is not bound to the current immutable candidate")
        if not test_lineage["ok"]: failures.append("Test evidence is not bound to the current immutable candidate")
        if review_lineage["ok"] and test_lineage["ok"]:
            if review_required and testing_required and review_lineage["binding"].get("candidate_fingerprint") != test_lineage["binding"].get("candidate_fingerprint"):
                failures.append("Review and Test evidence belong to different candidates")
            else:
                applicable_binding = test_lineage["binding"] or review_lineage["binding"]
                binding = {
                    "candidate_id": applicable_binding.get("candidate_id"),
                    "candidate_fingerprint": applicable_binding.get("candidate_fingerprint"),
                    "candidate_commit": applicable_binding.get("candidate_commit"),
                    "goal_fingerprint": applicable_binding.get("goal_fingerprint"),
                    "review_evidence_digest": review_lineage["binding"].get("evidence_digest"),
                    "test_evidence_digest": test_lineage["binding"].get("evidence_digest"),
                }
        if testing_required:
            artifacts = [x for x in task.get("artifacts", []) if artifact_ok(root, str(x.get("value", "")))]
            if not artifacts: failures.append("no verifiable screenshot or log artifact")
        if gate_required(task, "documentation"):
            docs = task.get("documents", [])
            if not any(str(x.get("value")) == "CHANGELOG.md" and x.get("status") == "UPDATED" for x in docs): failures.append("CHANGELOG.md update evidence missing")
            arch = [x for x in docs if str(x.get("value")) == "ARCHITECTURE.md"]
            if not arch or not any(x.get("status") in {"UPDATED", "NOT_APPLICABLE"} and (x.get("status") != "NOT_APPLICABLE" or x.get("reason")) for x in arch): failures.append("ARCHITECTURE.md update or justified NOT_APPLICABLE evidence missing")
        if git_branch != task.get("branch"): failures.append(f"current branch {git_branch} does not match task branch {task.get('branch')}")
        if dirty: failures.append("working tree is not clean")
        if gate_required(task, "architecture"):
            architecture = read_json(root / ".ai" / "evidence" / "architecture-guard" / f"{safe_id(str(task.get('task_id')))}.json", {}) or {}
            current_head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
            if architecture.get("result") not in {"PASS", "PASS_WITH_WARNINGS"}: failures.append("architecture guard evidence is missing or blocked")
            elif architecture.get("head") != current_head or architecture.get("worktree_fingerprint") != worktree_fingerprint(root): failures.append("architecture guard evidence is stale")
        locks = (read_json(common_dir(root) / "ai-engineering/file-locks.json", {}) or {}).get("locks", [])
        held = [x for x in locks if x.get("task_id") == task.get("task_id")]
        if held: failures.append("task still holds file locks")
    else:
        expected_state = last_applicable_state(task, "release")
        if task.get("state") != expected_state: failures.append(f"release gate requires the last applicable state: {expected_state}")
        if task.get("release", {}).get("status") != "PASS": failures.append("release evidence is not PASS")
        if gate_required(task, "merge") and not task.get("merge_commit"): failures.append("merge commit is missing")
        release_report = read_json(root / ".ai" / "evidence" / "release" / "latest.json", {}) or {}
        current_head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
        source_commit = task.get("merge_commit") if gate_required(task, "merge") else current_head
        if release_report.get("result") not in {"PASS", "PASS_WITH_WARNINGS"}: failures.append("current release-readiness report is not PASS")
        elif release_report.get("task_id") != task.get("task_id") or release_report.get("source_commit") != source_commit:
            failures.append("release-readiness report is stale or bound to another task/merge commit")
    convergence = task.get("convergence") or {}
    if convergence.get("required"):
        convergence_report = convergence_assess(convergence, phase)
        failures.extend(f"convergence: {value}" for value in convergence_report["blockers"])
        warnings.extend(f"convergence: {value}" for value in convergence_report["warnings"])
    return {
        "ok": not failures, "phase": phase, "task_id": task.get("task_id"),
        "failures": failures, "warnings": warnings, "checked_at": now(),
        "git_branch": git_branch, "binding": binding, "quality_lineage": lineage,
    }


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--task-id", required=True); ap.add_argument("--phase", choices=["merge", "release"], default="merge"); ap.add_argument("--operation-id"); ap.add_argument("--output", help="deprecated; only the deterministic closure evidence path is accepted"); args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        task = read_json(task_path(root, args.task_id), {}) or {}
        if not task: raise RuntimeError("unknown task")
        if args.output:
            expected = root / ".ai" / "evidence" / f"{safe_id(args.task_id).upper()}-{args.phase}-closure.json"
            supplied = Path(args.output)
            supplied = supplied if supplied.is_absolute() else root / supplied
            if os.path.normcase(os.path.realpath(supplied)) != os.path.normcase(os.path.realpath(expected)):
                raise RuntimeError("custom closure output is disabled; use the deterministic project evidence path")
        operation_id = args.operation_id or "closure-" + hashlib.sha256(
            f"{safe_id(args.task_id)}|{args.phase}|{worktree_fingerprint(root)}".encode("utf-8")
        ).hexdigest()[:32]
        core_scripts = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
        if str(core_scripts) not in sys.path: sys.path.insert(0, str(core_scripts))
        from control_workflow import record_closure
        result = record_closure(root, args.task_id, args.phase, operation_id)
        print(json.dumps({"ok": bool(result.get("closure_ok")), "result": result}, ensure_ascii=False, indent=2))
        return 0 if result.get("closure_ok") else 2
    except (RuntimeError, ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
