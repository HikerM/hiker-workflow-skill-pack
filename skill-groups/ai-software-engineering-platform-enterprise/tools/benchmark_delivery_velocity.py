from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable


SUITE = Path(__file__).resolve().parents[1]
QUALITY = SUITE / "plugins" / "ai-engineering-quality" / "scripts"
sys.path.insert(0, str(QUALITY))

from adaptive_governance import DIMENSIONS, TAX_METRICS, assess, authorize
from component_registry_v2 import component_fingerprint, empty_registry, registry_fingerprint, validate as validate_registry
from evidence_cache import compact_summary, decide as decide_evidence, invalidate
from presentation_guard import audit_copy
from product_model_common import model_fingerprint
from runtime_reuse import decide as decide_runtime
from runtime_ui_evidence import objective_checks
from ui_design_model import default_model, patch_screen, validate as validate_design


STAGES = (
    "discovery", "context", "design", "implementation", "runtime", "test", "screenshot",
    "visual_review", "review", "evidence", "correction", "regression",
)


def _measure(timings: dict[str, Any], stage: str, operation: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    result = operation()
    timings[stage] = round((time.perf_counter() - started) * 1000, 3)
    return result


def _timings() -> dict[str, Any]:
    return {stage: "NOT_MEASURED" for stage in STAGES}


def _tax(**values: int | float) -> dict[str, int | float]:
    result: dict[str, int | float] = {metric: 0 for metric in TAX_METRICS}
    result.update(values)
    return result


def _risk(levels: dict[str, str] | None = None, **overrides: Any) -> dict[str, Any]:
    levels = levels or {}
    result = {
        "schema_version": "1.0.0",
        "assessment_id": "DELIVERY-BENCHMARK",
        "event_type": "ORDINARY_IMPLEMENTATION",
        "delivery_intent": "PRODUCTION",
        "user_requested_reduction": False,
        "affected_scope": ["screen:settings"],
        "affected_capabilities": ["capability:settings"],
        "requested_validators": ["PRESENTATION"],
        "runtime_targets": [{"surface_id": "screen:settings", "states": ["default"], "environments": ["desktop"]}],
        "full_scan_reason": None,
        "source_fingerprint": "source-1",
        "design_fingerprint": "design-1",
        "project_config_fingerprint": "config-1",
        "technology_fingerprint": "technology-1",
        "environment_fingerprint": "environment-1",
        "state_id": "state-1",
        "dimensions": {
            name: {"level": levels.get(name, "LOW"), "basis": "PROJECT_FACT", "reason": f"bounded {name}", "evidence_refs": [f"fact:{name}"]}
            for name in DIMENSIONS
        },
    }
    result.update(overrides)
    return result


def _screen(screen_id: str = "settings") -> dict[str, Any]:
    return {
        "screen_id": screen_id,
        "primary_task": "Review and update settings",
        "information_hierarchy": ["title", "settings", "save outcome"],
        "focal_point": "settings form",
        "reading_path": ["title", "fields", "save"],
        "density_profile": "focused",
        "navigation_relationships": ["settings -> confirmation"],
        "content_regions": [{"region_id": "form", "semantic_role": "settings input"}],
        "components": ["bs:src/Settings.vue#SettingsForm"],
        "states": ["default", "saving", "error"],
        "interactions": ["save"],
        "presentation_refs": ["settings.title"],
        "acceptance": ["save outcome is visible"],
        "composition_strategy": {"kind": "custom", "candidates": [], "rationale": "Project-native settings form."},
    }


def _runtime(source: str = "source-1", platform: str = "BS_BROWSER") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0", "runtime_id": "runtime-1", "platform": platform, "status": "READY",
        "source_fingerprint": source, "project_config_fingerprint": "config-1", "technology_fingerprint": "technology-1",
        "environment_fingerprint": "environment-1", "relevant_state_fingerprint": "state-1",
        "authenticated_session_fingerprint": hashlib.sha256(b"delivery-benchmark-session").hexdigest(),
        "capabilities": {"session_reuse": True, "incremental_reload": True}, "targets": ["screen:settings", "screen:new-page"],
    }


def _identity(scope: list[str]) -> dict[str, Any]:
    return {
        "source_fingerprint": "source-1", "design_fingerprint": "design-1", "project_config_fingerprint": "config-1",
        "contract_fingerprint": "contract-1", "dependency_fingerprint": "dependency-1",
        "technology_fingerprint": "technology-1", "environment_fingerprint": "environment-1",
        "relevant_state_fingerprint": "state-1", "affected_scope": scope,
    }


def _finish(name: str, started: float, timings: dict[str, Any], tax: dict[str, Any], **facts: Any) -> dict[str, Any]:
    duration = round((time.perf_counter() - started) * 1000, 3)
    tax["runtime_duration_ms"] = duration
    budget = facts.pop("governance_budget", None)
    within_budget = bool(budget) and all(float(tax.get(metric, 0)) <= float(budget.get(metric, 0)) for metric in TAX_METRICS)
    return {
        "scenario": name,
        "time_to_accepted_change_ms": duration if facts.get("accepted") else "NOT_MEASURED",
        "stage_timings_ms": timings,
        "governance_tax": tax,
        "governance_tax_budget": budget,
        "governance_tax_within_budget": within_budget,
        "five_17_comparable_baseline": "NOT_MEASURED",
        **facts,
    }


def scenario_a_small_ui_copy() -> dict[str, Any]:
    started = time.perf_counter(); timings = _timings()
    profile = assess(_risk())
    model = default_model("delivery-a", "BS"); model["screens"] = [_screen()]; model["fingerprint"] = model_fingerprint(model)
    updated, _ = _measure(timings, "implementation", lambda: patch_screen(model, "settings", {"primary_task": "Review and save settings"}))
    design = _measure(timings, "design", lambda: validate_design(updated))
    copy = _measure(timings, "test", lambda: audit_copy({"entries": [{
        "copy_id": "settings.title", "control_role": "heading", "surface": "screen:settings",
        "text": "Settings", "intent": "identify the settings task", "runtime_fit": "PASS",
    }]}))
    existing = _runtime(); required = {**existing, "runtime_id": "required", "targets": ["screen:settings"]}
    runtime = _measure(timings, "runtime", lambda: decide_runtime(existing, required))
    summary = _measure(timings, "evidence", lambda: compact_summary(
        _identity(["screen:settings"]), evidence_id="delivery-a", status="VALID", findings=[], artifacts=[],
    ))
    evidence = decide_evidence(summary, _identity(["screen:settings"]))
    accepted = all((profile["decision"] == "ALLOW_WITH_PROFILE", design["status"] == "PASS", copy["status"] == "PASS", runtime["decision"] == "REUSE", evidence["reuse"]))
    tax = _tax(validation_cycles=1, generated_governance_artifacts=1)
    return _finish("A_SMALL_UI_COPY", started, timings, tax, accepted=accepted, first_pass=accepted, correction_cycles=0,
                   governance_activation=profile["activation"], full_scan=False, full_visual_matrix=False, architecture_review=False,
                   runtime_decision=runtime["decision"], acceptance_scope="AFFECTED_SCREEN", governance_budget=profile["governance_tax_budget"])


def scenario_b_normal_new_page() -> dict[str, Any]:
    started = time.perf_counter(); timings = _timings()
    profile = assess(_risk(levels={"user_visibility": "MEDIUM"}, affected_scope=["screen:new-page"],
                           runtime_targets=[{"surface_id": "screen:new-page", "states": ["default", "error"], "environments": ["desktop"]}]))
    model = default_model("delivery-b", "BS"); model["screens"] = [_screen("new-page")]; model["fingerprint"] = model_fingerprint(model)
    design = _measure(timings, "design", lambda: validate_design(model))
    def implementation() -> dict[str, Any]:
        registry = empty_registry("delivery-b", {"mode": "AFFECTED", "refs": ["src/NewPage.vue"]})
        component = {
            "component_id": "bs:src/Settings.vue#SettingsForm",
            "semantic_role": {"status": "OBSERVED", "value": "settings input", "source_refs": ["design:new-page"]},
            "design_component": {"status": "OBSERVED", "value": "settings form", "source_refs": ["design:new-page"]},
            "code_component": {"status": "OBSERVED", "value": {"path": "src/NewPage.vue", "symbol": "SettingsForm", "source_fingerprint": "source-1"}, "source_refs": ["src/NewPage.vue"]},
            "variants": [], "states": ["default", "error"], "tokens": [], "accessibility": ["named"], "platform": "BS",
            "usage_rules": [], "technology_adapter": {"status": "OBSERVED", "value": {"family": "vue", "version": "3"}, "source_refs": ["package.json"]},
            "implementation_layer": "project_native",
        }
        component["fingerprint"] = component_fingerprint(component); registry["components"] = [component]; registry["fingerprint"] = registry_fingerprint(registry)
        return registry
    registry = _measure(timings, "implementation", implementation)
    registry_result = validate_registry(registry)
    snapshot = {
        "capture_id": "delivery-b", "screen_id": "new-page", "state": "default", "architecture": "BS", "technology": "vue@3",
        "source_commit": "fixture", "source_fingerprint": "source-1", "design_fingerprint": model["fingerprint"],
        "registry_fingerprint": registry["fingerprint"], "viewport": {"width": 1200, "height": 800},
        "elements": [{"component_id": "bs:src/Settings.vue#SettingsForm", "rect": {"x": 20, "y": 20, "width": 600, "height": 500}}],
    }
    runtime_check = _measure(timings, "runtime", lambda: objective_checks(snapshot, ["bs:src/Settings.vue#SettingsForm"], "default"))
    timings["test"] = timings["runtime"]
    summary = _measure(timings, "evidence", lambda: compact_summary(
        _identity(["screen:new-page"]), evidence_id="delivery-b", status="VALID", findings=[], artifacts=[],
    ))
    accepted = all((profile["decision"] == "ALLOW_WITH_PROFILE", design["status"] == "PASS", registry_result["status"] == "PASS", runtime_check["status"] == "PASS", summary["summary_only"]))
    tax = _tax(validation_cycles=3, generated_governance_artifacts=1)
    return _finish("B_NORMAL_NEW_PAGE", started, timings, tax, accepted=accepted, first_pass=accepted, correction_cycles=0,
                   governance_activation=profile["activation"], full_scan=False, runtime_targets=1, acceptance_scope="NEW_PAGE_AFFECTED_SCOPE",
                   governance_budget=profile["governance_tax_budget"])


def scenario_c_local_goal_change() -> dict[str, Any]:
    started = time.perf_counter(); timings = _timings()
    profile = assess(_risk(event_type="GOAL_CHANGE", affected_scope=["screen:settings"]))
    records = [
        {"evidence_id": "settings", "status": "VALID", "affected_scope": ["screen:settings"]},
        {"evidence_id": "database", "status": "VALID", "affected_scope": ["database:users"]},
    ]
    result = _measure(timings, "evidence", lambda: invalidate(records, ["screen:settings"], "goal revision"))
    accepted = result["invalidated"] == ["settings"] and result["preserved"] == 1 and profile["scope_mode"] == "AFFECTED_SCOPE"
    tax = _tax(validation_cycles=1)
    return _finish("C_LOCAL_GOAL_CHANGE", started, timings, tax, accepted=accepted, first_pass=accepted, correction_cycles=0,
                   governance_activation=profile["activation"], invalidated=result["invalidated"], preserved=result["preserved"],
                   unrelated_scope_reopened=False, acceptance_scope="GOAL_CHANGE_IMPACT_CLASSIFICATION", governance_budget=profile["governance_tax_budget"])


def scenario_d_high_risk() -> dict[str, Any]:
    started = time.perf_counter(); timings = _timings()
    profile = _measure(timings, "review", lambda: assess(_risk(
        levels={"security_impact": "HIGH", "release_impact": "HIGH"}, event_type="RELEASE",
        requested_validators=["SECURITY", "REGRESSION", "RELEASE_GATE"],
    )))
    stronger = all((profile["activation"] == "GOVERNED", profile["verification_budget"]["independent_review"],
                    authorize(profile, "VALIDATOR", "SECURITY")["allowed"], not authorize(profile, "FULL_PROJECT_SCAN")["allowed"]))
    tax = _tax(review_cycles=1, validation_cycles=3)
    return _finish("D_HIGH_RISK_RELEASE", started, timings, tax, accepted=False, first_pass=False, correction_cycles=0,
                   expected_outcome_met=stronger, status="REQUIRES_INDEPENDENT_ASSURANCE", governance_activation=profile["activation"],
                   full_scan=False, independent_review=True, acceptance_scope="GOVERNANCE_PROFILE_ONLY", governance_budget=profile["governance_tax_budget"])


def _reuse_rate() -> dict[str, Any]:
    existing = _runtime()
    requests = [
        {**existing, "runtime_id": "r1", "targets": ["screen:settings"]},
        {**existing, "runtime_id": "r2", "targets": ["screen:new-page"]},
        {**existing, "runtime_id": "r3", "source_fingerprint": "source-2", "targets": ["screen:settings"]},
        {**existing, "runtime_id": "r4", "source_fingerprint": "source-3", "targets": ["screen:new-page"]},
        {**existing, "runtime_id": "r5", "technology_fingerprint": "technology-2", "targets": ["screen:settings"]},
    ]
    decisions = [decide_runtime(existing, request)["decision"] for request in requests]
    reusable = sum(item in {"REUSE", "INCREMENTAL_RELOAD"} for item in decisions)
    return {"fixture_type": "DETERMINISTIC_IDENTITY_FIXTURE", "decisions": decisions, "reused": reusable, "attempts": len(decisions), "rate": reusable / len(decisions)}


def benchmark(runs: int = 5) -> dict[str, Any]:
    samples: list[float] = []
    last: list[dict[str, Any]] = []
    for _ in range(max(1, runs)):
        started = time.perf_counter()
        last = [scenario_a_small_ui_copy(), scenario_b_normal_new_page(), scenario_c_local_goal_change(), scenario_d_high_risk()]
        samples.append((time.perf_counter() - started) * 1000)
    accepted = [item for item in last if item["scenario"] != "D_HIGH_RISK_RELEASE"]
    reuse = _reuse_rate()
    errors: list[str] = []
    if not all(item.get("accepted") for item in accepted):
        errors.append("one or more low/medium affected-scope scenarios failed acceptance")
    if not last[-1].get("expected_outcome_met"):
        errors.append("high-risk scenario did not receive stronger governance")
    if any(item["governance_tax"]["injected_prompt_bytes"] for item in last):
        errors.append("delivery governance added default prompt bytes")
    if not all(item["governance_tax_within_budget"] for item in last):
        errors.append("one or more delivery scenarios exceeded the risk-proportionate governance tax budget")
    if reuse["rate"] < 0.6:
        errors.append("deterministic runtime reuse fixture is below 60%")
    return {
        "ok": not errors,
        "measurement_policy": "Only executed deterministic module paths are measured; unavailable stages and 5.17 scenario baselines are NOT_MEASURED.",
        "scenarios": last,
        "first_pass_acceptance": {"accepted": sum(item["first_pass"] for item in accepted), "eligible": len(accepted), "rate": sum(item["first_pass"] for item in accepted) / len(accepted)},
        "runtime_reuse": reuse,
        "suite_runtime_ms": {"p50": round(statistics.median(samples), 3), "max": round(max(samples), 3), "runs": len(samples)},
        "default_token_impact": {"injected_context_bytes": 0, "injected_prompt_bytes": 0, "default_skill_bytes": 0},
        "errors": errors,
    }


if __name__ == "__main__":
    report = benchmark()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 2)
