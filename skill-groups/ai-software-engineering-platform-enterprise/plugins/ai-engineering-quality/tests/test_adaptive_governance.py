from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from adaptive_governance import DIMENSIONS, TAX_METRICS, assess, authorize, evaluate_tax
from risk_review import review


def assessment(
    *,
    levels: dict[str, str] | None = None,
    event: str = "ORDINARY_IMPLEMENTATION",
    intent: str = "PRODUCTION",
    reduce: bool = False,
    scope: list[str] | None = None,
    validators: list[str] | None = None,
    runtime_targets: list[dict] | None = None,
    full_scan_reason: str | None = None,
) -> dict:
    levels = levels or {}
    return {
        "schema_version": "1.0.0",
        "assessment_id": "RISK-001",
        "event_type": event,
        "delivery_intent": intent,
        "user_requested_reduction": reduce,
        "affected_scope": scope or ["surface:local"],
        "affected_capabilities": ["capability:local"],
        "requested_validators": validators or [],
        "runtime_targets": runtime_targets or [],
        "full_scan_reason": full_scan_reason,
        "source_fingerprint": "source-1",
        "design_fingerprint": "design-1",
        "project_config_fingerprint": "config-1",
        "technology_fingerprint": "technology-1",
        "environment_fingerprint": "environment-1",
        "state_id": "state-1",
        "dimensions": {
            name: {
                "level": levels.get(name, "LOW"),
                "basis": "MODEL_ASSESSMENT",
                "reason": f"bounded assessment for {name}",
                "evidence_refs": [f"fact:{name}"],
            }
            for name in DIMENSIONS
        },
    }


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


class AdaptiveGovernanceTests(unittest.TestCase):
    def test_low_ordinary_work_keeps_model_free_and_governance_inactive(self):
        profile = assess(assessment())
        self.assertEqual("VERIFIED", profile["status"])
        self.assertEqual("LOW", profile["risk_level"])
        self.assertEqual("NONE", profile["activation"])
        self.assertEqual("NONE", profile["scope_mode"])
        self.assertEqual([], profile["contract"]["fixed_steps"])
        self.assertTrue(all(value == 0 for value in profile["governance_tax_budget"].values()))
        self.assertEqual("MODEL_DECIDES", profile["model_freedom"]["implementation_order"])

    def test_ten_dimensions_raise_risk_without_file_count_or_keywords(self):
        profile = assess(assessment(levels={
            "business_criticality": "MEDIUM",
            "shared_scope": "MEDIUM",
            "runtime_impact": "MEDIUM",
        }))
        self.assertEqual("HIGH", profile["semantic_level"])
        self.assertEqual("HIGH", profile["risk_level"])
        self.assertEqual("GOVERNED", profile["activation"])
        self.assertEqual("INDEPENDENT", profile["review_policy"]["depth"])

    def test_sparse_key_event_is_targeted_and_evidence_is_scope_reusable(self):
        first = assess(assessment(event="GOAL_CHANGE", scope=["screen:settings"]))
        second = assess(assessment(event="GOAL_CHANGE", scope=["screen:settings"]))
        changed = assess(assessment(event="GOAL_CHANGE", scope=["screen:profile"]))
        self.assertEqual("TARGETED", first["activation"])
        self.assertEqual("AFFECTED_SCOPE", first["scope_mode"])
        self.assertFalse(first["evidence_policy"]["cold_history_scan"])
        self.assertEqual(first["evidence_policy"]["reuse_key"], second["evidence_policy"]["reuse_key"])
        self.assertNotEqual(first["evidence_policy"]["reuse_key"], changed["evidence_policy"]["reuse_key"])

    def test_prototype_reduces_only_non_safety_governance(self):
        prototype = assess(assessment(
            levels={"business_criticality": "HIGH"}, intent="PROTOTYPE", reduce=True,
        ))
        security = assess(assessment(
            levels={"security_impact": "HIGH"}, intent="PROTOTYPE", reduce=True,
        ))
        invalid = assess(assessment(intent="PRODUCTION", reduce=True))
        self.assertEqual("PROTOTYPE", prototype["artifact_status"])
        self.assertFalse(prototype["release_ready"])
        self.assertEqual("MEDIUM", prototype["control_level"])
        self.assertEqual("TARGETED", prototype["activation"])
        self.assertEqual("HIGH", security["control_level"])
        self.assertEqual("GOVERNED", security["activation"])
        self.assertIn("SECURITY_BOUNDARY", security["hard_boundaries"])
        self.assertEqual("INVALID", invalid["status"])
        self.assertEqual("REQUIRES_REVIEW", invalid["decision"])

    def test_invalid_semantic_assessment_fails_closed_without_guessing(self):
        payload = assessment()
        del payload["dimensions"]["evidence_uncertainty"]
        profile = assess(payload)
        self.assertEqual("INVALID", profile["status"])
        self.assertEqual("REQUIRES_REVIEW", profile["decision"])
        self.assertEqual("GOVERNED", profile["activation"])

    def test_governance_tax_compares_to_517_and_blocks_simple_task_inflation(self):
        profile = assess(assessment())
        baseline = {metric: 0 for metric in TAX_METRICS}
        self.assertTrue(evaluate_tax(profile, baseline, baseline)["ok"])
        inflated = dict(baseline)
        inflated["governance_tool_calls"] = 1
        report = evaluate_tax(profile, inflated, baseline)
        self.assertFalse(report["ok"])
        self.assertIn("inactive sparse governance added cost", " ".join(report["errors"]))

    def test_existing_risk_report_uses_semantic_dimensions_without_second_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            git(root, "init", "-b", "main")
            git(root, "config", "user.email", "hiker.invalid")
            git(root, "config", "user.name", "Hiker")
            (root / "README.md").write_text("baseline\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "baseline")
            (root / "README.md").write_text("small change\n", encoding="utf-8")
            report = review(root, risk_context=assessment(levels={"architecture_impact": "HIGH"}))
        self.assertEqual(3, report["schema_version"])
        self.assertEqual("LOW", report["risk"]["observed_level"])
        self.assertEqual("HIGH", report["risk"]["level"])
        self.assertEqual("VERIFIED", report["semantic_assessment"]["status"])
        self.assertEqual("GOVERNED", report["controls"]["activation"])

    def test_low_ui_work_authorizes_only_the_requested_targeted_verification(self):
        profile = assess(assessment(
            validators=["PRESENTATION"],
            runtime_targets=[{
                "surface_id": "screen:settings",
                "states": ["default"],
                "environments": ["desktop"],
            }],
        ))
        budget = profile["verification_budget"]
        self.assertEqual("PASS", budget["status"])
        self.assertEqual("TARGETED", profile["activation"])
        self.assertEqual("TARGETED", budget["runtime_mode"])
        self.assertEqual("TARGETED_ONLY", budget["visual_matrix"])
        self.assertTrue(authorize(profile, "VALIDATOR", "PRESENTATION")["allowed"])
        self.assertFalse(authorize(profile, "VALIDATOR", "ARCHITECTURE")["allowed"])
        self.assertFalse(authorize(profile, "FULL_VISUAL_MATRIX")["allowed"])
        self.assertFalse(authorize(profile, "FULL_PROJECT_SCAN")["allowed"])

    def test_low_task_must_be_reclassified_when_verification_scope_is_too_large(self):
        profile = assess(assessment(validators=["PRESENTATION", "CONTENT_STRESS", "INTERACTION"]))
        self.assertEqual("REQUIRES_RECLASSIFICATION", profile["verification_budget"]["status"])
        self.assertEqual("REQUIRES_REVIEW", profile["decision"])
        self.assertFalse(profile["release_ready"])
        self.assertFalse(authorize(profile, "TARGETED_RUNTIME")["allowed"])

    def test_critical_release_enables_release_matrix_and_independent_review(self):
        profile = assess(assessment(
            levels={"release_impact": "CRITICAL"},
            event="RELEASE",
            validators=["SECURITY"],
        ))
        budget = profile["verification_budget"]
        self.assertEqual("PASS", budget["status"])
        self.assertEqual("RELEASE_MATRIX", budget["runtime_mode"])
        self.assertTrue(budget["independent_review"])
        self.assertIn("RELEASE_GATE", budget["authorized_validators"])
        self.assertIn("REGRESSION", budget["authorized_validators"])
        self.assertTrue(authorize(profile, "FULL_VISUAL_MATRIX")["allowed"])
        self.assertTrue(authorize(profile, "INDEPENDENT_REVIEW")["allowed"])

    def test_full_repository_scan_requires_an_explicit_allowed_reason(self):
        denied = assess(assessment(levels={"architecture_impact": "HIGH"}))
        allowed = assess(assessment(
            levels={"architecture_impact": "HIGH"},
            full_scan_reason="TECHNOLOGY_MIGRATION",
        ))
        self.assertFalse(authorize(denied, "FULL_PROJECT_SCAN")["allowed"])
        self.assertTrue(authorize(allowed, "FULL_PROJECT_SCAN")["allowed"])

    def test_evidence_reuse_key_binds_configuration_technology_environment_and_state(self):
        original = assessment()
        base = assess(original)["evidence_policy"]["reuse_key"]
        for field in (
            "project_config_fingerprint", "technology_fingerprint",
            "environment_fingerprint", "state_id",
        ):
            changed = dict(original)
            changed[field] = f"different-{field}"
            self.assertNotEqual(base, assess(changed)["evidence_policy"]["reuse_key"])


if __name__ == "__main__":
    unittest.main()
