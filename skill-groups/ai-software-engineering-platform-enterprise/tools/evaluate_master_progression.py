from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "ai-engineering-core" / "scripts"
WORKSPACE = ROOT / "plugins" / "ai-engineering-workspace" / "scripts"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(WORKSPACE))

from bounded_run import run_bounded  # noqa: E402
from convergence_guard import record_progress  # noqa: E402
from dispatch_guard import observe as dispatch_observe  # noqa: E402
from goal_contract import ensure_contract, set_contract  # noqa: E402
from goal_change_transaction import apply_goal_change  # noqa: E402
from governance_state import (  # noqa: E402
    create_task,
    init_project,
    load_task,
    record,
    save_task,
    set_change_contract,
    transition,
)
from session_epoch import record as epoch_record, rotate as epoch_rotate  # noqa: E402
from session_pool import bind as session_bind, plan as session_plan  # noqa: E402
from task_router import route  # noqa: E402
from workspacelib import atomic_json  # noqa: E402


def ns(**values):
    return argparse.Namespace(**values)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def initialize_repo(root: Path) -> None:
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "hiker")
    git(root, "config", "user.name", "Hiker")
    (root / "README.md").write_text("# evaluation\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "chore: initialize evaluation repository")
    git(root, "branch", "develop")
    git(root, "branch", "release")


def project(root: Path, architecture: str = "backend") -> None:
    initialize_repo(root)
    init_project(root, ns(
        project_id="EVAL-PROJECT", architecture=architecture, version="1.0.0",
        database_version="001", api_version="v1",
    ))


def contract_args(task_id: str, allowed: list[str]):
    return ns(
        task_id=task_id, agent_role="Planning Agent", allowed_files=allowed,
        allowed_modules=None, protected_modules=None, public_contract_changes=None,
        behavior_invariants=["现有行为保持"], characterization_tests=[], consumer_tests=[],
        required_tests=["聚焦回归"], consumers=[], max_blast_radius=20,
        warn_lines=None, block_lines=None, warn_growth=None, block_growth=None,
    )


def scenario_small_real_progress() -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project(root)
        set_contract(root, "GOAL-SMALL", "完成一个可验证的局部能力", acceptance_ids=["AC-001"])
        create_task(root, ns(
            task_id="EV-001", goal="实现局部能力", owner_agent="Planning Agent",
            ownership_lane="service", branch="feature/EV-001", base_branch="develop", affected_files=[],
        ))
        transition(root, ns(task_id="EV-001", to="Planning", agent_role="Planning Agent", commit_id=None))
        set_change_contract(root, contract_args("EV-001", ["src/service.py"]))
        task = load_task(root, "EV-001")
        task["convergence"] = {"required": True, "delivery_progress": {"consecutive_governance_only_cycles": 2}}
        save_task(root, task)
        developed = transition(root, ns(task_id="EV-001", to="Development", agent_role="Developer Agent", commit_id=None))
        blocked_without_source = False
        try:
            transition(root, ns(task_id="EV-001", to="Review", agent_role="Developer Agent", commit_id=None))
        except RuntimeError as error:
            blocked_without_source = "commit" in str(error)
        (root / "src").mkdir()
        (root / "src" / "service.py").write_text("def ready():\n    return True\n", encoding="utf-8")
        git(root, "add", "src/service.py")
        git(root, "commit", "-m", "feat: add evaluated capability")
        commit_id = git(root, "rev-parse", "HEAD")
        record(root, ns(
            task_id="EV-001", kind="commit", value=commit_id, status="PASS", command="git commit",
            reason="真实业务源码提交", agent_role="Developer Agent",
        ))
        task = load_task(root, "EV-001")
        record_progress(
            task["convergence"], "business", "完成首个业务源码切片",
            "运行聚焦回归", commit_id,
        )
        save_task(root, task)
        local_route = route("局部实现", proposal={
            "architecture": "backend", "client_families": [], "risk_class": "local",
            "parallel_mode": "auto-safe", "contract_change": False,
        })
        return {
            "ok": all((
                developed["state"] == "Development",
                not developed["convergence"]["delivery_progress"].get("business_source_started", False),
                task["convergence"]["delivery_progress"]["business_source_started"],
                blocked_without_source,
                commit_id in task["commits"],
                not any(item["lane"] == "contract-data" for item in local_route["lanes"]),
                (root / ".ai/runtime/task-contexts/EV-001.md").is_file(),
            )),
            "evidence": {
                "state": task["state"], "real_commit": commit_id[:12],
                "review_blocked_before_real_commit": blocked_without_source,
                "governance_transition_did_not_fake_progress": not developed["convergence"]["delivery_progress"].get("business_source_started", False),
                "business_progress_verified_after_commit": task["convergence"]["delivery_progress"]["business_source_started"],
                "contract_lane_skipped": not any(item["lane"] == "contract-data" for item in local_route["lanes"]),
            },
        }


def scenario_large_dynamic_parallelism() -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project(root)
        task_map = route("大型服务端模块演进", proposal={
            "architecture": "backend", "client_families": [], "risk_class": "structural",
            "parallel_mode": "auto-safe", "contract_change": False,
            "implementation_lanes": [
                {"id": "orders", "surface": "backend-service", "write_scope": ["src/orders"]},
                {"id": "billing", "surface": "backend-service", "write_scope": ["src/billing"]},
                {"id": "orders-read", "surface": "backend-service", "write_scope": ["src/orders/read"]},
            ],
        })
        atomic_json(root / ".ai/workspace/task-map.json", task_map)
        first = session_plan(root, "EVAL-PROJECT", "EV-101", "Developer Agent", str(root), "base", "EMPTY_CONFIRMED", ownership_lane="orders")
        session_bind(root, "EVAL-PROJECT", "EV-101", "Developer Agent", str(root), "base", "thread-orders", None, "RUNNING", ownership_lane="orders")
        second = session_plan(root, "EVAL-PROJECT", "EV-102", "Developer Agent", str(root), "base", "EMPTY_CONFIRMED", ownership_lane="billing")
        session_bind(root, "EVAL-PROJECT", "EV-102", "Developer Agent", str(root), "base", "thread-billing", None, "RUNNING", ownership_lane="billing")
        third = session_plan(root, "EVAL-PROJECT", "EV-103", "Developer Agent", str(root), "base", "EMPTY_CONFIRMED", ownership_lane="infrastructure")
        conflict = dispatch_observe(root, ns(
            task_id="EV-104", role="Developer Agent", repository=str(root), base_sha="base",
            api_result="EMPTY", project_id="EVAL-PROJECT", thread_id=None, client_thread_id=None,
            runtime_status=None, detail="", ownership_lane="orders-read", require_isolated_runtime=False,
        ))
        lanes = {item["lane"]: item for item in task_map["lanes"]}
        return {
            "ok": all((
                first["action"] == "CREATE_THREAD", second["action"] == "CREATE_THREAD",
                third["action"] == "QUEUE", conflict["session"]["action"] == "BLOCK_SCOPE_CONFLICT",
                lanes["orders"]["serial_with"] == ["orders-read"],
            )),
            "evidence": {
                "first_writer": first["action"], "second_writer": second["action"],
                "third_writer": third["action"], "overlap": conflict["session"]["action"],
                "planned_lanes": ["orders", "billing", "orders-read"], "active_limit": 2,
            },
        }


def scenario_long_master_and_output() -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        assessment = epoch_record(root, substantive_turns=40, tool_calls=80, tool_output_chars=120_000, compactions=2)
        checkpoint = root / ".ai" / "runtime" / "checkpoints" / "CP-EPOCH-001.json"
        atomic_json(checkpoint, {"event": "checkpoint", "created_at": "2026-01-01T00:00:00+00:00"})
        rotated = epoch_rotate(root, "CP-EPOCH-001")
        bounded = run_bounded(
            root, "EVAL-LONG-OUTPUT",
            [sys.executable, "-X", "utf8", "-c", "print('x' * 12000)"],
            max_chars=1000, timeout=30,
        )
        return {
            "ok": all((
                assessment["rotation_required"], rotated["epoch"] == 2,
                rotated["last_checkpoint_id"] == ".ai/runtime/checkpoints/CP-EPOCH-001.json", bounded["truncated"],
                Path(root / bounded["evidence_path"]).is_file(),
                (root / ".ai/archive/session-epochs/epoch-0001.json").is_file(),
            )),
            "evidence": {
                "rotation_reasons": assessment["reasons"], "new_epoch": rotated["epoch"],
                "checkpoint": rotated["last_checkpoint_id"], "output_truncated": bounded["truncated"],
                "captured_chars": bounded["captured_chars"], "conversation_excerpt_chars": len(bounded["stdout_excerpt"]),
            },
        }


def scenario_goal_adjustment() -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project(root)
        set_contract(root, "GOAL-ADJUST", "交付初始目标", acceptance_ids=["AC-OLD"])
        create_task(root, ns(
            task_id="EV-201", goal="执行目标", owner_agent="Planning Agent", ownership_lane="service",
            branch="feature/EV-201", base_branch="develop", affected_files=[],
        ))
        direct_revision_blocked = False
        try:
            set_contract(root, "GOAL-ADJUST", "交付调整后的目标", non_goals=["旧扩展"], acceptance_ids=["AC-NEW"])
        except RuntimeError as error:
            direct_revision_blocked = "goal-change" in str(error)
        current = ensure_contract(root)
        plan = {
            "schema_version": "1.0.0",
            "change_kind": "MODIFY",
            "base_goal": {
                "goal_id": current["goal_id"], "revision": current["revision"],
                "fingerprint": current["fingerprint"],
            },
            "new_goal": {
                "goal_id": current["goal_id"], "outcome": "交付调整后的目标",
                "non_goals": ["旧扩展"], "acceptance_ids": ["AC-NEW"],
                "behavior_invariants": [], "constraints": [], "priority_order": [],
            },
            "changed_surface_ids": ["GOAL:ACCEPTANCE"],
            "tasks": [{
                "task_id": "EV-201", "classification": "AFFECTED",
                "impact_summary": "验收条件由 AC-OLD 调整为 AC-NEW",
                "affected_surface_ids": ["GOAL:ACCEPTANCE"], "retained_surface_ids": [],
                "invalidations": {
                    "implementation_route_ids": [], "review_record_ids": [], "test_record_ids": [],
                    "checkpoint_ids": [], "acceptance_ids": [],
                },
                "invalidate_candidate": False, "change_contract_required": True,
            }],
        }
        apply_goal_change(root, plan, "eval-goal-adjustment")
        rebound = load_task(root, "EV-201")
        stale_blocked = False
        try:
            transition(root, ns(task_id="EV-201", to="Planning", agent_role="Planning Agent", commit_id=None))
        except RuntimeError as error:
            stale_blocked = "goal adjustment" in str(error).lower()
        set_change_contract(root, contract_args("EV-201", []))
        planned = transition(root, ns(task_id="EV-201", to="Planning", agent_role="Planning Agent", commit_id=None))
        return {
            "ok": direct_revision_blocked and stale_blocked and rebound["goal_binding"]["revision"] == 2 and planned["state"] == "Planning",
            "evidence": {
                "direct_revision_blocked": direct_revision_blocked,
                "stale_task_blocked": stale_blocked, "rebound_revision": rebound["goal_binding"]["revision"],
                "resumed_state": planned["state"],
            },
        }


SCENARIOS = {
    "small_real_progress": scenario_small_real_progress,
    "large_dynamic_parallelism": scenario_large_dynamic_parallelism,
    "long_master_and_output": scenario_long_master_and_output,
    "goal_adjustment": scenario_goal_adjustment,
}


def evaluate() -> dict:
    results = []
    for name, scenario in SCENARIOS.items():
        started = time.perf_counter()
        try:
            result = scenario()
        except Exception as error:  # noqa: BLE001 - release gate reports bounded scenario failure
            result = {"ok": False, "evidence": {"error": str(error)[:500]}}
        results.append({"scenario": name, "seconds": round(time.perf_counter() - started, 3), **result})
    return {"ok": all(item["ok"] for item in results), "scenario_count": len(results), "results": results}


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
