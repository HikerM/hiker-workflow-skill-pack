from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from bootstrap_project import initialize
from decision_memory import MAX_DECISIONS, record, retrieve


GOAL = {"status": "ACTIVE", "goal_id": "GOAL-2", "revision": 2, "fingerprint": "goal-fp-2"}


def decision(decision_id: str, **overrides):
    value = {
        "id": decision_id,
        "status": "LOCKED",
        "content": f"content:{decision_id}",
        "authority": "PROJECT_DECISION",
        "goal_binding": dict(GOAL),
        "task_relevance": ["TASK-2"],
        "generation": 4,
        "scope": ["services/api"],
        "superseded_by": None,
    }
    value.update(overrides)
    return value


class DecisionMemoryTests(unittest.TestCase):
    def test_retrieval_enforces_goal_task_generation_scope_authority_and_superseded_state(self):
        decisions = [
            decision("CURRENT"),
            decision("OLD-GOAL", goal_binding={"goal_id": "GOAL-1", "revision": 1, "fingerprint": "old"}),
            decision("OTHER-TASK", task_relevance=["TASK-OTHER"]),
            decision("OLD-GENERATION", generation=3),
            decision("OTHER-SCOPE", scope=["apps/client"]),
            decision("SUPERSEDED", status="SUPERSEDED", superseded_by="CURRENT"),
            decision("UNTRUSTED", authority="MODEL_PROPOSAL"),
        ]
        result = retrieve(
            {"decisions": decisions}, current_goal=GOAL, current_task="TASK-2",
            current_generation=4, current_scope=["services/api/routes/auth.py"],
        )
        self.assertEqual(["CURRENT"], [item["id"] for item in result["selected"]])
        self.assertEqual(1, result["excluded"]["GOAL_MISMATCH"])
        self.assertEqual(1, result["excluded"]["TASK_MISMATCH"])
        self.assertEqual(1, result["excluded"]["GENERATION_MISMATCH"])
        self.assertEqual(1, result["excluded"]["SCOPE_MISMATCH"])
        self.assertEqual(1, result["excluded"]["SUPERSEDED_OR_INACTIVE"])
        self.assertEqual(1, result["excluded"]["UNTRUSTED_AUTHORITY"])

    def test_legacy_project_global_decision_remains_compatible(self):
        result = retrieve({"decisions": [{"id": "LEGACY", "status": "LOCKED", "content": "keep contract", "superseded_by": None}]})
        self.assertEqual(["LEGACY"], [item["id"] for item in result["selected"]])
        self.assertEqual("USER_LOCKED_DECISION", result["selected"][0]["authority"])

    def test_retrieval_is_bounded_without_injecting_all_history(self):
        values = [{"id": f"D-{index}", "status": "LOCKED", "content": "x"} for index in range(1000)]
        result = retrieve({"decisions": values}, limit=5)
        self.assertEqual(1000, result["considered_count"])
        self.assertEqual(5, result["selected_count"])
        self.assertEqual(["D-995", "D-996", "D-997", "D-998", "D-999"], [item["id"] for item in result["selected"]])
        self.assertTrue(result["bounded"])

    def test_oversized_decision_collection_fails_closed_instead_of_partial_recall(self):
        values = [{"id": f"D-{index}", "status": "LOCKED", "content": "x"} for index in range(MAX_DECISIONS + 1)]
        result = retrieve({"decisions": values})
        self.assertEqual([], result["selected"])
        self.assertTrue(result["requires_compaction"])
        self.assertIn("MEMORY_OVERFLOW", result["excluded"])

    def test_record_binds_current_goal_and_supersedes_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            goal_path = root / ".ai/governance/goal-contract.json"
            goal_path.write_text(json.dumps(GOAL), encoding="utf-8")
            first = record(root, decision_id="D-1", content="old", reason="initial", scope=["services/api"])
            second = record(root, decision_id="D-2", content="new", reason="replacement", scope=["services/api"], supersedes="D-1")
            stored = json.loads((root / ".ai/governance/locked-decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(GOAL["goal_id"], first["decision"]["goal_binding"]["goal_id"])
        self.assertEqual("D-2", stored["decisions"][0]["superseded_by"])
        self.assertEqual("SUPERSEDED", stored["decisions"][0]["status"])
        self.assertEqual("LOCKED", second["decision"]["status"])

    def test_statectl_exposes_precise_decision_contract_without_new_state_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            (root / ".ai/governance/goal-contract.json").write_text(json.dumps(GOAL), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(PLUGIN / "scripts/statectl.py"), "--root", str(root), "lock-decision",
                "--id", "D-CLI", "--content", "keep API contract", "--reason", "consumer compatibility",
                "--authority", "ARCHITECTURE_CONSTRAINT", "--generation", "4", "--task-id", "TASK-2",
                "--scope", "services/api",
            ], text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            payload = json.loads(result.stdout)
            stored = json.loads((root / ".ai/governance/locked-decisions.json").read_text(encoding="utf-8"))
        self.assertEqual("RECORDED", payload["status"])
        self.assertEqual("GOAL-2", stored["decisions"][0]["goal_binding"]["goal_id"])
        self.assertEqual(["TASK-2"], stored["decisions"][0]["task_relevance"])
        self.assertEqual(["services/api"], stored["decisions"][0]["scope"])

    def test_session_context_injects_only_applicable_decision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            (root / ".ai/governance/goal-contract.json").write_text(json.dumps(GOAL), encoding="utf-8")
            task_dir = root / ".ai/tasks"; task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "TASK-2.json").write_text(json.dumps({"affected_files": ["services/api/routes/auth.py"]}), encoding="utf-8")
            (root / ".ai/governance/locked-decisions.json").write_text(json.dumps({"schema_version": "2.0.0", "decisions": [
                decision("CURRENT"), decision("OLD-GOAL", goal_binding={"goal_id": "GOAL-1", "revision": 1}),
                decision("OTHER-SCOPE", scope=["apps/client"]),
            ]}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PLUGIN / "scripts/session_context.py")], cwd=root,
                input=json.dumps({"cwd": str(root), "source": "test", "task_id": "TASK-2", "project_generation": 4}),
                text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            )
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("content:CURRENT", context)
        self.assertNotIn("content:OLD-GOAL", context)
        self.assertNotIn("content:OTHER-SCOPE", context)
        self.assertIn("当前适用决定（1/3）", context)


if __name__ == "__main__":
    unittest.main()
