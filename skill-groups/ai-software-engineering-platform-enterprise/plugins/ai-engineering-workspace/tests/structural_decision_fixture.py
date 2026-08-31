from __future__ import annotations

import hashlib


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def base_proposal() -> dict:
    return {
        "architecture": "backend",
        "client_families": [],
        "risk_class": "bounded",
        "contract_change": False,
    }


def observed_catalog(goal: str) -> dict:
    return {
        "schema_version": "hiker-observed-fact-catalog/v1",
        "authority": "EXTERNAL_OBSERVED_EVIDENCE",
        "scope_fingerprint": digest(goal),
        "facts": [
            {
                "ref": "src/service.py",
                "kind": "SCOPE",
                "evidence_fingerprint": digest("scope"),
                "freshness": "CURRENT",
            },
            {
                "ref": "problem://local-bug",
                "kind": "PROBLEM",
                "evidence_fingerprint": digest("problem"),
                "freshness": "CURRENT",
            },
            {
                "ref": "structure://cohesive",
                "kind": "STRUCTURE",
                "evidence_fingerprint": digest("structure"),
                "freshness": "CURRENT",
                "claims": ["COHESIVE_RESPONSIBILITY", "LOCALIZED_CHANGE"],
            },
            {
                "ref": "artifact://service",
                "kind": "ARTIFACT",
                "evidence_fingerprint": digest("artifact"),
                "freshness": "CURRENT",
            },
            {
                "ref": "actor://future-maintainer",
                "kind": "ACTOR",
                "evidence_fingerprint": digest("actor"),
                "freshness": "CURRENT",
            },
        ],
        "acceptance_refs": [],
    }


def structural_decision() -> dict:
    return {
        "schema_version": "hiker-structural-change-decision/v1",
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "action": "MODIFY_EXISTING",
        "decision_scope": ["src/service.py"],
        "problem_refs": ["problem://local-bug"],
        "evidence_refs": ["structure://cohesive"],
        "reason": "The defect is local to the existing cohesive responsibility.",
        "alternatives_rejected": [
            {
                "action": "INTRODUCE_ABSTRACTION",
                "reason": "No shared invariant or multiple consumer evidence exists.",
            },
        ],
        "expected_gain": {
            "classification": "OBSERVED",
            "statement": "The change stays inside the current responsibility.",
            "evidence_refs": ["structure://cohesive"],
        },
        "migration_cost": {
            "level": "NONE",
            "reason": "No route or authority migration is proposed.",
            "evidence_refs": [],
        },
        "regression_risk": {
            "level": "LOW",
            "reason": "The current consumer surface is explicitly represented.",
            "evidence_refs": ["structure://cohesive"],
        },
        "rollback_or_exit_condition": "Restore the prior implementation if the focused regression fails.",
        "confidence": "HIGH",
    }


def perspective_plan() -> dict:
    return {
        "schema_version": "hiker-perspective-applicability/v1",
        "authority": "CHATGPT_SEMANTIC_SELECTION",
        "artifacts": [{"id": "service", "type": "CODE", "fact_refs": ["artifact://service"]}],
        "actors": [{"id": "future-maintainer", "fact_refs": ["actor://future-maintainer"]}],
        "usage_conditions": [],
        "risk_facts": [],
        "project_fact_refs": [],
        "perspectives": [{
            "id": "future-maintainer",
            "rationale": "The bounded change should preserve one understandable responsibility.",
            "basis": {
                "artifact_ids": ["service"],
                "actor_ids": ["future-maintainer"],
                "usage_condition_ids": [],
                "risk_ids": [],
                "project_fact_refs": [],
            },
            "acceptance_refs": ["semantic://cohesive-maintenance"],
        }],
    }
