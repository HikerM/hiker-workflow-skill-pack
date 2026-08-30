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
from gate_applicability import GATES, SCHEMA, fingerprint, gate_required, last_applicable_state, transition_path, validate_plan
from governance_state import create_task, init_project, set_change_contract, transition
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
    def test_structural_risk_cannot_skip_any_gate(self):
        with self.assertRaisesRegex(RuntimeError, "REQUIRED_GATE_CANNOT_BE_SKIPPED"):
            validate_plan(plan("高风险变更", required=set(), risk="structural"), task_goal="高风险变更")

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
            },
        )
        normalized = validate_plan(candidate, task_goal=goal, change_contract={})
        task = {"goal": goal, "change_contract": {}, "gate_applicability": normalized}
        self.assertFalse(gate_required(task, "merge"))
        self.assertEqual("Testing", last_applicable_state(task, "release"))

    def test_conditional_gate_is_model_visible_but_cannot_be_silently_skipped(self):
        goal = "先判断是否需要额外复验"
        candidate = plan(goal, required=set())
        candidate["gates"]["testing"] = {"status": "CONDITIONAL", "reason_code": "MODEL_DECISION_PENDING"}
        normalized = validate_plan(candidate, task_goal=goal, change_contract={})
        task = {"goal": goal, "change_contract": {}, "gate_applicability": normalized}
        self.assertTrue(gate_required(task, "testing"))
        with self.assertRaisesRegex(RuntimeError, "required lifecycle gate cannot be skipped: testing"):
            transition_path(task, "Created", "Released", {"Planning"})
        routed = route(goal, proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "local",
            "contract_change": False, "gate_applicability": candidate,
        })
        testing = next(item for item in routed["lanes"] if item["lane"] == "testing")
        self.assertEqual("CONDITIONAL", testing["applicability"])
        self.assertEqual("CONDITIONAL", testing["status"])
        self.assertEqual(0, routed["execution_topology"]["default_new_agent_count"])

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
                required={"development", "merge"},
                basis={
                    "repository_change": True,
                    "runtime_change": False,
                    "architecture_impact": False,
                    "shared_scope": False,
                    "release_impact": False,
                },
            )
            plan_path = root / "gate-plan.json"
            plan_path.write_text(json.dumps(applicability, ensure_ascii=False), encoding="utf-8")
            set_change_contract(root, self.contract_args("KG-001", plan_path, allowed_files=["README.md"]))
            developed = transition(root, ns(task_id="KG-001", to="Development", agent_role="Developer Agent", commit_id=None))
            self.assertEqual(["Planning"], developed["history"][-1]["skipped_not_applicable_states"])
            with self.assertRaisesRegex(RuntimeError, "required lifecycle gate cannot be skipped: merge"):
                transition(root, ns(task_id="KG-001", to="Released", agent_role="Master Agent", commit_id=None))

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
