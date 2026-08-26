from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SUITE = PLUGIN.parents[1]
for scripts in (
    PLUGIN / "scripts",
    SUITE / "plugins" / "ai-engineering-web" / "scripts",
    SUITE / "plugins" / "ai-engineering-unity" / "scripts",
):
    sys.path.insert(0, str(scripts))

from bs_ui_adapter import observe as observe_bs
from component_registry_v2 import component_fingerprint, empty_registry, merge_observations, registry_fingerprint, validate as validate_registry
from cs_ui_adapter import observe as observe_cs
from content_assurance import CONTENT_CASES, evaluate as evaluate_content, plan as content_plan
from error_experience_guard import audit_sources, contract_fingerprint as error_fingerprint, validate_contract as validate_error_contract, validate_event
from presentation_guard import audit_bindings, audit_copy, contract_fingerprint as presentation_fingerprint, validate_contract as validate_presentation_contract
from product_model_common import model_fingerprint
from runtime_ui_evidence import bind_artifact, objective_checks
from ui_design_model import default_model, validate as validate_design
from visual_fidelity import evaluate as evaluate_fidelity


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def design(architecture: str, screen_id: str, component_id: str) -> dict:
    model = default_model(f"e2e-{architecture.lower()}", architecture)
    model["screens"] = [{
        "screen_id": screen_id,
        "primary_task": "inspect current operational status",
        "information_hierarchy": ["status", "details", "available action"],
        "focal_point": "current status",
        "reading_path": ["status", "details", "action"],
        "density_profile": "task-focused",
        "navigation_relationships": [],
        "content_regions": [{"region_id": "main", "semantic_role": "status inspection"}],
        "components": [component_id],
        "states": ["default", "error"],
        "interactions": ["inspect"],
        "presentation_refs": ["status.label"],
        "acceptance": ["primary status is visible without clipping"],
        "composition_strategy": {"kind": "custom", "candidates": ["inspection"], "rationale": "The workflow is a focused inspection task."},
    }]
    model["fingerprint"] = model_fingerprint(model)
    return model


def mapped_registry(observations: dict, registry_id: str) -> dict:
    registry = merge_observations(empty_registry(registry_id), observations)
    for component in registry["components"]:
        component["semantic_role"] = {"status": "OBSERVED", "value": "primary operational status", "source_refs": ["design:main"]}
        component["design_component"] = {"status": "OBSERVED", "value": "OperationalStatus", "source_refs": ["design:main"]}
        component["fingerprint"] = component_fingerprint(component)
    registry["fingerprint"] = registry_fingerprint(registry)
    return registry


def snapshot(model: dict, registry: dict, component_id: str, architecture: str, rect: dict, technology: str) -> dict:
    data = {
        "capture_id": f"CAP-{architecture}", "screen_id": "main", "state": "default", "architecture": architecture,
        "technology": technology, "source_commit": "e2e-source", "workspace_fingerprint": None, "source_fingerprint": "e2e-source",
        "design_fingerprint": model["fingerprint"], "registry_fingerprint": registry["fingerprint"],
        "viewport": {"width": 1280 if architecture == "CS" else 390, "height": 720 if architecture == "CS" else 844, "dpi": 144 if architecture == "CS" else 96},
        "elements": [{"component_id": component_id, "rect": rect, "tokens": {}}],
    }
    return bind_artifact(data, None)


def presentation_contract() -> dict:
    contract = {
        "schema_version": "1.0.0", "contract_id": "record-presentation-e2e", "revision": 1,
        "fields": [
            {"field_id": "record.business_number", "semantic_role": "business reference", "presentation_role": "secondary identifier", "visibility": "USER_VISIBLE", "priority": "secondary", "format": {"kind": "business_identifier"}, "fallback": {"kind": "localized_empty"}, "overflow_policy": {"strategy": "truncate_with_access", "runtime_validation_required": True}, "sensitivity": "PERSONAL", "identifier_kind": "BUSINESS", "business_meaning": "Operator-visible reference"},
            {"field_id": "record.internal_id", "semantic_role": "database identity", "presentation_role": "none", "visibility": "HIDDEN", "priority": "none", "format": {"kind": "none"}, "fallback": {"kind": "none"}, "overflow_policy": {"strategy": "project_native", "runtime_validation_required": True}, "sensitivity": "SENSITIVE", "identifier_kind": "TECHNICAL", "business_meaning": None},
            {"field_id": "record.status", "semantic_role": "workflow status", "presentation_role": "status label", "visibility": "USER_VISIBLE", "priority": "primary", "format": {"kind": "domain_enum"}, "fallback": {"kind": "localized_unknown"}, "overflow_policy": {"strategy": "wrap", "runtime_validation_required": True}, "sensitivity": "PUBLIC", "identifier_kind": "NONE", "business_meaning": None},
        ],
    }
    contract["fingerprint"] = presentation_fingerprint(contract)
    return contract


def error_contract() -> dict:
    contract = {
        "schema_version": "1.0.0", "contract_id": "operation-errors-e2e", "revision": 1,
        "protocol": {"family": "CUSTOM", "serialization": "project-native", "existing_contract_ref": "contracts/errors", "semantic_mappings": {"classification": "kind", "user_message": "safe_message", "developer_diagnostic": "diagnostic", "error_code": "code", "correlation": "error_id", "retry": "retry"}},
        "classifications": [
            {"code": "CONFLICT", "kind": "EXPECTED_BUSINESS", "retry_semantics": "AFTER_CHANGE", "user_message_policy": "explain conflict and next step", "diagnostic_requirements": ["operation"]},
            {"code": "UNEXPECTED", "kind": "UNEXPECTED_SYSTEM", "retry_semantics": "UNKNOWN", "user_message_policy": "safe message and error id", "diagnostic_requirements": ["exception", "stack", "cause", "source-version"]},
        ],
    }
    contract["fingerprint"] = error_fingerprint(contract)
    return contract


def error_event(kind: str) -> dict:
    unexpected = kind == "UNEXPECTED_SYSTEM"
    return {
        "schema_version": "1.0.0", "error_id": "ERR-E2E-0001", "trace_id": "TRACE-E2E-1", "timestamp": "2026-08-26T12:00:00Z",
        "operation": "update-record", "version": "5.18-candidate", "source_fingerprint": "source-e2e",
        "classification": "UNEXPECTED" if unexpected else "CONFLICT", "kind": kind, "retry_semantics": "UNKNOWN" if unexpected else "AFTER_CHANGE",
        "user": {"message": "暂时无法完成，请稍后重试。" if unexpected else "记录已经变化，请刷新后重试。", "next_step": "提供错误编号联系支持" if unexpected else "刷新记录", "error_id": "ERR-E2E-0001"},
        "developer": {"error_id": "ERR-E2E-0001", "trace_id": "TRACE-E2E-1", "exception_type": "DependencyUnavailable" if unexpected else None, "cause": "dependency unavailable" if unexpected else None, "stack_ref": "evidence://errors/stack-e2e" if unexpected else None, "diagnostic_evidence_refs": ["evidence://errors/event-e2e"], "redaction_status": "PASS"},
    }


class ProductDeliveryE2E(unittest.TestCase):
    def test_bs_requirement_design_code_runtime_capture_fix_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "src/components").mkdir(parents=True)
            (root / "package.json").write_text(json.dumps({"dependencies": {"vue": "3.5.1"}}), encoding="utf-8")
            source = root / "src/components/StatusPanel.vue"
            source.write_text("<main><button aria-label='Inspect'>Inspect</button></main>", encoding="utf-8")
            observations = observe_bs(root, ["src/components/StatusPanel.vue"])
            component_id = observations["components"][0]["component_id"]
            registry = mapped_registry(observations, "bs-e2e")
            model = design("BS", "main", component_id)
            self.assertEqual(validate_design(model)["status"], "PASS")
            self.assertEqual(validate_registry(registry, release=True)["status"], "PASS")

            broken = snapshot(model, registry, component_id, "BS", {"x": 20, "y": 20, "width": 520, "height": 80}, "vue@3.5.1")
            self.assertEqual(objective_checks(broken, [component_id], "default")["status"], "BLOCKED")

            screenshot = root / "runtime-fixed.png"; screenshot.write_bytes(PNG_1X1)
            fixed = snapshot(model, registry, component_id, "BS", {"x": 20, "y": 20, "width": 350, "height": 80}, "vue@3.5.1")
            fixed = bind_artifact({key: value for key, value in fixed.items() if key not in {"fingerprint", "capture_artifact"}}, screenshot)
            evidence = evaluate_fidelity(model, registry, fixed, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["capture:runtime-fixed.png"], "findings": []}, "C-BS", 2)
            self.assertEqual(evidence["verdict"], "PASS")
            self.assertEqual(evidence["actual"]["capture_artifact"]["sha256"], __import__("hashlib").sha256(PNG_1X1).hexdigest())

    def test_cs_requirement_design_code_runtime_resolution_fix_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "ui").mkdir()
            source = root / "ui/StatusPanel.qml"
            source.write_text("Item { Accessible.name: 'Status'; property bool offline: false }", encoding="utf-8")
            observations = observe_cs(root, ["ui/StatusPanel.qml"])
            component_id = observations["components"][0]["component_id"]
            registry = mapped_registry(observations, "cs-e2e")
            model = design("CS", "main", component_id)
            broken = snapshot(model, registry, component_id, "CS", {"x": 1180, "y": 20, "width": 240, "height": 100}, "qt")
            self.assertEqual(objective_checks(broken, [component_id], "default")["status"], "BLOCKED")
            fixed = snapshot(model, registry, component_id, "CS", {"x": 40, "y": 40, "width": 600, "height": 100}, "qt")
            evidence = evaluate_fidelity(model, registry, fixed, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["capture:client-equivalent"], "findings": []}, "C-CS", 2)
            self.assertEqual(evidence["verdict"], "PASS")
            self.assertEqual(evidence["viewport"]["dpi"], 144)

    def test_runtime_state_not_declared_by_design_is_blocked(self) -> None:
        observations = {
            "scope": {"mode": "EXPLICIT", "refs": ["Status.qml"]},
            "components": [],
        }
        registry = merge_observations(empty_registry("state-e2e"), observations)
        model = design("CS", "main", "missing")
        runtime = snapshot(model, registry, "missing", "CS", {"x": 0, "y": 0, "width": 10, "height": 10}, "project-native")
        runtime["state"] = "debug"
        result = evaluate_fidelity(model, registry, runtime, {"verdict": "PASS", "reviewer": "independent", "evidence_refs": ["review:1"], "findings": []})
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(any(item["code"] == "RUNTIME_STATE_NOT_IN_DESIGN" for item in result["blockers"]))

    def test_presentation_leakage_content_and_copy_fix_pass(self) -> None:
        contract = presentation_contract()
        self.assertEqual("PASS", validate_presentation_contract(contract)["status"])
        leaking = audit_bindings(contract, {"bindings": [
            {"source_field": "internal_id", "presentation_field": "record.internal_id", "mapping": "direct", "visible": True, "sample": "8f60"},
            {"source_field": "status_code", "presentation_field": "record.status", "mapping": "direct", "visible": True, "sample": "RECORD_V2"},
        ]})
        self.assertEqual("BLOCKED", leaking["status"])
        fixed = audit_bindings(contract, {"bindings": [
            {"source_field": "record_number", "presentation_field": "record.business_number", "mapping": "domain", "visible": True, "sample": "REC-1001"},
            {"source_field": "status_code", "presentation_field": "record.status", "mapping": "presentation", "visible": True, "sample": "处理中"},
        ]})
        self.assertEqual("PASS", fixed["status"])
        plan = content_plan(sorted(CONTENT_CASES), ["record-dialog"])
        runtime = {"results": [{"case": case, "surface": "record-dialog", "measurements": {}, "evidence_ref": f"capture:{case}"} for case in sorted(CONTENT_CASES)]}
        self.assertEqual("PASS", evaluate_content(plan, runtime)["status"])
        copy = audit_copy({"entries": [{"copy_id": "failure", "control_role": "error", "surface": "record-dialog", "text": "无法保存记录。", "intent": "report safe failure", "next_step": "稍后重试或提供错误编号联系支持", "runtime_fit": "PASS"}]})
        self.assertEqual("PASS", copy["status"])

    def test_error_contract_channels_correlation_and_catch_hide_fix_pass(self) -> None:
        contract = error_contract()
        self.assertEqual("PASS", validate_error_contract(contract)["status"])
        correlations = {"correlations": {"ERR-E2E-0001": {"trace_id": "TRACE-E2E-1", "diagnostic_ref": "evidence://errors/event-e2e"}}}
        self.assertEqual("PASS", validate_event(contract, error_event("EXPECTED_BUSINESS"), correlations)["status"])
        self.assertEqual("PASS", validate_event(contract, error_event("UNEXPECTED_SYSTEM"), correlations)["status"])
        unsafe = error_event("UNEXPECTED_SYSTEM")
        unsafe["user"]["message"] = "SQLSTATE 08006 at C:" + r"\Users\operator\service.py"
        self.assertEqual("BLOCKED", validate_event(contract, unsafe, correlations)["status"])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "handler.ts"
            source.write_text("try { run(); } catch (error) { return toast('failed'); }", encoding="utf-8")
            self.assertEqual("BLOCKED", audit_sources(root, ["handler.ts"])["status"])
            source.write_text("try { run(); } catch (error) { logger.error(error); throw error; }", encoding="utf-8")
            self.assertEqual("PASS", audit_sources(root, ["handler.ts"])["status"])


if __name__ == "__main__":
    unittest.main()
