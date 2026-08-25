from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PROFILE_FIELDS = {"id", "plugin", "rules", "script", "arguments", "test", "positive_case", "negative_case", "dimensions"}
REQUIRED_POLICY = {
    "on_demand_only": True,
    "default_prompt": False,
    "writes_state_by_default": False,
    "external_model_api": False,
}


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def audit(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve(); profile_path = root / "docs" / "specialization-maturity-profiles.json"
    data = load(profile_path); errors: list[dict[str, str]] = []

    def error(code: str, profile: str, message: str, path: str = "docs/specialization-maturity-profiles.json") -> None:
        errors.append({"code": code, "profile": profile, "message": message, "path": path})

    if data.get("schema_version") != "1.0.0":
        error("PROFILE_SCHEMA", "suite", "missing or unsupported profile schema")
    template = str(data.get("template") or "")
    if not template or not (root / template).is_file():
        error("MISSING_MATURITY_TEMPLATE", "suite", template or "template is empty", template or profile_path.relative_to(root).as_posix())
    policy = data.get("policy") or {}
    for key, expected in REQUIRED_POLICY.items():
        if policy.get(key) is not expected:
            error("UNSAFE_PROFILE_POLICY", "suite", f"{key} must be {expected!r}")
    minimum = int(policy.get("min_dimensions") or 6)
    profiles = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    ids: set[str] = set()
    plugins = {path.name for path in (root / "plugins").iterdir() if path.is_dir()}
    for profile in profiles:
        if not isinstance(profile, dict):
            error("INVALID_PROFILE", "unknown", "profile entry must be an object"); continue
        profile_id = str(profile.get("id") or "unknown")
        missing = sorted(REQUIRED_PROFILE_FIELDS - set(profile))
        if missing:
            error("INCOMPLETE_PROFILE", profile_id, f"missing fields: {missing}"); continue
        if profile_id in ids:
            error("DUPLICATE_PROFILE", profile_id, "profile id must be unique")
        ids.add(profile_id)
        if profile.get("plugin") not in plugins:
            error("UNKNOWN_PROFILE_PLUGIN", profile_id, str(profile.get("plugin")))
        dimensions = profile.get("dimensions") if isinstance(profile.get("dimensions"), list) else []
        if len(set(str(item) for item in dimensions)) < minimum:
            error("SHALLOW_PROFILE", profile_id, f"requires at least {minimum} unique dimensions")
        for field in ("rules", "script", "test"):
            relative = str(profile.get(field) or "")
            if not relative or not (root / relative).is_file():
                error("MISSING_PROFILE_ASSET", profile_id, f"missing {field}: {relative}", relative or profile_path.relative_to(root).as_posix())
        test_path = root / str(profile.get("test") or "")
        test_text = test_path.read_text(encoding="utf-8", errors="ignore") if test_path.is_file() else ""
        for field in ("positive_case", "negative_case"):
            case_name = str(profile.get(field) or "")
            if not case_name or f"def {case_name}(" not in test_text:
                error("MISSING_PROFILE_CASE", profile_id, f"{field} not found: {case_name}", str(profile.get("test") or ""))
    required = {"laravel-php", "node-typescript", "unity", "qt"}
    if ids != required:
        error("REPRESENTATIVE_PROFILE_DRIFT", "suite", f"missing={sorted(required-ids)}, extra={sorted(ids-required)}")
    return {
        "ok": not errors, "schema_version": "1.0.0", "profile_count": len(profiles),
        "profiles": sorted(ids), "minimum_dimensions": minimum,
        "default_path_impact": {"scripts": 0, "state_writes": 0, "prompt_bytes": 0},
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate evidence maturity for on-demand engineering specializations")
    parser.add_argument("--root", default=str(ROOT)); args = parser.parse_args(); result = audit(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
