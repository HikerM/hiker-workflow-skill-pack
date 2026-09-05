from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from component_registry import build as build_registry
from weblib import SOURCE_EXT, digest, read_json, source_inventory
CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from source_surface import TraversalLimitReached,iter_git_nul_records,is_reserved_source_path


HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
DIRECT_HTTP = re.compile(r"\b(?:axios\.(?:get|post|put|patch|delete)|fetch\s*\()")
ANY_TS = re.compile(r"(?<![A-Za-z0-9_])any(?![A-Za-z0-9_])")
IMPORTANT = re.compile(r"!important\b")
BOOTSTRAP_IMPORT = re.compile(r"(?:import\s+|from\s*|require\s*\(|@import\s+|url\s*\()[^\n]{0,120}['\"]?bootstrap", re.I)
BOOTSTRAP_CLASS = re.compile(r"(?:class|className)\s*=\s*['\"][^'\"]*\b(?:container-fluid|row|col-(?:sm|md|lg|xl|xxl)-\d+|btn-primary|card-body|navbar-expand)\b", re.I)
CARD_SIGNAL = re.compile(r"(?:<[A-Z][A-Za-z0-9]*(?:Card|Panel|Surface|Paper|Tile|Widget)\b|\bclass(?:Name)?\s*=\s*['\"][^'\"]*\bcard(?:[-_\s]|['\"]))", re.I)
CLASS_ATTRIBUTE = re.compile(r"(?:class|className)\s*=\s*['\"]([^'\"]+)['\"]", re.I)
RAW_SPACING = re.compile(r"\b(?:margin|padding|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left|inline|block))?\s*:\s*-?(?:\d+(?:\.\d+)?)(?:px|rem)\b", re.I)
DECORATIVE_EFFECT = re.compile(r"(?:linear-gradient|radial-gradient|box-shadow\s*:|backdrop-filter\s*:)", re.I)
TOKEN_USAGE = re.compile(r"(?:var\(\s*--[a-z0-9_-]+|\b(?:theme|tokens?|designTokens)\s*[.\[]|\b(?:text|bg|border|ring)-(?:primary|secondary|accent|muted|surface|canvas|danger|warning|success)\b)", re.I)
REQUIRED_COMPOSITION_FIELDS = {
    "primary_task", "composition_pattern", "focal_point", "reading_path",
    "density_zones", "signature_element", "card_usages", "non_card_alternatives",
}


def _run_git(root: Path, args: list[str]) -> list[str]:
    try:
        return [item.strip().replace("\\","/") for item in iter_git_nul_records(root,[*args,"-z","--",".",":(exclude).ai/**"],max_items=20000) if item.strip()]
    except (OSError,RuntimeError,TraversalLimitReached):
        return []


def _changed_sources(root: Path) -> list[Path]:
    changed = set(_run_git(root, ["diff", "--name-only", "--diff-filter=ACMRT", "HEAD"]))
    changed.update(_run_git(root, ["ls-files", "--others", "--exclude-standard"]))
    paths = [root / name for name in sorted(changed)]
    return [path for path in paths if path.is_file() and path.suffix.lower() in SOURCE_EXT and not is_reserved_source_path(root,path)]


def _surface_utility_count(text: str) -> int:
    count = 0
    for raw in CLASS_ATTRIBUTE.findall(text):
        tokens = set(raw.lower().split())
        has_background = any(token.startswith(("bg-", "surface-")) for token in tokens)
        has_shape = any(token.startswith("rounded") for token in tokens)
        has_boundary = any(token.startswith(("shadow", "border", "ring-")) for token in tokens)
        has_spacing = any(re.fullmatch(r"(?:p|px|py|pt|pr|pb|pl)-.+", token) for token in tokens)
        if has_background and has_spacing and (has_shape or has_boundary):
            count += 1
    return count


def _source_fingerprint(root: Path, scanned: Iterable[Path]) -> str:
    value = hashlib.sha256()
    for path in sorted(scanned):
        value.update(path.relative_to(root).as_posix().encode("utf-8"))
        value.update(digest(path).encode("ascii"))
    return value.hexdigest()


def _composition_contract(root: Path, contract_path: str | None) -> tuple[dict[str, Any], str]:
    path = Path(contract_path).resolve() if contract_path else root / ".ai" / "design" / "ui-contract.json"
    data = read_json(path, {}) or {}
    location = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    return data, location


def _visual_evidence(root: Path, evidence_path: str | None, fingerprint: str, mode: str) -> tuple[list[str], dict[str, Any]]:
    if mode == "quick":
        return [], {"required": False, "status": "NOT_REQUIRED_IN_QUICK_MODE"}
    path = Path(evidence_path).resolve() if evidence_path else root / ".ai" / "quality" / "web-visual-evidence.json"
    data = read_json(path, {}) or {}
    blockers: list[str] = []
    if not data:
        blockers.append("missing current visual evidence")
    elif data.get("source_fingerprint") != fingerprint:
        blockers.append("visual evidence source fingerprint is stale")
    screenshots = data.get("screenshots") if isinstance(data.get("screenshots"), list) else []
    required_count = 4 if mode == "release" else 2
    valid = 0
    for item in screenshots:
        raw = item.get("path") if isinstance(item, dict) else item
        if not raw:
            continue
        target = Path(str(raw))
        if not target.is_absolute():
            target = root / target
        if target.is_file() and target.stat().st_size > 0:
            valid += 1
    if data and valid < required_count:
        blockers.append(f"visual evidence requires {required_count} existing screenshots; found {valid}")
    states = {str(value).lower() for value in data.get("states", [])} if isinstance(data.get("states"), list) else set()
    if data and "default" not in states:
        blockers.append("visual evidence does not include the default state")
    location = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    return blockers, {
        "required": True, "status": "PASS" if not blockers else "BLOCKED", "path": location,
        "valid_screenshot_count": valid, "states": sorted(states),
    }


def audit(
    root: Path,
    scope: str = "full",
    mode: str = "quick",
    contract_path: str | None = None,
    evidence_path: str | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    inventory_truncated = False
    if scope == "full":
        all_sources, inventory_truncated = source_inventory(root)
        scanned = all_sources
        actual_scope = "full"
    else:
        scanned = _changed_sources(root)
        all_sources = scanned
        actual_scope = "changed" if scanned else "none"
    token_files = sorted(
        path.relative_to(root).as_posix() for path in all_sources
        if any(token in path.relative_to(root).as_posix().lower() for token in ("token", "theme", "variable", "design-system", "design_system"))
    )
    token_usage_files: set[str] = set()
    surface_files: dict[str, int] = {}
    bootstrap_files: set[str] = set()
    for path in scanned:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.count("\n") + 1
        lower = rel.lower()
        if TOKEN_USAGE.search(text) and rel not in token_files:
            token_usage_files.add(rel)
        if lines > 500:
            findings.append({"severity": "HIGH", "rule": "large-file", "path": rel, "detail": f"{lines} lines"})
            counts["large_file"] += 1
        elif lines > 300:
            findings.append({"severity": "MEDIUM", "rule": "large-file", "path": rel, "detail": f"{lines} lines"})
            counts["large_file"] += 1
        if any(token in lower for token in ("/pages/", "/views/", "page.", "view.")) and DIRECT_HTTP.search(text):
            findings.append({"severity": "HIGH", "rule": "direct-http-in-page", "path": rel, "detail": "页面/视图中发现直接HTTP调用"})
            counts["direct_http"] += 1
        if path.suffix.lower() in {".ts", ".tsx", ".vue"}:
            any_count = len(ANY_TS.findall(text))
            if any_count > 5:
                findings.append({"severity": "MEDIUM", "rule": "excessive-any", "path": rel, "detail": f"any occurrences: {any_count}"})
                counts["any"] += any_count
        if not any(token in lower for token in ("token", "theme", "variable", "config")):
            color_count = len(HEX.findall(text))
            if color_count > 3:
                findings.append({"severity": "MEDIUM", "rule": "hardcoded-color", "path": rel, "detail": f"hex colors: {color_count}"})
                counts["hardcoded_color"] += color_count
        important_count = len(IMPORTANT.findall(text))
        if important_count > 2:
            findings.append({"severity": "LOW", "rule": "important-overuse", "path": rel, "detail": f"!important: {important_count}"})
            counts["important"] += important_count
        bootstrap_signal = bool(BOOTSTRAP_IMPORT.search(text) or BOOTSTRAP_CLASS.search(text))
        if bootstrap_signal:
            bootstrap_files.add(rel)
            findings.append({"severity": "MEDIUM", "rule": "bootstrap-style-review", "path": rel, "detail": "发现 Bootstrap 依赖或典型默认类；需核验项目 Token、构图和组件适配"})
            counts["bootstrap_style"] += 1
        named_surfaces = len(CARD_SIGNAL.findall(text))
        utility_surfaces = _surface_utility_count(text)
        surface_count = max(named_surfaces, utility_surfaces)
        if surface_count:
            surface_files[rel] = surface_count
            counts["card_like_surface"] += surface_count
        if not any(token in lower for token in ("token", "theme", "variable", "config")):
            spacing_count = len(RAW_SPACING.findall(text))
            if spacing_count > 5:
                findings.append({"severity": "MEDIUM", "rule": "hardcoded-spacing", "path": rel, "detail": f"raw spacing values: {spacing_count}"})
                counts["hardcoded_spacing"] += spacing_count
        effect_count = len(DECORATIVE_EFFECT.findall(text))
        if effect_count > 6:
            findings.append({"severity": "LOW", "rule": "decorative-effect-review", "path": rel, "detail": f"gradient/shadow/backdrop occurrences: {effect_count}; 需核验是否服务层级与交互"})
            counts["decorative_effect"] += effect_count

    contract, contract_location = _composition_contract(root, contract_path)
    missing_contract_fields = sorted(REQUIRED_COMPOSITION_FIELDS - set(contract))
    contract_card_usages = contract.get("card_usages") if isinstance(contract.get("card_usages"), list) else []
    total_surfaces = sum(surface_files.values())
    repeated_surface = total_surfaces >= 4 or any(value >= 3 for value in surface_files.values())
    if repeated_surface and not contract_card_usages:
        findings.append({
            "severity": "HIGH", "rule": "unjustified-card-layout", "path": ", ".join(sorted(surface_files)),
            "detail": f"检测到 {total_surfaces} 个卡片式表面，但构图契约没有卡片语义与非卡片替代证据",
        })
    elif repeated_surface:
        findings.append({
            "severity": "MEDIUM", "rule": "card-layout-visual-review", "path": ", ".join(sorted(surface_files)),
            "detail": f"检测到 {total_surfaces} 个卡片式表面；需用实际截图执行移除表面测试",
        })
    if mode in {"review", "release"} and missing_contract_fields:
        findings.append({
            "severity": "HIGH", "rule": "composition-contract-incomplete", "path": contract_location,
            "detail": "missing: " + ", ".join(missing_contract_fields),
        })
    if token_files and not token_usage_files:
        findings.append({"severity": "HIGH" if mode != "quick" else "MEDIUM", "rule": "declared-token-system-unused", "path": ", ".join(token_files), "detail": "发现 Token/Theme 文件，但扫描范围内没有可观察的语义 Token 消费"})
    elif mode in {"review", "release"} and not token_files:
        findings.append({"severity": "HIGH", "rule": "design-token-system-missing", "path": actual_scope, "detail": "新增或重做界面缺少可定位的设计 Token 文件"})

    registry = build_registry(root, scanned)
    for name, paths in registry["duplicate_names"].items():
        findings.append({"severity": "MEDIUM", "rule": "duplicate-component-name", "path": ", ".join(paths), "detail": name})
    fingerprint = _source_fingerprint(root, scanned)
    blockers, visual = _visual_evidence(root, evidence_path, fingerprint, mode)
    if inventory_truncated:
        blockers.append("source inventory exceeded 5000 files; split the audit by module")
    finding_count = len(findings)
    if finding_count > 200:
        findings = findings[:199] + [{"severity": "MEDIUM", "rule": "findings-truncated", "path": actual_scope, "detail": f"{finding_count - 199} additional findings kept out of conversation output"}]
    blocking = any(item["severity"] == "HIGH" for item in findings)
    result = "BLOCKED" if blockers else "FAIL" if blocking else "PASS_WITH_WARNINGS" if findings else "PASS"
    return {
        "schema_version": "2.0.0", "result": result, "mode": mode, "scope": actual_scope,
        "source_fingerprint": fingerprint, "summary": dict(counts), "findings": findings, "blockers": blockers,
        "design_system_evidence": {
            "token_files": token_files, "token_usage_files": sorted(token_usage_files),
            "status": "USED" if token_usage_files else "DECLARED_UNUSED" if token_files else "MISSING",
        },
        "composition_contract": {
            "path": contract_location, "missing_fields": missing_contract_fields,
            "card_usage_count": len(contract_card_usages),
        },
        "visual_evidence": visual, "component_count": len(registry["components"]), "finding_count": finding_count,
        "inventory_truncated": inventory_truncated,
        "duplicate_component_names": dict(list(registry["duplicate_names"].items())[:100]), "bootstrap_files": sorted(bootstrap_files)[:200],
        "surface_files": surface_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default=".ai/quality/web-audit.json")
    parser.add_argument("--scope", choices=["auto", "changed", "full"], default="auto")
    parser.add_argument("--mode", choices=["quick", "review", "release"], default="quick")
    parser.add_argument("--contract")
    parser.add_argument("--visual-evidence")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    data = audit(root, args.scope, args.mode, args.contract, args.visual_evidence)
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 2 if data["result"] in {"FAIL", "BLOCKED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
