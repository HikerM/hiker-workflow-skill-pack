from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "ai-engineering-core" / "scripts"))

from suite_router import route, skill_display


DESIGN = {"web-ui-design", "cs-ui-design", "unity-ui-design"}
IMPLEMENTATION = {
    "web-component-implementation", "backend-component-implementation",
    "cs-component-implementation", "unity-component-implementation",
}
PLANNING = {
    "project-bootstrap", "greenfield-project-planning", "architecture-decision-challenge",
    "brownfield-requirement-reconciliation", "api-event-contract-design",
}
REVIEW = {
    "design-readiness-review", "full-change-risk-review", "interaction-conflict-governance",
    "web-quality-review", "backend-quality-review", "cs-quality-review", "unity-quality-review",
}


def stage_for(skill: str) -> str:
    if skill in DESIGN:
        return "design"
    if skill in IMPLEMENTATION:
        return "development"
    if skill in PLANNING:
        return "planning"
    if skill in REVIEW:
        return "review"
    if skill == "regression-test-planner":
        return "testing"
    if skill == "release-readiness-review":
        return "release"
    if skill == "change-ownership-merge":
        return "merge"
    return "governance"


def architecture_for(skill: str) -> str:
    if skill.startswith("web-"):
        return "bs"
    if skill.startswith("backend-") or skill in {"api-event-contract-design", "database-migration-governance"}:
        return "backend"
    if skill.startswith("cs-") or skill.startswith("unity-"):
        return "cs"
    return "unknown"


def proposal_for(skill: str) -> dict:
    return {
        "project_mode": "unknown",
        "architecture": architecture_for(skill),
        "stage": stage_for(skill),
        "current_action": "执行当前 Eval 阶段目标",
        "confidence": "high",
        "candidates": [skill],
    }


def evaluate() -> dict:
    positive = negative = positive_total = negative_total = 0
    failures = []
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        for csv_path in sorted((ROOT / "plugins").glob("*/evals/prompts.csv")):
            for row in csv.DictReader(csv_path.open(encoding="utf-8")):
                should_trigger = str(row.get("should_trigger", "")).lower() == "true"
                skill = row["skill"]
                if skill == "ai-engineering-router":
                    # Host-side metadata activation belongs to ChatGPT. Locally verify that raw
                    # prose cannot make the guard select an atomic Skill.
                    data = route(project, row["prompt"])
                    ok = data["guard_decision"] == "PROPOSAL_REQUIRED" and not data["selected"]
                elif should_trigger:
                    data = route(project, proposal_for(skill))
                    selected = [item["skill"] for item in data["selected"]]
                    ok = data["accepted"] and skill_display(skill) in selected
                else:
                    data = route(project, row["prompt"])
                    selected = [item["skill"] for item in data["selected"]]
                    ok = data["guard_decision"] == "PROPOSAL_REQUIRED" and not selected
                if should_trigger:
                    positive_total += 1
                    positive += int(ok)
                else:
                    negative_total += 1
                    negative += int(ok)
                if not ok:
                    failures.append({
                        "id": row["id"], "expected_skill": skill,
                        "should_trigger": should_trigger,
                        "guard_decision": data.get("guard_decision"),
                        "selected": [item["skill"] for item in data.get("selected", [])],
                        "diagnostics": data.get("diagnostics", []),
                    })
    return {
        "ok": not failures,
        "scope": "模型候选守门与无关键词自动选 Skill；ChatGPT 原生语义选择由 Skill 元数据和真实会话评测",
        "positive": {"passed": positive, "total": positive_total, "recall": round(positive / positive_total, 4) if positive_total else 1.0},
        "negative": {"passed": negative, "total": negative_total, "specificity": round(negative / negative_total, 4) if negative_total else 1.0},
        "failures": failures,
    }


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)
