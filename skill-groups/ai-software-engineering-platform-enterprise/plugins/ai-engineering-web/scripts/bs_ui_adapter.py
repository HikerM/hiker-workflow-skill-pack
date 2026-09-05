from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from source_surface import TraversalLimitReached,iter_git_nul_records,is_reserved_source_path,read_bounded_text


EXTENSIONS = {".vue", ".tsx", ".jsx", ".svelte", ".html"}
MAX_FILES = 500
TOKEN = re.compile(r"(?:var\(\s*--[a-z0-9_-]+|\b(?:theme|tokens?|designTokens)\s*[.\[]|\b(?:text|bg|border)-(?:primary|secondary|accent|muted|danger|warning|success)\b)", re.I)
STATE = re.compile(r"\b(?:loading|pending|empty|error|disabled|selected|expanded|open|closed)\b", re.I)


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _component_name(path: Path, text: str) -> str:
    for pattern in (r"(?:function|class)\s+([A-Z][A-Za-z0-9_]*)", r"const\s+([A-Z][A-Za-z0-9_]*)\s*=", r"name\s*:\s*['\"]([^'\"]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return path.stem


def _technology(root: Path, paths: list[Path]) -> dict[str, Any]:
    manifests: list[Path] = []
    for path in paths:
        current = path.parent
        while current == root or root in current.parents:
            manifest = current / "package.json"
            if manifest.is_file():
                manifests.append(manifest)
                break
            if current == root:
                break
            current = current.parent
    for manifest in sorted(set(manifests)):
        try:
            raw,truncated=read_bounded_text(manifest,8*1024*1024);data = {} if truncated else json.loads(raw)
        except Exception:
            continue
        dependencies = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        matches = [name for name in ("react", "vue", "@angular/core", "svelte") if name in dependencies]
        if matches:
            return {"status": "OBSERVED", "value": {"family": matches[0], "version": str(dependencies[matches[0]])}, "source_refs": [manifest.relative_to(root).as_posix()]}
    return {"status": "UNKNOWN", "value": None, "source_refs": []}


def _changed(root: Path) -> list[Path]:
    try:rows=list(iter_git_nul_records(root,["diff","--name-only","-z","--diff-filter=ACMR","HEAD","--",".",":(exclude).ai/**"],max_items=MAX_FILES+1))
    except (RuntimeError,TraversalLimitReached):return []
    return [root/row for row in rows if row and ".." not in Path(row).parts]


def _explicit(root: Path, requested: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in requested:
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts:
            continue
        candidate=root/relative
        if not is_reserved_source_path(root,candidate):paths.append(candidate)
    return paths


def observe(root: Path, requested: list[str], changed: bool = False) -> dict[str, Any]:
    candidates = _changed(root) if changed else _explicit(root, requested)
    paths = [path for path in candidates if path.is_file() and path.suffix.lower() in EXTENSIONS][:MAX_FILES]
    technology = _technology(root, paths)
    components = []
    for path in paths:
        text = read_bounded_text(path,200_000)[0]
        rel = path.relative_to(root).as_posix()
        name = _component_name(path, text)
        code_fingerprint = _fingerprint(path)
        component = {
            "component_id": f"bs:{rel}#{name}",
            "semantic_role": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "design_component": {"status": "UNKNOWN", "value": None, "source_refs": []},
            "code_component": {"status": "OBSERVED", "value": {"path": rel, "symbol": name, "source_fingerprint": code_fingerprint}, "source_refs": [rel]},
            "variants": [],
            "states": sorted(set(match.lower() for match in STATE.findall(text)))[:64],
            "tokens": sorted(set(match.lower() for match in TOKEN.findall(text)))[:64],
            "accessibility": [item for item, pattern in (("aria", r"\baria-[a-z-]+"), ("semantic-html", r"<(?:button|nav|main|header|footer|label)\b")) if re.search(pattern, text, re.I)],
            "platform": "BS",
            "usage_rules": [],
            "technology_adapter": technology,
            "implementation_layer": "project_native",
        }
        from_payload = {key: value for key, value in component.items() if key != "fingerprint"}
        component["fingerprint"] = hashlib.sha256(json.dumps(from_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        components.append(component)
    refs = [path.relative_to(root).as_posix() for path in paths]
    return {
        "schema_version": "1.0.0",
        "architecture": "BS",
        "scope": {"mode": "AFFECTED" if changed else "EXPLICIT", "refs": refs},
        "technology": technology,
        "components": components,
        "bounded": {"max_files": MAX_FILES, "scanned_files": len(paths), "truncated": len(candidates) > MAX_FILES},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded B/S UI observation adapter")
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
