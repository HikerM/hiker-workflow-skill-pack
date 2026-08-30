from __future__ import annotations

import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from interaction_guard import evaluate, evaluate_handoffs


def contract() -> dict:
    return {
        "handoffs": [{
            "id": "HND-EDGE-BATCH",
            "participants": [
                {"id": "edge-node-alpha", "category": "project-defined-origin"},
                {"id": "batch-runner-x", "category": "project-defined-destination"},
            ],
            "trigger": {"event_ref": "event://batch-ready"},
            "state_transition": {"from": "queued", "to": "processing"},
            "authority_transfer": {
                "from_participant": "edge-node-alpha", "to_participant": "batch-runner-x",
            },
            "data_transfer": {"contract_ref": "contract://batch-payload"},
            "failure_recovery": {"evidence_ref": "test://batch-retry"},
            "downstream_visibility": {"surface_ref": "surface://batch-status"},
            "evidence_refs": ["fact://edge-batch-flow"],
        }],
    }


class HandoffContinuityTests(unittest.TestCase):
    def test_absent_handoff_is_not_applicable_and_does_not_force_model(self) -> None:
        result = evaluate({"interactions": []})
        self.assertEqual("PASS", result["status"])
        self.assertEqual("NOT_APPLICABLE", result["handoff_continuity"]["status"])
        self.assertEqual(0, result["handoff_continuity"]["case_specific_role_count"])

    def test_project_defined_participants_and_complete_continuity_pass(self) -> None:
        result = evaluate(contract())
        self.assertEqual("PASS", result["status"], result)
        self.assertEqual("PASS", result["handoff_continuity"]["status"])
        self.assertEqual(0, result["handoff_continuity"]["case_specific_role_count"])

    def test_missing_continuity_dimension_is_blocked(self) -> None:
        data = contract()
        del data["handoffs"][0]["failure_recovery"]
        result = evaluate_handoffs(data["handoffs"])
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("HANDOFF_CONTINUITY_DIMENSION_MISSING", {item["code"] for item in result["errors"]})

    def test_not_applicable_dimension_requires_reason(self) -> None:
        data = contract()
        data["handoffs"][0]["authority_transfer"] = {"applicable": False}
        self.assertEqual("BLOCKED", evaluate_handoffs(data["handoffs"])["status"])
        data["handoffs"][0]["authority_transfer"] = {"applicable": False, "reason": "data-only transfer"}
        self.assertEqual("PASS", evaluate_handoffs(data["handoffs"])["status"])

    def test_unknown_participant_reference_is_blocked(self) -> None:
        data = contract()
        data["handoffs"][0]["authority_transfer"]["to_participant"] = "not-declared"
        result = evaluate_handoffs(data["handoffs"])
        self.assertIn("UNKNOWN_HANDOFF_PARTICIPANT_REFERENCE", {item["code"] for item in result["errors"]})

    def test_handoff_requires_project_fact_evidence(self) -> None:
        data = contract()
        data["handoffs"][0]["evidence_refs"] = []
        result = evaluate_handoffs(data["handoffs"])
        self.assertIn("HANDOFF_PROJECT_FACT_EVIDENCE_REQUIRED", {item["code"] for item in result["errors"]})


if __name__ == "__main__":
    unittest.main()
