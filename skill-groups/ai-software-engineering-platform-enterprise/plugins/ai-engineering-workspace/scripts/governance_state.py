from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, effective_budget, load_state, locked_state, read_json, repo_root, run, safe_id, state_lock, worktree_fingerprint
from bounded_context import crop, ensure_policy, retain_checkpoints
from convergence_guard import assess as convergence_assess
from gate_applicability import default_plan as default_gate_plan
from gate_applicability import gate_required, last_applicable_state, load_plan as load_gate_plan, transition_path, validate_plan as validate_gate_plan
from goal_contract import ensure_contract as ensure_goal_contract, task_binding, verify_binding
from governance_documents import ensure_supporting_docs, render_context, render_project_state
from governance_quality import quality_lineage, verify_quality_lineage
from implementation_guard import enforce_registry as enforce_implementation_registry
from task_router import execution_class_for

SCHEMA = "2.0.0"
TASK_STATES = ["Created", "Planning", "Development", "Review", "Testing", "MergedPendingCleanup", "Merged", "Released"]
TRANSITIONS = {
    "Created": {"Planning"},
    "Planning": {"Development"},
    "Development": {"Review"},
    "Review": {"Development", "Testing"},
    "Testing": {"Development", "MergedPendingCleanup"},
    "MergedPendingCleanup": {"Merged"},
    "Merged": {"Released"},
    "Released": set(),
}
TARGET_EXECUTION_CLASSES = {
    "Planning": {"CONTROL"},
    "Development": {"CONTROL", "WRITE", "ASSURE"},
    "Review": {"CONTROL", "WRITE"},
    "Testing": {"CONTROL", "ASSURE"},
    "MergedPendingCleanup": {"CONTROL"},
    "Merged": {"CONTROL"},
    "Released": {"CONTROL"},
}
RECORD_EXECUTION_CLASSES = {
    "commit": {"WRITE", "CONTROL"},
    "review": {"ASSURE"},
    "test": {"ASSURE"},
    "release": {"CONTROL"},
    "artifact": {"WRITE", "ASSURE"},
    "document": {"CONTROL"},
    "decision": {"CONTROL"},
    "prohibition": {"CONTROL", "ASSURE"},
    "risk": {"CONTROL", "WRITE", "ASSURE"},
    "completed": {"WRITE", "CONTROL"},
    "pending": {"CONTROL", "WRITE", "ASSURE"},
}
RECORD_STATES = {"commit": {"Development"}, "review": {"Review"}, "test": {"Testing"}, "release": {"Merged"}}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_snapshot(root: Path) -> dict[str, Any]:
    branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip() or "DETACHED"
    head = run(["git", "rev-parse", "HEAD"], root, check=False).stdout.strip() or None
    dirty = run(["git", "status", "--porcelain"], root, check=False).stdout.splitlines()
    return {"branch": branch, "head": head, "dirty": dirty}


def state_file(root: Path) -> Path:
    return root / ".ai" / "governance" / "project-state.json"


def task_file(root: Path, task_id: str) -> Path:
    return root / ".ai" / "tasks" / f"{safe_id(task_id)}.json"


def task_index_file(root: Path) -> Path:
    return root / ".ai" / "governance" / "task-index.json"


def task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"), "goal": crop(task.get("goal"), 240), "state": task.get("state"),
        "control_status": task.get("control_status"), "owner_agent": task.get("owner_agent"),
        "branch": task.get("branch"), "ownership_lane": task.get("ownership_lane", "default"),
        "goal_revision": (task.get("goal_binding") or {}).get("revision"), "updated_at": task.get("updated_at"),
    }


@locked_state
def update_task_index(root: Path, task: dict[str, Any]) -> None:
    path = task_index_file(root); index = read_json(path, {}) or {}
    summaries = [item for item in index.get("tasks", []) if isinstance(item, dict) and item.get("task_id") != task.get("task_id")]
    summaries.append(task_summary(task)); summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    active = [item for item in summaries if item.get("state") not in {"Merged", "Released"}]
    closed = [item for item in summaries if item.get("state") in {"Merged", "Released"}]
    keep_closed = ensure_policy(root)["max_task_index_closed"]; overflow = closed[keep_closed:]
    chain = str(index.get("compacted_hash_chain") or ""); compacted = int(index.get("compacted_closed_count") or 0)
    for item in reversed(overflow):
        digest = hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        chain = hashlib.sha256(f"{chain}|{item.get('task_id')}|{digest}".encode("utf-8")).hexdigest(); compacted += 1
    atomic_json(path, {
        "schema_version": SCHEMA, "tasks": active + closed[:keep_closed],
        "active_count": len(active), "retained_closed_count": min(len(closed), keep_closed),
        "compacted_closed_count": compacted, "compacted_hash_chain": chain or None,
        "facts_source": ".ai/tasks/*.json", "updated_at": now(),
    })


def load_project(root: Path) -> dict[str, Any]:
    data = read_json(state_file(root), {}) or {}
    if not data:
        raise RuntimeError("project governance is not initialized; run init first")
    return data


def load_task(root: Path, task_id: str) -> dict[str, Any]:
    data = read_json(task_file(root, task_id), {}) or {}
    if not data:
        raise RuntimeError(f"unknown task: {task_id}")
    return data


@locked_state
def save_task(root: Path, task: dict[str, Any]) -> None:
    task["updated_at"] = now()
    compact_task_history(root, task)
    atomic_json(task_file(root, str(task["task_id"])), task)
    update_task_index(root, task)


def all_tasks(root: Path) -> list[dict[str, Any]]:
    folder = root / ".ai" / "tasks"
    return [read_json(path, {}) or {} for path in sorted(folder.glob("*.json"))] if folder.exists() else []


def indexed_task_summaries(root: Path, include_closed: bool = False) -> list[dict[str, Any]]:
    index = read_json(task_index_file(root), {}) or {}
    summaries = [item for item in index.get("tasks", []) if isinstance(item, dict)]
    if include_closed:
        return summaries
    return [item for item in summaries if item.get("state") not in {"Merged", "Released"}]


def indexed_tasks(root: Path, include_closed: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    summaries = indexed_task_summaries(root, include_closed)[:limit]
    if summaries or task_index_file(root).exists():
        return [load_task(root, str(item["task_id"])) for item in summaries if item.get("task_id") and task_file(root, str(item["task_id"])).is_file()]
    return all_tasks(root)[:limit]


def compact_task_history(root: Path, task: dict[str, Any]) -> None:
    policy = ensure_policy(root)
    limit = int(policy.get("max_task_history_events", 40))
    history = list(task.get("history") or [])
    if len(history) <= limit:
        return
    pruned = history[:-limit]
    archive = root / ".ai" / "archive" / "task-history" / f"{safe_id(str(task.get('task_id')))}.jsonl"
    archive.parent.mkdir(parents=True, exist_ok=True)
    ledger = dict(task.get("history_archive") or {})
    chain = str(ledger.get("hash_chain") or "")
    with archive.open("a", encoding="utf-8", newline="\n") as handle:
        for event in pruned:
            raw = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            chain = hashlib.sha256(f"{chain}|{raw}".encode("utf-8")).hexdigest()
            handle.write(raw + "\n")
    task["history"] = history[-limit:]
    task["history_archive"] = {
        "count": int(ledger.get("count") or 0) + len(pruned),
        "hash_chain": chain,
        "path": archive.relative_to(root).as_posix(),
    }


@locked_state
def init_project(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(root)
    existing = read_json(state_file(root), {}) or {}
    parallel_budget = effective_budget("task", existing.get("parallel_budget", {}))
    session_budget = effective_budget("execution", existing.get("session_budget", {}))
    project = {
        "schema_version": SCHEMA,
        "project_id": safe_id(args.project_id),
        "architecture": args.architecture,
        "version": args.version,
        "database_version": args.database_version,
        "api_version": args.api_version,
        "pending_issues": existing.get("pending_issues", []),
        "risks": existing.get("risks", []),
        "parallel_budget": parallel_budget,
        "session_budget": session_budget,
        "created_at": existing.get("created_at", now()),
        "updated_at": now(),
    }
    atomic_json(state_file(root), project)
    (root / ".ai" / "tasks").mkdir(parents=True, exist_ok=True)
    (root / ".ai" / "runtime" / "checkpoints").mkdir(parents=True, exist_ok=True)
    ensure_policy(root)
    ensure_goal_contract(root)
    if not task_index_file(root).exists():
        for task in all_tasks(root):
            if task: update_task_index(root, task)
    ensure_supporting_docs(root, args.architecture)
    render_project_state(root, project)
    render_context(root, None)
    return project


@locked_state
def create_task(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    project = load_project(root)
    task_id = safe_id(args.task_id).upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d{3,}", task_id):
        raise RuntimeError("task id must look like KG-001")
    path = task_file(root, task_id)
    if path.exists():
        raise RuntimeError(f"task already exists: {task_id}")
    if args.branch in {"main", "develop", "release"}:
        raise RuntimeError("feature task cannot write a protected branch")
    index = read_json(task_index_file(root), {}) or {}
    indexed = index.get("tasks", []) if isinstance(index.get("tasks"), list) else []
    open_tasks = [item for item in indexed if isinstance(item, dict) and item.get("state") not in {"Merged", "Released"}]
    max_open = effective_budget("task", project.get("parallel_budget", {}))["max_total_active_tasks"]
    if len(open_tasks) >= max_open:
        raise RuntimeError(f"total open task budget exceeded: {len(open_tasks)}/{max_open}")
    task = {
        "schema_version": SCHEMA,
        "project_id": project["project_id"],
        "task_id": task_id,
        "goal": args.goal,
        "goal_binding": task_binding(root, task_id, args.goal),
        "goal_adjustment": {"status": "CURRENT", "change_contract_required": False},
        "state": "Created",
        "control_status": "ACTIVE",
        "owner_agent": args.owner_agent,
        "ownership_lane": getattr(args, "ownership_lane", None) or "default",
        "branch": args.branch,
        "base_branch": args.base_branch,
        "affected_files": args.affected_files or [],
        "change_contract": {
            "allowed_files": args.affected_files or [],
            "allowed_modules": [],
            "protected_modules": [],
            "public_contract_changes": [],
            "behavior_invariants": [],
            "characterization_tests": [],
            "consumer_tests": [],
            "required_tests": [],
            "structural_decisions": [],
            "consumers": [],
            "max_blast_radius": 80,
            "file_growth_budget": {"warn_lines": 400, "block_lines": 700, "warn_growth": 80, "block_growth": 200},
        },
        "gate_applicability": default_gate_plan(args.goal),
        "dependencies": getattr(args, "dependencies", None) or [],
        "commits": [],
        "review": {"status": "PENDING", "records": []},
        "tests": {"status": "PENDING", "records": []},
        "artifacts": [],
        "documents": [],
        "decisions": [],
        "prohibitions": ["WRITE responsibility 不得直接修改 main、develop 或 release", "不得修改未授权或被其他任务锁定的文件"],
        "completed_changes": [],
        "pending_items": [],
        "risks": [],
        "closure": {"merge": "PENDING", "release": "PENDING"},
        "release": {"status": "PENDING", "records": []},
        "convergence": {"required": False},
        "history": [{"at": now(), "event": "CREATED", "agent_role": args.owner_agent}],
        "created_at": now(),
        "updated_at": now(),
    }
    save_task(root, task)
    render_project_state(root, project)
    render_context(root, task)
    return task


@locked_state
def transition(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    goal_check = verify_binding(root, task.get("goal_binding"))
    if not goal_check["ok"]:
        raise RuntimeError("goal contract revision is stale; rebind the task to the current goal before continuing")
    if (task.get("goal_adjustment") or {}).get("status") == "REPLAN_REQUIRED":
        raise RuntimeError("goal adjustment is not reconciled; update the change contract before continuing")
    current, target = task["state"], args.to
    if target in {"Review", "Testing", "MergedPendingCleanup"}:
        enforce_implementation_registry(root)
    skipped_states = transition_path(task, current, target, TRANSITIONS.get(current, set()))
    execution_class = execution_class_for(args.agent_role)
    if execution_class not in TARGET_EXECUTION_CLASSES[target]:
        raise RuntimeError(f"{execution_class or 'UNKNOWN'} responsibility cannot transition a task to {target}")
    if task.get("control_status") == "PAUSED":
        raise RuntimeError("paused task must be resumed before transition")
    if target == "Development":
        contract = task.get("change_contract", {})
        if not (contract.get("allowed_files") or contract.get("allowed_modules")):
            raise RuntimeError("Planning -> Development requires an allowed file or module scope")
        if not contract.get("behavior_invariants"):
            raise RuntimeError("Planning -> Development requires behavior invariants")
        if gate_required(task, "testing") and not contract.get("required_tests"):
            raise RuntimeError("Development with a required Testing gate requires required tests")
        project = load_project(root)
        budget = effective_budget("task", project.get("parallel_budget", {}))
        other_tasks = [item for item in indexed_tasks(root, limit=20) if item.get("task_id") != task.get("task_id")]
        active_writes = [item for item in other_tasks if item.get("state") == "Development" and item.get("control_status") == "ACTIVE"]
        max_writes = int(budget.get("max_active_write_tasks", 2))
        if len(active_writes) >= max_writes:
            raise RuntimeError(f"parallel write budget exceeded: {len(active_writes)}/{max_writes} active Development tasks")
        merge_debt = [item for item in other_tasks if item.get("state") in {"Review", "Testing"}]
        max_debt = int(budget.get("max_merge_debt", 2))
        if len(merge_debt) >= max_debt:
            raise RuntimeError(f"merge debt budget exceeded: {len(merge_debt)}/{max_debt} tasks await closure")
        convergence = task.get("convergence") or {}
        governance_cycles = int((convergence.get("delivery_progress") or {}).get("consecutive_governance_only_cycles", 0))
        if convergence.get("required") and governance_cycles >= 2:
            progress = convergence.setdefault("delivery_progress", {})
            convergence["status"] = "BUSINESS_REQUIRED"
            progress["last_lane"] = "governance"
            progress["last_summary"] = "治理预算已用尽；进入开发不等于业务进展，必须产生新的源码指纹"
            progress["next_business_gate"] = "完成当前Task允许范围内的最小实现与单元验证"
            task["convergence"] = convergence
            task["history"].append({"at": now(), "event": "GOVERNANCE_BUDGET_EXIT_TO_DEVELOPMENT", "agent_role": args.agent_role})
    if target == "Review":
        if gate_required(task, "development") and not task.get("commits"):
            raise RuntimeError("Development -> Review requires at least one commit")
        if gate_required(task, "architecture"):
            evidence = read_json(root / ".ai" / "evidence" / "architecture-guard" / f"{safe_id(str(task['task_id']))}.json", {}) or {}
            snapshot = git_snapshot(root)
            if evidence.get("result") not in {"PASS", "PASS_WITH_WARNINGS"}:
                raise RuntimeError("Review requires architecture guard evidence when the Architecture gate is required")
            if evidence.get("head") != snapshot.get("head") or evidence.get("worktree_fingerprint") != worktree_fingerprint(root):
                raise RuntimeError("architecture guard evidence is stale; rerun it for the current change set")
        candidate = task.get("review_candidate") or {}
        if not candidate.get("candidate_id"):
            raise RuntimeError("Development -> Review requires a frozen immutable candidate")
        from candidate_guard import verify as verify_candidate
        candidate_report = verify_candidate(root, str(candidate["candidate_id"]))
        if candidate_report.get("result") != "PASS":
            raise RuntimeError("review candidate is stale; freeze a new candidate before Review")
        convergence = task.get("convergence") or {}
        if convergence.get("required"):
            report = convergence_assess(convergence, "review")
            if not report["ok"]:
                raise RuntimeError("convergence guard blocks Review: " + "; ".join(report["blockers"]))
    if target == "Testing":
        if gate_required(task, "review"):
            review_lineage = verify_quality_lineage(root, task, "review", require_live_candidate=True)
            if not review_lineage["ok"]:
                raise RuntimeError("Testing requires current review evidence bound to the immutable candidate")
    if target == "MergedPendingCleanup":
        if gate_required(task, "testing") and task.get("tests", {}).get("status") != "PASS":
            raise RuntimeError("merge requires tests PASS when the Testing gate is required")
        if task.get("closure", {}).get("merge") != "PASS":
            raise RuntimeError("merge closure is not PASS")
        review_lineage = verify_quality_lineage(root, task, "review", require_live_candidate=False) if gate_required(task, "review") else {"ok": True, "binding": {}}
        test_lineage = verify_quality_lineage(root, task, "test", require_live_candidate=False) if gate_required(task, "testing") else {"ok": True, "binding": {}}
        closure_binding = (task.get("closure_bindings") or {}).get("merge") or {}
        if not review_lineage["ok"] or not test_lineage["ok"]:
            raise RuntimeError("merge requires each applicable quality gate to be bound to one immutable candidate")
        applicable_binding = test_lineage["binding"] or review_lineage["binding"]
        if applicable_binding and closure_binding.get("candidate_fingerprint") != applicable_binding.get("candidate_fingerprint"):
            raise RuntimeError("merge closure is not bound to the applicable immutable candidate")
        if not args.commit_id:
            raise RuntimeError("MergedPendingCleanup transition requires merge commit id")
        convergence = task.get("convergence") or {}
        if convergence.get("required"):
            report = convergence_assess(convergence, "merge")
            if not report["ok"]:
                raise RuntimeError("convergence guard blocks merge: " + "; ".join(report["blockers"]))
        task["merge_commit"] = args.commit_id
    if target == "Merged":
        from worktree_inventory import inventory
        remaining = [item for item in inventory(root, "quick")["entries"] if not item.get("primary") and item.get("branch") == task.get("branch")]
        runtime = load_state(root)
        registered = [item for key, item in runtime.get("worktrees", {}).items() if key == task.get("task_id") or item.get("task_id") == task.get("task_id")]
        if remaining or registered:
            raise RuntimeError("MergedPendingCleanup -> Merged requires the task worktree to be closed")
    if target == "Released" and gate_required(task, "release") and (task.get("release", {}).get("status") != "PASS" or task.get("closure", {}).get("release") != "PASS"):
        raise RuntimeError("Merged -> Released requires current release review PASS and release closure PASS")
    if target == "Released":
        convergence = task.get("convergence") or {}
        if convergence.get("required"):
            report = convergence_assess(convergence, "release")
            if not report["ok"]:
                raise RuntimeError("convergence guard blocks release: " + "; ".join(report["blockers"]))
    task["state"] = target
    task["history"].append({
        "at": now(), "event": f"STATE:{current}->{target}", "agent_role": args.agent_role,
        "execution_class": execution_class,
        "commit_id": args.commit_id, "operation_id": getattr(args, "operation_id", None),
        "skipped_not_applicable_states": skipped_states,
    })
    save_task(root, task)
    project = load_project(root)
    render_project_state(root, project); render_context(root, task)
    return task


@locked_state
def record(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    if (task.get("goal_adjustment") or {}).get("status") == "REPLAN_REQUIRED":
        raise RuntimeError("goal adjustment is not reconciled; old evidence cannot be recorded as current")
    execution_class = execution_class_for(args.agent_role)
    if execution_class not in RECORD_EXECUTION_CLASSES.get(args.kind, set()):
        raise RuntimeError(f"{execution_class or 'UNKNOWN'} responsibility cannot record {args.kind} evidence")
    allowed_states = RECORD_STATES.get(args.kind)
    if args.kind == "release" and task.get("state") != last_applicable_state(task, "release"):
        raise RuntimeError(f"release evidence requires the last applicable state: {last_applicable_state(task, 'release')}")
    if args.kind != "release" and allowed_states and task.get("state") not in allowed_states:
        raise RuntimeError(f"{args.kind} evidence is not allowed while task state is {task.get('state')}")
    if task.get("control_status") != "ACTIVE":
        raise RuntimeError("task must be ACTIVE before recording evidence")
    item = {"at": now(), "value": args.value, "status": args.status, "command": args.command, "reason": args.reason, "agent_role": args.agent_role, "execution_class": execution_class}
    if args.kind == "commit":
        task["commits"].append(args.value)
    elif args.kind in {"review", "test", "release"}:
        key = "tests" if args.kind == "test" else args.kind
        if args.kind == "release" and (args.status or "").upper() == "PASS":
            report = read_json(root / ".ai" / "evidence" / "release" / "latest.json", {}) or {}
            if report.get("result") not in {"PASS", "PASS_WITH_WARNINGS"}:
                raise RuntimeError("release PASS requires the current release-readiness report")
            expected_commit = task.get("merge_commit") if gate_required(task, "merge") else git_snapshot(root).get("head")
            if report.get("task_id") != task.get("task_id") or report.get("source_commit") != expected_commit:
                raise RuntimeError("release-readiness report is stale or belongs to another task/merge commit")
        if args.kind in {"review", "test"}:
            binding = quality_lineage(root, task)
            digest_basis = {
                "kind": args.kind, "value": args.value, "status": args.status,
                "command": args.command, "reason": args.reason, "binding": binding,
            }
            binding["evidence_digest"] = hashlib.sha256(
                json.dumps(digest_basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            item["binding"] = binding
            task[key]["binding"] = binding
        task[key]["status"] = args.status or "RECORDED"; task[key]["records"].append(item)
    elif args.kind == "artifact": task["artifacts"].append(item)
    elif args.kind == "document": task["documents"].append(item)
    elif args.kind == "decision": task["decisions"].append(args.value)
    elif args.kind == "prohibition": task["prohibitions"].append(args.value)
    elif args.kind == "risk": task["risks"].append(args.value)
    elif args.kind == "completed": task["completed_changes"].append(args.value)
    elif args.kind == "pending": task["pending_items"].append(args.value)
    else: raise RuntimeError(f"unsupported record kind: {args.kind}")
    task["history"].append({"at": now(), "event": f"RECORD:{args.kind}", "agent_role": args.agent_role})
    save_task(root, task); render_context(root, task); render_project_state(root, load_project(root))
    return task


@locked_state
def set_change_contract(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    if execution_class_for(args.agent_role) != "CONTROL":
        raise RuntimeError("CONTROL responsibility is required to set a change contract")
    if task.get("state") not in {"Created", "Planning", "Development"}:
        raise RuntimeError("change contract can only be set before Review")
    original_contract = dict(task.get("change_contract") or {})
    contract = dict(original_contract)
    list_fields = {
        "allowed_files": args.allowed_files,
        "allowed_modules": args.allowed_modules,
        "protected_modules": args.protected_modules,
        "public_contract_changes": args.public_contract_changes,
        "behavior_invariants": args.behavior_invariants,
        "characterization_tests": args.characterization_tests,
        "consumer_tests": args.consumer_tests,
        "required_tests": args.required_tests,
        "structural_decisions": getattr(args, "structural_decisions", None),
        "consumers": args.consumers,
    }
    for key, value in list_fields.items():
        if value is not None:
            contract[key] = list(dict.fromkeys(value))
    if args.max_blast_radius is not None:
        contract["max_blast_radius"] = args.max_blast_radius
    budget = dict(contract.get("file_growth_budget") or {})
    for key in ("warn_lines", "block_lines", "warn_growth", "block_growth", "preempt_lines", "responsibility_growth"):
        value = getattr(args, key, None)
        if value is not None:
            budget[key] = value
    contract["file_growth_budget"] = budget
    gate_plan_file = getattr(args, "gate_plan_file", None)
    if gate_plan_file:
        plan_path = Path(gate_plan_file)
        if not plan_path.is_absolute():
            plan_path = root / plan_path
        plan_path = plan_path.resolve()
        try:
            plan_path.relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError("gate applicability plan must remain inside the project root") from exc
        task["gate_applicability"] = validate_gate_plan(
            load_gate_plan(plan_path), task_goal=str(task.get("goal") or ""), change_contract=contract
        )
    else:
        existing_gate_plan = task.get("gate_applicability") or {}
        if not existing_gate_plan or set((existing_gate_plan.get("gates") or {}).keys()) == set(default_gate_plan()["gates"]) and all(
            isinstance(item, dict) and item.get("reason_code") == "COMPATIBILITY_FAIL_CLOSED"
            for item in (existing_gate_plan.get("gates") or {}).values()
        ):
            existing_gate_plan = default_gate_plan(str(task.get("goal") or ""), contract)
        task["gate_applicability"] = validate_gate_plan(
            existing_gate_plan,
            task_goal=str(task.get("goal") or ""),
            change_contract=contract,
        )
    task["change_contract"] = contract
    task["affected_files"] = contract.get("allowed_files", [])
    adjustment = task.get("goal_adjustment") or {}
    if adjustment.get("status") == "REPLAN_REQUIRED":
        if not verify_binding(root, task.get("goal_binding"))["ok"]:
            raise RuntimeError("current goal must be rebound before updating its change contract")
        adjustment["status"] = "CURRENT"
        adjustment["change_contract_required"] = False
        adjustment["reconciled_at"] = now()
        task["goal_adjustment"] = adjustment
        task["control_status"] = "ACTIVE"
    convergence = task.get("convergence") or {}
    if convergence.get("required") and contract != original_contract:
        convergence["acceptance_revision"] = int(convergence.get("acceptance_revision", 1)) + 1
        convergence["status"] = "WARNING"
        for criterion in convergence.get("criteria", []):
            criterion["status"] = "PENDING"
        convergence.setdefault("events", []).append({
            "at": now(),
            "kind": "acceptance-baseline-invalidated",
            "summary": "变更契约已修改，旧验收证据需要按新修订重新确认",
            "acceptance_revision": convergence["acceptance_revision"],
        })
        convergence["events"] = convergence["events"][-40:]
        task["convergence"] = convergence
    task["history"].append({"at": now(), "event": "CHANGE_CONTRACT_UPDATED", "agent_role": args.agent_role})
    save_task(root, task)
    render_context(root, task)
    return task


@locked_state
def bind_review_candidate(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    if (task.get("goal_adjustment") or {}).get("status") == "REPLAN_REQUIRED":
        raise RuntimeError("goal adjustment is not reconciled; cannot freeze a review candidate")
    if execution_class_for(args.agent_role) not in {"WRITE", "CONTROL"}:
        raise RuntimeError("WRITE or CONTROL responsibility is required to freeze a review candidate")
    if task.get("state") != "Development":
        raise RuntimeError("review candidate can only be frozen in Development")
    from candidate_guard import freeze as freeze_candidate
    candidate = freeze_candidate(root, args.candidate_id, str(task["task_id"]), args.review_source)
    task["review_candidate"] = {
        "candidate_id": candidate["candidate_id"], "candidate_fingerprint": candidate["candidate_fingerprint"],
        "candidate_commit": candidate["candidate_commit"], "worktree_fingerprint": candidate["worktree_fingerprint"],
        "writable": False, "frozen_at": candidate["frozen_at"],
    }
    task["history"].append({"at": now(), "event": "REVIEW_CANDIDATE_FROZEN", "candidate_id": candidate["candidate_id"], "agent_role": args.agent_role})
    save_task(root, task)
    return task


@locked_state
def rebind_task_goal(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    raise RuntimeError(
        "direct task goal rebind is disabled; use hikerctl goal-change so all task classifications share one transaction"
    )


def checkpoint(root: Path, task: dict[str, Any], label: str, operation_id: str | None = None) -> Path:
    git = git_snapshot(root)
    data = {
        "schema_version": SCHEMA, "created_at": now(), "label": label,
        "event": "WorkspaceCheckpoint", "task": task, "git": git,
        "operation_id": safe_id(operation_id) if operation_id else None,
    }
    if operation_id:
        path = root / ".ai" / "runtime" / "checkpoints" / f"control-{safe_id(operation_id)}-{safe_id(task['task_id'])}-{safe_id(label)}.json"
        existing = read_json(path, {}) or {}
        if existing.get("operation_id") == safe_id(operation_id):
            return path
    else:
        stamp = now().replace(":", "-")
        path = root / ".ai" / "runtime" / "checkpoints" / f"{stamp}-{safe_id(task['task_id'])}-{safe_id(label)}.json"
    atomic_json(path, data); render_context(root, task); retain_checkpoints(root, now())
    return path


@locked_state
def control(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(root, args.task_id)
    if args.action == "pause": task["control_status"] = "PAUSED"
    elif args.action == "resume":
        if (task.get("goal_adjustment") or {}).get("status") == "REPLAN_REQUIRED":
            raise RuntimeError("goal adjustment must be reconciled before resume")
        task["control_status"] = "ACTIVE"
    elif args.action == "adjust":
        task["control_status"] = "ADJUSTING"; task["pending_items"].append(f"方向调整：{args.instruction}")
    elif args.action == "insert":
        if not args.new_task_id or not args.branch or not args.instruction:
            raise RuntimeError("insert requires --new-task-id, --branch and --instruction")
        task["pending_items"].append(f"插入需求 {args.new_task_id}：{args.instruction}")
    task["history"].append({
        "at": now(), "event": f"CONTROL:{args.action}", "instruction": args.instruction,
        "agent_role": "Master Agent", "operation_id": getattr(args, "operation_id", None),
    })
    save_task(root, task); path = checkpoint(root, task, args.action, operation_id=getattr(args, "operation_id", None))
    if args.action == "insert":
        inserted = create_task(root, argparse.Namespace(task_id=args.new_task_id, goal=args.instruction, owner_agent="Planning Agent", branch=args.branch, base_branch=args.base_branch, affected_files=[], dependencies=[task["task_id"]]))
        inserted["history"].append({"at": now(), "event": "INSERTED", "agent_role": "Master Agent", "parent_task": task["task_id"]}); save_task(root, inserted); render_context(root, inserted)
        return {"task": task, "inserted_task": inserted, "checkpoint": str(path)}
    return {"task": task, "checkpoint": str(path)}


def validate(root: Path, full: bool = False) -> dict[str, Any]:
    required = ["PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md", ".ai/governance/project-state.json"]
    missing = [name for name in required if not (root / name).exists()]
    issues = []
    tasks = all_tasks(root) if full else indexed_tasks(root, limit=20)
    for task in tasks:
        if task.get("state") not in TASK_STATES: issues.append(f"{task.get('task_id')}: invalid state")
        if task.get("project_id") != (read_json(state_file(root), {}) or {}).get("project_id"): issues.append(f"{task.get('task_id')}: project context mismatch")
    git = git_snapshot(root)
    active = [t for t in tasks if t.get("state") == "Development" and t.get("control_status") == "ACTIVE"]
    if active and git["branch"] in {"main", "develop", "release"}: issues.append("active development task is on a protected branch")
    budget = effective_budget("task", (read_json(state_file(root), {}) or {}).get("parallel_budget", {}))
    if len(active) > int(budget.get("max_active_write_tasks", 2)):
        issues.append("active Development tasks exceed the parallel write budget")
    merge_debt = [t for t in tasks if t.get("state") in {"Review", "Testing"}]
    if len(merge_debt) > int(budget.get("max_merge_debt", 2)):
        issues.append("Review/Testing tasks exceed the merge debt budget")
    open_tasks = [t for t in tasks if t.get("state") not in {"Merged", "Released"}]
    if len(open_tasks) > int(budget.get("max_total_active_tasks", 5)):
        issues.append("open tasks exceed the total active task budget")
    index = read_json(task_index_file(root), {}) or {}
    return {"ok": not missing and not issues, "schema_version": SCHEMA, "missing": missing, "issues": issues, "git": git, "task_count": int(index.get("active_count") or len(open_tasks)) + int(index.get("retained_closed_count") or 0), "scope": "full" if full else "active-index"}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--project-id", required=True); p.add_argument("--architecture", choices=["bs", "cs", "hybrid", "backend"], required=True); p.add_argument("--version", default="0.1.0"); p.add_argument("--database-version", default="unversioned"); p.add_argument("--api-version", default="v1")
    p = sub.add_parser("task-create"); p.add_argument("--task-id", required=True); p.add_argument("--goal", required=True); p.add_argument("--owner-agent", default="Master Agent"); p.add_argument("--ownership-lane", default="default"); p.add_argument("--branch", required=True); p.add_argument("--base-branch", default="develop"); p.add_argument("--affected-files", nargs="*")
    p = sub.add_parser("transition", help="deprecated compatibility entry; delegates to hikerctl"); p.add_argument("--task-id", required=True); p.add_argument("--to", choices=TASK_STATES, required=True); p.add_argument("--agent-role", required=True); p.add_argument("--commit-id"); p.add_argument("--operation-id", required=True)
    p = sub.add_parser("record"); p.add_argument("--task-id", required=True); p.add_argument("--kind", choices=["commit", "review", "test", "artifact", "document", "decision", "prohibition", "risk", "completed", "pending", "release"], required=True); p.add_argument("--value", required=True); p.add_argument("--status"); p.add_argument("--command"); p.add_argument("--reason"); p.add_argument("--agent-role", required=True)
    p = sub.add_parser("contract-set"); p.add_argument("--task-id", required=True); p.add_argument("--agent-role", required=True); p.add_argument("--gate-plan-file"); p.add_argument("--allowed-files", nargs="*"); p.add_argument("--allowed-modules", nargs="*"); p.add_argument("--protected-modules", nargs="*"); p.add_argument("--public-contract-changes", nargs="*"); p.add_argument("--behavior-invariants", nargs="*"); p.add_argument("--characterization-tests", nargs="*"); p.add_argument("--consumer-tests", nargs="*"); p.add_argument("--required-tests", nargs="*"); p.add_argument("--structural-decisions", nargs="*"); p.add_argument("--consumers", nargs="*"); p.add_argument("--max-blast-radius", type=int); p.add_argument("--warn-lines", type=int); p.add_argument("--block-lines", type=int); p.add_argument("--warn-growth", type=int); p.add_argument("--block-growth", type=int); p.add_argument("--preempt-lines", type=int); p.add_argument("--responsibility-growth", type=int)
    p = sub.add_parser("candidate-freeze"); p.add_argument("--task-id", required=True); p.add_argument("--candidate-id", required=True); p.add_argument("--review-source", default="independent-review"); p.add_argument("--agent-role", required=True)
    p = sub.add_parser("goal-rebind", help="deprecated compatibility entry; delegates to hikerctl"); p.add_argument("--task-id", required=True); p.add_argument("--agent-role", required=True); p.add_argument("--impact", choices=["affected", "unaffected"], default="affected"); p.add_argument("--impact-summary", required=True); p.add_argument("--retain-change", action="append", default=[]); p.add_argument("--revise-change", action="append", default=[]); p.add_argument("--retire-change", action="append", default=[]); p.add_argument("--operation-id", required=True)
    p = sub.add_parser("checkpoint", help="deprecated compatibility entry; delegates to hikerctl"); p.add_argument("--task-id", required=True); p.add_argument("--label", required=True); p.add_argument("--operation-id", required=True)
    p = sub.add_parser("control", help="deprecated compatibility entry; delegates to hikerctl"); p.add_argument("--task-id", required=True); p.add_argument("--action", choices=["pause", "resume", "adjust", "insert"], required=True); p.add_argument("--instruction", default=""); p.add_argument("--new-task-id"); p.add_argument("--branch"); p.add_argument("--base-branch", default="develop"); p.add_argument("--operation-id", required=True)
    p = sub.add_parser("status"); p.add_argument("--task-id")
    p = sub.add_parser("validate"); p.add_argument("--full", action="store_true")
    args = ap.parse_args(); root = repo_root(Path(args.root).resolve())
    try:
        if args.cmd in {"transition", "goal-rebind", "checkpoint", "control"}:
            core_scripts = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
            if str(core_scripts) not in sys.path:
                sys.path.insert(0, str(core_scripts))
            import control_workflow

            if args.cmd == "transition":
                args.control_action = None; args.instruction = ""; args.new_task_id = None; args.branch = None; args.base_branch = "develop"
                data = control_workflow.transition(root, args)
            elif args.cmd == "goal-rebind":
                data = control_workflow.rebind_goal(root, args)
            elif args.cmd == "checkpoint":
                data = control_workflow.checkpoint(root, args.task_id, args.label, args.operation_id)
            else:
                args.control_action = args.action; args.to = None; args.agent_role = "Master Agent"; args.commit_id = None
                data = control_workflow.transition(root, args)
            print(json.dumps({"ok": True, "result": data}, ensure_ascii=False, indent=2))
            return 0
        with state_lock(root):
            if args.cmd == "init": data = init_project(root, args)
            elif args.cmd == "task-create": data = create_task(root, args)
            elif args.cmd == "record": data = record(root, args)
            elif args.cmd == "contract-set": data = set_change_contract(root, args)
            elif args.cmd == "candidate-freeze": data = bind_review_candidate(root, args)
            elif args.cmd == "status": data = {"project": load_project(root), "task": load_task(root, args.task_id) if args.task_id else None, "task_summaries": indexed_task_summaries(root, include_closed=True), "git": git_snapshot(root)}
            else: data = validate(root, args.full)
        print(json.dumps({"ok": data.get("ok", True) if isinstance(data, dict) else True, "result": data}, ensure_ascii=False, indent=2))
        return 0 if args.cmd != "validate" or data["ok"] else 2
    except (RuntimeError, ValueError, subprocess.CalledProcessError, TimeoutError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(json.dumps({"ok": False, "error": detail}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
