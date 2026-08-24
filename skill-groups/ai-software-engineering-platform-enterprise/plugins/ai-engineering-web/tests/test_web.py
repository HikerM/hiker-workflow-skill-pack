from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
PLUGIN=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(PLUGIN/"scripts"))
from component_registry import build
from web_audit import audit
from weblib import glob_match
from backend_guard import audit as backend_audit, detect as backend_detect

class WebTests(unittest.TestCase):
    def test_node_modules_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"node_modules/pkg").mkdir(parents=True);(root/"node_modules/pkg/Bad.vue").write_text("fetch('/api')")
            self.assertEqual([],list(__import__("weblib").source_files(root)))
    def test_auto_scope_never_falls_back_to_full_repository(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"src/pages").mkdir(parents=True);(root/"src/pages/Legacy.tsx").write_text("fetch('/api')")
            data=audit(root,scope="auto")
            self.assertEqual("none",data["scope"]);self.assertEqual(0,data["component_count"])
    def test_full_inventory_and_findings_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"src/pages").mkdir(parents=True)
            for i in range(5100):(root/f"src/pages/F{i}.tsx").write_text("fetch('/api')")
            data=audit(root,scope="full")
            self.assertTrue(data["inventory_truncated"]);self.assertLessEqual(len(data["findings"]),200)
            self.assertTrue(any("5000" in item for item in data["blockers"]))
    def test_registry_and_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/components").mkdir(parents=True); (root/"src/pages").mkdir()
            (root/"src/components/Card.vue").write_text("<template/><script setup lang='ts'></script>")
            (root/"src/pages/Card.vue").write_text("<template/><script setup lang='ts'></script>")
            data=build(root); self.assertIn("card",data["duplicate_names"])
    def test_audit_direct_http_and_root_file(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/pages").mkdir(parents=True); (root/"src/pages/UserPage.ts").write_text("fetch('/api/users');\n"+"const x:any=1;\n"*6)
            data=audit(root); rules={x["rule"] for x in data["findings"]}; self.assertIn("direct-http-in-page",rules); self.assertIn("excessive-any",rules)
    def test_glob_root_and_nested(self):
        self.assertTrue(glob_match("src/a.ts","src/**/*.ts")); self.assertTrue(glob_match("src/x/a.ts","src/**/*.ts"))
    def test_audit_flags_bootstrap_card_soup_and_raw_spacing(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/pages").mkdir(parents=True)
            (root/"src/pages/Dashboard.tsx").write_text("import 'bootstrap/dist/css/bootstrap.css';\n"+"<MetricCard className='card' />\n"*6+"const css=`padding:8px; margin:8px; gap:8px; padding-top:8px; margin-top:8px; row-gap:8px;`;\n")
            data=audit(root); rules={x["rule"] for x in data["findings"]}
            self.assertIn("bootstrap-style-review",rules); self.assertIn("unjustified-card-layout",rules); self.assertIn("hardcoded-spacing",rules)
            self.assertEqual("2.0.0",data["schema_version"])
            self.assertEqual("FAIL",data["result"])
    def test_audit_records_design_token_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/theme").mkdir(parents=True); (root/"src/theme/tokens.css").write_text(":root{--space-2:8px;--color-action:#0369a1}")
            data=audit(root); self.assertEqual(["src/theme/tokens.css"],data["design_system_evidence"]["token_files"])
            self.assertEqual("DECLARED_UNUSED",data["design_system_evidence"]["status"])
    def test_audit_detects_tailwind_surfaces_without_card_names(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/pages").mkdir(parents=True)
            surface='<section className="bg-white rounded-xl border p-6">x</section>\n'
            (root/"src/pages/Workspace.tsx").write_text(surface*4,encoding="utf-8")
            data=audit(root); rules={item["rule"] for item in data["findings"]}
            self.assertIn("unjustified-card-layout",rules); self.assertEqual("FAIL",data["result"])
    def test_review_requires_current_visual_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/theme").mkdir(parents=True); (root/"src/pages").mkdir(parents=True); (root/".ai/design").mkdir(parents=True)
            (root/"src/theme/tokens.css").write_text(":root{--color-surface:#fff}",encoding="utf-8")
            (root/"src/pages/Main.tsx").write_text("const x='var(--color-surface)'",encoding="utf-8")
            contract={key:[] if key in {"density_zones","card_usages","non_card_alternatives"} else "defined" for key in __import__("web_audit").REQUIRED_COMPOSITION_FIELDS}
            (root/".ai/design/ui-contract.json").write_text(json.dumps(contract),encoding="utf-8")
            data=audit(root,mode="review")
            self.assertEqual("BLOCKED",data["result"]); self.assertIn("missing current visual evidence",data["blockers"])
    def test_backend_guard_detects_stack_contract_and_migration(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"server").mkdir();(root/"server/package.json").write_text(json.dumps({"engines":{"node":">=20"},"packageManager":"pnpm@9","dependencies":{"@nestjs/core":"11.0.0"}}))
            (root/"server/openapi.yaml").write_text("openapi: 3.1.0\n");(root/"server/migrations").mkdir();(root/"server/migrations/001.sql").write_text("create table x(id int);\n")
            data=backend_detect(root);self.assertEqual("NestJS",data["stacks"][0]["framework"]);self.assertIn("server/openapi.yaml",data["contracts"]);self.assertIn("server/migrations/001.sql",data["migrations"])
            self.assertEqual("11.0.0",data["stacks"][0]["framework_version"])
            reviewed=backend_audit(root);self.assertEqual("PASS_WITH_WARNINGS",reviewed["result"]);self.assertTrue(any("回滚" in x for x in reviewed["warnings"]))
    def test_backend_guard_does_not_guess_without_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            data=backend_audit(Path(td));self.assertEqual("BLOCKED",data["result"]);self.assertTrue(data["blockers"])
    def test_backend_guard_rejects_frontend_and_desktop_false_positives(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"package.json").write_text(json.dumps({"dependencies":{"react":"19.0.0","vite":"7.0.0"}}),encoding="utf-8")
            self.assertEqual([],backend_detect(root)["stacks"])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"App.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0-windows</TargetFramework><UseWPF>true</UseWPF></PropertyGroup></Project>',encoding="utf-8")
            self.assertEqual([],backend_detect(root)["stacks"])
    def test_backend_guard_extracts_framework_runtime_and_package_manager(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"package.json").write_text(json.dumps({"engines":{"node":">=22"},"dependencies":{"express":"^5.1.0"}}),encoding="utf-8");(root/"pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n",encoding="utf-8")
            stack=backend_detect(root)["stacks"][0]
            self.assertEqual(("Express","5.1.0",">=22","pnpm"),(stack["framework"],stack["framework_version"],stack["runtime"],stack["package_manager"]))
if __name__=="__main__": unittest.main()
