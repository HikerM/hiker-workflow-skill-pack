from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from engineering_manifests import DiscoveryBudget, discover_engineering_manifests
from route_contract import normalize_route_contract
from suite_router import inspect_project, route


def proposal(*skills: str, **overrides):
    result = {
        "project_mode": "existing",
        "architecture": "unknown",
        "stage": "development",
        "current_action": "执行当前受影响范围",
        "confidence": "high",
        "candidates": list(skills),
    }
    result.update(overrides)
    return result


def package(path: Path, dependencies: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"dependencies": dependencies}), encoding="utf-8")


def bs_fixture(root: Path) -> None:
    package(root / "apps" / "admin" / "package.json", {"react": "19.0.0"})
    package(root / "services" / "api" / "package.json", {"express": "5.0.0", "pg": "8.0.0"})


class RoutingIntelligenceTests(unittest.TestCase):
    def test_bs_project_backend_task_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "backend-component-implementation", architecture="backend", task_scope=["backend"]
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual("bs", result["project_architecture"])
        self.assertEqual(["backend"], result["task_scope"])
        self.assertFalse(result["conflict_receipt"]["is_positive_contradiction"])

    def test_bs_project_frontend_task_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "web-component-implementation", architecture="bs", task_scope=["frontend"]
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual("bs", result["project_architecture"])

    def test_bs_project_database_task_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "database-migration-governance", architecture="backend", task_scope=["database"]
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual("bs", result["project_architecture"])

    def test_bs_project_fullstack_task_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "web-component-implementation", "backend-component-implementation",
                architecture="bs", task_scope=["frontend", "backend"],
                intent_atoms=[
                    {"id": "I1", "state": "CURRENT", "operation": "frontend mutation", "target": "apps/admin", "capability_family": "frontend"},
                    {"id": "I2", "state": "CURRENT", "operation": "backend mutation", "target": "services/api", "capability_family": "backend", "dependencies": ["I1"]},
                ],
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual("DEEP", result["routing_cost"])
        self.assertEqual(2, len(result["selected"]))

    def test_backend_only_service_remains_backend_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package(root / "package.json", {"fastify": "5.0.0"})
            facts = inspect_project(root)["project_facts"]
        self.assertEqual("backend", facts["project_architecture"])
        self.assertEqual([], facts["fact_plane"]["project_topology"]["value"]["frontend_roots"])

    def test_task_scope_cannot_mutate_project_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            first = route(root, proposal("backend-component-implementation", architecture="backend", task_scope=["backend"]))
            second = route(root, proposal("web-component-implementation", architecture="bs", task_scope=["frontend"]))
        self.assertEqual("bs", first["project_architecture"])
        self.assertEqual("bs", second["project_architecture"])
        self.assertNotEqual(first["task_scope"], second["task_scope"])

    def test_route_target_cannot_mutate_project_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            backend = route(root, proposal("backend-component-implementation", architecture="backend"))
            database = route(root, proposal("database-migration-governance", architecture="backend", task_scope=["database"]))
        self.assertEqual("bs", backend["project_architecture"])
        self.assertEqual("bs", database["project_architecture"])

    def test_stale_legacy_backend_hint_cannot_override_current_bs_topology(self):
        legacy = {
            "facts": {
                "project_id": "project-1",
                "project_generation": 7,
                "project_architecture": {
                    "value": "backend", "authority": "IMPORTED_LEGACY", "generation": 1,
                    "source_fingerprint": "a" * 64, "freshness": "HISTORICAL", "lifecycle": "ARCHIVED",
                },
            }
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal("web-component-implementation", architecture="bs"), legacy)
        self.assertEqual("bs", result["project_architecture"])
        self.assertNotEqual("IMPORTED_LEGACY", result["project_fact_plane"]["project_architecture"]["authority"])

    def test_architecture_conflict_requires_positive_contradiction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            compatible = route(root, proposal(
                "backend-component-implementation", architecture="backend", task_scope=["backend"]
            ))
            conflict = route(root, proposal(
                "cs-component-implementation", project_architecture="cs", architecture="cs", task_scope=["client"]
            ))
        self.assertFalse(compatible["conflict_receipt"]["is_positive_contradiction"])
        self.assertTrue(conflict["conflict_receipt"]["is_positive_contradiction"])
        self.assertIn("ARCHITECTURE_CONFLICT", {item["code"] for item in conflict["diagnostics"]})

    def test_controlled_untracked_manifest_is_discovered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "hiker.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
            (root / "README.md").write_text("fixture", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, stdout=subprocess.PIPE)
            package(root / "apps" / "admin" / "package.json", {"react": "19.0.0"})
            facts = inspect_project(root)["project_facts"]["fact_plane"]
        discovery = facts["manifest_discovery"]
        self.assertIn("apps/admin/package.json", discovery["sources"])
        self.assertEqual(1, discovery["metrics"]["controlled_untracked_manifests"])
        self.assertEqual("bs", facts["project_architecture"]["value"])

    def test_random_untracked_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "notes").mkdir()
            for index in range(50):
                (root / "notes" / f"random-{index}.txt").write_text("react express unity", encoding="utf-8")
            package(root / "package.json", {"express": "5.0.0"})
            discovery = inspect_project(root)["project_facts"]["fact_plane"]["manifest_discovery"]
        self.assertEqual(["package.json"], discovery["sources"])
        self.assertLess(discovery["metrics"]["bytes_read"], 1024)

    def test_node_modules_never_enters_topology(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package(root / "node_modules" / "fake" / "package.json", {"react": "19.0.0"})
            package(root / "services" / "api" / "package.json", {"express": "5.0.0"})
            facts = inspect_project(root)["project_facts"]["fact_plane"]
        self.assertTrue(all("node_modules" not in path for path in facts["manifest_discovery"]["sources"]))
        self.assertEqual("backend", facts["project_architecture"]["value"])

    def test_bounded_manifest_discovery_respects_budget(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for index in range(12):
                package(root / f"app-{index}" / "package.json", {"react": "19.0.0"})
            report = discover_engineering_manifests(
                root, budget=DiscoveryBudget(max_depth=2, max_dirs=4, max_manifests=3, max_bytes=1024)
            )
        self.assertLessEqual(report["metrics"]["directories_read"], 4)
        self.assertLessEqual(report["metrics"]["manifests_read"], 3)
        self.assertLessEqual(report["metrics"]["bytes_read"], 1024)
        self.assertTrue(report["metrics"]["truncated"])
        self.assertEqual(0, report["metrics"]["full_scan_count"])

    def test_negative_intent_is_not_selected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "backend-component-implementation", architecture="backend",
                intent_atoms=[{
                    "id": "I1", "state": "NEGATED", "operation": "backend mutation",
                    "candidate_capabilities": ["backend-component-implementation"],
                }],
            ))
        self.assertFalse(result["accepted"])
        self.assertIn("NON_CURRENT_INTENT_SELECTED", {item["code"] for item in result["diagnostics"]})

    def test_historical_resolved_intent_is_not_current(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "backend-component-implementation", architecture="backend",
                intent_atoms=[{
                    "id": "I1", "state": "RESOLVED", "operation": "past backend problem",
                    "candidate_capabilities": ["backend-component-implementation"],
                }],
            ))
        self.assertFalse(result["accepted"])
        self.assertEqual(["I1"], result["route_contract"]["historical_intents"])

    def test_conditional_intent_is_deferred(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "web-component-implementation", architecture="bs", task_scope=["frontend"],
                deferred=["backend-component-implementation"],
                intent_atoms=[
                    {"id": "I1", "state": "CURRENT", "operation": "frontend fix", "capability_family": "frontend"},
                    {"id": "I2", "state": "CONDITIONAL", "operation": "backend fix", "capability_family": "backend", "dependencies": ["I1"]},
                ],
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual(["I2"], result["route_contract"]["conditional_intents"])
        self.assertEqual(["backend-component-implementation"], [item["id"] for item in result["deferred"]])

    def test_multi_intent_message_builds_intent_dag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bs_fixture(root)
            result = route(root, proposal(
                "backend-component-implementation", architecture="backend",
                intent_atoms=[
                    {"id": "I1", "state": "CURRENT", "operation": "fix login", "capability_family": "backend"},
                    {"id": "I2", "state": "CONDITIONAL", "operation": "inspect frontend", "capability_family": "frontend", "dependencies": ["I1"]},
                    {"id": "I3", "state": "NEGATED", "operation": "database mutation", "capability_family": "database"},
                    {"id": "I4", "state": "FUTURE", "operation": "test", "capability_family": "quality", "dependencies": ["I1"]},
                ],
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual(4, len(result["intent_dag"]["nodes"]))
        self.assertEqual(2, len(result["intent_dag"]["edges"]))
        self.assertEqual("DEEP", result["routing_cost"])

    def test_active_skills_never_exceed_two(self):
        with tempfile.TemporaryDirectory() as td:
            result = route(Path(td), proposal(
                "project-state-manager", "long-chain-change-convergence", "regression-test-planner",
                architecture="tooling", stage="governance",
            ))
        self.assertFalse(result["accepted"])
        self.assertEqual([], result["load"])

    def test_safe_ambiguity_proceeds_evidence_first(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package(root / "package.json", {"react": "19.0.0"})
            result = route(root, proposal(
                "web-component-implementation", architecture="bs",
                ambiguities=[{"id": "A1", "safe_common_action": "read-only evidence"}],
            ))
        self.assertTrue(result["accepted"], result["diagnostics"])
        self.assertEqual("EVIDENCE_FIRST", result["ambiguity_policy"])

    def test_dangerous_ambiguity_requires_user(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package(root / "package.json", {"express": "5.0.0"})
            result = route(root, proposal(
                "database-migration-governance", architecture="backend", task_scope=["database"],
                risk={"level": "HIGH", "reversible": False},
                ambiguities=[{"id": "A1", "data_direction": True, "irreversible": True}],
            ))
        self.assertFalse(result["accepted"])
        self.assertEqual("ASK_REQUIRED", result["ambiguity_policy"])
        self.assertIn("AMBIGUITY_REQUIRES_USER", {item["code"] for item in result["diagnostics"]})

    def test_simple_route_does_not_enter_deep_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package(root / "package.json", {"react": "19.0.0"})
            result = route(root, proposal("web-component-implementation", architecture="bs", task_scope=["frontend"]))
        self.assertEqual("FAST", result["routing_cost"])

    def test_large_project_does_not_expand_fast_route_cost(self):
        plane = {
            "project_architecture": {"value": "bs", "authority": "AUTHORITATIVE_CURRENT", "source_fingerprint": "a" * 64},
            "source_identity": {"tracked_file_count": 1_000_000},
        }
        normalized = normalize_route_contract(
            proposal("web-component-implementation", architecture="bs", task_scope=["frontend"]),
            plane,
            {"web-component-implementation"},
        )
        self.assertEqual("FAST", normalized["contract"]["routing_cost"])

    def test_candidate_is_not_applied(self):
        with tempfile.TemporaryDirectory() as td:
            result = route(Path(td), proposal("project-state-manager", architecture="tooling", stage="governance"))
        self.assertEqual(["project-state-manager"], result["route_receipt"]["candidate"])
        self.assertEqual(["project-state-manager"], result["route_receipt"]["selected"])
        self.assertEqual([], result["route_receipt"]["loaded"])
        self.assertEqual([], result["route_receipt"]["applied"])

    def test_route_receipt_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package(root / "package.json", {"express": "5.0.0"})
            first = route(root, proposal("backend-component-implementation", architecture="backend"))
            second = route(root, proposal("backend-component-implementation", architecture="backend"))
        self.assertEqual(first["route_receipt"]["fingerprint"], second["route_receipt"]["fingerprint"])
        self.assertEqual(first["route_contract"]["route_contract_fingerprint"], second["route_contract"]["route_contract_fingerprint"])

    def test_capability_prefilter_is_bounded_without_loading_skill_bodies(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); package(root / "package.json", {"express": "5.0.0"})
            result = route(root, proposal(
                "backend-component-implementation", architecture="backend",
                intent_atoms=[{"id": "I1", "state": "CURRENT", "operation": "implement", "capability_family": "backend"}],
            ))
        candidates = result["capability_prefilter"]["candidates"]
        self.assertGreaterEqual(len(candidates), 3)
        self.assertLessEqual(len(candidates), 6)
        self.assertEqual(1, len(result["load"]))


if __name__ == "__main__":
    unittest.main()
