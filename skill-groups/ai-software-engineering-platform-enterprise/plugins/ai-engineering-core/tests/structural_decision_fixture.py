from __future__ import annotations

import hashlib


HASH = "a" * 64
PROJECT_HASH = "b" * 64


def fact(ref: str, kind: str, *claims: str, freshness: str = "CURRENT", critical: bool = False) -> dict:
    return {
        "ref": ref,
        "kind": kind,
        "evidence_fingerprint": HASH,
        "freshness": freshness,
        "claims": list(claims),
        "safety_critical": critical,
    }


def catalog(*facts: dict) -> dict:
    return {
        "schema_version": "hiker-observed-fact-catalog/v1",
        "authority": "EXTERNAL_OBSERVED_EVIDENCE",
        "scope_fingerprint": HASH,
        "project_fact_fingerprint": PROJECT_HASH,
        "facts": [fact("src/service.py", "SCOPE"), fact("problem://change", "PROBLEM"), *facts],
        "acceptance_refs": [],
    }


def decision(action: str, evidence_refs: list[str]) -> dict:
    alternative = "KEEP_CURRENT_STRUCTURE" if action != "KEEP_CURRENT_STRUCTURE" else "MODIFY_EXISTING"
    return {
        "schema_version": "hiker-structural-change-decision/v1",
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "action": action,
        "decision_scope": ["src/service.py"],
        "problem_refs": ["problem://change"],
        "evidence_refs": evidence_refs,
        "reason": "The selected action follows the current bounded engineering evidence.",
        "alternatives_rejected": [{
            "action": alternative,
            "reason": "It does not fit the current responsibility and consumer evidence.",
        }],
        "expected_gain": {
            "classification": "OBSERVED",
            "statement": "The current evidence identifies a bounded structural gain.",
            "evidence_refs": evidence_refs[:1],
        },
        "migration_cost": {
            "level": "LOW",
            "reason": "The affected scope and migration surface are bounded.",
            "evidence_refs": evidence_refs[:1],
        },
        "regression_risk": {
            "level": "LOW",
            "reason": "The current consumer surface is explicitly represented.",
            "evidence_refs": evidence_refs[:1],
        },
        "rollback_or_exit_condition": "Restore the prior path or stop when cited evidence is stale.",
        "confidence": "HIGH",
    }
