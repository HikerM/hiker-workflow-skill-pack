from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from structural_change_decision import validate_decision
from structural_decision_fixture import HASH, PROJECT_HASH, catalog, decision, fact


def validate(value: dict, observed: dict) -> dict:
    return validate_decision(
        value,
        observed_fact_catalog=observed,
        expected_scope_fingerprint=HASH,
        expected_project_fact_fingerprint=PROJECT_HASH,
    )


class StructuralChangeDecisionTests(unittest.TestCase):
    def test_similar_code_with_different_change_reason_does_not_allow_abstraction(self):
        observed = catalog(
            fact("structure://different-reason", "STRUCTURE", "DIFFERENT_CHANGE_REASON"),
            fact("consumer://two", "CONSUMER", "MULTIPLE_CONSUMERS_PROVEN"),
        )
        with self.assertRaisesRegex(RuntimeError, "ABSTRACTION_BOUNDARY_CONFLICT"):
            validate(
                decision(
                    "INTRODUCE_ABSTRACTION",
                    ["structure://different-reason", "consumer://two"],
                ),
                observed,
            )

    def test_shared_invariant_and_real_consumers_allow_abstraction(self):
        observed = catalog(
            fact("structure://shared", "STRUCTURE", "SHARED_INVARIANT", "SAME_CHANGE_REASON"),
            fact("consumer://two", "CONSUMER", "MULTIPLE_CONSUMERS_PROVEN"),
        )
        result = validate(
            decision("INTRODUCE_ABSTRACTION", ["structure://shared", "consumer://two"]),
            observed,
        )
        self.assertEqual("INTRODUCE_ABSTRACTION", result["action"])
        self.assertFalse(result["runtime_selected_action"])

    def test_large_but_cohesive_file_does_not_force_split(self):
        observed = catalog(fact("structure://cohesive", "STRUCTURE", "COHESIVE_RESPONSIBILITY"))
        result = validate(
            decision("KEEP_CURRENT_STRUCTURE", ["structure://cohesive"]),
            observed,
        )
        self.assertEqual("KEEP_CURRENT_STRUCTURE", result["action"])
        self.assertNotIn("file_size", result)

    def test_multiple_active_implementations_same_authority_allow_consolidation(self):
        observed = catalog(
            fact("authority://same", "AUTHORITY", "MULTIPLE_ACTIVE_IMPLEMENTATIONS", "SAME_AUTHORITY"),
            fact("structure://same-life", "STRUCTURE", "SAME_LIFECYCLE"),
        )
        result = validate(
            decision("CONSOLIDATE_SIMPLIFY", ["authority://same", "structure://same-life"]),
            observed,
        )
        self.assertEqual("CONSOLIDATE_SIMPLIFY", result["action"])

    def test_different_lifecycle_rejects_consolidation(self):
        observed = catalog(
            fact("authority://same", "AUTHORITY", "MULTIPLE_ACTIVE_IMPLEMENTATIONS", "SAME_AUTHORITY"),
            fact("structure://different-life", "STRUCTURE", "DIVERGENT_LIFECYCLE"),
        )
        with self.assertRaisesRegex(RuntimeError, "CONSOLIDATION_LIFECYCLE_CONFLICT"):
            validate(
                decision("CONSOLIDATE_SIMPLIFY", ["authority://same", "structure://different-life"]),
                observed,
            )

    def test_local_bug_with_cohesive_responsibility_modifies_existing(self):
        observed = catalog(
            fact("structure://local", "STRUCTURE", "COHESIVE_RESPONSIBILITY", "LOCALIZED_CHANGE"),
        )
        result = validate(decision("MODIFY_EXISTING", ["structure://local"]), observed)
        self.assertEqual("MODIFY_EXISTING", result["action"])

    def test_unknown_runtime_consumer_rejects_delete(self):
        observed = catalog(
            fact("consumer://unknown", "CONSUMER", "UNKNOWN_RUNTIME_CONSUMER"),
            fact("migration://complete", "MIGRATION", "MIGRATION_COMPLETE"),
        )
        with self.assertRaisesRegex(RuntimeError, "DELETE_RUNTIME_CONSUMER_NOT_CLOSED"):
            validate(
                decision("DELETE_SAFELY", ["consumer://unknown", "migration://complete"]),
                observed,
            )

    def test_proven_no_consumer_and_complete_migration_allow_delete(self):
        observed = catalog(
            fact("consumer://none", "CONSUMER", "NO_RUNTIME_CONSUMER_PROVEN"),
            fact("migration://complete", "MIGRATION", "MIGRATION_COMPLETE"),
            fact("control://rollback", "CONTROL", "ROLLBACK_AVAILABLE", "REVERSIBLE"),
        )
        result = validate(
            decision(
                "DELETE_SAFELY",
                ["consumer://none", "migration://complete", "control://rollback"],
            ),
            observed,
        )
        self.assertEqual("DELETE_SAFELY", result["action"])

    def test_patch_on_patch_problem_evidence_can_support_consolidation(self):
        observed = catalog(
            fact("problem://pivot-required", "PROBLEM"),
            fact("authority://same", "AUTHORITY", "MULTIPLE_ACTIVE_IMPLEMENTATIONS", "SAME_AUTHORITY"),
            fact("structure://same-life", "STRUCTURE", "SAME_LIFECYCLE"),
        )
        proposed = decision("CONSOLIDATE_SIMPLIFY", ["authority://same", "structure://same-life"])
        proposed["problem_refs"] = ["problem://pivot-required"]
        result = validate(proposed, observed)
        self.assertEqual("CONSOLIDATE_SIMPLIFY", result["action"])
        self.assertNotIn("workflow", result)

if __name__ == "__main__":
    unittest.main()
