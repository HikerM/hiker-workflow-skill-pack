from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from evidence_cache import compact_summary, decide as decide_evidence, evidence_key, invalidate, minimum_verification_set
from runtime_reuse import decide as decide_runtime


def runtime(platform: str = "BS_BROWSER") -> dict:
    return {
        "schema_version": "1.0.0",
        "runtime_id": "runtime-1",
        "platform": platform,
        "status": "READY",
        "source_fingerprint": "source-1",
        "project_config_fingerprint": "config-1",
        "technology_fingerprint": "technology-1",
        "environment_fingerprint": "environment-1",
        "relevant_state_fingerprint": "state-1",
        "authenticated_session_fingerprint": hashlib.sha256(b"opaque-session").hexdigest(),
        "capabilities": {"session_reuse": True, "incremental_reload": True},
        "targets": ["screen:settings", "screen:profile"],
    }


def identity(scope: list[str]) -> dict:
    return {
        "source_fingerprint": "source-1",
        "contract_fingerprint": "contract-1",
        "dependency_fingerprint": "dependency-1",
        "design_fingerprint": "design-1",
        "project_config_fingerprint": "config-1",
        "technology_fingerprint": "technology-1",
        "environment_fingerprint": "environment-1",
        "relevant_state_fingerprint": "state-1",
        "affected_scope": scope,
    }


class IncrementalGovernanceTests(unittest.TestCase):
    def test_browser_and_client_runtime_are_reused_only_with_matching_identity(self):
        for platform in ("BS_BROWSER", "CS_CLIENT"):
            existing = runtime(platform)
            required = dict(existing)
            required["runtime_id"] = "required"
            required["targets"] = ["screen:settings"]
            self.assertEqual("REUSE", decide_runtime(existing, required)["decision"])

    def test_source_change_uses_incremental_reload_but_technology_change_rebuilds(self):
        existing = runtime()
        source_changed = {**existing, "runtime_id": "required", "source_fingerprint": "source-2"}
        technology_changed = {**existing, "runtime_id": "required", "technology_fingerprint": "technology-2"}
        self.assertEqual("INCREMENTAL_RELOAD", decide_runtime(existing, source_changed)["decision"])
        self.assertEqual("REBUILD_REQUIRED", decide_runtime(existing, technology_changed)["decision"])

    def test_raw_authenticated_session_is_rejected_instead_of_reused(self):
        existing = runtime()
        required = {**existing, "runtime_id": "required", "authenticated_session_fingerprint": "session-cookie=value"}
        result = decide_runtime(existing, required)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("DO_NOT_REUSE", result["decision"])

    def test_evidence_cache_requires_all_identity_facts_and_exact_match(self):
        current = identity(["screen:settings"])
        record = {"status": "VALID", "evidence_key": evidence_key(current)}
        self.assertEqual("REUSE", decide_evidence(record, current)["status"])
        changed = dict(current)
        changed["environment_fingerprint"] = "environment-2"
        self.assertEqual("STALE", decide_evidence(record, changed)["status"])

    def test_local_change_invalidates_only_intersecting_evidence(self):
        records = [
            {"evidence_id": "settings", "status": "VALID", "affected_scope": ["screen:settings"]},
            {"evidence_id": "database", "status": "VALID", "affected_scope": ["database:users"]},
        ]
        result = invalidate(records, ["screen:settings"], "goal revision")
        self.assertEqual(["settings"], result["invalidated"])
        self.assertEqual(1, result["preserved"])
        self.assertEqual("VALID", result["records"][1]["status"])

    def test_scope_invalidation_understands_path_ancestors_and_rejects_unscoped_pass(self):
        records = [
            {"evidence_id": "service", "status": "VALID", "affected_scope": ["services/api"]},
            {"evidence_id": "client", "status": "VALID", "affected_scope": ["apps/client"]},
            {"evidence_id": "legacy-unscoped", "status": "VALID", "affected_scope": []},
        ]
        result = invalidate(records, ["services/api/routes/auth.ts"], "source change")
        self.assertEqual(["service", "legacy-unscoped"], result["invalidated"])
        self.assertEqual("VALID", result["records"][1]["status"])

    def test_minimum_verification_reuses_only_exact_current_pass(self):
        current = identity(["services/api"])
        key = evidence_key(current)
        checks = [
            {"verification_id": "api-unit", "affected_scope": ["services/api"], "command": "npm test"},
            {"verification_id": "client-unit", "affected_scope": ["apps/client"], "command": "npm test"},
        ]
        records = [{
            "verification_id": "api-unit", "evidence_id": "EV-API", "status": "VALID",
            "result": "PASS", "freshness": "CURRENT", "evidence_key": key,
            "affected_scope": ["services/api"],
        }]
        base = {key: value for key, value in current.items() if key != "affected_scope"}
        result = minimum_verification_set(checks, records, base)
        self.assertEqual(["api-unit"], [item["verification_id"] for item in result["reused"]])
        self.assertEqual(["client-unit"], [item["verification_id"] for item in result["execute"]])
        self.assertFalse(result["full_rerun"])

    def test_contract_or_dependency_change_cannot_reuse_pass(self):
        current = identity(["services/api"])
        record = {
            "verification_id": "api-unit", "status": "VALID", "result": "PASS", "freshness": "CURRENT",
            "evidence_key": evidence_key(current), "affected_scope": ["services/api"],
        }
        check = [{"verification_id": "api-unit", "affected_scope": ["services/api"]}]
        for field in ("contract_fingerprint", "dependency_fingerprint"):
            changed = {key: value for key, value in current.items() if key != "affected_scope"}
            changed[field] += "-changed"
            with self.subTest(field=field):
                result = minimum_verification_set(check, [record], changed)
                self.assertEqual(0, result["reuse_count"])
                self.assertEqual("STALE", result["execute"][0]["reuse_status"])

    def test_failed_or_historical_evidence_cannot_be_reused(self):
        current = identity(["services/api"])
        base = {key: value for key, value in current.items() if key != "affected_scope"}
        check = [{"verification_id": "api-unit", "affected_scope": ["services/api"]}]
        for record in (
            {"verification_id": "api-unit", "status": "VALID", "result": "FAIL", "freshness": "CURRENT", "evidence_key": evidence_key(current)},
            {"verification_id": "api-unit", "status": "VALID", "result": "PASS", "freshness": "HISTORICAL", "evidence_key": evidence_key(current)},
        ):
            self.assertEqual(0, minimum_verification_set(check, [record], base)["reuse_count"])

    def test_cold_summary_keeps_only_bounded_refs_hashes_and_findings(self):
        summary = compact_summary(
            identity(["screen:settings"]),
            evidence_id="evidence-1",
            status="VALID",
            findings=[{"code": "PASS", "surface": "screen:settings"}],
            artifacts=[{"ref": "capture.png", "sha256": "a" * 64, "bytes": 1024}],
        )
        self.assertTrue(summary["summary_only"])
        self.assertEqual(["ref", "sha256", "bytes"], list(summary["artifacts"][0]))
        with self.assertRaises(ValueError):
            compact_summary(
                identity(["screen:settings"]), evidence_id="bad", status="VALID", findings=[],
                artifacts=[{"ref": "capture.png", "sha256": "a" * 64, "bytes": 1024, "screenshot_bytes": "raw"}],
            )


if __name__ == "__main__":
    unittest.main()
