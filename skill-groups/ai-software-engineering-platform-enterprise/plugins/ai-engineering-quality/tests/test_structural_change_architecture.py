from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from architecture_guard import evaluate
from structural_change_decision import validate_decision


HASH = "c" * 64


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def normalized_decision() -> dict:
    catalog = {
        "schema_version": "hiker-observed-fact-catalog/v1",
        "authority": "EXTERNAL_OBSERVED_EVIDENCE",
        "scope_fingerprint": HASH,
        "facts": [
            {"ref": "src/Feature.ts", "kind": "SCOPE", "evidence_fingerprint": HASH},
            {"ref": "problem://growth", "kind": "PROBLEM", "evidence_fingerprint": HASH},
            {
                "ref": "structure://cohesive",
                "kind": "STRUCTURE",
                "evidence_fingerprint": HASH,
                "claims": ["COHESIVE_RESPONSIBILITY"],
            },
        ],
        "acceptance_refs": [],
    }
    proposal = {
        "schema_version": "hiker-structural-change-decision/v1",
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "action": "KEEP_CURRENT_STRUCTURE",
        "decision_scope": ["src/Feature.ts"],
        "problem_refs": ["problem://growth"],
        "evidence_refs": ["structure://cohesive"],
        "reason": "The current file is large but retains one cohesive responsibility.",
        "alternatives_rejected": [
            {"action": "INTRODUCE_ABSTRACTION", "reason": "No shared invariant or multiple consumer evidence exists."},
        ],
        "expected_gain": {
            "classification": "OBSERVED",
            "statement": "The current responsibility remains cohesive.",
            "evidence_refs": ["structure://cohesive"],
        },
        "migration_cost": {"level": "NONE", "reason": "No migration is proposed.", "evidence_refs": []},
        "regression_risk": {
            "level": "LOW",
            "reason": "The behavior boundary remains unchanged.",
            "evidence_refs": ["structure://cohesive"],
        },
        "rollback_or_exit_condition": "Re-evaluate when a second change reason or shared consumer is proven.",
        "confidence": "HIGH",
    }
    return validate_decision(
        proposal,
        observed_fact_catalog=catalog,
        expected_scope_fingerprint=HASH,
    )


def task(decision: dict) -> dict:
    return {
        "project_id": "APP",
        "task_id": "KG-202",
        "change_contract": {
            "allowed_files": ["src/Feature.ts"],
            "allowed_modules": [],
            "protected_modules": [],
            "public_contract_changes": [],
            "behavior_invariants": ["Existing behavior remains unchanged"],
            "required_tests": ["Focused regression"],
            "characterization_tests": [],
            "consumer_tests": [],
            "consumers": [],
            "structural_decisions": [],
            "structural_change_decision": decision,
        },
    }


class StructuralChangeArchitectureTests(unittest.TestCase):
    def test_architecture_guard_consumes_one_validated_structural_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            git(root, "init")
            git(root, "config", "user.email", "hiker-test")
            git(root, "config", "user.name", "Test")
            source = root / "src" / "Feature.ts"
            source.parent.mkdir()
            source.write_text("\n".join(["// stable"] * 321) + "\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "feat: establish feature")
            source.write_text(source.read_text(encoding="utf-8") + "export function added() { return true }\n", encoding="utf-8")
            task_dir = root / ".ai" / "tasks"
            task_dir.mkdir(parents=True)
            state = task(normalized_decision())
            (task_dir / "KG-202.json").write_text(json.dumps(state), encoding="utf-8")
            result = evaluate(root, "KG-202")
            self.assertFalse(any("缺少编码前结构决策" in item for item in result["blockers"]))
            self.assertEqual(
                "NEXT_02_STRUCTURAL_CHANGE_DECISION",
                result["structural_decisions"][0]["authority"],
            )

    def test_new_and_legacy_decision_authorities_conflict(self):
        state = task(normalized_decision())
        state["change_contract"]["structural_decisions"] = ["src/Feature.ts|KEEP|legacy reason"]
        from architecture_guard import structural_decisions

        decisions, errors = structural_decisions(state["change_contract"])
        self.assertEqual({}, decisions)
        self.assertEqual(["STRUCTURAL_DECISION_AUTHORITY_CONFLICT"], errors)

    def test_tampered_normalized_decision_is_rejected(self):
        state = task(normalized_decision())
        state["change_contract"]["structural_change_decision"]["action"] = "DELETE_SAFELY"
        from architecture_guard import structural_decisions

        decisions, errors = structural_decisions(state["change_contract"])
        self.assertEqual({}, decisions)
        self.assertIn("STRUCTURAL_DECISION_RECEIPT_FINGERPRINT_MISMATCH", errors)


if __name__ == "__main__":
    unittest.main()
