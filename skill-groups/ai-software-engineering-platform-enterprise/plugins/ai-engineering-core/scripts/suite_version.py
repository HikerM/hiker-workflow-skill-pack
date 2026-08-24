from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PLUGIN_NAMES = (
    "ai-engineering-core",
    "ai-engineering-quality",
    "ai-engineering-unity",
    "ai-engineering-web",
    "ai-engineering-workspace",
)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def layout() -> dict[str, Any]:
    current = Path(__file__).resolve().parents[1]
    if current.name == "ai-engineering-core" and (current / ".codex-plugin" / "plugin.json").is_file():
        manifest = _read_manifest(current / ".codex-plugin" / "plugin.json")
        return {"mode": "source", "plugins_root": current.parent, "version": str(manifest.get("version") or "")}
    if current.parent.name == "ai-engineering-core" and (current / ".codex-plugin" / "plugin.json").is_file():
        manifest = _read_manifest(current / ".codex-plugin" / "plugin.json")
        return {
            "mode": "cache",
            "marketplace_root": current.parent.parent,
            "version_dir": current.name,
            "version": str(manifest.get("version") or ""),
        }
    return {"mode": "unknown", "version": ""}


def plugin_root(plugin: str) -> Path:
    info = layout()
    if info["mode"] == "source":
        return Path(info["plugins_root"]) / plugin
    if info["mode"] == "cache":
        return Path(info["marketplace_root"]) / plugin / str(info["version_dir"])
    return Path(__file__).resolve().parents[1]


def skill_path(plugin: str, skill: str) -> Path:
    return plugin_root(plugin) / "skills" / skill / "SKILL.md"


def inspect_suite() -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    missing: list[str] = []
    for plugin in PLUGIN_NAMES:
        root = plugin_root(plugin)
        manifest = _read_manifest(root / ".codex-plugin" / "plugin.json")
        version = str(manifest.get("version") or "").strip() or None
        if manifest.get("name") != plugin or not version:
            missing.append(plugin)
        versions[plugin] = version
    distinct = sorted({value for value in versions.values() if value})
    consistent = not missing and len(distinct) == 1
    basis = {"versions": versions, "mode": layout().get("mode")}
    fingerprint = hashlib.sha256(json.dumps(basis, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "schema_version": "1.0.0",
        "consistent": consistent,
        "version": distinct[0] if consistent else None,
        "fingerprint": fingerprint,
        "versions": versions,
        "missing": missing,
        "layout": layout().get("mode"),
        "policy": "五个插件必须来自同一完整版本；旧会话版本漂移时只允许Checkpoint与接管",
    }


if __name__ == "__main__":
    print(json.dumps(inspect_suite(), ensure_ascii=False, indent=2))
