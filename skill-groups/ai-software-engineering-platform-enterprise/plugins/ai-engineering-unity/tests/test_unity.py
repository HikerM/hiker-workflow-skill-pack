from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
PLUGIN=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PLUGIN/"scripts"))
from unity_audit import audit
from unity_registry import build
from client_stack import classify
from cs_ui_adapter import observe as observe_cs_ui

class UnityTests(unittest.TestCase):
    def make_project(self,root:Path):
        (root/"ProjectSettings").mkdir();(root/"Packages").mkdir();(root/"Assets/UI").mkdir(parents=True)
        (root/"ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.62f1\n")
        (root/"Packages/manifest.json").write_text(json.dumps({"dependencies":{"com.unity.ugui":"1.0.0"}}))
    def test_library_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make_project(root);(root/"Library/ScriptAssemblies").mkdir(parents=True);(root/"Library/ScriptAssemblies/Bad.cs").write_text('GameObject.Find("x")')
            data=audit(root);self.assertNotIn("Library/ScriptAssemblies/Bad.cs",{f.get("path") for f in data["findings"]})
    def test_registry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make_project(root);(root/"Assets/UI/Page.cs").write_text("class PageRenderer {}") ;(root/"Assets/UI/Page.cs.meta").write_text("guid: abc")
            data=build(root);self.assertEqual(data["unity_version"],"2022.3.62f1");self.assertEqual(len(data["scripts"]),1)
    def test_audit_patterns_and_meta(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make_project(root);(root/"Assets/UI/Page.cs").write_text("class P { void Update(){} void X(){ GameObject.Find(\"A\"); } }")
            data=audit(root);rules={f["rule"] for f in data["findings"]};self.assertIn("gameobject-find",rules);self.assertIn("ui-update-loop",rules);self.assertIn("missing-meta",rules)
    def test_missing_script(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make_project(root);(root/"Assets/UI/X.prefab").write_text("m_Script: {fileID: 0}");(root/"Assets/UI/X.prefab.meta").write_text("guid: aaa")
            data=audit(root);self.assertIn("missing-script",{f["rule"] for f in data["findings"]})
    def test_client_stack_routes_supported_families_without_repository_scan(self):
        cases={
            "unity":"Unity", "qt":"Qt", "dotnet-desktop":"WPF", "electron-tauri":"Tauri",
            "flutter":"Flutter", "android":"Jetpack Compose", "apple-native":"SwiftUI",
            "react-native":"React Native", "java-desktop":"JavaFX", "embedded-hmi":"LVGL",
        }
        for expected,framework in cases.items():
            with self.subTest(framework=framework):
                data=classify({"projects":[{"frameworks":[{"name":framework}]}]})
                self.assertEqual(expected,data["family"])
                self.assertEqual("load-one-phase-and-one-family-only",data["performance_policy"])
    def test_client_stack_unknown_is_explicit(self):
        data=classify({"projects":[]});self.assertEqual("unknown",data["family"]);self.assertTrue(data["uncertainties"])
    def test_client_stack_reports_version_evidence_and_gaps(self):
        data=classify({"projects":[{"manifest":"App.csproj","languages":[{"name":"C#","version":None}],"frameworks":[{"name":"WPF","version":"net8.0-windows","evidence":"TargetFramework"}]}]})
        self.assertEqual("dotnet-desktop",data["family"]);self.assertEqual("net8.0-windows",next(x for x in data["technologies"] if x["name"]=="WPF")["version"]);self.assertIn("C#",data["version_gaps"])
    def test_cs_ui_adapter_uses_explicit_scope_and_keeps_unseen_semantics_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"ui").mkdir()
            (root/"ui/Main.qml").write_text("Item { property bool busy: true; Accessible.name: 'Main' }",encoding="utf-8")
            data=observe_cs_ui(root,["ui/Main.qml"])
            self.assertEqual(data["scope"]["mode"],"EXPLICIT")
            self.assertEqual(data["technology"]["value"]["families"],["qt"])
            self.assertEqual(data["components"][0]["design_component"]["status"],"UNKNOWN")
if __name__=="__main__":unittest.main()
