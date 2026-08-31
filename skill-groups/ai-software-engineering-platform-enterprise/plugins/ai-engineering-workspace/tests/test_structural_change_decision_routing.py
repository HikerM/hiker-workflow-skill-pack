from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from structural_decision_fixture import base_proposal, observed_catalog, perspective_plan, structural_decision
from task_router import route


class StructuralChangeDecisionRoutingTests(unittest.TestCase):
    def test_omitted_decision_keeps_default_route_shape_and_state_tax_zero(self):
        result = route("Fix a local service defect", proposal=base_proposal())
        self.assertEqual("ACCEPTED", result["status"])
        self.assertNotIn("structural_change_decision", result)
        self.assertNotIn("state_write", result)
        self.assertNotIn("skills", result)

    def test_model_decision_is_validated_and_preserved_without_runtime_selection(self):
        goal = "Fix a local service defect"
        result = route(
            goal,
            tech_stack={"observed_fact_catalog": observed_catalog(goal)},
            proposal={**base_proposal(), "structural_change_decision": structural_decision()},
        )
        self.assertEqual("ACCEPTED", result["status"])
        normalized = result["structural_change_decision"]
        self.assertEqual("MODIFY_EXISTING", normalized["action"])
        self.assertFalse(normalized["runtime_selected_action"])
        self.assertEqual("VALIDATED", normalized["status"])

    def test_legacy_and_new_decisions_cannot_be_parallel_authorities(self):
        goal = "Fix a local service defect"
        result = route(
            goal,
            tech_stack={"observed_fact_catalog": observed_catalog(goal)},
            proposal={
                **base_proposal(),
                "structural_change_decision": structural_decision(),
                "structural_decisions": ["src/service.py|KEEP|legacy"],
            },
        )
        self.assertEqual("REJECTED", result["status"])
        self.assertIn("STRUCTURAL_DECISION_AUTHORITY_CONFLICT", ";".join(result["diagnostics"]))

    def test_dynamic_perspective_and_structural_decision_share_one_fact_catalog(self):
        goal = "Fix a local service defect"
        result = route(
            goal,
            tech_stack={"observed_fact_catalog": observed_catalog(goal)},
            proposal={
                **base_proposal(),
                "perspective_applicability": perspective_plan(),
                "structural_change_decision": structural_decision(),
            },
        )
        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual("APPLICABLE", result["perspective_applicability"]["status"])
        self.assertEqual("VALIDATED", result["structural_change_decision"]["status"])
        self.assertEqual(
            result["perspective_applicability"]["evidence_grounding"]["scope_fingerprint"],
            result["structural_change_decision"]["evidence_grounding"]["scope_fingerprint"],
        )

if __name__ == "__main__":
    unittest.main()
