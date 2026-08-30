from __future__ import annotations

import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from query_index_evidence import evaluate


def query(query_id: str = "Q-1", field: str = "phase") -> dict:
    return {
        "query_id": query_id,
        "entity": "work_items",
        "tenant_scope": "tenant_id",
        "filters": [{"field": field, "operator": "EQ"}],
        "joins": [],
        "sort": [{"field": "created_at", "direction": "DESC"}],
        "read_write_ratio": {"reads_per_write": 12},
        "field_stats": {field: {"rows": 100_000, "distinct": 4}},
        "evidence_refs": ["trace://query/Q-1", "plan://explain/Q-1"],
    }


class QueryDrivenIndexTests(unittest.TestCase):
    def test_composite_index_is_supported_by_real_query_prefix(self):
        payload = {"queries": [query()], "proposed_indexes": [{
            "index_id": "IDX-1", "entity": "work_items",
            "columns": ["tenant_id", "phase", "created_at"], "query_ids": ["Q-1"],
        }]}
        result = evaluate(payload)
        self.assertEqual("PASS", result["status"])
        self.assertEqual("SUPPORTED", result["decisions"][0]["decision"])
        self.assertEqual([], result["recommendations"])

    def test_blind_index_without_query_evidence_is_blocked(self):
        result = evaluate({"queries": [], "proposed_indexes": [{
            "index_id": "IDX-BLIND", "entity": "work_items", "columns": ["phase"], "query_ids": [],
        }]})
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("BLIND_INDEX_WITHOUT_QUERY_EVIDENCE", {item["code"] for item in result["findings"]})

    def test_low_selectivity_rule_uses_stats_not_field_name(self):
        payload = {"queries": [query(field="phase")], "proposed_indexes": [{
            "index_id": "IDX-PHASE", "entity": "work_items", "columns": ["phase"], "query_ids": ["Q-1"],
        }]}
        blocked = evaluate(payload)
        self.assertIn("LOW_SELECTIVITY_INDEX_REQUIRES_JUSTIFICATION", {item["code"] for item in blocked["findings"]})
        payload["proposed_indexes"][0]["justification"] = "measured hot read path with covering benefit"
        self.assertEqual("PASS", evaluate(payload)["status"])

    def test_no_query_evidence_never_invents_an_index(self):
        result = evaluate(None)
        self.assertEqual("NOT_APPLICABLE", result["status"])
        self.assertEqual([], result["recommendations"])
        self.assertEqual("NO_QUERY_EVIDENCE_NO_INDEX_RECOMMENDATION", result["rule"])

    def test_write_heavy_index_requires_explicit_cost_justification(self):
        observed = query(); observed["read_write_ratio"] = {"reads_per_write": 0.2}; observed["field_stats"] = {}
        payload = {"queries": [observed], "proposed_indexes": [{
            "index_id": "IDX-WRITE", "entity": "work_items", "columns": ["tenant_id", "phase"], "query_ids": ["Q-1"],
        }]}
        self.assertIn("WRITE_HEAVY_INDEX_REQUIRES_JUSTIFICATION", {item["code"] for item in evaluate(payload)["findings"]})


if __name__ == "__main__":
    unittest.main()
