from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from structural_change_decision import validate_decision


class StructuralFieldEvidenceTests(unittest.TestCase):
    def test_two_read_only_business_fields_revalidate(self):
        evidence_path = PLUGIN.parents[1] / "docs" / "evidence" / "NEXT-02-structural-field.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertFalse(evidence["business_source_modified_by_field"])
        self.assertEqual("NOT_RUN_JUSTIFIED", evidence["implementation_field"])
        self.assertEqual(2, len(evidence["samples"]))
        for sample in evidence["samples"]:
            catalog = sample["observed_fact_catalog"]
            result = validate_decision(
                sample["structural_decision"],
                observed_fact_catalog=catalog,
                expected_scope_fingerprint=catalog["scope_fingerprint"],
            )
            expected = sample["expected_runtime_result"]
            self.assertEqual(expected["status"], result["status"])
            self.assertEqual(expected["action"], result["action"])
            self.assertEqual(expected["runtime_selected_action"], result["runtime_selected_action"])
            self.assertEqual(expected["decision_fingerprint"], result["decision_fingerprint"])
            self.assertEqual(sample["head_before"], sample["head_after"])
            self.assertEqual(sample["status_fingerprint_before"], sample["status_fingerprint_after"])


if __name__ == "__main__":
    unittest.main()
