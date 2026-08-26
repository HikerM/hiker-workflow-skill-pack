from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from component_registry_v2 import (
    component_fingerprint,
    design_to_code_plan,
    empty_registry,
    merge_observations,
    migrate_legacy as migrate_legacy_registry,
    registry_fingerprint,
    validate as validate_registry,
)
from architecture_product_profile import profile_fingerprint, validate as validate_architecture_profile
from content_assurance import CONTENT_CASES, evaluate as evaluate_content, plan as content_plan
from error_experience_guard import audit_sources, contract_fingerprint as error_contract_fingerprint, validate_contract as validate_error_contract, validate_event
from presentation_guard import audit_bindings, audit_copy, contract_fingerprint, validate_contract
from product_release_gate import evaluate as evaluate_product_release
from product_model_common import apply_decision, make_decision, model_fingerprint
from runtime_ui_evidence import bind_artifact, objective_checks
from ui_design_model import default_model, inspect, migrate_legacy, patch_screen, validate
from visual_fidelity import evaluate as evaluate_fidelity


def valid_screen() -> dict:
    return {
        "screen_id": "record-list",
        "primary_task": "Find and inspect a domain record",
        "information_hierarchy": ["query", "results", "selection details"],
        "focal_point": "matching records",
        "reading_path": ["query", "result summary", "selected record"],
        "density_profile": "data-dense with progressive detail",
        "navigation_relationships": ["records -> record detail"],
        "content_regions": [
            {"region_id": "query", "semantic_role": "task input"},
            {"region_id": "results", "semantic_role": "search results"},
        ],
        "components": ["bs:src/Search.vue#SearchField", "bs:src/RecordRow.vue#RecordRow"],
        "states": ["default", "loading", "empty", "error"],
        "interactions": ["submit-query", "select-result"],
        "presentation_refs": ["record.business_identifier"],
        "acceptance": ["selection remains visible while details load"],
        "composition_strategy": {
            "kind": "hybrid",
            "candidates": ["task-focused", "master-detail"],
            "rationale": "Frequent lookup followed by focused inspection.",
        },
    }


def valid_registry() -> dict:
    registry = empty_registry("domain-components", {"mode": "EXPLICIT", "refs": ["src/Search.vue", "src/RecordRow.vue"]})
    for component_id, role, path, token in (
        ("bs:src/Search.vue#SearchField", "task input", "src/Search.vue", "color=primary"),
        ("bs:src/RecordRow.vue#RecordRow", "search result", "src/RecordRow.vue", "color=surface"),
    ):
        component = {
            "component_id": component_id,
            "semantic_role": {"status": "OBSERVED", "value": role, "source_refs": ["design:record-list"]},
            "design_component": {"status": "OBSERVED", "value": role, "source_refs": ["design:record-list"]},
            "code_component": {"status": "OBSERVED", "value": {"path": path, "symbol": component_id.split("#")[-1], "source_fingerprint": "source"}, "source_refs": [path]},
            "variants": [], "states": ["default"], "tokens": [token], "accessibility": ["named"],
            "platform": "BS", "usage_rules": [],
            "technology_adapter": {"status": "OBSERVED", "value": {"family": "vue", "version": "3.5"}, "source_refs": ["package.json"]},
            "implementation_layer": "project_native",
        }
        component["fingerprint"] = component_fingerprint(component)
        registry["components"].append(component)
    from component_registry_v2 import registry_fingerprint
    registry["fingerprint"] = registry_fingerprint(registry)
    return registry


def valid_snapshot(design: dict, registry: dict) -> dict:
    snapshot = {
        "capture_id": "CAP-1", "screen_id": "record-list", "state": "default", "architecture": "BS", "technology": "vue@3.5",
        "source_commit": "abc", "workspace_fingerprint": None, "source_fingerprint": "source",
        "design_fingerprint": design["fingerprint"], "registry_fingerprint": registry["fingerprint"],
        "viewport": {"width": 1200, "height": 800, "device_scale_factor": 1},
        "elements": [
            {"component_id": "bs:src/Search.vue#SearchField", "rect": {"x": 20, "y": 20, "width": 400, "height": 40}, "tokens": {"color": "primary"}},
            {"component_id": "bs:src/RecordRow.vue#RecordRow", "rect": {"x": 20, "y": 80, "width": 800, "height": 40}, "tokens": {"color": "surface"}},
        ],
    }
    return bind_artifact(snapshot, None)


def valid_presentation_contract() -> dict:
    contract = {
        "schema_version": "1.0.0", "contract_id": "record-presentation", "revision": 1,
        "fields": [
            {
                "field_id": "record.business_number", "semantic_role": "record reference", "presentation_role": "secondary identifier",
                "visibility": "USER_VISIBLE", "priority": "secondary", "format": {"kind": "business_identifier"},
                "fallback": {"kind": "localized_empty"}, "overflow_policy": {"strategy": "truncate_with_access", "runtime_validation_required": True},
                "sensitivity": "PERSONAL", "identifier_kind": "BUSINESS", "business_meaning": "A number used by authorized operators",
            },
            {
                "field_id": "record.internal_id", "semantic_role": "database identity", "presentation_role": "none",
                "visibility": "HIDDEN", "priority": "none", "format": {"kind": "none"},
                "fallback": {"kind": "none"}, "overflow_policy": {"strategy": "project_native", "runtime_validation_required": True},
                "sensitivity": "SENSITIVE", "identifier_kind": "TECHNICAL", "business_meaning": None,
            },
            {
                "field_id": "record.status", "semantic_role": "workflow status", "presentation_role": "status label",
                "visibility": "USER_VISIBLE", "priority": "primary", "format": {"kind": "domain_enum"},
                "fallback": {"kind": "localized_unknown"}, "overflow_policy": {"strategy": "wrap", "runtime_validation_required": True},
                "sensitivity": "PERSONAL", "identifier_kind": "NONE", "business_meaning": None,
            },
        ],
    }
    contract["fingerprint"] = contract_fingerprint(contract)
    return contract


def valid_error_contract(family: str = "PROBLEM_DETAILS") -> dict:
    contract = {
        "schema_version": "1.0.0", "contract_id": "school-errors", "revision": 1,
        "protocol": {
            "family": family, "serialization": "project-native", "existing_contract_ref": "contracts/errors" if family == "CUSTOM" else None,
            "semantic_mappings": {
                "classification": "type", "user_message": "detail", "developer_diagnostic": "diagnostic",
                "error_code": "code", "correlation": "error_id", "retry": "retry",
            },
        },
        "classifications": [
            {"code": "ENROLMENT_CONFLICT", "kind": "EXPECTED_BUSINESS", "retry_semantics": "AFTER_CHANGE", "user_message_policy": "explain conflict and next step", "diagnostic_requirements": ["operation", "entity-version"]},
            {"code": "UNEXPECTED", "kind": "UNEXPECTED_SYSTEM", "retry_semantics": "UNKNOWN", "user_message_policy": "safe message and error id", "diagnostic_requirements": ["exception", "stack", "cause", "source-version"]},
        ],
    }
    contract["fingerprint"] = error_contract_fingerprint(contract)
    return contract


def valid_error_event(kind: str = "UNEXPECTED_SYSTEM") -> dict:
    unexpected = kind == "UNEXPECTED_SYSTEM"
    return {
        "schema_version": "1.0.0", "error_id": "ERR-20260826-0001", "trace_id": "trace-1",
        "timestamp": "2026-08-26T12:00:00Z", "operation": "enrol", "version": "1.4.0", "source_fingerprint": "source",
        "classification": "UNEXPECTED" if unexpected else "ENROLMENT_CONFLICT", "kind": kind,
        "retry_semantics": "UNKNOWN" if unexpected else "AFTER_CHANGE",
        "user": {"message": "暂时无法完成，请稍后重试。", "next_step": "联系支持并提供错误编号", "error_id": "ERR-20260826-0001"},
        "developer": {
            "error_id": "ERR-20260826-0001", "trace_id": "trace-1", "exception_type": "DatabaseUnavailable" if unexpected else None,
            "cause": "dependency unavailable" if unexpected else None, "stack_ref": "evidence://errors/stack-1" if unexpected else None,
            "diagnostic_evidence_refs": ["evidence://errors/event-1"], "redaction_status": "PASS",
        },
    }


def valid_architecture_profile(architecture: str = "BS") -> dict:
    required = ["browser", "route", "responsive", "async_state", "accessibility", "hidden_surfaces"] if architecture == "BS" else ["window", "screen", "dpi", "resolution", "input", "resource", "lifecycle", "update", "crash_recovery"]
    profile = {
        "schema_version": "1.0.0", "profile_id": f"profile-{architecture.lower()}", "architecture": architecture,
        "project_facts": [{"status": "OBSERVED", "subject": "target-environment", "value": "browser" if architecture == "BS" else "desktop-keyboard", "source_refs": ["project:target"]}],
        "required_dimensions": required,
        "dimensions": {name: {"status": "PASS", "evidence_refs": [f"evidence:{name}"], "reason": None} for name in required},
    }
    profile["fingerprint"] = profile_fingerprint(profile)
    return profile


class ProductAssuranceTests(unittest.TestCase):
    def test_semantic_ui_model_accepts_custom_or_hybrid_composition(self) -> None:
        model = default_model("school-admin", "BS")
        model["screens"] = [valid_screen()]
        model["fingerprint"] = model_fingerprint(model)
        self.assertEqual(validate(model)["status"], "PASS")

    def test_screen_patch_changes_only_the_affected_screen(self) -> None:
        model = default_model("school-admin", "BS")
        first = valid_screen()
        second = {**valid_screen(), "screen_id": "record-detail", "primary_task": "Inspect one record"}
        model["screens"] = [first, second]
        model["fingerprint"] = model_fingerprint(model)
        preserved_before = json.dumps(second, sort_keys=True)
        updated, impact = patch_screen(model, "record-list", {"focal_point": "urgent matching records"})
        self.assertEqual("urgent matching records", updated["screens"][0]["focal_point"])
        self.assertEqual(preserved_before, json.dumps(updated["screens"][1], sort_keys=True))
        self.assertEqual(["screen:record-list"], impact["affected_scope"])
        self.assertEqual(1, impact["preserved_screen_count"])
        self.assertEqual("PASS", validate(updated)["status"])

    def test_template_shape_and_unproven_observation_are_rejected(self) -> None:
        model = default_model("school-admin", "BS")
        screen = valid_screen()
        screen["columns"] = 3
        model["screens"] = [screen]
        model["visual_context"] = [{"status": "OBSERVED", "subject": "reference", "value": "blue", "source_refs": []}]
        model["fingerprint"] = model_fingerprint(model)
        codes = {item["code"] for item in validate(model)["errors"]}
        self.assertIn("TEMPLATE_SHAPE_FORBIDDEN", codes)
        self.assertIn("OBSERVED_REQUIRES_SOURCE", codes)

    def test_user_decision_supersedes_baseline_but_not_system_invariant(self) -> None:
        model = default_model("school-admin", "BS")
        baseline = make_decision("D-1", "APPROVED_BASELINE", "layout.direction", "dense", "approved", ["review:1"], ["screen:records"])
        model, _ = apply_decision(model, baseline)
        user = make_decision("D-2", "USER_LOCKED_DECISION", "layout.direction", "calm", "user changed direction", ["request:r2"], ["screen:records"], "D-1")
        model, impact = apply_decision(model, user)
        self.assertEqual(model["decisions"][0]["status"], "SUPERSEDED")
        self.assertTrue(impact["goal_change_required"])

        invariant = make_decision("D-3", "SYSTEM_INVARIANT", "privacy.stack", "hidden", "production safety", ["policy:privacy"], ["screen:*"])
        model, _ = apply_decision(model, invariant)
        override = make_decision("D-4", "USER_LOCKED_DECISION", "privacy.stack", "visible", "requested", ["request:r3"], ["screen:error"], "D-3")
        with self.assertRaisesRegex(ValueError, "lower authority"):
            apply_decision(model, override)

    def test_inspect_old_project_is_read_only_and_does_not_create_ai(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".ai" / "ui" / "project-ui.json"
            result = inspect(path)
            self.assertEqual(result["status"], "LEGACY_NO_UI_IR")
            self.assertEqual(result["writes"], 0)
            self.assertFalse(path.parent.exists())

    def test_bounded_legacy_migration_preserves_unknowns_without_templates(self) -> None:
        legacy = {
            "schema_version": "1.0.0",
            "framework": "Vue",
            "screens": [{"id": "records", "components": ["RecordTable"]}],
        }
        model = migrate_legacy(legacy, "school-admin", "BS", ".ai/design/ui-contract.json")
        self.assertEqual(model["migration"]["status"], "MIGRATED_BOUNDED")
        self.assertEqual(model["technology"]["status"], "INFERRED")
        self.assertEqual(model["screens"][0]["focal_point"], "UNKNOWN")
        self.assertEqual(validate(model)["status"], "PASS")

    def test_cli_init_then_decide_writes_only_explicit_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = SCRIPTS / "ui_design_model.py"
            created = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "init", "--project-ui-id", "client", "--architecture", "CS"],
                text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            updated = subprocess.run(
                [
                    sys.executable, str(script), "--root", str(root), "decide",
                    "--decision-id", "D-1", "--authority", "MODEL_PROPOSAL",
                    "--topic", "composition", "--value-json", json.dumps("inspection"),
                    "--rationale", "based on the inspection workflow", "--affected", "screen:main",
                ],
                text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(updated.returncode, 0, updated.stderr)
            files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
            self.assertEqual(files, [".ai/ui/project-ui.json"])

    def test_component_registry_migration_is_bounded_and_release_fails_on_unknown_mapping(self) -> None:
        legacy = {"schema_version": "1.0.0", "components": [{"name": "RecordRow", "path": "src/RecordRow.vue", "sha256": "abc"}]}
        registry = migrate_legacy_registry(legacy, "domain-components", ".ai/context/components-web.json")
        self.assertEqual(validate_registry(registry)["status"], "PASS_WITH_GAPS")
        release = validate_registry(registry, release=True)
        self.assertEqual(release["status"], "BLOCKED")
        self.assertTrue(any(item["code"] == "RELEASE_COMPONENT_GAP" for item in release["errors"]))

    def test_adapter_merge_refreshes_code_facts_without_overwriting_design_semantics(self) -> None:
        registry = empty_registry("school-components")
        observed = {
            "scope": {"mode": "EXPLICIT", "refs": ["src/RecordRow.vue"]},
            "components": [{
                "component_id": "bs:src/RecordRow.vue#RecordRow",
                "semantic_role": {"status": "UNKNOWN", "value": None, "source_refs": []},
                "design_component": {"status": "UNKNOWN", "value": None, "source_refs": []},
                "code_component": {"status": "OBSERVED", "value": {"path": "src/RecordRow.vue", "symbol": "RecordRow", "source_fingerprint": "abc"}, "source_refs": ["src/RecordRow.vue"]},
                "variants": [], "states": ["selected"], "tokens": [], "accessibility": [],
                "platform": "BS", "usage_rules": [],
                "technology_adapter": {"status": "OBSERVED", "value": {"family": "vue", "version": "3.5"}, "source_refs": ["package.json"]},
                "implementation_layer": "project_native",
            }],
        }
        observed["components"][0]["fingerprint"] = component_fingerprint(observed["components"][0])
        registry = merge_observations(registry, observed)
        registry["components"][0]["semantic_role"] = {"status": "OBSERVED", "value": "record search result", "source_refs": ["design:record-list"]}
        registry["components"][0]["design_component"] = {"status": "OBSERVED", "value": "RecordResult", "source_refs": ["design:record-list"]}
        registry["components"][0]["fingerprint"] = component_fingerprint(registry["components"][0])
        from component_registry_v2 import registry_fingerprint
        registry["fingerprint"] = registry_fingerprint(registry)
        refreshed = json.loads(json.dumps(observed))
        refreshed["components"][0]["code_component"]["value"]["source_fingerprint"] = "def"
        refreshed["components"][0]["fingerprint"] = component_fingerprint(refreshed["components"][0])
        registry = merge_observations(registry, refreshed)
        component = registry["components"][0]
        self.assertEqual(component["semantic_role"]["value"], "record search result")
        self.assertEqual(component["code_component"]["value"]["source_fingerprint"], "def")
        self.assertEqual(validate_registry(registry)["status"], "PASS")
        plan = design_to_code_plan(registry, [component["component_id"], "missing"])
        self.assertEqual(plan["architecture_policy"], "respect-project-native")
        self.assertEqual(plan["unresolved"], ["missing"])

    def test_runtime_objective_checks_detect_layout_state_and_token_failures(self) -> None:
        design = default_model("school-admin", "BS"); design["screens"] = [valid_screen()]; design["fingerprint"] = model_fingerprint(design)
        registry = valid_registry(); snapshot = valid_snapshot(design, registry)
        snapshot["state"] = "loading"
        snapshot["elements"][0].update({"scroll_width": 500, "client_width": 400})
        snapshot["elements"][1]["rect"] = {"x": 300, "y": 20, "width": 1000, "height": 40}
        result = objective_checks(snapshot, list(valid_screen()["components"]) + ["missing"], "default", {"bs:src/Search.vue#SearchField": {"color": "danger"}})
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"MISSING_COMPONENT", "WRONG_STATE", "HORIZONTAL_OVERFLOW", "OFFSCREEN", "OVERLAP", "TOKEN_DRIFT"}.issubset(codes))

    def test_fidelity_separates_objective_and_perceptual_review_and_binds_facts(self) -> None:
        design = default_model("school-admin", "BS"); design["screens"] = [valid_screen()]; design["fingerprint"] = model_fingerprint(design)
        registry = valid_registry(); snapshot = valid_snapshot(design, registry)
        waiting = evaluate_fidelity(design, registry, snapshot, candidate_id="C-1", goal_revision=3)
        self.assertEqual(waiting["verdict"], "REQUIRES_REVIEW")
        passed = evaluate_fidelity(design, registry, snapshot, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["review:R-1"], "findings": []}, "C-1", 3)
        self.assertEqual(passed["verdict"], "PASS")
        self.assertEqual(passed["objective_checks"]["status"], "PASS")
        self.assertEqual(passed["design_fingerprint"], design["fingerprint"])
        self.assertEqual(passed["registry_fingerprint"], registry["fingerprint"])

    def test_capture_and_migration_evidence_do_not_persist_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "screen.png"; artifact.write_bytes(b"png")
            design = default_model("school-admin", "BS"); design["screens"] = [valid_screen()]; design["fingerprint"] = model_fingerprint(design)
            registry = valid_registry(); snapshot = valid_snapshot(design, registry)
            bound = bind_artifact({key: value for key, value in snapshot.items() if key not in {"fingerprint", "capture_artifact"}}, artifact)
            self.assertEqual(bound["capture_artifact"]["ref"], "screen.png")
            self.assertNotIn(td, json.dumps(bound))
            migrated = migrate_legacy({"schema_version": "1.0.0", "screens": []}, "project", "BS", ".ai/design/ui-contract.json")
            self.assertNotIn(td, json.dumps(migrated))

    def test_fidelity_becomes_stale_when_design_or_registry_changes(self) -> None:
        design = default_model("school-admin", "BS"); design["screens"] = [valid_screen()]; design["fingerprint"] = model_fingerprint(design)
        registry = valid_registry(); snapshot = valid_snapshot(design, registry)
        snapshot["design_fingerprint"] = "old"
        result = evaluate_fidelity(design, registry, snapshot, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["review:R-1"], "findings": []})
        self.assertEqual(result["verdict"], "STALE")

    def test_fidelity_blocks_design_component_missing_from_registry(self) -> None:
        design = default_model("school-admin", "BS"); design["screens"] = [valid_screen()]; design["fingerprint"] = model_fingerprint(design)
        registry = valid_registry(); registry["components"] = registry["components"][:1]; registry["fingerprint"] = registry_fingerprint(registry)
        snapshot = valid_snapshot(design, registry); snapshot["elements"] = snapshot["elements"][:1]
        result = evaluate_fidelity(design, registry, snapshot, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["review:R-1"], "findings": []})
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(any(item["code"] == "DESIGN_COMPONENT_NOT_IN_REGISTRY" for item in result["blockers"]))

    def test_presentation_contract_allows_business_identifier_but_blocks_technical_identifier(self) -> None:
        contract = valid_presentation_contract()
        self.assertEqual(validate_contract(contract)["status"], "PASS")
        contract["fields"][1]["visibility"] = "USER_VISIBLE"
        contract["fingerprint"] = contract_fingerprint(contract)
        codes = {item["code"] for item in validate_contract(contract)["errors"]}
        self.assertIn("TECHNICAL_IDENTIFIER_CANNOT_BE_USER_VISIBLE", codes)

    def test_schema_to_ui_leakage_uses_semantic_mapping_and_does_not_echo_values(self) -> None:
        contract = valid_presentation_contract()
        bindings = {"bindings": [
            {"source_field": "record_number", "presentation_field": "record.business_number", "mapping": "domain", "visible": True, "sample": "REC-1001"},
            {"source_field": "status_code", "presentation_field": "record.status", "mapping": "direct", "visible": True, "sample": "RECORD_V2"},
        ]}
        result = audit_bindings(contract, bindings)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("SCHEMA_TO_UI_DIRECT_LEAKAGE", codes)
        self.assertIn("RAW_ENUM_LEAKAGE", codes)
        self.assertNotIn("RECORD_V2", json.dumps(result))

    def test_content_stress_is_runtime_measured_without_character_limits(self) -> None:
        cases = sorted(CONTENT_CASES)
        test_plan = content_plan(cases, ["record-dialog"])
        results = {"results": [{"case": case, "surface": "record-dialog", "measurements": {}, "evidence_ref": f"capture:{case}"} for case in cases]}
        self.assertEqual(evaluate_content(test_plan, results)["status"], "PASS")
        results["results"][0]["measurements"]["dialog_overflow"] = True
        self.assertEqual(evaluate_content(test_plan, results)["status"], "BLOCKED")

    def test_interaction_copy_checks_semantics_and_runtime_fit_not_character_count(self) -> None:
        long_but_valid = "请核对所选记录、范围和生效日期后继续；系统将在提交前再次显示变更摘要。" * 20
        passed = audit_copy({"entries": [{
            "copy_id": "confirm", "control_role": "dialog_help", "surface": "enrolment", "text": long_but_valid,
            "intent": "explain consequences", "next_step": "review summary", "runtime_fit": "PASS",
        }]})
        self.assertEqual(passed["status"], "PASS")
        blocked = audit_copy({"entries": [{
            "copy_id": "error", "control_role": "error", "surface": "enrolment", "text": "SQLSTATE 23000",
            "intent": "report failure", "next_step": None, "runtime_fit": "NOT_RUN",
        }]})
        codes = {item["code"] for item in blocked["findings"]}
        self.assertTrue({"TECHNICAL_COPY_LEAKAGE", "COPY_MISSING_NEXT_STEP", "COPY_RUNTIME_FIT_UNVERIFIED"}.issubset(codes))

    def test_error_contract_is_protocol_neutral(self) -> None:
        for family in ("REST", "PROBLEM_DETAILS", "GRAPHQL", "GRPC", "CS_LOCAL", "CUSTOM"):
            with self.subTest(family=family):
                result = validate_error_contract(valid_error_contract(family))
                self.assertEqual(result["status"], "PASS")

    def test_error_channels_and_correlation_are_traceable(self) -> None:
        contract = valid_error_contract(); event = valid_error_event()
        correlations = {"correlations": {"ERR-20260826-0001": {"trace_id": "trace-1", "diagnostic_ref": "evidence://errors/event-1"}}}
        self.assertEqual(validate_event(contract, event, correlations)["status"], "PASS")
        business = valid_error_event("EXPECTED_BUSINESS")
        self.assertEqual(validate_event(contract, business, correlations)["status"], "PASS")

    def test_unsafe_user_error_and_decorative_error_id_are_blocked(self) -> None:
        contract = valid_error_contract(); event = valid_error_event()
        event["user"]["message"] = "SQLSTATE 08006 at C:" + r"\Users\operator\server.py"
        event["developer"]["error_id"] = "different"
        result = validate_event(contract, event, {"correlations": {}})
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"UNSAFE_USER_ERROR_MESSAGE", "ERROR_ID_CORRELATION_MISMATCH", "ERROR_ID_NOT_TRACEABLE"}.issubset(codes))

    def test_catch_and_hide_requires_diagnostic_path_and_retains_no_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "bad.ts").write_text("try { work(); } catch (error) { return toast('操作失败'); }", encoding="utf-8")
            (root / "good.ts").write_text("try { work(); } catch (error) { logger.error(error); throw error; }", encoding="utf-8")
            result = audit_sources(root, ["bad.ts", "good.ts"])
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["findings"][0]["code"], "CATCH_AND_HIDE")
            self.assertFalse(result["source_content_retained"])
            self.assertNotIn("操作失败", json.dumps(result, ensure_ascii=False))

    def test_product_release_gate_is_optional_for_old_projects_and_fail_closed_for_ui_projects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(evaluate_product_release(root)["status"], "NOT_APPLICABLE")
            ui = root / ".ai" / "ui"; evidence_dir = ui / "evidence"; evidence_dir.mkdir(parents=True)
            design = default_model("school-admin", "BS"); design["screens"] = [valid_screen()]; design["fingerprint"] = model_fingerprint(design)
            registry = valid_registry(); presentation = valid_presentation_contract(); error_contract = valid_error_contract()
            snapshot = valid_snapshot(design, registry)
            visual = evaluate_fidelity(design, registry, snapshot, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["review:R-1"], "findings": []}, "C-1", 3)
            for path, value in (
                (ui / "project-ui.json", design), (ui / "component-registry.json", registry),
                (ui / "presentation-contract.json", presentation), (ui / "error-contract.json", error_contract),
                (ui / "architecture-profile.json", valid_architecture_profile("BS")),
                (evidence_dir / "index.json", {"records": [visual]}),
                (evidence_dir / "content.json", {"status": "PASS"}),
                (evidence_dir / "presentation.json", {"status": "PASS"}),
                (evidence_dir / "error.json", {"status": "PASS"}),
            ):
                path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(evaluate_product_release(root)["status"], "PASS")
            incomplete_registry = valid_registry(); incomplete_registry["components"] = incomplete_registry["components"][:1]; incomplete_registry["fingerprint"] = registry_fingerprint(incomplete_registry)
            (ui / "component-registry.json").write_text(json.dumps(incomplete_registry), encoding="utf-8")
            registry_blocked = evaluate_product_release(root)
            self.assertTrue(any(item["code"] == "DESIGN_COMPONENT_NOT_REGISTERED" for item in registry_blocked["blockers"]))
            (ui / "component-registry.json").write_text(json.dumps(registry), encoding="utf-8")
            visual["design_fingerprint"] = "stale"
            (evidence_dir / "index.json").write_text(json.dumps({"records": [visual]}), encoding="utf-8")
            blocked = evaluate_product_release(root)
            self.assertEqual(blocked["status"], "BLOCKED")
            self.assertTrue(any(item["code"] == "STALE_OR_UNBOUND_VISUAL_EVIDENCE" for item in blocked["blockers"]))

    def test_bs_and_cs_architecture_dimensions_are_selected_from_project_facts(self) -> None:
        bs = valid_architecture_profile("BS")
        self.assertEqual(validate_architecture_profile(bs)["status"], "PASS")
        bs["dimensions"].pop("hidden_surfaces")
        bs["fingerprint"] = profile_fingerprint(bs)
        self.assertEqual(validate_architecture_profile(bs)["status"], "BLOCKED")

        cs = valid_architecture_profile("CS")
        cs["dimensions"]["offline"] = {"status": "NOT_APPLICABLE", "evidence_refs": [], "reason": "target project has no offline workflow"}
        cs["dimensions"]["device"] = {"status": "NOT_APPLICABLE", "evidence_refs": [], "reason": "desktop target has no external device integration"}
        cs["fingerprint"] = profile_fingerprint(cs)
        result = validate_architecture_profile(cs)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["selection_policy"], "project-facts-and-target-environment")

    def test_architecture_profile_requires_schema_identity(self) -> None:
        profile = valid_architecture_profile("BS")
        profile["schema_version"] = "0.0.0"
        profile["profile_id"] = ""
        profile["fingerprint"] = profile_fingerprint(profile)
        codes = {item["code"] for item in validate_architecture_profile(profile)["errors"]}
        self.assertEqual(codes, {"UNSUPPORTED_SCHEMA_VERSION", "MISSING_PROFILE_ID"})

    def test_published_product_schemas_are_closed_and_parseable(self) -> None:
        names = {
            "architecture-product-profile.schema.json", "component-registry-v2.schema.json",
            "error-contract.schema.json", "presentation-contract.schema.json",
            "ui-design-model.schema.json", "visual-evidence.schema.json",
        }
        for name in names:
            with self.subTest(schema=name):
                schema = json.loads((PLUGIN / "schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
