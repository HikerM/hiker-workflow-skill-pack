from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from goal_coordination import evaluate  # noqa: E402


class GoalCoordinationTests(unittest.TestCase):
    def _root(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / ".ai" / "governance").mkdir(parents=True)
        (root / ".ai" / "tasks").mkdir(parents=True)
        return root

    def _task(self, root: Path, task_id: str, goal_id: str, revision: int, surfaces: list[str]) -> None:
        task = {
            "task_id": task_id,
            "state": "Development",
            "control_status": "ACTIVE",
            "goal_binding": {"scope": "project", "goal_id": goal_id, "revision": revision, "fingerprint": f"fp-{goal_id}-{revision}"},
            "change_contract": {"owned_surface_ids": surfaces, "consumed_surface_ids": []},
        }
        (root / ".ai" / "tasks" / f"{task_id}.json").write_text(json.dumps(task), encoding="utf-8")

    def test_disjoint_goals_can_run_in_parallel(self):
        root = self._root()
        self._task(root, "TASK-A", "GOAL-A", 1, ["src/a"])
        self._task(root, "TASK-B", "GOAL-B", 1, ["src/b"])
        (root / ".ai" / "governance" / "task-index.json").write_text(json.dumps({"tasks": [{"task_id": "TASK-A"}, {"task_id": "TASK-B"}]}), encoding="utf-8")
        result = evaluate(root, task_id="TASK-A")
        self.assertTrue(result["ok"], result)

    def test_overlapping_goals_are_serialized(self):
        root = self._root()
        self._task(root, "TASK-A", "GOAL-A", 1, ["src/shared"])
        self._task(root, "TASK-B", "GOAL-B", 1, ["src/shared/api"])
        (root / ".ai" / "governance" / "task-index.json").write_text(json.dumps({"tasks": [{"task_id": "TASK-A"}, {"task_id": "TASK-B"}]}), encoding="utf-8")
        result = evaluate(root, task_id="TASK-A")
        self.assertFalse(result["ok"])
        self.assertTrue(any(item["code"] == "GOAL_SCOPE_CONFLICT" for item in result["blockers"]))

    def test_revision_change_blocks_every_active_task_until_transaction_finishes(self):
        root = self._root()
        self._task(root, "TASK-A", "GOAL-A", 1, ["src/a"])
        (root / ".ai" / "governance" / "task-index.json").write_text(json.dumps({"tasks": [{"task_id": "TASK-A"}]}), encoding="utf-8")
        (root / ".ai" / "governance" / "goal-change-active.json").write_text(json.dumps({"status": "APPLYING", "operation_id": "OP-1", "new_goal_revision": 2}), encoding="utf-8")
        result = evaluate(root, task_id="TASK-A")
        self.assertFalse(result["ok"])
        self.assertEqual("GOAL_CHANGE_IN_PROGRESS", result["blockers"][0]["code"])


if __name__ == "__main__":
    unittest.main()
