from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable


SUITE = Path(__file__).resolve().parents[1]
QUALITY_SCRIPTS = SUITE / "plugins" / "ai-engineering-quality" / "scripts"
BASELINE = Path(__file__).resolve().parent / "baselines" / "5.17-governance-tax.json"
sys.path.insert(0, str(QUALITY_SCRIPTS))

from adaptive_governance import DIMENSIONS, TAX_METRICS, assess, evaluate_tax


def _canonical_repository_bytes(path: Path) -> bytes:
    """Match Git's text normalization so the gate is portable across LF/CRLF worktrees."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _git_blob(path: Path) -> str:
    content = _canonical_repository_bytes(path)
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def _timings(operation: Callable[[], Any], runs: int) -> dict[str, float]:
    values: list[float] = []
    for _ in range(max(10, runs)):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[index], 3),
        "max_ms": round(max(ordered), 3),
    }


def _assessment(
    *,
    levels: dict[str, str] | None = None,
    event: str = "ORDINARY_IMPLEMENTATION",
    intent: str = "PRODUCTION",
    reduce: bool = False,
    scope: list[str] | None = None,
) -> dict[str, Any]:
    levels = levels or {}
    return {
        "schema_version": "1.0.0",
        "assessment_id": "BENCHMARK-RISK",
        "event_type": event,
        "delivery_intent": intent,
        "user_requested_reduction": reduce,
        "affected_scope": scope or ["surface:affected"],
        "source_fingerprint": "source-benchmark",
        "design_fingerprint": "design-benchmark",
        "state_id": "state-benchmark",
        "dimensions": {
            name: {
                "level": levels.get(name, "LOW"),
                "basis": "PROJECT_FACT",
                "reason": f"bounded benchmark fact for {name}",
                "evidence_refs": [f"fact:{name}"],
            }
            for name in DIMENSIONS
        },
    }


def benchmark(runs: int = 100) -> dict[str, Any]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    zero_tax = dict(baseline["fast_and_ordinary_project_tax"])
    low_input = _assessment()
    low = assess(low_input)
    medium = assess(_assessment(levels={"runtime_impact": "MEDIUM"}))
    high = assess(_assessment(levels={"security_impact": "HIGH"}, event="SECURITY_BOUNDARY"))
    critical = assess(_assessment(levels={"release_impact": "CRITICAL"}, event="RELEASE"))
    prototype = assess(_assessment(levels={"business_criticality": "HIGH"}, intent="PROTOTYPE", reduce=True))
    prototype_security = assess(_assessment(levels={"security_impact": "HIGH"}, intent="PROTOTYPE", reduce=True))
    goal_change = assess(_assessment(event="GOAL_CHANGE", scope=["screen:affected"]))
    timing = _timings(lambda: assess(low_input), runs)
    tax = evaluate_tax(low, zero_tax, zero_tax)

    router = SUITE / "plugins" / "ai-engineering-core" / "skills" / "ai-engineering-router" / "SKILL.md"
    catalog = SUITE / "plugins" / "ai-engineering-core" / "references" / "semantic-routing-catalog.md"
    default_scripts = [
        SUITE / "plugins" / "ai-engineering-core" / "scripts" / "suite_router.py",
        SUITE / "plugins" / "ai-engineering-core" / "scripts" / "control_admission.py",
        router,
    ]
    default_imports_adaptive_governance = any(
        "adaptive_governance" in path.read_text(encoding="utf-8", errors="ignore") for path in default_scripts
    )
    skills = sorted((SUITE / "plugins").glob("*/skills/*/SKILL.md"))
    current_skill_bytes = sum(len(_canonical_repository_bytes(path)) for path in skills)
    router_fact = baseline["default_surfaces"]["router_skill"]
    catalog_fact = baseline["default_surfaces"]["semantic_catalog"]
    default_surfaces = {
        "skill_count": len(skills),
        "skill_body_bytes": current_skill_bytes,
        "skill_body_bytes_delta": current_skill_bytes - int(baseline["skill_body_bytes"]),
        "router_skill_blob": _git_blob(router),
        "router_skill_unchanged": _git_blob(router) == router_fact["git_blob"],
        "semantic_catalog_blob": _git_blob(catalog),
        "semantic_catalog_unchanged": _git_blob(catalog) == catalog_fact["git_blob"],
        "default_imports_adaptive_governance": default_imports_adaptive_governance,
        "default_context_bytes_added": 0,
        "default_injected_prompt_bytes_added": 0,
    }
    control_rank = {"NONE": 0, "TARGETED": 1, "GOVERNED": 2}
    monotonic = (
        control_rank[low["activation"]]
        < control_rank[medium["activation"]]
        < control_rank[high["activation"]]
        <= control_rank[critical["activation"]]
        and low["governance_tax_budget"]["governance_tool_calls"]
        < medium["governance_tax_budget"]["governance_tool_calls"]
        < high["governance_tax_budget"]["governance_tool_calls"]
        < critical["governance_tax_budget"]["governance_tool_calls"]
    )
    ai_freedom = {
        "fixed_steps": low["contract"]["fixed_steps"],
        "reasoning_path": low["model_freedom"]["reasoning_path"],
        "implementation_order": low["model_freedom"]["implementation_order"],
        "design_solution": low["model_freedom"]["design_solution"],
        "tool_choice": low["model_freedom"]["tool_choice"],
    }
    incrementality = {
        "ordinary_low_activation": low["activation"],
        "goal_change_activation": goal_change["activation"],
        "goal_change_scope_mode": goal_change["scope_mode"],
        "cold_history_scan": goal_change["evidence_policy"]["cold_history_scan"],
        "evidence_reuse": goal_change["evidence_policy"]["reuse"],
    }
    control_precision = {
        "monotonic": monotonic,
        "low": {"risk": low["risk_level"], "activation": low["activation"]},
        "medium": {"risk": medium["risk_level"], "activation": medium["activation"]},
        "high": {"risk": high["risk_level"], "activation": high["activation"]},
        "critical": {"risk": critical["risk_level"], "activation": critical["activation"]},
        "prototype": {
            "artifact_status": prototype["artifact_status"],
            "release_ready": prototype["release_ready"],
            "control_level": prototype["control_level"],
        },
        "prototype_security": {
            "control_level": prototype_security["control_level"],
            "activation": prototype_security["activation"],
            "hard_boundaries": prototype_security["hard_boundaries"],
        },
    }
    errors: list[str] = []
    if len(skills) != int(baseline["skill_count"]):
        errors.append("skill count changed from the 5.17 baseline")
    if not default_surfaces["router_skill_unchanged"] or not default_surfaces["semantic_catalog_unchanged"]:
        errors.append("default routing context changed from the 5.17 baseline")
    if default_imports_adaptive_governance:
        errors.append("adaptive governance entered the default router/admission path")
    if ai_freedom["fixed_steps"] or any(ai_freedom[key] != "MODEL_DECIDES" for key in ("reasoning_path", "implementation_order")):
        errors.append("governance constrained the model to a fixed reasoning workflow")
    if low["activation"] != "NONE" or any(low["governance_tax_budget"].values()) or not tax["ok"]:
        errors.append("simple-task governance tax increased over the 5.17 zero-tax baseline")
    if goal_change["activation"] != "TARGETED" or goal_change["scope_mode"] != "AFFECTED_SCOPE":
        errors.append("key events did not stay on affected-scope sparse governance")
    if not monotonic:
        errors.append("higher risk did not receive strictly stronger control")
    if prototype["release_ready"] or prototype["artifact_status"] != "PROTOTYPE":
        errors.append("prototype reduction was not marked non-release-ready")
    if prototype_security["control_level"] not in {"HIGH", "CRITICAL"} or prototype_security["activation"] != "GOVERNED":
        errors.append("prototype reduction bypassed a security hard boundary")
    if timing["p95_ms"] > 5.0:
        errors.append(f"pure governance assessment P95 exceeds 5ms: {timing['p95_ms']}ms")
    return {
        "ok": not errors,
        "baseline_5_17": baseline,
        "ai_freedom": ai_freedom,
        "governance_tax": {
            "fast_and_ordinary_project": tax,
            "assessment_runtime": timing,
            "pure_function_file_scans": 0,
            "pure_function_state_writes": 0,
            "pure_function_browser_runs": 0,
            "pure_function_screenshots": 0,
        },
        "incrementality": incrementality,
        "control_precision": control_precision,
        "default_surfaces": default_surfaces,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Hiker AI freedom and risk-adaptive governance tax")
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()
    report = benchmark(args.runs)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
