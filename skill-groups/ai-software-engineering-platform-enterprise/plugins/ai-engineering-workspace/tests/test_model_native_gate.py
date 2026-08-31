from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from gate_applicability import GATES, SCHEMA, fingerprint
from dispatch_guard import observe as dispatch_observe
from governance_state import init_project
from session_pool import bind as session_bind
from task_router import route
from workspacelib import atomic_json


def applicability(goal: str, required: set[str], *, risk: str = "local") -> dict:
    return {
        "schema_version": SCHEMA,
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "task_intent_fingerprint": fingerprint(goal),
        "deliverable_fingerprint": fingerprint("model-native-gate"),
        "risk_class": risk,
        "basis": {
            "repository_change": "development" in required,
            "runtime_change": "testing" in required,
            "architecture_impact": risk == "structural",
            "shared_scope": risk == "structural",
            "release_impact": risk == "structural",
            "merge_required": "merge" in required,
        },
        "gates": {
            gate: {
                "status": "REQUIRED" if gate in required else "NOT_APPLICABLE",
                "reason_code": "MODEL_NATIVE_REQUIRED" if gate in required else "MODEL_NATIVE_NOT_APPLICABLE",
            }
            for gate in GATES
        },
    }


class ModelNativePreservationGate(unittest.TestCase):
    def test_case_1_simple_local_change_has_no_agent_worktree_or_full_lifecycle_tax(self) -> None:
        goal = "Apply one bounded local change"
        result = route(goal, proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "local",
            "contract_change": False,
            "gate_applicability": applicability(goal, {"development", "merge"}),
        })
        topology = result["execution_topology"]
        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual(0, topology["default_new_agent_count"])
        self.assertEqual(0, topology["default_new_provider_session_count"])
        self.assertEqual("CURRENT_WORKTREE_IF_SAFE", topology["bindings"][0]["worktree_policy"])
        active = {item["lane"] for item in result["lanes"] if item["status"] != "NOT_APPLICABLE"}
        self.assertEqual({"implementation", "merge"}, active)

    def test_case_2_model_proposed_independent_ranges_remain_parallel_eligible(self) -> None:
        result = route("Implement two independent slices", proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "bounded", "contract_change": False,
            "implementation_lanes": [
                {"id": "slice-a", "surface": "custom-a", "write_scope": ["apps/a"], "authority_ids": ["MODULE:A"]},
                {"id": "slice-b", "surface": "custom-b", "write_scope": ["apps/b"], "authority_ids": ["MODULE:B"]},
            ],
        })
        lanes = {item["lane"]: item for item in result["lanes"]}
        self.assertTrue(lanes["slice-a"]["parallel_eligible"])
        self.assertTrue(lanes["slice-b"]["parallel_eligible"])
        self.assertEqual([], lanes["slice-a"]["serial_with"])
        self.assertEqual([], lanes["slice-b"]["serial_with"])

    def test_case_3_shared_authority_blocks_for_authority_not_topology(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            init_project(root, argparse.Namespace(project_id="PROJECT-A", architecture="unknown", version="1", database_version="1", api_version="1"))
            result = route("Change two consumers of one contract", proposal={
                "architecture": "unknown", "client_families": [], "risk_class": "bounded", "contract_change": True,
                "implementation_lanes": [
                    {"id": "consumer-a", "surface": "custom-a", "write_scope": ["apps/a"], "authority_ids": ["API:SHARED"]},
                    {"id": "consumer-b", "surface": "custom-b", "write_scope": ["apps/b"], "authority_ids": ["API:SHARED"]},
                ],
            })
            lanes = {item["lane"]: item for item in result["lanes"]}
            self.assertEqual([], lanes["consumer-b"]["scope_conflicts"])
            self.assertEqual([{"lane": "consumer-a", "shared_authority_ids": ["API:SHARED"]}], lanes["consumer-b"]["authority_conflicts"])
            atomic_json(root / ".ai/workspace/task-map.json", result)
            session_bind(root, "PROJECT-A", "KG-001", "Developer Agent", str(root), "base", "thread-a", None, "RUNNING", ownership_lane="consumer-a")
            observed = dispatch_observe(root, argparse.Namespace(
                task_id="KG-002", role="Developer Agent", repository=str(root), base_sha="base",
                api_result="EMPTY", project_id="PROJECT-A", thread_id=None, client_thread_id=None,
                runtime_status=None, detail="", ownership_lane="consumer-b", require_isolated_runtime=False,
            ))
            self.assertEqual("BLOCK_AUTHORITY_CONFLICT", observed["session"]["action"])
            self.assertEqual([], observed["scope_conflicts"])

    def test_case_4_high_risk_raises_assurance_without_seven_agent_ontology(self) -> None:
        result = route("Perform a high-risk migration", proposal={
            "architecture": "backend", "client_families": [], "risk_class": "structural", "contract_change": True,
        })
        topology = result["execution_topology"]
        assurance = next(item for item in topology["bindings"] if item["binding_id"] == "assurance")
        self.assertTrue(topology["independent_assurance_required"])
        self.assertEqual({"REVIEW", "TESTING"}, set(assurance["responsibilities"]))
        self.assertLess(len(topology["bindings"]), 7)
        self.assertEqual(0, topology["default_new_agent_count"])

    def test_case_5_strong_model_can_plan_write_and_verify_in_current_session(self) -> None:
        goal = "Plan implement and verify one low-risk slice"
        result = route(goal, proposal={
            "architecture": "unknown", "client_families": [], "risk_class": "local",
            "contract_change": False, "independent_assurance": False,
            "gate_applicability": applicability(goal, {"development", "testing", "merge"}),
        })
        topology = result["execution_topology"]
        self.assertEqual(1, len(topology["bindings"]))
        self.assertEqual({"CONTROL", "WRITE", "ASSURE"}, set(topology["bindings"][0]["execution_classes"]))
        self.assertEqual("REUSE_CURRENT_PROVIDER_SESSION", topology["bindings"][0]["provider_session_policy"])
        self.assertFalse(topology["independent_assurance_required"])

    def test_reference_topology_does_not_override_project_facts(self) -> None:
        reference = (
            PLUGIN
            / "skills"
            / "multi-agent-project-governance"
            / "references"
            / "system-lane-model.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Example != Architecture Constant", reference)
        self.assertNotIn("Browser UI → API Contract → Server/Application", reference)
        self.assertNotIn("离线单机也要显式标记", reference)

        result = route("Inspect the bounded current facts", proposal={
            "architecture": "bs", "client_families": [], "risk_class": "local",
            "contract_change": False,
        })
        active = {item["lane"] for item in result["lanes"] if item["status"] != "NOT_APPLICABLE"}
        self.assertEqual(set(), active)


if __name__ == "__main__":
    unittest.main()
