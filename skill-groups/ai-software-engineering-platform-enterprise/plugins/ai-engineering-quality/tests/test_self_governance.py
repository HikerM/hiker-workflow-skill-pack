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
