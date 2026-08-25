from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from unity_specialization import audit


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")


class UnitySpecializationTests(unittest.TestCase):
    def make_identity(self, root: Path, with_lock: bool = True) -> None:
        write(root, "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 2022.3.62f1\n")
        write(root, "Packages/manifest.json", json.dumps({"dependencies":{"com.unity.ugui":"1.0.0","com.unity.test-framework":"1.3.9"}}))
        if with_lock:
            write(root, "Packages/packages-lock.json", json.dumps({"dependencies":{"com.unity.ugui":{"version":"1.0.0"},"com.unity.test-framework":{"version":"1.3.9"}}}))

    def test_unity_positive_evidence_covers_all_dimensions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.make_identity(root)
            write(root, "ProjectSettings/ProjectSettings.asset", "selectedBuildTargetGroup: Android\n")
            write(root, "ProjectSettings/EditorBuildSettings.asset", "m_Scenes: []\n")
            write(root, "Assets/App/App.asmdef", json.dumps({"name":"App","includePlatforms":["Android"]}))
            write(root, "Assets/App/Screen.cs", """
using UnityEngine; using UnityEngine.UI;
class Screen : MonoBehaviour { Button button; void OnEnable(){ button.onClick += Run; } void OnDisable(){ button.onClick -= Run; } void Update(){ Tick(); } void Run(){} void Tick(){} }
""")
            write(root, "Assets/App/Screen.prefab", "m_Script: {fileID: 11500000, guid: abc}\n")
            write(root, "Assets/App/Screen.prefab.meta", "guid: abc\n")
            write(root, "Assets/Editor/Build.cs", "#if UNITY_ANDROID\nBuildPipeline.BuildPlayer(new BuildPlayerOptions { target = BuildTarget.Android });\n#endif")
            write(root, "Assets/Tests/EditMode/AppTests.asmdef", json.dumps({"name":"App.Tests","optionalUnityReferences":["TestAssemblies"]}))
            write(root, "Assets/Tests/EditMode/AppTests.cs", "using NUnit.Framework; class AppTests { [Test] public void Works(){} }")
            data = audit(root)
            self.assertEqual("PASS", data["result"], data)
            self.assertEqual("2022.3.62f1", data["identity"]["unity_version"])
            self.assertEqual(["uGUI"], data["identity"]["ui_systems"])
            self.assertTrue(all(item["status"] == "PASS" for item in data["dimensions"].values()))

    def test_unity_negative_detects_lifecycle_gc_and_asset_failures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.make_identity(root, with_lock=False)
            write(root, "Assets/UI/Bad.cs", """
using UnityEngine; using UnityEngine.UI; using System.Collections.Generic;
class Bad : MonoBehaviour { Button button; void OnEnable(){ button.onClick += Run; } void Update(){ var x = new List<int>(); } void Run(){} }
""")
            write(root, "Assets/UI/Bad.prefab", "m_Script: {fileID: 0}\n")
            data = audit(root)
            self.assertEqual("BLOCKED", data["result"])
            self.assertEqual("GAP", data["dimensions"]["identity_and_packages"]["status"])
            self.assertIn("subscription-without-unsubscribe", {item["rule"] for item in data["dimensions"]["lifecycle"]["findings"]})
            self.assertIn("hot-loop-allocation", {item["rule"] for item in data["dimensions"]["gc_allocation"]["findings"]})
            self.assertIn("missing-script-reference", {item["rule"] for item in data["dimensions"]["asset_references"]["findings"]})

    def test_non_unity_project_is_blocked_instead_of_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            data = audit(Path(td))
            self.assertEqual("BLOCKED", data["result"])
            self.assertEqual("unknown", data["identity"]["unity_version"])

    def test_default_audit_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.make_identity(root); audit(root)
            self.assertFalse((root / ".ai").exists())


if __name__ == "__main__":
    unittest.main()
