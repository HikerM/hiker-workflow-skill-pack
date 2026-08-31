from __future__ import annotations

import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from implementation_guard import assess_proposal, validate_registry
from workspacelib import RESOURCE_HARD_MAX


def evidence() -> dict:
    return {
        "change_contract_fingerprint": "a" * 64,
        "impact": {
            "fingerprint": "b" * 64,
            "responsibilities": ["orders"],
            "write_authorities": ["authority://orders"],
            "contracts": ["contract://orders"],
        },
        "architecture": {
            "fingerprint": "c" * 64,
            "responsibilities": ["orders"],
            "call_paths": ["call://orders"],
            "contracts": ["contract://orders"],
        },
    }


def route(route_id: str, responsibility: str, path: str, contract: str, *, writer: bool = False) -> dict:
    return {
        "route_id": route_id,
        "path": path,
        "responsibility": responsibility,
        "call_paths": {f"call://{responsibility}"},
        "write_authorities": {f"authority://{responsibility}"},
        "contracts": {contract},
        "active_usage": True,
        "writes_canonical_state": writer,
    }


class ImplementationGuardTests(unittest.TestCase):
    def test_filename_similarity_is_not_a_duplicate_signal(self):
        data = {"capabilities": [
            {"id": "CAP-A", "responsibility": "billing", "implementations": [{
                "id": "billing", "path": "src/Service.py", "status": "active", "authoritative": True,
                "writes_canonical_state": False, "call_paths": ["call://billing"], "contracts": ["contract://billing"],
            }]},
            {"id": "CAP-B", "responsibility": "catalog", "implementations": [{
                "id": "catalog", "path": "src/ServiceV2.py", "status": "active", "authoritative": True,
                "writes_canonical_state": False, "call_paths": ["call://catalog"], "contracts": ["contract://catalog"],
            }]},
        ]}
        result = validate_registry(Path("."), data)
        self.assertTrue(result["ok"], result["errors"])
        self.assertFalse(result["filename_semantics_used"])

    def test_cross_group_shared_responsibility_and_contract_is_competing(self):
        data = {"capabilities": [
            {"id": "CAP-CURRENT", "responsibility": "orders", "implementations": [{
                "id": "current", "path": "src/orders/current.py", "status": "active", "authoritative": True,
                "writes_canonical_state": True, "contracts": ["contract://orders"], "active_usage": True,
            }]},
            {"id": "CAP-NEXT", "responsibility": "orders", "implementations": [{
                "id": "next", "path": "src/orders/next.py", "status": "active", "authoritative": True,
                "writes_canonical_state": False, "contracts": ["contract://orders"], "active_usage": True,
            }]},
        ]}
        result = validate_registry(Path("."), data)
        self.assertFalse(result["ok"])
        self.assertIn("COMPETING_IMPLEMENTATION_PATH", {item["code"] for item in result["errors"]})

    def test_parallel_proposal_is_blocked_and_modify_existing_is_preferred(self):
        current = route("orders-current", "orders", "src/orders.py", "contract://orders", writer=True)
        proposed = {
            "route_id": "orders-v2", "path": "src/orders_v2.py", "responsibility": "orders",
            "call_paths": ["call://orders"], "write_authorities": ["authority://orders"],
            "contracts": ["contract://orders"], "active_usage": True,
        }
        blocked = assess_proposal([current], {"action": "ADD_PARALLEL_IMPLEMENTATION", "route": proposed, "evidence": evidence()})
        self.assertEqual("BLOCK", blocked["status"])
        self.assertEqual("MODIFY_EXISTING", blocked["decision"])
        modified = assess_proposal([current], {"action": "MODIFY_EXISTING", "existing_route_id": "orders-current", "route": current})
        self.assertTrue(modified["ok"])

    def test_unknown_boundaries_require_review_instead_of_filename_guess(self):
        current = route("current", "orders", "src/Service.py", "contract://orders")
        result = assess_proposal([current], {
            "action": "ADD_PARALLEL_IMPLEMENTATION",
            "route": {"route_id": "new", "path": "src/NotSimilarAtAll.py", "responsibility": "orders"},
        })
        self.assertEqual("REQUIRES_REVIEW", result["status"])
        self.assertFalse(result["filename_semantics_used"])

    def test_bounded_migration_requires_exit_and_one_canonical_writer(self):
        current = route("current", "orders", "src/current.py", "contract://orders", writer=True)
        proposed = {
            "route_id": "next", "path": "src/next.py", "responsibility": "orders",
            "call_paths": ["call://orders"], "write_authorities": ["authority://orders"],
            "contracts": ["contract://orders"], "active_usage": True, "writes_canonical_state": False,
        }
        result = assess_proposal([current], {
            "action": "MIGRATE", "route": proposed, "evidence": evidence(),
            "migration": {"source_route_id": "current", "canonical_writer_route_id": "current", "exit_conditions": ["consumer regression PASS", "old route unreachable"]},
        })
        self.assertEqual("BOUNDED_MIGRATION", result["decision"])
        proposed["writes_canonical_state"] = True
        blocked = assess_proposal([current], {
            "action": "MIGRATE", "route": proposed, "evidence": evidence(),
            "migration": {"source_route_id": "current", "canonical_writer_route_id": "next", "exit_conditions": ["old route unreachable"]},
        })
        self.assertEqual("MULTIPLE_CANONICAL_WRITERS", blocked["code"])

    def test_registry_evaluation_is_bounded_and_fails_closed(self):
        limit = RESOURCE_HARD_MAX["implementation_registry"]["max_capabilities"]
        result = validate_registry(Path("."), {"capabilities": [
            {"id": f"CAP-{index}", "implementations": []} for index in range(limit + 1)
        ]})
        self.assertFalse(result["ok"])
        self.assertIn("CAPABILITY_BUDGET_EXCEEDED", {item["code"] for item in result["errors"]})
        self.assertEqual(limit, result["bounded_evaluation"]["capabilities"])
        self.assertLessEqual(
            result["bounded_evaluation"]["comparisons"],
            RESOURCE_HARD_MAX["implementation_registry"]["max_comparisons"],
        )


if __name__ == "__main__":
    unittest.main()
