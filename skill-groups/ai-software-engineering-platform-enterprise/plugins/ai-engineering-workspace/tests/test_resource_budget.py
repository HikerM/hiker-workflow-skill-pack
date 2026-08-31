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

from bounded_context import ensure_policy
from event_budget import HARD_LIMITS
from governance_state import init_project
from session_pool import project_policy
from task_router import route
from workspacelib import RESOURCE_HARD_MAX


class WorkspaceResourceBudgetTests(unittest.TestCase):
    def repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_context_configuration_can_only_lower_hard_max(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root)
            path = root / ".ai" / "governance" / "context-retention.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema_version": "1.1.0", "active_context_max_chars": 99_999_999}), encoding="utf-8")
            policy = ensure_policy(root)
            self.assertEqual(RESOURCE_HARD_MAX["context"]["active_context_max_chars"], policy["active_context_max_chars"])

    def test_project_session_budget_cannot_create_extra_agents_or_turns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root)
            path = root / ".ai" / "governance" / "project-state.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"session_budget": {"max_writer_slots": 99, "max_active_turns": 99}}), encoding="utf-8")
            policy = project_policy(root)
            self.assertEqual(2, policy["max_writer_slots"])
            self.assertEqual(2, policy["max_active_turns"])

    def test_project_initialization_normalizes_oversized_existing_budgets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root)
            path = root / ".ai" / "governance" / "project-state.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "parallel_budget": {"max_total_active_tasks": 500},
                "session_budget": {"max_resident_slots": 500},
            }), encoding="utf-8")
            project = init_project(root, argparse.Namespace(
                project_id="PROJECT-A", architecture="backend", version="1.0.0",
                database_version="001", api_version="v1",
            ))
            self.assertEqual(5, project["parallel_budget"]["max_total_active_tasks"])
            self.assertEqual(6, project["session_budget"]["max_resident_slots"])

    def test_complex_proposal_cannot_break_lane_or_turn_hard_max(self):
        proposal = {
            "architecture": "unknown", "client_families": [], "contract_change": False,
            "implementation_lanes": [
                {"id": f"lane-{index}", "surface": "custom", "write_scope": [f"apps/{index}"]}
                for index in range(9)
            ],
        }
        rejected = route("复杂项目", proposal=proposal)
        self.assertEqual("REJECTED", rejected["status"])
        accepted = route("复杂项目", proposal={**proposal, "implementation_lanes": proposal["implementation_lanes"][:8]})
        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual(2, accepted["execution_topology"]["active_turn_hard_limit"])
        self.assertEqual(2, accepted["execution_topology"]["writer_binding_hard_limit"])
        self.assertEqual(0, accepted["execution_topology"]["default_new_agent_count"])

    def test_event_hard_limits_come_from_same_authority(self):
        for key, value in HARD_LIMITS.items():
            self.assertEqual(RESOURCE_HARD_MAX["event"][key], value)


if __name__ == "__main__":
    unittest.main()
