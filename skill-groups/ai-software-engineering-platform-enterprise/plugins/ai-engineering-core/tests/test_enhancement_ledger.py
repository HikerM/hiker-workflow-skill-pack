from __future__ import annotations

import json
import unittest
from pathlib import Path


SUITE = Path(__file__).resolve().parents[3]
LEDGER = SUITE / "docs" / "engineering-enhancement-ledger.json"
REQUIRED_FIELDS = {
    "ENHANCEMENT_ID",
    "PROBLEM",
    "TARGET_CAPABILITY",
    "WHY",
    "IMPLEMENTATION_STATUS",
    "SOURCE_EVIDENCE",
    "TEST_EVIDENCE",
    "FIELD_EVIDENCE",
    "VERSION_INTRODUCED",
    "CURRENT_AUTHORITY",
    "REAL_PROJECT_OUTCOME",
}


class EnhancementLedgerTests(unittest.TestCase):
    def test_ledger_is_one_non_authoritative_release_evidence_index(self) -> None:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
        self.assertEqual("RELEASE_EVIDENCE_INDEX", payload["role"])
        self.assertIs(False, payload["state_authority"])
        self.assertEqual(len(payload["enhancements"]), len({item["ENHANCEMENT_ID"] for item in payload["enhancements"]}))

    def test_entries_have_bounded_status_and_existing_source_test_refs(self) -> None:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
        allowed = set(payload["allowed_statuses"])
        for item in payload["enhancements"]:
            self.assertEqual(set(), REQUIRED_FIELDS - set(item))
            self.assertIn(item["IMPLEMENTATION_STATUS"], allowed)
            for ref in [*item["SOURCE_EVIDENCE"], *item["TEST_EVIDENCE"], *item["FIELD_EVIDENCE"]]:
                self.assertTrue((SUITE / ref).is_file(), ref)
            if item["IMPLEMENTATION_STATUS"] == "FIELD_PROVEN":
                self.assertTrue(item["FIELD_EVIDENCE"])
                self.assertNotIn("PENDING", item["REAL_PROJECT_OUTCOME"])


if __name__ == "__main__":
    unittest.main()
