from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
ROOT = PLUGIN.parents[1]
EVAL_DIR = PLUGIN / "evals" / "semantic-routing"
TOOL = ROOT / "tools" / "evaluate_semantic_routing.py"
SPEC = importlib.util.spec_from_file_location("evaluate_semantic_routing", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class SemanticRoutingEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))
        self.gold = json.loads((EVAL_DIR / "gold.json").read_text(encoding="utf-8"))
        self.predictions = json.loads((EVAL_DIR / "host-baseline.json").read_text(encoding="utf-8"))

    def evaluate(self, cases=None, gold=None, predictions=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = []
            for name, data in (
                ("cases.json", cases or self.cases),
                ("gold.json", gold or self.gold),
                ("predictions.json", predictions or self.predictions),
            ):
                path = root / name
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                paths.append(path)
            return MODULE.evaluate(*paths)

    def prediction(self, predictions, case_id):
        return next(item for item in predictions["predictions"] if item["id"] == case_id)

    def test_current_host_baseline_executes_semantic_cases(self):
        result = self.evaluate()
        self.assertTrue(result["ok"], result)
        self.assertEqual(39, result["case_count"])
        self.assertEqual(1.0, result["metrics"]["top1_accuracy"])
        self.assertEqual(1.0, result["metrics"]["top2_recall"])
        self.assertEqual(0.0, result["metrics"]["wrong_plugin_rate"])
        self.assertEqual(0.0, result["metrics"]["overload_rate"])
        self.assertEqual(1.0, result["metrics"]["reject_unknown_quality"])
        self.assertEqual(1.0, result["metrics"]["guard_conservation_rate"])
        self.assertTrue(result["provenance_valid"])

    def test_negated_laravel_specialization_is_a_real_failure(self):
        predictions = copy.deepcopy(self.predictions)
        item = self.prediction(predictions, "N01")
        item["specializations"] = ["backend-laravel-php"]
        result = self.evaluate(predictions=predictions)
        self.assertFalse(result["ok"])
        self.assertEqual(1, result["forbidden_selection_count"])
        self.assertIn("N01", {failure["id"] for failure in result["failures"]})

    def test_third_active_skill_is_counted_as_overload(self):
        predictions = copy.deepcopy(self.predictions)
        item = self.prediction(predictions, "D01")
        item["candidates"].append("regression-test-planner")
        item["deferred"] = []
        result = self.evaluate(predictions=predictions)
        self.assertFalse(result["ok"])
        self.assertGreater(result["metrics"]["overload_rate"], 0)
        self.assertLess(result["metrics"]["guard_conservation_rate"], 1)

    def test_required_third_capability_must_be_deferred(self):
        predictions = copy.deepcopy(self.predictions)
        self.prediction(predictions, "D01")["deferred"] = []
        result = self.evaluate(predictions=predictions)
        self.assertFalse(result["ok"])
        self.assertLess(result["metrics"]["deferred_recall"], 1)
        self.assertIn("D01", {failure["id"] for failure in result["failures"]})

    def test_false_rejection_is_measured(self):
        predictions = copy.deepcopy(self.predictions)
        item = self.prediction(predictions, "E01")
        item["disposition"] = "UNKNOWN"
        item["candidates"] = []
        result = self.evaluate(predictions=predictions)
        self.assertFalse(result["ok"])
        self.assertGreater(result["metrics"]["false_rejection_rate"], 0)

    def test_wrong_plugin_and_unnecessary_skill_are_measured(self):
        predictions = copy.deepcopy(self.predictions)
        item = self.prediction(predictions, "E01")
        item["candidates"] = ["cs-component-implementation"]
        item["architecture"] = "cs"
        result = self.evaluate(predictions=predictions)
        self.assertFalse(result["ok"])
        self.assertGreater(result["metrics"]["wrong_plugin_rate"], 0)
        self.assertGreater(result["metrics"]["unnecessary_skill_rate"], 0)

    def test_selection_payload_cannot_contain_gold_fields(self):
        cases = copy.deepcopy(self.cases)
        cases["cases"][0]["expected"] = "web-component-implementation"
        with self.assertRaisesRegex(ValueError, "answer fields"):
            self.evaluate(cases=cases)

    def test_missing_host_prediction_cannot_be_silently_skipped(self):
        predictions = copy.deepcopy(self.predictions)
        predictions["predictions"].pop()
        with self.assertRaisesRegex(ValueError, "exactly the same ids"):
            self.evaluate(predictions=predictions)

    def test_external_model_provenance_blocks_the_baseline(self):
        predictions = copy.deepcopy(self.predictions)
        predictions["external_model_calls"] = 1
        result = self.evaluate(predictions=predictions)
        self.assertFalse(result["ok"])
        self.assertFalse(result["provenance_valid"])

    def test_raw_laravel_word_never_makes_guard_select_a_skill(self):
        from suite_router import route

        with tempfile.TemporaryDirectory() as td:
            result = route(Path(td), "不要 Laravel，当前使用 FastAPI")
        self.assertEqual("PROPOSAL_REQUIRED", result["guard_decision"])
        self.assertEqual([], result["selected"])


if __name__ == "__main__":
    unittest.main()
