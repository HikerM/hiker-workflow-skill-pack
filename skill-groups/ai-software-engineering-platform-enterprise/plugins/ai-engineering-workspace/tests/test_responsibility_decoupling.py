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

from dispatch_guard import observe as dispatch_observe
from gate_applicability import GATES, SCHEMA, fingerprint
from session_pool import resolved_slot_key, role_family, status as session_status
from task_router import route


def ns(**values):
    return argparse.Namespace(**values)


def applicability(goal: str, required: set[str], risk: str = "local") -> dict:
    repository_change = "development" in required
    return {
        "schema_version": SCHEMA,
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "task_intent_fingerprint": fingerprint(goal),
        "deliverable_fingerprint": fingerprint("e03-fixture"),
        "risk_class": risk,
        "basis": {
            "repository_change": repository_change,
            "runtime_change": "testing" in required,
            "architecture_impact": risk == "structural",
            "shared_scope": risk == "structural",
            "release_impact": risk == "structural",
        },
        "gates": {
            gate: {
                "status": "REQUIRED" if gate in required else "NOT_APPLICABLE",
                "reason_code": "E03_REQUIRED" if gate in required else "E03_NOT_APPLICABLE",
            }
            for gate in GATES
        },
    }


class ResponsibilityDecouplingTests(unittest.TestCase):
    def test_simple_local_task_reuses_current_controller_for_control_and_write(self):
        goal = "执行一个局部有界修改"
        gate_plan = applicability(goal, {"development", "merge"})
        result = route(goal, proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "local",
            "contract_change": False, "gate_applicability": gate_plan,
        })
        topology = result["execution_topology"]
        self.assertEqual(0, topology["default_new_agent_count"])
        self.assertEqual(0, topology["default_new_provider_session_count"])
        self.assertEqual(1, len(topology["bindings"]))
        self.assertEqual({"CONTROL", "WRITE"}, set(topology["bindings"][0]["execution_classes"]))
        lanes = {item["lane"]: item for item in result["lanes"]}
        self.assertEqual("REUSE_CURRENT_PROVIDER_SESSION", lanes["implementation"]["provider_session_policy"])
        self.assertEqual("CURRENT_WORKTREE_IF_SAFE", lanes["implementation"]["worktree_policy"])

    def test_structural_review_and_testing_share_one_independent_assurance_binding(self):
        result = route("结构性服务端变更", proposal={
            "architecture": "backend", "client_families": [], "risk_class": "structural", "contract_change": True,
        })
        topology = result["execution_topology"]
        bindings = {item["binding_id"]: item for item in topology["bindings"]}
        self.assertTrue(topology["independent_assurance_required"])
        self.assertEqual("SEPARATE_PROVIDER_SESSION", bindings["assurance"]["provider_session_policy"])
        self.assertEqual({"REVIEW", "TESTING"}, set(bindings["assurance"]["responsibilities"]))
        self.assertEqual(["ASSURE"], bindings["assurance"]["execution_classes"])

    def test_model_can_raise_assurance_independence_for_bounded_change(self):
        goal = "对有界修改执行独立保证"
        result = route(goal, proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "bounded",
            "contract_change": False, "independent_assurance": True,
            "gate_applicability": applicability(goal, {"development", "review", "merge"}, risk="bounded"),
        })
        self.assertEqual("ACCEPTED", result["status"])
        bindings = {item["binding_id"]: item for item in result["execution_topology"]["bindings"]}
        self.assertEqual("SEPARATE_PROVIDER_SESSION", bindings["assurance"]["provider_session_policy"])
        self.assertEqual("MODEL_PROPOSAL", result["execution_topology"]["assurance_independence_authority"])

    def test_model_cannot_lower_structural_assurance_invariant(self):
        result = route("结构性迁移", proposal={
            "architecture": "backend", "client_families": [], "risk_class": "structural",
            "contract_change": True, "independent_assurance": False,
        })
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual(["ASSURANCE_INDEPENDENCE_REQUIRED_BY_RISK"], result["diagnostics"])

    def test_responsibility_is_not_an_agent_or_session_identity(self):
        result = route("普通后端改动", proposal={
            "architecture": "backend", "client_families": [], "risk_class": "bounded", "contract_change": False,
        })
        for lane in result["lanes"]:
            self.assertIn(lane["execution_class"], {"CONTROL", "WRITE", "ASSURE"})
            self.assertEqual("COMPATIBILITY_RESPONSIBILITY_LABEL", lane["agent_role_semantics"])
            self.assertNotEqual(lane["responsibility"], lane["binding_id"])
        self.assertEqual(
            ["responsibility != agent", "agent != provider session", "provider session != worktree", "worktree != task"],
            result["execution_topology"]["invariants"],
        )

    def test_role_compatibility_collapses_to_three_execution_families(self):
        self.assertEqual("control", role_family("Master Agent"))
        self.assertEqual("control", role_family("Document Agent"))
        self.assertEqual("writer", role_family("Developer Agent"))
        self.assertEqual("assurance", role_family("Review Agent"))
        self.assertEqual("assurance", role_family("Test Agent"))
        self.assertEqual("assurance", role_family("Browser Agent"))

    def test_legacy_master_slot_is_reused_as_control_without_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            state = {"slots": {"legacy-master": {
                "project_id": "PROJECT-A", "repository": str(root), "role_family": "master", "state": "READY",
            }}}
            self.assertEqual("legacy-master", resolved_slot_key(state, "PROJECT-A", str(root), "control"))

    def test_current_session_policy_never_reserves_a_new_slot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            goal = "执行一个局部有界修改"
            task_map = route(goal, proposal={
                "architecture": "unknown", "client_families": [], "risk_class": "local", "contract_change": False,
                "gate_applicability": applicability(goal, {"development", "merge"}),
            })
            target = root / ".ai" / "workspace" / "task-map.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(task_map), encoding="utf-8")
            result = dispatch_observe(root, self.dispatch_args(root, "Developer Agent", "implementation"))
            self.assertEqual("CONTINUE_CURRENT_SESSION", result["session"]["action"])
            self.assertFalse(result["create_allowed"])
            self.assertEqual([], session_status(root, "PROJECT-A")["slots"])

    def test_structural_assurance_remains_independent_without_role_explosion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.repo(root)
            task_map = route("结构性服务端变更", proposal={
                "architecture": "backend", "client_families": [], "risk_class": "structural", "contract_change": True,
            })
            target = root / ".ai" / "workspace" / "task-map.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(task_map), encoding="utf-8")
            review = dispatch_observe(root, self.dispatch_args(root, "Review Agent", "review"))
            self.assertEqual("CREATE_THREAD", review["session"]["action"])
            testing = dispatch_observe(root, self.dispatch_args(root, "Test Agent", "test"))
            self.assertNotEqual("CREATE_THREAD", testing["session"]["action"])
            self.assertEqual(1, len(session_status(root, "PROJECT-A")["slots"]))

    def dispatch_args(self, root: Path, role: str, lane: str) -> argparse.Namespace:
        return ns(
            task_id="KG-001", role=role, repository=str(root), base_sha="base-a", api_result="EMPTY",
            project_id="PROJECT-A", thread_id=None, client_thread_id=None, runtime_status=None,
            detail="", ownership_lane=lane, require_isolated_runtime=False,
        )

    def repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "test: init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


if __name__ == "__main__":
    unittest.main()
