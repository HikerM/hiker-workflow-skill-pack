from __future__ import annotations

import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SUITE = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from capability_metadata import capability_families, load_registry, routable_plugin_map  # noqa: E402
from control_common import capability_indexes, load_capability_registry  # noqa: E402
from suite_router import PLUGIN_FOR  # noqa: E402


class CapabilityAuthorityTests(unittest.TestCase):
    def test_capability_metadata_has_one_authoritative_source(self):
        paths = sorted(SUITE.rglob("SKILL_REGISTRY.json"))
        self.assertEqual([PLUGIN / "references" / "SKILL_REGISTRY.json"], paths)
        self.assertFalse((PLUGIN / "references" / "capability-registry.json").exists())
        registry = load_registry()
        self.assertEqual("SINGLE_CAPABILITY_METADATA_AUTHORITY", registry["authority"])
        self.assertEqual(42, len(registry["skills"]))

    def test_router_and_control_indexes_are_registry_projections(self):
        registry = load_capability_registry()
        skills, focuses = capability_indexes(registry)
        self.assertEqual(set(registry["skills"]), set(skills))
        self.assertEqual(routable_plugin_map(), PLUGIN_FOR)
        self.assertEqual(41, len(PLUGIN_FOR))
        for focus_id, focus in focuses.items():
            expected = {
                skill
                for skill, metadata in registry["skills"].items()
                if focus_id in metadata.get("specializations", [])
            }
            self.assertEqual(expected, set(focus["skills"]))

    def test_family_index_is_derived_without_static_router_maps(self):
        registry = load_registry()
        expected: dict[str, list[str]] = {}
        for skill, metadata in registry["skills"].items():
            if not metadata.get("routable", True):
                continue
            for family in metadata.get("families", []):
                expected.setdefault(family, []).append(skill)
        self.assertEqual(
            {family: tuple(skills) for family, skills in expected.items()},
            capability_families(),
        )
        router = (PLUGIN / "scripts" / "suite_router.py").read_text(encoding="utf-8")
        contract = (PLUGIN / "scripts" / "route_contract.py").read_text(encoding="utf-8")
        for duplicate in (
            "PLUGIN_FOR = {",
            "DESIGN_SKILLS =",
            "IMPLEMENTATION_SKILLS =",
            "WEB_SKILLS =",
            "BACKEND_SKILLS =",
            "CLIENT_SKILLS =",
            "SOURCE_CONFLICT_SAFE =",
            "AI_STATE_DEPENDENT_SKILLS =",
            "VERSION_RECOVERY_SKILLS =",
        ):
            self.assertNotIn(duplicate, router)
        self.assertNotIn("CAPABILITY_FAMILIES: dict", contract)


if __name__ == "__main__":
    unittest.main()
