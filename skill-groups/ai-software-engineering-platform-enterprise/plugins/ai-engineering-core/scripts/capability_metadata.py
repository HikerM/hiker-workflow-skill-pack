from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "references" / "SKILL_REGISTRY.json"
MODE_STAGES = {
    "planning": ("planning", "design", "review"),
    "design": ("design",),
    "implementation": ("development",),
    "review": ("review", "testing", "release"),
}


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if data.get("authority") != "SINGLE_CAPABILITY_METADATA_AUTHORITY":
        raise RuntimeError("capability metadata authority is invalid")
    skills = data.get("skills")
    if not isinstance(skills, dict) or not skills:
        raise RuntimeError("capability metadata does not define skills")
    for skill, metadata in skills.items():
        if not isinstance(metadata, dict):
            raise RuntimeError(f"capability metadata is invalid: {skill}")
        for field in ("plugin", "mode", "capability", "domain"):
            if not str(metadata.get(field) or "").strip():
                raise RuntimeError(f"capability metadata is missing {field}: {skill}")
        for field in ("families", "stages", "surfaces", "specializations"):
            if field in metadata and not isinstance(metadata.get(field), list):
                raise RuntimeError(f"capability metadata is missing {field}: {skill}")
    return data


def skill_records() -> dict[str, dict[str, Any]]:
    return load_registry()["skills"]


def metadata_for(skill: str) -> dict[str, Any]:
    return skill_records().get(skill, {})


@lru_cache(maxsize=1)
def routable_plugin_map() -> dict[str, str]:
    return {
        skill: str(metadata["plugin"])
        for skill, metadata in skill_records().items()
        if bool(metadata.get("routable", True))
    }


@lru_cache(maxsize=1)
def capability_families() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for skill, metadata in skill_records().items():
        if not bool(metadata.get("routable", True)):
            continue
        for family in metadata.get("families", []):
            result.setdefault(str(family), []).append(skill)
    return {family: tuple(skills) for family, skills in result.items()}


def supports_stage(skill: str, stage: str) -> bool:
    metadata = metadata_for(skill)
    stages = tuple(metadata.get("stages") or MODE_STAGES.get(str(metadata.get("mode")), ("*",)))
    return "*" in stages or stage in stages


def supports_surface(skill: str, surface: str) -> bool:
    surfaces = tuple(metadata_for(skill).get("surfaces") or ("*",))
    return "*" in surfaces or surface in surfaces


def policy_enabled(skill: str, policy: str) -> bool:
    return bool(metadata_for(skill).get(policy))
