from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from detect_project import detect
from engineering_manifests import DiscoveryBudget, discover_engineering_manifests
from project_fact_plane import build_project_fact_plane
from technology_markers import (
    ENGINEERING_MANIFEST_NAMES,
    PROJECT_MARKER_PATHS,
    STATE_FINGERPRINT_NAMES,
    manifest_signals,
)


class TechnologyMarkerAuthorityTests(unittest.TestCase):
    def test_node_manifest_has_one_shared_framework_and_topology_parser(self):
        content = json.dumps({
            "engines": {"node": ">=22"},
            "dependencies": {"react": "19", "express": "5", "pg": "8"},
        })
        signals = manifest_signals("apps/portal/package.json", content)
        self.assertEqual(["backend", "frontend"], signals["roles"])
        self.assertEqual(["express", "react"], signals["frameworks"])
        self.assertEqual(["postgresql"], signals["databases"])
        self.assertEqual(["node:>=22"], signals["runtimes"])

    def test_react_native_does_not_create_a_false_browser_surface(self):
        signals = manifest_signals(
            "mobile/package.json",
            json.dumps({"dependencies": {"react": "19", "react-native": "0.80"}}),
        )
        self.assertEqual(["client"], signals["roles"])
        self.assertEqual(["react-native"], signals["frameworks"])

    def test_new_static_marker_is_consumed_by_detection_and_fact_plane(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Package.swift").write_text("// swift-tools-version: 6.0\nimport SwiftUI\n", encoding="utf-8")
            detected = detect(root)
            self.assertEqual("swift", detected["projects"][0]["kind"])
            facts = build_project_fact_plane(root)
            self.assertEqual("cs", facts["project_architecture"]["value"])
            self.assertIn("apple-native", facts["framework_facts"]["value"])
            self.assertEqual(["."], facts["project_topology"]["value"]["client_roots"])

    def test_registry_drives_bounded_discovery_without_source_scan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "src" / "fake.py").write_text("express react Package.swift", encoding="utf-8")
            (root / "pubspec.yaml").write_text("dependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
            report = discover_engineering_manifests(root, budget=DiscoveryBudget(max_depth=2, max_dirs=8, max_manifests=4, max_bytes=4096))
            self.assertEqual(["pubspec.yaml"], [item["path"] for item in report["manifests"]])
            self.assertEqual(0, report["metrics"]["full_scan_count"])
            self.assertLessEqual(report["metrics"]["directories_read"], 8)

    def test_identity_and_state_fingerprints_share_registry_constants(self):
        self.assertIn("Package.swift", ENGINEERING_MANIFEST_NAMES)
        self.assertIn("Packages/manifest.json", PROJECT_MARKER_PATHS)
        self.assertIn("package-lock.json", STATE_FINGERPRINT_NAMES)
        self.assertNotIn("create_model_node_docx.py", PROJECT_MARKER_PATHS)

    def test_core_consumers_do_not_redeclare_marker_or_framework_tables(self):
        detect_source = (PLUGIN / "scripts" / "detect_project.py").read_text(encoding="utf-8")
        fact_source = (PLUGIN / "scripts" / "project_fact_plane.py").read_text(encoding="utf-8")
        identity_source = (PLUGIN / "scripts" / "source_identity.py").read_text(encoding="utf-8")
        consistency_source = (PLUGIN / "scripts" / "state_consistency.py").read_text(encoding="utf-8")
        self.assertNotIn("MANIFESTS={", detect_source)
        self.assertNotIn("FRONTEND_DEPENDENCIES", fact_source)
        self.assertNotIn("BACKEND_DEPENDENCIES", fact_source)
        self.assertIn("PROJECT_MARKERS = PROJECT_MARKER_PATHS", identity_source)
        self.assertIn("MANIFEST_NAMES = STATE_FINGERPRINT_NAMES", consistency_source)


if __name__ == "__main__":
    unittest.main()
