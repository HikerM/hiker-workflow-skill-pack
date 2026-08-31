from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from structural_change_decision import ACTIONS, SCHEMA_VERSION, validate_receipt
from structural_decision_fixture import catalog, decision, fact
from test_structural_change_decision import validate


class StructuralDecisionContractTests(unittest.TestCase):
    def test_published_schema_matches_runtime_contract(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "structural-change-decision.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(SCHEMA_VERSION, schema["properties"]["schema_version"]["const"])
        self.assertEqual(ACTIONS, set(schema["properties"]["action"]["enum"]))
        required = {
            "decision_scope", "problem_refs", "evidence_refs", "reason", "alternatives_rejected",
            "expected_gain", "migration_cost", "regression_risk", "rollback_or_exit_condition", "confidence",
        }
        self.assertTrue(required.issubset(schema["required"]))

    def test_good_current_structure_can_be_kept(self):
        observed = catalog(fact("structure://cohesive", "STRUCTURE", "COHESIVE_RESPONSIBILITY"))
        result = validate(decision("KEEP_CURRENT_STRUCTURE", ["structure://cohesive"]), observed)
        self.assertEqual("VALIDATED", result["status"])

    def test_fabricated_evidence_is_rejected(self):
        observed = catalog(fact("structure://cohesive", "STRUCTURE", "COHESIVE_RESPONSIBILITY"))
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_STRUCTURAL_EVIDENCE_REF"):
            validate(decision("KEEP_CURRENT_STRUCTURE", ["evidence://fabricated"]), observed)

    def test_stale_evidence_is_rejected(self):
        observed = catalog(fact("structure://stale", "STRUCTURE", "COHESIVE_RESPONSIBILITY", freshness="STALE"))
        with self.assertRaisesRegex(RuntimeError, "STALE_STRUCTURAL_EVIDENCE_REF"):
            validate(decision("KEEP_CURRENT_STRUCTURE", ["structure://stale"]), observed)

    def test_observed_gain_requires_direct_evidence_and_receipt_is_tamper_evident(self):
        observed = catalog(fact("structure://cohesive", "STRUCTURE", "COHESIVE_RESPONSIBILITY"))
        proposed = decision("KEEP_CURRENT_STRUCTURE", ["structure://cohesive"])
        proposed["expected_gain"]["evidence_refs"] = []
        with self.assertRaisesRegex(RuntimeError, "OBSERVED_GAIN_EVIDENCE_REQUIRED"):
            validate(proposed, observed)
        normalized = validate(decision("KEEP_CURRENT_STRUCTURE", ["structure://cohesive"]), observed)
        receipt, errors = validate_receipt(normalized)
        self.assertIsNotNone(receipt)
        self.assertEqual([], errors)
        tampered = copy.deepcopy(normalized)
        tampered["action"] = "DELETE_SAFELY"
        receipt, errors = validate_receipt(tampered)
        self.assertIsNone(receipt)
        self.assertIn("STRUCTURAL_DECISION_RECEIPT_FINGERPRINT_MISMATCH", errors)


if __name__ == "__main__":
    unittest.main()
