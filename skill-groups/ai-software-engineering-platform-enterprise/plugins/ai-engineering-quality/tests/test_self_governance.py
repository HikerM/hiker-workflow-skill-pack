from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SUITE = PLUGIN.parents[1]
REPOSITORY = SUITE.parents[1]
sys.path.insert(0, str(SUITE / "tools"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

from audit_public_content import _scan_text
from audit_release_facts import audit as audit_release_facts, synchronize
from benchmark_product_assurance import benchmark as benchmark_product_assurance
from benchmark_governance_precision import benchmark as benchmark_governance_precision
from benchmark_delivery_velocity import benchmark as benchmark_delivery_velocity
from audit_governance_enforcement import audit as audit_governance_enforcement
from audit_resource_budgets import audit as audit_resource_budgets
from audit_static_drift import audit as audit_static_drift
from package_facts import audit_packages
from package_release import build_candidates, release
from self_governance import STAGE_ORDER, architecture_gate, run_pipeline


def stage(name: str, ok: bool = True) -> dict:
    return {"name": name, "status": "PASS" if ok else "BLOCKED", "seconds": 0.0, "errors": [] if ok else ["injected"], "facts": {}}


class SelfGovernanceTests(unittest.TestCase):
    def test_pipeline_is_ordered_and_fails_closed_without_running_later_stages(self):
        called: list[str] = []
        overrides = {}
        for name in STAGE_ORDER:
            def handler(current: str = name) -> dict:
                called.append(current)
                return stage(current, current != "version_facts")
            overrides[name] = handler
        report = run_pipeline(REPOSITORY, SUITE, overrides=overrides)
        self.assertFalse(report["ok"])
        self.assertEqual("version_facts", report["blocked_stage"])
        self.assertEqual(["architecture", "privacy", "version_facts"], called)
        self.assertEqual(["NOT_RUN", "NOT_RUN", "NOT_RUN"], [item["status"] for item in report["stages"][3:]])

    def test_gate_exception_is_blocked_not_ignored(self):
        report = run_pipeline(
            REPOSITORY,
            SUITE,
            overrides={"architecture": lambda: (_ for _ in ()).throw(RuntimeError("boom"))},
        )
        self.assertFalse(report["ok"])
        self.assertEqual("architecture", report["blocked_stage"])
        self.assertIn("unhandled gate error", report["stages"][0]["errors"][0])

    def test_privacy_detects_raw_escaped_paths_and_credentials_but_allows_product_ids(self):
        unsafe = "\n".join([
            "C:" + r"\Users\Administrator\project\file.txt",
            '"path":"C:' + r'\\Users\\Administrator\\project\\file.txt"',
            "/ho" + "me/alice/project/file.txt",
            'access_' + 'token = "super-secret-value-123"',
            "Authorization: " + "Bearer " + "abcdefghijklmnopqrstuvwxyz012345",
            "-----BEGIN PRIVATE" + " KEY-----",
        ])
        codes = {item["code"] for item in _scan_text("fixture.json", unsafe)}
        self.assertTrue({"WINDOWS_USER_PATH", "UNIX_USER_PATH", "SECRET_LITERAL", "BEARER_TOKEN", "PRIVATE_KEY_BLOCK"}.issubset(codes))
        self.assertEqual([], _scan_text("product.txt", "Hiker hikerctl HIKER_CONTROL_TRACE Hiker Engineering Capability System"))

    def test_architecture_gate_enforces_thin_cli_and_single_task_writer(self):
        report = architecture_gate(REPOSITORY, SUITE)
        self.assertEqual("PASS", report["status"], report["errors"])
        self.assertLessEqual(report["facts"]["hikerctl_lines"], 250)
        self.assertLessEqual(report["facts"]["governance_state_lines"], 700)
        self.assertTrue(report["facts"]["single_task_writer"])
        self.assertTrue(report["facts"]["governance_enforcement"]["ok"])

    def test_machine_enforceable_rules_have_runtime_tests_and_no_default_hook(self):
        report = audit_governance_enforcement(SUITE)
        self.assertTrue(report["ok"], report["errors"])
        self.assertGreater(report["classifications"]["machine_enforceable"], 0)
        self.assertGreater(report["classifications"]["reasoning_guidance"], 0)
        self.assertEqual(0, report["default_prompt_bytes_added"])

    def test_resource_budget_authority_is_release_blocking_and_bounded(self):
        report = audit_resource_budgets(SUITE)
        self.assertTrue(report["ok"], report["errors"])
        self.assertGreater(report["checked_files"], 10)
        self.assertFalse(report["full_repository_scan"])
        self.assertEqual(0, report["default_prompt_bytes_added"])
        with tempfile.TemporaryDirectory() as td:
            copied = Path(td) / "suite"
            shutil.copytree(SUITE, copied, ignore=shutil.ignore_patterns("dist", "__pycache__", "*.pyc"))
            bounded_run = copied / "plugins" / "ai-engineering-core" / "scripts" / "bounded_run.py"
            bounded_run.write_text(
                bounded_run.read_text(encoding="utf-8").replace("effective_value", "detached_value"),
                encoding="utf-8",
            )
            blocked = audit_resource_budgets(copied)
        self.assertFalse(blocked["ok"])
        self.assertTrue(any("enforcement disconnected" in item for item in blocked["errors"]))

    def test_static_drift_audit_is_release_only_and_blocks_parallel_authorities(self):
        report = audit_static_drift(SUITE)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(0, report["runtime_cost_delta"])
        self.assertEqual(0, report["runtime_imports_added"])
        self.assertFalse(report["full_repository_scan"])
        self.assertEqual("CI_RELEASE_OR_EXPLICIT_AUDIT_ONLY", report["execution_scope"])
        with tempfile.TemporaryDirectory() as td:
            copied = Path(td) / "suite"
            shutil.copytree(SUITE, copied, ignore=shutil.ignore_patterns("dist", "__pycache__", "*.pyc"))
            convergence = copied / "plugins" / "ai-engineering-workspace" / "scripts" / "convergence_guard.py"
            convergence.write_text(convergence.read_text(encoding="utf-8") + "\ndef save_task(root, task):\n    pass\n", encoding="utf-8")
            task_router = copied / "plugins" / "ai-engineering-workspace" / "scripts" / "task_router.py"
            task_router.write_text(task_router.read_text(encoding="utf-8") + '\nif project_id == "FIELD-CUSTOMER-A":\n    pass\n', encoding="utf-8")
            blocked = audit_static_drift(copied)
        self.assertFalse(blocked["ok"])
        self.assertTrue(any("parallel governed Task writer" in item for item in blocked["errors"]))
        self.assertTrue(any("field-specific business branch" in item for item in blocked["errors"]))

    def test_product_assurance_performance_is_bounded_by_hot_index(self):
        report = benchmark_product_assurance(runs=5, cold_records=50, component_count=50, element_count=64)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(1, report["legacy_no_ui"]["reads"])
        self.assertEqual(9, report["active_hot_index"]["reads"])
        self.assertFalse(report["cold_history"]["scanned"])
        self.assertEqual(0, report["default_prompt_or_skill_bytes_added"])

    def test_governance_precision_preserves_ai_freedom_and_zero_simple_task_tax(self):
        report = benchmark_governance_precision(runs=20)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual([], report["ai_freedom"]["fixed_steps"])
        self.assertEqual("NONE", report["control_precision"]["low"]["activation"])
        self.assertEqual("GOVERNED", report["control_precision"]["high"]["activation"])
        self.assertTrue(report["control_precision"]["monotonic"])
        self.assertEqual(0, report["default_surfaces"]["default_context_bytes_added"])

    def test_delivery_velocity_uses_real_module_paths_and_marks_missing_baselines(self):
        report = benchmark_delivery_velocity(runs=2)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(1.0, report["first_pass_acceptance"]["rate"])
        self.assertGreaterEqual(report["runtime_reuse"]["rate"], 0.6)
        self.assertTrue(all(item["five_17_comparable_baseline"] == "NOT_MEASURED" for item in report["scenarios"]))
        self.assertEqual(0, report["default_token_impact"]["injected_prompt_bytes"])

    def test_package_facts_detect_source_change_after_candidate_build(self):
        with tempfile.TemporaryDirectory() as td:
            suite = Path(td) / "suite"
            plugin = suite / "plugins" / "demo"
            (plugin / ".codex-plugin").mkdir(parents=True)
            (plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "demo", "version": "1.2.3"}), encoding="utf-8")
            (plugin / "README_CN.md").write_text("first\n", encoding="utf-8")
            candidate = Path(td) / "candidate"
            build_candidates(suite, candidate)
            self.assertTrue(audit_packages(suite, candidate)["ok"])
            (plugin / "README_CN.md").write_text("changed\n", encoding="utf-8")
            report = audit_packages(suite, candidate)
            self.assertFalse(report["ok"])
            self.assertTrue(any("stale source member" in item for item in report["errors"]))

    def test_blocked_source_gate_never_builds_or_publishes(self):
        calls: list[str] = []
        report = release(
            REPOSITORY,
            SUITE,
            Path("unused"),
            preflight_runner=lambda *_: {"ok": False, "release_gate": "BLOCKED"},
            builder=lambda *_: calls.append("build") or [],
            publisher=lambda *_: calls.append("publish") or [],
        )
        self.assertFalse(report["published"])
        self.assertEqual([], calls)

    def test_blocked_package_facts_never_publish(self):
        stages = [stage(name) for name in STAGE_ORDER]
        preflight = {"ok": True, "stages": stages, "release_gate": "PASS_FOR_PACKAGING"}
        calls: list[str] = []
        report = release(
            REPOSITORY,
            SUITE,
            Path("unused"),
            preflight_runner=lambda *_: preflight,
            builder=lambda *_: [],
            publisher=lambda *_: calls.append("publish") or [],
        )
        self.assertFalse(report["published"])
        self.assertEqual([], calls)
        self.assertEqual("package-facts", report["phase"])

    def test_blocked_clean_install_never_publishes_verified_candidates(self):
        stages = [stage(name) for name in STAGE_ORDER]
        preflight = {"ok": True, "stages": stages, "release_gate": "PASS_FOR_PACKAGING"}
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as td:
            suite = Path(td) / "suite"
            plugin = suite / "plugins" / "demo"
            (plugin / ".codex-plugin").mkdir(parents=True)
            (plugin / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "demo", "version": "1.2.3"}), encoding="utf-8"
            )
            (plugin / "README_CN.md").write_text("candidate\n", encoding="utf-8")
            report = release(
                REPOSITORY,
                suite,
                Path(td) / "dist",
                preflight_runner=lambda *_: preflight,
                installer_verifier=lambda *_: {"ok": False, "errors": ["injected install failure"]},
                publisher=lambda *_: calls.append("publish") or [],
            )
        self.assertFalse(report["ok"])
        self.assertFalse(report["published"])
        self.assertEqual([], calls)
        self.assertEqual("clean-install", report["phase"])
        self.assertEqual("clean_install", report["self_governance"]["blocked_stage"])
        self.assertEqual("BLOCKED", report["self_governance"]["release_gate"])

    def test_single_version_source_repairs_derived_surfaces_without_version_bump(self):
        with tempfile.TemporaryDirectory() as td:
            copied = Path(td) / "repo"
            shutil.copytree(REPOSITORY, copied, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__", "*.pyc"))
            version_source = json.loads((copied / "release-versions.json").read_text(encoding="utf-8"))
            manifest = copied / "skill-groups" / "ai-software-engineering-platform-enterprise" / "plugins" / "ai-engineering-core" / ".codex-plugin" / "plugin.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["version"] = "9.9.9"
            manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.assertFalse(audit_release_facts(copied, require_archives=False, require_test_report=False)["ok"])
            synced = synchronize(copied)
            self.assertEqual("release-versions.json", synced["source"])
            self.assertTrue(audit_release_facts(copied, require_archives=False, require_test_report=False)["ok"])
            self.assertEqual(version_source["repository"], (copied / "VERSION").read_text(encoding="utf-8").strip())
            self.assertEqual(version_source["engineering"], json.loads(manifest.read_text(encoding="utf-8"))["version"])


if __name__ == "__main__":
    unittest.main()
