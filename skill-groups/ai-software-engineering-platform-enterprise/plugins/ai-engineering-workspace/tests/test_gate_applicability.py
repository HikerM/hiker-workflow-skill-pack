from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from closure_gate import evaluate as closure_evaluate
from dispatch_guard import observe as dispatch_observe
from gate_applicability import GATES, SCHEMA, fingerprint, gate_required, last_applicable_state, plan_for, resolve_existing_or_pending_plan, transition_path, validate_plan
from governance_state import create_task, init_project, load_task, set_change_contract, transition
from task_router import route


def ns(**values):
    return argparse.Namespace(**values)


def plan(goal: str, *, required: set[str], basis: dict[str, bool] | None = None, risk: str = "local") -> dict:
    return {
        "schema_version": SCHEMA,
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "task_intent_fingerprint": fingerprint(goal),
        "deliverable_fingerprint": fingerprint("bounded-test-deliverable"),
        "risk_class": risk,
        "basis": basis or {
            "repository_change": False,
            "runtime_change": False,
            "architecture_impact": False,
            "shared_scope": False,
            "release_impact": False,
            "merge_required": False,
        },
        "gates": {
            gate: {
                "status": "REQUIRED" if gate in required else "NOT_APPLICABLE",
                "reason_code": "TEST_REQUIRED" if gate in required else "TEST_NOT_APPLICABLE",
            }
            for gate in GATES
        },
    }


class GateApplicabilityTests(unittest.TestCase):
    def test_structural_risk_does_not_create_work_when_no_work_exists(self):
        normalized = validate_plan(plan("高风险待判断事项", required=set(), risk="structural"), task_goal="高风险待判断事项")
        self.assertTrue(all(item["status"] == "NOT_APPLICABLE" for item in normalized["gates"].values()))

    def test_structural_risk_deepens_assurance_only_for_existing_work(self):
        goal = "修改一个高风险实现切片"
        candidate = plan(goal, required={"development", "review", "testing"}, risk="structural", basis={
            "repository_change": True,
            "runtime_change": False,
            "architecture_impact": False,
            "shared_scope": False,
            "release_impact": False,
            "merge_required": False,
        })
        normalized = validate_plan(candidate, task_goal=goal)
        self.assertEqual("NOT_APPLICABLE", normalized["gates"]["planning"]["status"])
        self.assertEqual("NOT_APPLICABLE", normalized["gates"]["merge"]["status"])
        self.assertEqual("NOT_APPLICABLE", normalized["gates"]["release"]["status"])

    def test_runtime_and_shared_contract_cannot_skip_assurance(self):
        candidate = plan(
            "修改共享契约",
            required={"development", "merge"},
            basis={
                "repository_change": True,
                "runtime_change": True,
                "architecture_impact": False,
                "shared_scope": False,
                "release_impact": False,
                "merge_required": True,
            },
        )
        contract = {
            "allowed_files": ["src/contract.ts"],
            "public_contract_changes": ["API:v2"],
            "consumers": ["web"],
            "required_tests": ["contract test"],
        }
        with self.assertRaisesRegex(RuntimeError, "SHARED_CONTRACT_REQUIRES_SHARED_SCOPE|REQUIRED_GATE_CANNOT_BE_SKIPPED"):
            validate_plan(candidate, task_goal="修改共享契约", change_contract=contract)

    def test_router_marks_irrelevant_lanes_not_applicable_without_write_lane(self):
        goal = "调查现有事实并输出本地结论"
        applicability = plan(goal, required=set())
        result = route(goal, proposal={
            "architecture": "unknown",
            "client_families": [],
            "risk_class": "local",
            "contract_change": False,
            "gate_applicability": applicability,
        })
        self.assertEqual("ACCEPTED", result["status"])
        lanes = {item["lane"]: item for item in result["lanes"]}
        self.assertNotIn("implementation", lanes)
        self.assertTrue(all(item["status"] == "NOT_APPLICABLE" for item in lanes.values()))

    def test_release_impact_does_not_force_an_unrelated_merge_gate(self):
        goal = "验证既有候选并执行受控交付"
        candidate = plan(
            goal,
            required={"review", "testing", "documentation", "release"},
            basis={
                "repository_change": False,
                "runtime_change": False,
                "architecture_impact": False,
                "shared_scope": False,
                "release_impact": True,
                "merge_required": False,
            },
        )
        normalized = validate_plan(candidate, task_goal=goal, change_contract={})
        task = {"goal": goal, "change_contract": {}, "gate_applicability": normalized}
        self.assertFalse(gate_required(task, "merge"))
        self.assertEqual("Testing", last_applicable_state(task, "release"))

    def test_unresolved_conditional_cannot_execute(self):
        goal = "先判断是否需要额外复验"
        candidate = plan(goal, required=set())
        candidate["gates"]["testing"] = {"status": "CONDITIONAL", "reason_code": "MODEL_DECISION_PENDING"}
        with self.assertRaisesRegex(RuntimeError, "UNRESOLVED_CONDITIONAL_CANNOT_EXECUTE:testing"):
            validate_plan(candidate, task_goal=goal, change_contract={})
        routed = route(goal, proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "local",
            "contract_change": False, "gate_applicability": candidate,
        })
        self.assertEqual("REJECTED", routed["status"])
        self.assertTrue(any("UNRESOLVED_CONDITIONAL_CANNOT_EXECUTE" in item for item in routed["diagnostics"]))

    def test_non_repository_task_can_close_without_feature_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            init_project(root, ns(project_id="PROJECT-A", architecture="unknown", version="1.0.0", database_version="unknown", api_version="unknown"))
            goal = "只读检查并交付结论"
            create_task(root, ns(task_id="KG-001", goal=goal, owner_agent="Planning Agent", branch="feature/KG-001-audit", base_branch="develop", affected_files=[]))
            plan_path = root / "gate-plan.json"
            plan_path.write_text(json.dumps(plan(goal, required=set()), ensure_ascii=False), encoding="utf-8")
            set_change_contract(root, self.contract_args("KG-001", plan_path, allowed_files=[]))
            closed = transition(root, ns(task_id="KG-001", to="Released", agent_role="Master Agent", commit_id=None))
            self.assertEqual("Released", closed["state"])
            self.assertEqual(
                ["Planning", "Development", "Review", "Testing", "MergedPendingCleanup", "Merged"],
                closed["history"][-1]["skipped_not_applicable_states"],
            )

    def test_not_applicable_responsibility_cannot_reserve_a_session(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            init_project(root, ns(project_id="PROJECT-A", architecture="unknown", version="1.0.0", database_version="unknown", api_version="unknown"))
            goal = "只读检查"
            create_task(root, ns(task_id="KG-001", goal=goal, owner_agent="Planning Agent", branch="feature/KG-001-read", base_branch="develop", affected_files=[]))
            applicability = plan(goal, required=set())
            plan_path = root / "gate-plan.json"
            plan_path.write_text(json.dumps(applicability), encoding="utf-8")
            set_change_contract(root, self.contract_args("KG-001", plan_path, allowed_files=[]))
            task_map = route(goal, proposal={
                "architecture": "unknown", "client_families": [], "risk_class": "local",
                "contract_change": False, "gate_applicability": applicability,
            })
            task_map_path = root / ".ai" / "workspace" / "task-map.json"
            task_map_path.parent.mkdir(parents=True, exist_ok=True)
            task_map_path.write_text(json.dumps(task_map), encoding="utf-8")
            result = dispatch_observe(root, ns(
                task_id="KG-001", role="Review Agent", repository=str(root), base_sha="base-a",
                api_result="EMPTY", project_id="PROJECT-A", thread_id=None, client_thread_id=None,
                runtime_status=None, detail="", ownership_lane="review", require_isolated_runtime=False,
            ))
            self.assertEqual("BLOCK_GATE_NOT_APPLICABLE", result["session"]["action"])
            self.assertFalse(result["session"]["reservation_created"])
            self.assertFalse(result["create_allowed"])

    def test_local_repository_change_skips_planning_but_not_development(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            init_project(root, ns(project_id="PROJECT-A", architecture="unknown", version="1.0.0", database_version="unknown", api_version="unknown"))
            goal = "局部修改一个有界文件"
            create_task(root, ns(task_id="KG-001", goal=goal, owner_agent="Planning Agent", branch="feature/KG-001-local", base_branch="develop", affected_files=[]))
            applicability = plan(
                goal,
                required={"development"},
                basis={
                    "repository_change": True,
                    "runtime_change": False,
                    "architecture_impact": False,
                    "shared_scope": False,
                    "release_impact": False,
                    "merge_required": False,
                },
            )
            plan_path = root / "gate-plan.json"
            plan_path.write_text(json.dumps(applicability, ensure_ascii=False), encoding="utf-8")
            set_change_contract(root, self.contract_args("KG-001", plan_path, allowed_files=["README.md"]))
            developed = transition(root, ns(task_id="KG-001", to="Development", agent_role="Developer Agent", commit_id=None))
            self.assertEqual(["Planning"], developed["history"][-1]["skipped_not_applicable_states"])
            released = transition(root, ns(task_id="KG-001", to="Released", agent_role="Master Agent", commit_id=None))
            self.assertEqual("Released", released["state"])

    def test_local_merge_does_not_require_non_applicable_quality_or_document_gates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            goal = "提交局部非运行时修改"
            applicability = plan(
                goal,
                required={"development", "merge"},
                basis={
                    "repository_change": True,
                    "runtime_change": False,
                    "architecture_impact": False,
                    "shared_scope": False,
                    "release_impact": False,
                    "merge_required": True,
                },
            )
            task = {
                "task_id": "KG-001",
                "goal": goal,
                "state": "Development",
                "branch": "main",
                "commits": ["fixture-commit"],
                "change_contract": {"allowed_files": ["README.md"]},
                "gate_applicability": applicability,
                "review": {"status": "PENDING", "records": []},
                "tests": {"status": "PENDING", "records": []},
                "documents": [],
                "artifacts": [],
            }
            result = closure_evaluate(root, task, "merge")
            self.assertTrue(result["ok"], result["failures"])

    def test_present_but_damaged_plan_fails_closed(self):
        task = {
            "goal": "有界任务",
            "change_contract": {},
            "gate_applicability": {"schema_version": SCHEMA, "gates": {}},
        }
        with self.assertRaisesRegex(RuntimeError, "task gate applicability is unsafe"):
            gate_required(task, "testing")

        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_GATE_APPLICABILITY"):
            resolve_existing_or_pending_plan(task, {})

    def test_only_legacy_missing_plan_uses_compatibility_all_required(self):
        legacy = {"goal": "旧任务", "change_contract": {}, "schema_version": "2.0.0"}
        normalized = plan_for(legacy)
        self.assertEqual("RUNTIME_LEGACY_COMPATIBILITY", normalized["authority"])
        self.assertTrue(all(item["status"] == "REQUIRED" for item in normalized["gates"].values()))

    def test_normal_new_task_does_not_use_compatibility_all_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            init_project(root, ns(project_id="PROJECT-A", architecture="unknown", version="1.0.0", database_version="unknown", api_version="unknown"))
            goal = "修改一个明确文件"
            created = create_task(root, ns(
                task_id="KG-001", goal=goal, owner_agent="CONTROL",
                branch="feature/KG-001", base_branch="develop", affected_files=[],
            ))
            self.assertIsNone(created["gate_applicability"])
            self.assertEqual("NEW_TASK_MODEL_PLAN_PENDING", created["gate_plan_origin"])
            transition(root, ns(task_id="KG-001", to="Planning", agent_role="CONTROL", commit_id=None))
            args = self.contract_args("KG-001", root / "unused.json", allowed_files=["README.md"])
            args.gate_plan_file = None
            set_change_contract(root, args)
            planned = load_task(root, "KG-001")
            self.assertEqual("MODEL_STRUCTURED_CONTRACT", planned["gate_plan_origin"])
            statuses = {name: item["status"] for name, item in planned["gate_applicability"]["gates"].items()}
            self.assertEqual("REQUIRED", statuses["development"])
            self.assertEqual("REQUIRED", statuses["merge"])
            self.assertEqual("NOT_APPLICABLE", statuses["architecture"])
            self.assertEqual("NOT_APPLICABLE", statuses["release"])
            self.assertNotIn(
                "COMPATIBILITY_FAIL_CLOSED",
                {item["reason_code"] for item in planned["gate_applicability"]["gates"].values()},
            )

    def contract_args(self, task_id: str, plan_path: Path, *, allowed_files: list[str]) -> argparse.Namespace:
        return ns(
            task_id=task_id,
            agent_role="Planning Agent",
            gate_plan_file=str(plan_path),
            allowed_files=allowed_files,
            allowed_modules=[],
            protected_modules=[],
            public_contract_changes=[],
            behavior_invariants=["现有事实保持一致"] if allowed_files else [],
            characterization_tests=[],
            consumer_tests=[],
            required_tests=[],
            structural_decisions=[],
            consumers=[],
            max_blast_radius=10,
            warn_lines=None,
            block_lines=None,
            warn_growth=None,
            block_growth=None,
            preempt_lines=None,
            responsibility_growth=None,
        )

    def repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "test: init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "branch", "develop"], cwd=root, check=True)
        subprocess.run(["git", "branch", "release"], cwd=root, check=True)


if __name__ == "__main__":
    unittest.main()
