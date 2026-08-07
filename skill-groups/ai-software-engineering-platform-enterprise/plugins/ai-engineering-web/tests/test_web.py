from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
PLUGIN=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(PLUGIN/"scripts"))
from component_registry import build
from web_audit import audit
from weblib import glob_match

class WebTests(unittest.TestCase):
    def test_node_modules_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"node_modules/pkg").mkdir(parents=True);(root/"node_modules/pkg/Bad.vue").write_text("fetch('/api')")
            self.assertEqual([],list(__import__("weblib").source_files(root)))
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
            self.assertIn("bootstrap-style-review",rules); self.assertIn("repetitive-card-signal",rules); self.assertIn("hardcoded-spacing",rules)
            self.assertEqual("1.1.0",data["schema_version"])
    def test_audit_records_design_token_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"src/theme").mkdir(parents=True); (root/"src/theme/tokens.css").write_text(":root{--space-2:8px;--color-action:#0369a1}")
            data=audit(root); self.assertEqual(["src/theme/tokens.css"],data["design_system_evidence"]["token_files"])
if __name__=="__main__": unittest.main()
