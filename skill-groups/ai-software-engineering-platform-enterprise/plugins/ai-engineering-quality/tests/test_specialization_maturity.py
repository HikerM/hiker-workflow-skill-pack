from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
ROOT = PLUGIN.parents[1]
TOOL = ROOT / "tools" / "audit_specialization_maturity.py"
SPEC = importlib.util.spec_from_file_location("audit_specialization_maturity", TOOL)
MODULE = importlib.util.module_from_spec(SPEC); assert SPEC and SPEC.loader; SPEC.loader.exec_module(MODULE)


class SpecializationMaturityTests(unittest.TestCase):
    def test_current_profiles_are_complete_and_on_demand(self):
        result = MODULE.audit(ROOT)
        self.assertTrue(result["ok"], result)
        self.assertEqual(4, result["profile_count"])
        self.assertEqual({"laravel-php", "node-typescript", "unity", "qt"}, set(result["profiles"]))
        self.assertEqual({"scripts":0,"state_writes":0,"prompt_bytes":0}, result["default_path_impact"])

    def test_shallow_profile_is_rejected(self):
        source = json.loads((ROOT / "docs/specialization-maturity-profiles.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td); (temp / "docs").mkdir(); (temp / "plugins").mkdir()
            for plugin in {item["plugin"] for item in source["profiles"]}:
                (temp / "plugins" / plugin).mkdir()
            copied = copy.deepcopy(source); copied["profiles"][0]["dimensions"] = ["identity"]
            (temp / "docs/specialization-maturity-profiles.json").write_text(json.dumps(copied), encoding="utf-8")
            (temp / "docs/SPECIALIZATION_MATURITY_TEMPLATE.md").write_text("template", encoding="utf-8")
            result = MODULE.audit(temp)
        self.assertFalse(result["ok"])
        self.assertIn("SHALLOW_PROFILE", {item["code"] for item in result["errors"]})


if __name__ == "__main__":
    unittest.main()
