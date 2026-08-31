from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from bounded_run import run_bounded
from engineering_manifests import DiscoveryBudget, discover_engineering_manifests
from resource_budget import DEFAULT_BUDGETS, HARD_MAX, authority_receipt, effective_budget


class ResourceBudgetAuthorityTests(unittest.TestCase):
    def test_requested_budget_can_lower_but_never_raise_hard_max(self):
        for domain, hard_limits in HARD_MAX.items():
            raised = effective_budget(domain, {key: value * 100 for key, value in hard_limits.items()})
            lowered = effective_budget(domain, {key: 1 for key in hard_limits})
            self.assertEqual(hard_limits, raised)
            self.assertTrue(all(value == 1 for value in lowered.values()))

    def test_invalid_budget_falls_back_to_default_not_unbounded(self):
        result = effective_budget("execution", {"max_active_turns": "unbounded", "max_writer_slots": -1})
        self.assertEqual(DEFAULT_BUDGETS["execution"]["max_active_turns"], result["max_active_turns"])
        self.assertEqual(DEFAULT_BUDGETS["execution"]["max_writer_slots"], result["max_writer_slots"])

    def test_manifest_discovery_clamps_caller_supplied_limits(self):
        with tempfile.TemporaryDirectory() as td:
            report = discover_engineering_manifests(Path(td), budget=DiscoveryBudget(
                max_depth=10_000, max_dirs=10_000, max_manifests=10_000,
                max_bytes=10_000_000_000, max_entries_per_dir=10_000,
            ))
        self.assertEqual(HARD_MAX["manifest_scan"], report["budget"])

    def test_bounded_command_output_cannot_exceed_hard_max(self):
        with tempfile.TemporaryDirectory() as td:
            report = run_bounded(
                Path(td), "budget-test", [sys.executable, "-c", "print('x' * 200000)"],
                max_chars=10_000_000,
            )
        self.assertTrue(report["truncated"])
        self.assertLessEqual(
            len(report["stdout_excerpt"]) + len(report["stderr_excerpt"]),
            HARD_MAX["output"]["command_output_chars"] + 200,
        )

    def test_authority_receipt_is_machine_readable_and_has_no_dynamic_override(self):
        receipt = authority_receipt()
        self.assertEqual("hiker-resource-budget/v1", receipt["schema_version"])
        self.assertEqual("EFFECTIVE_BUDGET_LESS_THAN_OR_EQUAL_TO_HARD_MAX", receipt["rule"])
        self.assertEqual(HARD_MAX, receipt["hard_max"])


if __name__ == "__main__":
    unittest.main()
