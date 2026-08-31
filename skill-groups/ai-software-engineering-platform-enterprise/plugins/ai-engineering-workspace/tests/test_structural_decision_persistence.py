from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from governance_state import create_task, init_project, load_task, set_change_contract
from structural_decision_fixture import base_proposal, observed_catalog, structural_decision
from task_router import route


def contract_args(receipt_file: Path) -> Namespace:
    return Namespace(
        task_id="KG-202", agent_role="Planning Agent", gate_plan_file=None,
        structural_change_decision_file=str(receipt_file), risk_class=None, merge_required=None,
        allowed_files=["src/service.py"], allowed_modules=None, protected_modules=None,
        public_contract_changes=None, behavior_invariants=["Existing behavior remains unchanged"],
        characterization_tests=None, consumer_tests=None, required_tests=["Focused regression"],
        structural_decisions=[], consumers=None, max_blast_radius=None, warn_lines=None,
        block_lines=None, warn_growth=None, block_growth=None, preempt_lines=None,
        responsibility_growth=None,
    )


class StructuralDecisionPersistenceTests(unittest.TestCase):
    def test_existing_task_contract_writer_accepts_only_validated_receipt(self):
        goal = "Fix a local service defect"
        normalized = route(
            goal,
            tech_stack={"observed_fact_catalog": observed_catalog(goal)},
            proposal={**base_proposal(), "structural_change_decision": structural_decision()},
        )["structural_change_decision"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "hiker-test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "test: init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "branch", "develop"], cwd=root, check=True)
            subprocess.run(["git", "branch", "release"], cwd=root, check=True)
            init_project(root, Namespace(project_id="PROJECT-A", architecture="unknown", version="1.0.0",
                                         database_version="unknown", api_version="unknown"))
            create_task(root, Namespace(task_id="KG-202", goal=goal, owner_agent="Planning Agent",
                                        branch="feature/KG-202-structural", base_branch="develop",
                                        affected_files=["src/service.py"]))
            receipt_file = root / "structural-decision.json"
            receipt_file.write_text(json.dumps(normalized), encoding="utf-8")
            args = contract_args(receipt_file)
            set_change_contract(root, args)
            stored = load_task(root, "KG-202")["change_contract"]["structural_change_decision"]
            self.assertEqual(normalized["decision_fingerprint"], stored["decision_fingerprint"])
            args.structural_decisions = ["src/service.py|KEEP|legacy"]
            with self.assertRaisesRegex(RuntimeError, "STRUCTURAL_DECISION_AUTHORITY_CONFLICT"):
                set_change_contract(root, args)


if __name__ == "__main__":
    unittest.main()
