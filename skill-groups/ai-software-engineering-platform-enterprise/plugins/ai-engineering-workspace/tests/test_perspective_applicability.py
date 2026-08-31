from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from gate_applicability import GATES, SCHEMA as GATE_SCHEMA, fingerprint
from perspective_applicability import (
    ARTIFACT_TYPES,
    AUTHORITY,
    MAX_PERSPECTIVES,
    OBSERVED_FACT_CATALOG_AUTHORITY,
    OBSERVED_FACT_CATALOG_SCHEMA,
    SCHEMA_VERSION,
    validate_plan,
)
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
                "acceptance_refs": ["semantic://first-contact-clarity"],
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
                "acceptance_refs": ["semantic://permission-recovery"],
            },
        ],
    }


def evidence_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def observed_catalog(plan: dict | None = None, *, scope_text: str = "bounded-current-task-observation") -> dict:
    value = plan or ui_plan()
    facts: list[dict] = []
    for field, kind in (
        ("artifacts", "ARTIFACT"),
        ("actors", "ACTOR"),
        ("usage_conditions", "USAGE"),
        ("risk_facts", "RISK"),
    ):
        for item in value.get(field, []):
            for ref in item.get("fact_refs", []):
                facts.append({
                    "ref": ref,
                    "kind": kind,
                    "evidence_fingerprint": evidence_fingerprint(f"{kind}:{ref}"),
                    **({"safety_critical": bool(item.get("safety_critical"))} if kind == "RISK" else {}),
                })
    for ref in value.get("project_fact_refs", []):
        facts.append({
            "ref": ref,
            "kind": "PROJECT",
            "evidence_fingerprint": evidence_fingerprint(f"PROJECT:{ref}"),
        })
    return {
        "schema_version": OBSERVED_FACT_CATALOG_SCHEMA,
        "authority": OBSERVED_FACT_CATALOG_AUTHORITY,
        "scope_fingerprint": evidence_fingerprint(scope_text),
        "facts": facts,
        "acceptance_refs": [],
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
        with_plan = route(
            goal,
            tech_stack={"observed_fact_catalog": observed_catalog(scope_text=goal)},
            proposal={**base, "perspective_applicability": ui_plan()},
        )
        self.assertNotIn("perspective_applicability", without)
        self.assertEqual(without["lanes"], with_plan["lanes"])
        self.assertEqual(without["execution_topology"], with_plan["execution_topology"])
        self.assertNotIn("skills", with_plan["perspective_applicability"])
        self.assertNotIn("workflow", with_plan["perspective_applicability"])

    def test_model_selected_ui_perspectives_are_preserved(self) -> None:
        result = validate_plan(ui_plan(), observed_fact_catalog=observed_catalog())
        self.assertEqual("APPLICABLE", result["status"])
        self.assertEqual(
            ["customer-first-contact", "failure-recovery"],
            [item["id"] for item in result["perspectives"]],
        )

    def test_safety_critical_risk_requires_model_selected_coverage(self) -> None:
        plan = ui_plan()
        plan["perspectives"][1]["basis"]["risk_ids"] = []
        with self.assertRaisesRegex(RuntimeError, "SAFETY_CRITICAL_PERSPECTIVE_GAP:recovery-dead-end"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

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
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_unknown_basis_reference_is_rejected_not_inferred(self) -> None:
        plan = ui_plan()
        plan["perspectives"][0]["basis"]["actor_ids"] = ["invented-role"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_BASIS:actor_ids:invented-role"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_perspective_count_is_bounded(self) -> None:
        plan = ui_plan()
        template = copy.deepcopy(plan["perspectives"][0])
        plan["perspectives"] = []
        for index in range(MAX_PERSPECTIVES + 1):
            item = copy.deepcopy(template)
            item["id"] = f"model-view-{index}"
            plan["perspectives"].append(item)
        with self.assertRaisesRegex(RuntimeError, "TOO_MANY_APPLICABLE_PERSPECTIVES"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_required_artifact_taxonomy_is_supported_without_creating_artifacts(self) -> None:
        expected = {
            "REQUIREMENT", "ARCHITECTURE", "UI_PROTOTYPE", "UI_IMPLEMENTATION", "CODE", "API",
            "SCHEMA_DATA", "TEST", "COPY_TEXT", "DOCUMENTATION", "DEPLOYMENT", "OPERATIONS", "REFACTORING",
        }
        self.assertEqual(expected, ARTIFACT_TYPES)
        self.assertEqual(2, len(validate_plan(ui_plan(), observed_fact_catalog=observed_catalog())["artifacts"]))

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
                "acceptance_refs": ["semantic://bounded-change-radius"],
            },
            {
                "id": "api-caller",
                "rationale": "The current API has an observed caller whose compatibility must remain explicit.",
                "basis": {"artifact_ids": ["api.current"], "actor_ids": ["api-caller"], "usage_condition_ids": [], "risk_ids": [], "project_fact_refs": []},
                "acceptance_refs": ["semantic://caller-compatibility"],
            },
        ]
        result = validate_plan(plan, observed_fact_catalog=observed_catalog(plan))
        self.assertEqual(["future-maintainer", "api-caller"], [item["id"] for item in result["perspectives"]])

    def test_fabricated_artifact_fact_ref_is_rejected(self) -> None:
        plan = ui_plan()
        plan["artifacts"][0]["fact_refs"] = ["source://fabricated-ui"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_FACT_REF:ARTIFACT:source://fabricated-ui"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_fabricated_actor_fact_ref_is_rejected(self) -> None:
        plan = ui_plan()
        plan["actors"][0]["fact_refs"] = ["actor://fabricated-user"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_FACT_REF:ACTOR:actor://fabricated-user"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_fabricated_usage_fact_ref_is_rejected(self) -> None:
        plan = ui_plan()
        plan["usage_conditions"][0]["fact_refs"] = ["usage://fabricated-state"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_FACT_REF:USAGE:usage://fabricated-state"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_fabricated_risk_fact_ref_is_rejected(self) -> None:
        plan = ui_plan()
        plan["risk_facts"][0]["fact_refs"] = ["risk://fabricated-critical"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_FACT_REF:RISK:risk://fabricated-critical"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_fabricated_project_fact_ref_is_rejected(self) -> None:
        plan = ui_plan()
        plan["project_fact_refs"] = ["project://fabricated-stack"]
        plan["perspectives"][0]["basis"]["project_fact_refs"] = ["project://fabricated-stack"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_FACT_REF:PROJECT:project://fabricated-stack"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_known_external_critical_risk_cannot_be_silently_omitted(self) -> None:
        catalog = observed_catalog()
        catalog["facts"].append({
            "ref": "risk://known-security-boundary",
            "kind": "RISK",
            "evidence_fingerprint": evidence_fingerprint("observed security boundary"),
            "safety_critical": True,
        })
        with self.assertRaisesRegex(RuntimeError, "KNOWN_SAFETY_CRITICAL_RISK_OMITTED:risk://known-security-boundary"):
            validate_plan(ui_plan(), observed_fact_catalog=catalog)

    def test_known_external_critical_risk_is_covered_by_dynamic_perspective(self) -> None:
        plan = ui_plan()
        plan["risk_facts"].append({
            "id": "runtime-selected-risk-7c",
            "safety_critical": False,
            "fact_refs": ["risk://known-security-boundary"],
        })
        plan["perspectives"].append({
            "id": "model-selected-view-7c",
            "rationale": "Current evidence exposes a safety boundary that requires explicit acceptance coverage.",
            "basis": {
                "artifact_ids": ["screen.entry"],
                "actor_ids": [],
                "usage_condition_ids": [],
                "risk_ids": ["runtime-selected-risk-7c"],
                "project_fact_refs": [],
            },
            "acceptance_refs": ["semantic://security-boundary-preserved"],
        })
        catalog = observed_catalog(plan)
        for fact in catalog["facts"]:
            if fact["ref"] == "risk://known-security-boundary":
                fact["safety_critical"] = True
        result = validate_plan(plan, observed_fact_catalog=catalog)
        self.assertIn("model-selected-view-7c", [item["id"] for item in result["perspectives"]])
        self.assertTrue(result["risk_facts"][-1]["safety_critical"])

    def test_acceptance_refs_distinguish_bound_authority_from_semantic_labels(self) -> None:
        plan = ui_plan()
        plan["perspectives"][0]["acceptance_refs"] = [
            "metric://formal-first-contact",
            "semantic://customer-understands-next-step",
        ]
        catalog = observed_catalog()
        catalog["acceptance_refs"].append({
            "ref": "metric://formal-first-contact",
            "classification": "BOUND_ACCEPTANCE_REF",
            "evidence_fingerprint": evidence_fingerprint("formal acceptance authority"),
        })
        result = validate_plan(plan, observed_fact_catalog=catalog)
        self.assertEqual(
            ["BOUND_ACCEPTANCE_REF", "SEMANTIC_ACCEPTANCE_LABEL"],
            [item["classification"] for item in result["perspectives"][0]["acceptance_reference_semantics"]],
        )

    def test_unbound_metric_ref_is_rejected(self) -> None:
        plan = ui_plan()
        plan["perspectives"][0]["acceptance_refs"] = ["metric://self-declared"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_ACCEPTANCE_REF:metric://self-declared"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_proposal_cannot_embed_its_own_evidence_catalog(self) -> None:
        plan = ui_plan()
        plan["observed_fact_catalog"] = observed_catalog()
        with self.assertRaisesRegex(RuntimeError, "PERSPECTIVE_PROPOSAL_CANNOT_DECLARE_EVIDENCE_CATALOG"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_applicable_plan_requires_external_catalog(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "PERSPECTIVE_OBSERVED_FACT_CATALOG_REQUIRED"):
            validate_plan(ui_plan())

    def test_catalog_must_bind_current_project_fact_plane_when_present(self) -> None:
        catalog = observed_catalog()
        catalog["project_fact_fingerprint"] = "a" * 64
        with self.assertRaisesRegex(RuntimeError, "OBSERVED_PROJECT_FACT_FINGERPRINT_MISMATCH"):
            validate_plan(
                ui_plan(),
                observed_fact_catalog=catalog,
                expected_project_fact_fingerprint="b" * 64,
            )

    def test_route_rejects_catalog_from_another_task_scope(self) -> None:
        goal = "Implement one bounded UI slice"
        proposal = {
            "architecture": "bs",
            "client_families": [],
            "risk_class": "bounded",
            "contract_change": False,
            "gate_applicability": gate_plan(goal),
            "perspective_applicability": ui_plan(),
        }
        result = route(
            goal,
            tech_stack={"observed_fact_catalog": observed_catalog(scope_text="different task")},
            proposal=proposal,
        )
        self.assertEqual("REJECTED", result["status"])
        self.assertIn("OBSERVED_FACT_SCOPE_FINGERPRINT_MISMATCH", result["diagnostics"][0])

    def test_fact_ref_cannot_be_laundered_across_catalog_kinds(self) -> None:
        plan = ui_plan()
        plan["actors"][0]["fact_refs"] = ["src/pages/Entry.tsx"]
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_PERSPECTIVE_FACT_REF:ACTOR:src/pages/Entry.tsx"):
            validate_plan(plan, observed_fact_catalog=observed_catalog())

    def test_real_ui_field_existing_refs_are_externally_grounded(self) -> None:
        evidence_path = PLUGIN.parents[1] / "docs" / "evidence" / "NEXT-01-ui-field.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        result = validate_plan(
            evidence["perspective_applicability"],
            observed_fact_catalog=evidence["observed_fact_catalog"],
            expected_scope_fingerprint=evidence["field_task_scope"]["fingerprint"],
        )
        self.assertEqual("APPLICABLE", result["status"])
        self.assertEqual(len(evidence["observed_fact_catalog"]["facts"]), result["evidence_grounding"]["observed_fact_count"])


if __name__ == "__main__":
    unittest.main()
