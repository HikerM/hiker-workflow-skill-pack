from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from gate_applicability import GATES, SCHEMA as GATE_SCHEMA, fingerprint
from perspective_applicability import ARTIFACT_TYPES, AUTHORITY, MAX_PERSPECTIVES, SCHEMA_VERSION, validate_plan
from task_router import route


def gate_plan(goal: str) -> dict:
    required = {"development", "review", "testing"}
    return {
        "schema_version": GATE_SCHEMA,
        "authority": AUTHORITY,
        "task_intent_fingerprint": fingerprint(goal),
        "deliverable_fingerprint": fingerprint("perspective-applicability-test"),
        "risk_class": "bounded",
        "basis": {
            "repository_change": True,
            "runtime_change": True,
            "architecture_impact": False,
            "shared_scope": False,
            "release_impact": False,
            "merge_required": False,
        },
        "gates": {
            name: {
                "status": "REQUIRED" if name in required else "NOT_APPLICABLE",
                "reason_code": "MODEL_SELECTED" if name in required else "MODEL_NOT_APPLICABLE",
            }
            for name in GATES
        },
    }


def ui_plan() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "artifacts": [
            {"id": "screen.entry", "type": "UI_IMPLEMENTATION", "fact_refs": ["src/pages/Entry.tsx"]},
            {"id": "copy.entry", "type": "COPY_TEXT", "fact_refs": ["design://entry-copy"]},
        ],
        "actors": [
            {"id": "first-time-customer", "fact_refs": ["req://customer-onboarding"]},
            {"id": "support", "fact_refs": ["ops://support-runbook"]},
        ],
        "usage_conditions": [
            {"id": "permission-denied", "fact_refs": ["state://permission-denied"]},
        ],
        "risk_facts": [
            {"id": "recovery-dead-end", "safety_critical": True, "fact_refs": ["risk://no-recovery-action"]},
        ],
        "project_fact_refs": ["project://current-ui-stack"],
        "perspectives": [
            {
                "id": "customer-first-contact",
                "rationale": "The current requirement makes first-contact comprehension an acceptance concern.",
                "basis": {
                    "artifact_ids": ["screen.entry", "copy.entry"],
                    "actor_ids": ["first-time-customer"],
                    "usage_condition_ids": [],
                    "risk_ids": [],
                    "project_fact_refs": ["project://current-ui-stack"],
                },
                "acceptance_refs": ["acceptance://first-contact-clarity"],
            },
            {
                "id": "failure-recovery",
                "rationale": "The permission state must preserve a visible recovery route for the observed support flow.",
                "basis": {
                    "artifact_ids": ["screen.entry"],
                    "actor_ids": ["support"],
                    "usage_condition_ids": ["permission-denied"],
                    "risk_ids": ["recovery-dead-end"],
                    "project_fact_refs": [],
                },
                "acceptance_refs": ["acceptance://permission-recovery"],
            },
        ],
    }


class PerspectiveApplicabilityTests(unittest.TestCase):
    def test_omitted_plan_has_zero_default_tax(self) -> None:
        goal = "Implement one bounded UI slice"
        base = {
            "architecture": "bs",
            "client_families": [],
            "risk_class": "bounded",
            "contract_change": False,
            "gate_applicability": gate_plan(goal),
        }
        without = route(goal, proposal=base)
        with_plan = route(goal, proposal={**base, "perspective_applicability": ui_plan()})
        self.assertNotIn("perspective_applicability", without)
        self.assertEqual(without["lanes"], with_plan["lanes"])
        self.assertEqual(without["execution_topology"], with_plan["execution_topology"])
        self.assertNotIn("skills", with_plan["perspective_applicability"])
        self.assertNotIn("workflow", with_plan["perspective_applicability"])

    def test_model_selected_ui_perspectives_are_preserved(self) -> None:
        result = validate_plan(ui_plan())
        self.assertEqual("APPLICABLE", result["status"])
        self.assertEqual(
            ["customer-first-contact", "failure-recovery"],
            [item["id"] for item in result["perspectives"]],
        )

    def test_safety_critical_risk_requires_model_selected_coverage(self) -> None:
        plan = ui_plan()
        plan["perspectives"][1]["basis"]["risk_ids"] = []
        with self.assertRaisesRegex(RuntimeError, "SAFETY_CRITICAL_PERSPECTIVE_GAP:recovery-dead-end"):
            validate_plan(plan)

    def test_perspective_requires_declared_factual_basis(self) -> None:
        plan = ui_plan()
        plan["perspectives"][0]["basis"] = {
            "artifact_ids": ["screen.entry"],
            "actor_ids": [],
            "usage_condition_ids": [],
            "risk_ids": [],
            "project_fact_refs": [],
        }
        with self.assertRaisesRegex(RuntimeError, "PERSPECTIVE_FACTUAL_BASIS_REQUIRED"):
            validate_plan(plan)

    def test_unknown_basis_reference_is_rejected_not_inferred(self) -> None:
        plan = ui_plan()
        plan["perspectives"][0]["basis"]["actor_ids"] = ["invented-role"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_BASIS:actor_ids:invented-role"):
            validate_plan(plan)

    def test_perspective_count_is_bounded(self) -> None:
        plan = ui_plan()
        template = copy.deepcopy(plan["perspectives"][0])
        plan["perspectives"] = []
        for index in range(MAX_PERSPECTIVES + 1):
            item = copy.deepcopy(template)
            item["id"] = f"model-view-{index}"
            plan["perspectives"].append(item)
        with self.assertRaisesRegex(RuntimeError, "TOO_MANY_APPLICABLE_PERSPECTIVES"):
            validate_plan(plan)

    def test_required_artifact_taxonomy_is_supported_without_creating_artifacts(self) -> None:
        expected = {
            "REQUIREMENT", "ARCHITECTURE", "UI_PROTOTYPE", "UI_IMPLEMENTATION", "CODE", "API",
            "SCHEMA_DATA", "TEST", "COPY_TEXT", "DOCUMENTATION", "DEPLOYMENT", "OPERATIONS", "REFACTORING",
        }
        self.assertEqual(expected, ARTIFACT_TYPES)
        self.assertEqual(2, len(validate_plan(ui_plan())["artifacts"]))

    def test_architecture_maintainer_and_api_caller_are_dynamic_ids(self) -> None:
        plan = ui_plan()
        plan["artifacts"] = [
            {"id": "arch.current", "type": "ARCHITECTURE", "fact_refs": ["arch://current-boundaries"]},
            {"id": "api.current", "type": "API", "fact_refs": ["api://current-contract"]},
        ]
        plan["actors"] = [
            {"id": "future-maintainer", "fact_refs": ["decision://maintenance-cost"]},
            {"id": "api-caller", "fact_refs": ["consumer://studio-web"]},
        ]
        plan["usage_conditions"] = []
        plan["risk_facts"] = []
        plan["perspectives"] = [
            {
                "id": "future-maintainer",
                "rationale": "The changed boundary has an evidenced future maintenance consumer.",
                "basis": {"artifact_ids": ["arch.current"], "actor_ids": ["future-maintainer"], "usage_condition_ids": [], "risk_ids": [], "project_fact_refs": []},
                "acceptance_refs": ["acceptance://bounded-change-radius"],
            },
            {
                "id": "api-caller",
                "rationale": "The current API has an observed caller whose compatibility must remain explicit.",
                "basis": {"artifact_ids": ["api.current"], "actor_ids": ["api-caller"], "usage_condition_ids": [], "risk_ids": [], "project_fact_refs": []},
                "acceptance_refs": ["acceptance://caller-compatibility"],
            },
        ]
        result = validate_plan(plan)
        self.assertEqual(["future-maintainer", "api-caller"], [item["id"] for item in result["perspectives"]])


if __name__ == "__main__":
    unittest.main()
