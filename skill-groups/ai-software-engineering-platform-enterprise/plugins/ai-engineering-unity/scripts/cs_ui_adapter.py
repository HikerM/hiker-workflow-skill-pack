from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


EXTENSIONS = {".qml", ".ui", ".xaml", ".cs", ".dart", ".uxml"}
MAX_FILES = 500
STATE = re.compile(r"\b(?:loading|busy|empty|error|disabled|selected|expanded|visible|hidden|offline)\b", re.I)


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _component_name(path: Path, text: str) -> str:
    patterns = (r"\bclass\s+([A-Z][A-Za-z0-9_]*)", r"x:Class=['\"]([^'\"]+)", r"<class>([^<]+)</class>")
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).split(".")[-1]
    return path.stem


def _technology(root: Path, paths: list[Path]) -> dict[str, Any]:
    facts: list[tuple[str, Path]] = []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in {".qml", ".ui"}:
            facts.append(("qt", path))
        elif suffix == ".xaml":
            facts.append(("dotnet-desktop", path))
        elif suffix == ".dart":
            facts.append(("flutter", path))
        elif suffix == ".uxml":
            facts.append(("unity-ui-toolkit", path))
        elif suffix == ".cs" and any((parent / "ProjectSettings" / "ProjectVersion.txt").is_file() for parent in [path.parent, *path.parents] if parent == root or root in parent.parents):
            facts.append(("unity", path))
    if not facts:
        return {"status": "UNKNOWN", "value": None, "source_refs": []}
    families = sorted({item[0] for item in facts})
    refs = sorted({item[1].relative_to(root).as_posix() for item in facts})[:16]
    return {"status": "OBSERVED", "value": {"families": families}, "source_refs": refs}


def _changed(root: Path) -> list[Path]:
    process = subprocess.run(["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"], cwd=root, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [root / row.strip() for row in process.stdout.splitlines() if row.strip() and ".." not in Path(row.strip()).parts]


def _explicit(root: Path, requested: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in requested:
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts:
            continue
        paths.append(root / relative)
    return paths


def observe(root: Path, requested: list[str], changed: bool = False) -> dict[str, Any]:
    candidates = _changed(root) if changed else _explicit(root, requested)
    paths = [path for path in candidates if path.is_file() and path.suffix.lower() in EXTENSIONS][:MAX_FILES]
    technology = _technology(root, paths)
    components = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")[:200_000]
        rel = path.relative_to(root).as_posix()
        name = _component_name(path, text)
        component = {
            "component_id": f"cs:{rel}#{name}",
            "semantic_role": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "design_component": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "code_component": {"status": "OBSERVED", "value": {"path": rel, "symbol": name, "source_fingerprint": _fingerprint(path)}, "source_refs": [rel]},
            "variants": [],
            "states": sorted(set(match.lower() for match in STATE.findall(text)))[:64],
            "tokens": [],
            "accessibility": [item for item, pattern in (("automation-name", r"AutomationProperties\.Name"), ("accessible-name", r"accessibleName|Accessible\.name")) if re.search(pattern, text, re.I)],
            "platform": "CS",
            "usage_rules": [],
            "technology_adapter": technology,
            "implementation_layer": "project_native",
        }
        payload = {key: value for key, value in component.items() if key != "fingerprint"}
        component["fingerprint"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        components.append(component)
    refs = [path.relative_to(root).as_posix() for path in paths]
    return {
        "schema_version": "1.0.0",
        "architecture": "CS",
        "scope": {"mode": "AFFECTED" if changed else "EXPLICIT", "refs": refs},
        "technology": technology,
        "components": components,
        "bounded": {"max_files": MAX_FILES, "scanned_files": len(paths), "truncated": len(candidates) > MAX_FILES},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded C/S UI observation adapter")
    parser.add_argument("--root", default=".")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    if not args.path and not args.changed:
        raise SystemExit("explicit --path or --changed scope is required")
    root = Path(args.root).resolve()
    result = observe(root, args.path, args.changed)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = (root / args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
