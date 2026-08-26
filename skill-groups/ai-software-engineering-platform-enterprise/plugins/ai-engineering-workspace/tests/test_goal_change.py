from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1]
CORE = PLUGIN.parent / "ai-engineering-core" / "scripts"
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(CORE))

from control_workflow import change_goal  # noqa: E402
from goal_change_transaction import goal_change_status  # noqa: E402
from goal_contract import ensure_contract, set_contract, verify_binding  # noqa: E402
from governance_state import create_task, init_project, load_task, rebind_task_goal, save_task  # noqa: E402
from workspacelib import read_json  # noqa: E402


def ns(**values):
    return argparse.Namespace(**values)


def git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr)


class SimulatedProcessExit(BaseException):
    pass


class GoalChangeClosureTests(unittest.TestCase):
    def setUpProject(self, root: Path) -> None:
        git(root, "init", "-b", "main")
        git(root, "config", "user.email", "hiker")
        git(root, "config", "user.name", "Hiker")
        (root / "seed.txt").write_text("seed\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", "chore: initialize repository")
        git(root, "branch", "develop")
        git(root, "branch", "release")
        init_project(root, ns(
            project_id="PROJECT-A", architecture="hybrid", version="1.0.0",
            database_version="001", api_version="v1",
        ))
        set_contract(root, "GOAL-001", "交付稳定能力", acceptance_ids=["AC-001"])

    def createTask(
        self, root: Path, task_id: str, *, owned=None, consumed=None,
        state: str = "Development", surface: str | None = None,
    ) -> dict:
        task = create_task(root, ns(
            task_id=task_id, goal=f"实现 {task_id}", owner_agent="Planning Agent",
            ownership_lane=task_id.lower(), branch=f"feature/{task_id.lower()}",
            base_branch="develop", affected_files=[],
        ))
        task["state"] = state
        task["change_contract"]["owned_surface_ids"] = owned or []
        task["change_contract"]["consumed_surface_ids"] = consumed or []
        if surface:
            goal = ensure_contract(root)
            binding = {"goal_revision": goal["revision"], "goal_fingerprint": goal["fingerprint"]}
            task["review"] = {
                "status": "PASS", "binding": dict(binding),
                "records": [{"id": f"review-{task_id}", "status": "PASS", "surface_ids": [surface]}],
            }
            task["tests"] = {
                "status": "PASS", "binding": dict(binding),
                "records": [{"id": f"test-{task_id}", "status": "PASS", "surface_ids": [surface]}],
            }
            task["convergence"] = {
                "required": True, "acceptance_revision": 1,
                "criteria": [{"id": "AC-001", "status": "PASS"}],
                "implementation_routes": [{
                    "route_id": f"route-{task_id}", "status": "ACTIVE", "surface_ids": [surface],
                }],
            }
            task["checkpoint_refs"] = [{
                "checkpoint_id": f"cp-{task_id}", "status": "VALID", "surface_ids": [surface],
            }]
        save_task(root, task)
        return load_task(root, task_id)

    @staticmethod
    def entry(
        task_id: str, classification: str, *, affected=None, retained=None,
        invalidate: bool = False, replan: bool = False,
        summary: str = "模型提供的有界语义影响结论",
    ) -> dict:
        invalidations = {
            "implementation_route_ids": [], "review_record_ids": [],
            "test_record_ids": [], "product_evidence_ids": [], "checkpoint_ids": [], "acceptance_ids": [],
        }
        if invalidate:
            invalidations = {
                "implementation_route_ids": [f"route-{task_id}"],
                "review_record_ids": [f"review-{task_id}"],
                "test_record_ids": [f"test-{task_id}"],
                "product_evidence_ids": [],
                "checkpoint_ids": [f"cp-{task_id}"], "acceptance_ids": ["AC-001"],
            }
        return {
            "task_id": task_id, "classification": classification,
            "impact_summary": summary, "affected_surface_ids": affected or [],
            "retained_surface_ids": retained or [], "invalidations": invalidations,
            "invalidate_candidate": False, "change_contract_required": replan,
        }

    @staticmethod
    def plan(root: Path, entries: list[dict], changed: list[str], *, outcome="交付修订后的稳定能力", kind="MODIFY") -> dict:
        current = ensure_contract(root)
        plan = {
            "schema_version": "1.0.0", "change_kind": kind,
            "base_goal": {
                "goal_id": current["goal_id"], "revision": current["revision"],
                "fingerprint": current["fingerprint"],
            },
            "new_goal": {
                "goal_id": current["goal_id"], "outcome": outcome,
                "non_goals": current.get("non_goals") or [],
                "acceptance_ids": current.get("acceptance_ids") or [],
                "behavior_invariants": current.get("behavior_invariants") or [],
                "constraints": current.get("constraints") or [],
                "priority_order": current.get("priority_order") or [],
            },
            "changed_surface_ids": changed, "tasks": entries,
        }
        if kind == "UNDO":
            plan["undo_of_revision"] = current["revision"] - 1
        return plan

    @staticmethod
    def execute(root: Path, plan: dict, operation_id: str, fault=None) -> dict:
        with patch("control_workflow.write_gate", return_value={"suite_fingerprint": "test-suite"}):
            return change_goal(
                root, ns(plan=plan, plan_file=None, operation_id=operation_id),
                fault_injector=fault,
            )

    def test_frontend_change_preserves_database_verified_result(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"], surface="SURFACE:UI")
            database = self.createTask(root, "KG-002", owned=["SURFACE:DB"], surface="SURFACE:DB")
            plan = self.plan(root, [
                self.entry("KG-001", "AFFECTED", affected=["SURFACE:UI"], invalidate=True, replan=True),
                self.entry("KG-002", "UNAFFECTED", retained=["SURFACE:DB"]),
            ], ["SURFACE:UI"])
            result = self.execute(root, plan, "goal-ui-001")
            frontend, carried = load_task(root, "KG-001"), load_task(root, "KG-002")
            self.assertEqual("COMPLETE", result["transaction_status"])
            self.assertEqual("COMPLETE", result["operation_status"])
            self.assertEqual("REPLAN_REQUIRED", frontend["goal_adjustment"]["status"])
            self.assertEqual([], frontend["convergence"]["implementation_routes"])
            self.assertEqual(database["review"]["records"], carried["review"]["records"])
            self.assertEqual(database["tests"]["records"], carried["tests"]["records"])
            self.assertEqual(database["checkpoint_refs"], carried["checkpoint_refs"])
            self.assertEqual(database["state"], carried["state"])
            self.assertTrue(verify_binding(root, carried["goal_binding"])["ok"])
            replay = self.execute(root, plan, "goal-ui-001")
            self.assertTrue(replay["idempotent_replay"])
            events = [item for item in load_task(root, "KG-001")["history"] if item.get("operation_id") == "goal-ui-001"]
            self.assertEqual(1, len(events))

    def test_api_contract_change_invalidates_declared_consumers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["CONTRACT:API-V1"], surface="CONTRACT:API-V1")
            self.createTask(root, "KG-002", consumed=["CONTRACT:API-V1"], surface="CONTRACT:API-V1")
            self.createTask(root, "KG-003", consumed=["CONTRACT:API-V1"], surface="CONTRACT:API-V1")
            entries = [
                self.entry(t, "AFFECTED", affected=["CONTRACT:API-V1"], invalidate=True, replan=True)
                for t in ("KG-001", "KG-002", "KG-003")
            ]
            self.execute(root, self.plan(root, entries, ["CONTRACT:API-V1"]), "goal-api-001")
            for task_id in ("KG-001", "KG-002", "KG-003"):
                task = load_task(root, task_id)
                self.assertEqual("PENDING", task["tests"]["status"])
                self.assertEqual("INVALID", task["tests"]["records"][0]["status"])

    def test_consumer_cannot_be_marked_unaffected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", consumed=["CONTRACT:API-V1"])
            plan = self.plan(root, [self.entry("KG-001", "UNAFFECTED", retained=["SURFACE:UI"])], ["CONTRACT:API-V1"])
            with self.assertRaisesRegex(RuntimeError, "cannot be UNAFFECTED"):
                self.execute(root, plan, "goal-api-invalid")

    def test_superseded_and_review_required_preserve_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            old = self.createTask(root, "KG-001", owned=["SURFACE:OLD"], surface="SURFACE:OLD")
            uncertain = self.createTask(root, "KG-002", owned=["SURFACE:UNKNOWN"], surface="SURFACE:UNKNOWN")
            plan = self.plan(root, [
                self.entry("KG-001", "SUPERSEDED", affected=["SURFACE:OLD"]),
                self.entry("KG-002", "REQUIRES_REVIEW", affected=["SURFACE:UNKNOWN"]),
            ], ["SURFACE:OLD", "SURFACE:UNKNOWN"])
            self.execute(root, plan, "goal-class-001")
            superseded, review = load_task(root, "KG-001"), load_task(root, "KG-002")
            self.assertEqual("SUPERSEDED", superseded["control_status"])
            self.assertEqual(old["review"], superseded["review"])
            self.assertEqual(old["goal_binding"], superseded["goal_binding"])
            self.assertEqual("REVIEW_REQUIRED", review["control_status"])
            self.assertEqual(uncertain["tests"], review["tests"])
            self.assertEqual("REQUIRES_REVIEW", review["goal_adjustment"]["status"])

    def test_supported_requirement_change_kinds_use_same_structured_protocol(self):
        for index, kind in enumerate(("ADD", "REMOVE", "MODIFY", "ARCHITECTURE", "STACK_MIGRATION")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                root = Path(td); self.setUpProject(root)
                self.createTask(root, "KG-001", owned=["SURFACE:SYSTEM"])
                plan = self.plan(
                    root,
                    [self.entry("KG-001", "AFFECTED", affected=["SURFACE:SYSTEM"], replan=True)],
                    ["SURFACE:SYSTEM"], kind=kind, outcome=f"{kind} 后目标",
                )
                self.assertEqual(2, self.execute(root, plan, f"goal-kind-{index}")["goal_revision"])

    def test_undo_creates_new_revision_instead_of_rewinding(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            entry = self.entry("KG-001", "AFFECTED", affected=["SURFACE:UI"], replan=True)
            self.execute(root, self.plan(root, [entry], ["SURFACE:UI"], outcome="临时修改"), "goal-undo-prepare")
            invalid = self.plan(root, [entry], ["SURFACE:UI"], outcome="不是归档目标", kind="UNDO")
            with self.assertRaisesRegex(RuntimeError, "archived target revision"):
                self.execute(root, invalid, "goal-undo-invalid")
            undo = self.plan(root, [entry], ["SURFACE:UI"], outcome="交付稳定能力", kind="UNDO")
            result = self.execute(root, undo, "goal-undo-final")
            self.assertEqual(3, result["goal_revision"])
            self.assertEqual("交付稳定能力", ensure_contract(root)["outcome"])
            self.assertTrue((root / ".ai/archive/goal-contracts/GOAL-001-r2.json").exists())

    def test_completed_unaffected_task_remains_completed_with_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            completed = self.createTask(root, "KG-001", owned=["SURFACE:DB"], surface="SURFACE:DB", state="Released")
            plan = self.plan(root, [self.entry("KG-001", "UNAFFECTED", retained=["SURFACE:DB"])], ["SURFACE:UI"])
            self.execute(root, plan, "goal-completed-001")
            current = load_task(root, "KG-001")
            self.assertEqual("Released", current["state"])
            self.assertEqual(completed["tests"]["records"], current["tests"]["records"])
            self.assertEqual("PASS", current["tests"]["status"])

    def test_completed_affected_task_requires_review_or_follow_up(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:DB"], state="Released")
            plan = self.plan(root, [
                self.entry("KG-001", "AFFECTED", affected=["SURFACE:DB"], replan=True),
            ], ["SURFACE:DB"])
            with self.assertRaisesRegex(RuntimeError, "is closed"):
                self.execute(root, plan, "goal-closed-affected")

    def test_ui_goal_change_stales_only_affected_product_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            task = self.createTask(root, "KG-001", owned=["UI:RECORDS", "UI:DETAILS"])
            goal = ensure_contract(root)
            task["product_evidence"] = {
                "status": "PASS",
                "binding": {"goal_revision": goal["revision"], "goal_fingerprint": goal["fingerprint"]},
                "records": [
                    {"id": "visual-records", "status": "PASS", "surface_ids": ["UI:RECORDS"], "evidence_type": "VISUAL_FIDELITY"},
                    {"id": "visual-courses", "status": "PASS", "surface_ids": ["UI:COURSES"], "evidence_type": "VISUAL_FIDELITY"},
                ],
            }
            save_task(root, task)
            entry = self.entry("KG-001", "AFFECTED", affected=["UI:RECORDS"], replan=True)
            entry["invalidations"]["product_evidence_ids"] = ["visual-records"]
            self.execute(root, self.plan(root, [entry], ["UI:RECORDS"]), "goal-ui-product")
            current = load_task(root, "KG-001")
            records = {item["id"]: item for item in current["product_evidence"]["records"]}
            self.assertEqual("STALE", records["visual-records"]["status"])
            self.assertEqual("PASS", records["visual-courses"]["status"])
            self.assertEqual("PARTIAL", current["product_evidence"]["status"])

    def test_unaffected_ui_task_rebinds_without_losing_product_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            task = self.createTask(root, "KG-001", owned=["UI:COURSES"])
            goal = ensure_contract(root)
            task["product_evidence"] = {
                "status": "PASS",
                "binding": {"goal_revision": goal["revision"], "goal_fingerprint": goal["fingerprint"]},
                "records": [{"id": "visual-courses", "status": "PASS", "surface_ids": ["UI:COURSES"]}],
            }
            save_task(root, task)
            before = load_task(root, "KG-001")["product_evidence"]["records"]
            self.execute(root, self.plan(root, [self.entry("KG-001", "UNAFFECTED", retained=["UI:DETAILS"])], ["UI:RECORDS"]), "goal-ui-unaffected")
            current = load_task(root, "KG-001")
            self.assertEqual(before, current["product_evidence"]["records"])
            self.assertEqual(2, current["product_evidence"]["binding"]["goal_revision"])

    def test_ui_goal_change_recovers_mid_transaction_without_double_staling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            for task_id, surface in (("KG-001", "UI:RECORDS"), ("KG-002", "UI:DETAILS")):
                task = self.createTask(root, task_id, owned=[surface])
                goal = ensure_contract(root)
                task["product_evidence"] = {
                    "status": "PASS", "binding": {"goal_revision": goal["revision"], "goal_fingerprint": goal["fingerprint"]},
                    "records": [{"id": f"visual-{task_id}", "status": "PASS", "surface_ids": [surface]}],
                }
                save_task(root, task)
            affected = self.entry("KG-001", "AFFECTED", affected=["UI:RECORDS"], replan=True)
            affected["invalidations"]["product_evidence_ids"] = ["visual-KG-001"]
            plan = self.plan(root, [affected, self.entry("KG-002", "UNAFFECTED", retained=["UI:DETAILS"])], ["UI:RECORDS"])

            def crash(stage: str) -> None:
                if stage == "after_task:KG-001":
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                self.execute(root, plan, "goal-ui-crash", crash)
            self.execute(root, plan, "goal-ui-crash")
            records = load_task(root, "KG-001")["product_evidence"]["records"]
            self.assertEqual(1, sum(1 for item in records if item["status"] == "STALE"))

    def test_damaged_active_transaction_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            task = self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            marker = root / ".ai/governance/goal-change-active.json"
            marker.write_text("{broken", encoding="utf-8")
            self.assertEqual("GOAL_CHANGE_STATE_DAMAGED", verify_binding(root, task["goal_binding"])["status"])

    def test_text_does_not_override_structured_classification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:DB"])
            plan = self.plan(root, [self.entry(
                "KG-001", "UNAFFECTED", retained=["SURFACE:DB"],
                summary="历史讨论提到 API、数据库和技术栈迁移，但结构化分类仍为不受影响",
            )], ["SURFACE:UI"])
            result = self.execute(root, plan, "goal-no-keywords")
            self.assertEqual(1, result["classifications"]["UNAFFECTED"])

    def test_plan_must_classify_every_bounded_project_task(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            self.createTask(root, "KG-002", owned=["SURFACE:DB"])
            plan = self.plan(root, [self.entry("KG-001", "AFFECTED", affected=["SURFACE:UI"], replan=True)], ["SURFACE:UI"])
            with self.assertRaisesRegex(RuntimeError, "cover the bounded task index"):
                self.execute(root, plan, "goal-incomplete-plan")

    def test_direct_revision_and_direct_rebind_are_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            with self.assertRaisesRegex(RuntimeError, "must use hikerctl goal-change"):
                set_contract(root, "GOAL-001", "绕过事务的目标")
            with self.assertRaisesRegex(RuntimeError, "direct task goal rebind is disabled"):
                rebind_task_goal(root, ns(task_id="KG-001"))

    def test_crash_after_prepared_resumes_same_operation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            plan = self.plan(root, [self.entry("KG-001", "AFFECTED", affected=["SURFACE:UI"], replan=True)], ["SURFACE:UI"])

            def crash(stage: str) -> None:
                if stage == "after_prepare":
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                self.execute(root, plan, "goal-crash-prepared", crash)
            status = goal_change_status(root, "goal-crash-prepared")
            self.assertEqual([], status["projected"])
            self.assertEqual(["KG-001"], status["pending"])
            result = self.execute(root, plan, "goal-crash-prepared")
            self.assertTrue(result["recovered_after_interruption"])
            self.assertEqual(2, ensure_contract(root)["revision"])

    def test_crash_between_tasks_reports_progress_and_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            self.createTask(root, "KG-002", owned=["SURFACE:DB"])
            plan = self.plan(root, [
                self.entry("KG-001", "AFFECTED", affected=["SURFACE:UI"], replan=True),
                self.entry("KG-002", "UNAFFECTED", retained=["SURFACE:DB"]),
            ], ["SURFACE:UI"])

            def crash(stage: str) -> None:
                if stage == "after_task:KG-001":
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                self.execute(root, plan, "goal-crash-middle", crash)
            status = goal_change_status(root, "goal-crash-middle")
            self.assertEqual(["KG-001"], status["projected"])
            self.assertEqual(["KG-002"], status["pending"])
            self.assertTrue(status["safe_to_resume"])
            self.assertEqual(
                "GOAL_CHANGE_IN_PROGRESS",
                verify_binding(root, load_task(root, "KG-002")["goal_binding"])["status"],
            )
            result = self.execute(root, plan, "goal-crash-middle")
            self.assertTrue(result["recovered_after_interruption"])
            for task_id in ("KG-001", "KG-002"):
                events = [item for item in load_task(root, task_id)["history"] if item.get("operation_id") == "goal-crash-middle"]
                self.assertEqual(1, len(events))

    def test_crash_after_goal_activation_does_not_replay_projection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.setUpProject(root)
            self.createTask(root, "KG-001", owned=["SURFACE:UI"])
            plan = self.plan(root, [self.entry("KG-001", "AFFECTED", affected=["SURFACE:UI"], replan=True)], ["SURFACE:UI"])

            def crash(stage: str) -> None:
                if stage == "after_contract":
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                self.execute(root, plan, "goal-crash-committed", crash)
            self.assertEqual(2, ensure_contract(root)["revision"])
            result = self.execute(root, plan, "goal-crash-committed")
            self.assertTrue(result["recovered_after_interruption"])
            events = [item for item in load_task(root, "KG-001")["history"] if item.get("operation_id") == "goal-crash-committed"]
            self.assertEqual(1, len(events))
            marker = read_json(root / ".ai/governance/goal-change-active.json", {})
            self.assertEqual("COMPLETE", marker["status"])

    def test_schema_declares_four_classifications_and_closed_objects(self):
        schema = json.loads((PLUGIN / "schemas" / "goal-change-plan.schema.json").read_text(encoding="utf-8"))
        classification = schema["$defs"]["taskClassification"]
        self.assertFalse(classification["additionalProperties"])
        self.assertEqual(
            {"AFFECTED", "UNAFFECTED", "SUPERSEDED", "REQUIRES_REVIEW"},
            set(classification["properties"]["classification"]["enum"]),
        )


if __name__ == "__main__":
    unittest.main()
