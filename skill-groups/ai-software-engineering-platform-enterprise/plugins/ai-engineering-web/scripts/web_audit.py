from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from component_registry import build as build_registry
from weblib import source_files

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
DIRECT_HTTP = re.compile(r"\b(?:axios\.(?:get|post|put|patch|delete)|fetch\s*\()")
ANY_TS = re.compile(r"(?<![A-Za-z0-9_])any(?![A-Za-z0-9_])")
IMPORTANT = re.compile(r"!important\b")
BOOTSTRAP_IMPORT = re.compile(r"(?:import\s+|from\s*|require\s*\(|@import\s+|url\s*\()[^\n]{0,120}['\"]?bootstrap", re.I)
BOOTSTRAP_CLASS = re.compile(r"(?:class|className)\s*=\s*['\"][^'\"]*\b(?:container-fluid|row|col-(?:sm|md|lg|xl|xxl)-\d+|btn-primary|card-body|navbar-expand)\b", re.I)
CARD_SIGNAL = re.compile(r"(?:<[A-Z][A-Za-z0-9]*Card\b|\bclass(?:Name)?\s*=\s*['\"][^'\"]*\bcard(?:[-_\s]|['\"]))", re.I)
RAW_SPACING = re.compile(r"\b(?:margin|padding|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left|inline|block))?\s*:\s*-?(?:\d+(?:\.\d+)?)(?:px|rem)\b", re.I)
DECORATIVE_EFFECT = re.compile(r"(?:linear-gradient|radial-gradient|box-shadow\s*:|backdrop-filter\s*:)", re.I)


def audit(root: Path) -> dict:
    findings = []
    counts = Counter()
    scanned = list(source_files(root))
    token_files = sorted(path.relative_to(root).as_posix() for path in scanned if any(x in path.relative_to(root).as_posix().lower() for x in ("token", "theme", "variable", "design-system", "design_system")))
    for path in scanned:
        rel = path.relative_to(root).as_posix(); text = path.read_text(encoding="utf-8", errors="ignore"); lines = text.count("\n") + 1
        lower = rel.lower()
        if lines > 500: findings.append({"severity":"HIGH","rule":"large-file","path":rel,"detail":f"{lines} lines"}); counts["large_file"] += 1
        elif lines > 300: findings.append({"severity":"MEDIUM","rule":"large-file","path":rel,"detail":f"{lines} lines"}); counts["large_file"] += 1
        if any(x in lower for x in ("/pages/", "/views/", "page.", "view.")) and DIRECT_HTTP.search(text):
            findings.append({"severity":"HIGH","rule":"direct-http-in-page","path":rel,"detail":"页面/视图中发现直接HTTP调用"}); counts["direct_http"] += 1
        if path.suffix.lower() in {".ts", ".tsx", ".vue"}:
            n = len(ANY_TS.findall(text));
            if n > 5: findings.append({"severity":"MEDIUM","rule":"excessive-any","path":rel,"detail":f"any occurrences: {n}"}); counts["any"] += n
        if not any(x in lower for x in ("token", "theme", "variable", "config")):
            n = len(HEX.findall(text));
            if n > 3: findings.append({"severity":"MEDIUM","rule":"hardcoded-color","path":rel,"detail":f"hex colors: {n}"}); counts["hardcoded_color"] += n
        n = len(IMPORTANT.findall(text));
        if n > 2: findings.append({"severity":"LOW","rule":"important-overuse","path":rel,"detail":f"!important: {n}"}); counts["important"] += n
        bootstrap_signal = bool(BOOTSTRAP_IMPORT.search(text) or BOOTSTRAP_CLASS.search(text))
        if bootstrap_signal:
            findings.append({"severity":"MEDIUM","rule":"bootstrap-style-review","path":rel,"detail":"发现 Bootstrap 依赖或典型默认类；需人工核验是否通过项目 Token/组件层形成独立视觉语言"}); counts["bootstrap_style"] += 1
        n = len(CARD_SIGNAL.findall(text))
        if n >= 6:
            severity = "HIGH" if bootstrap_signal or not token_files else "MEDIUM"
            findings.append({"severity":severity,"rule":"repetitive-card-signal","path":rel,"detail":f"card-like occurrences: {n}; 与默认框架视觉或缺少 Design Token 同时出现时阻断，避免卡片汤"}); counts["card_signal"] += n
        if not any(x in lower for x in ("token", "theme", "variable", "config")):
            n = len(RAW_SPACING.findall(text))
            if n > 5: findings.append({"severity":"MEDIUM","rule":"hardcoded-spacing","path":rel,"detail":f"raw spacing values: {n}"}); counts["hardcoded_spacing"] += n
        n = len(DECORATIVE_EFFECT.findall(text))
        if n > 6:
            findings.append({"severity":"LOW","rule":"decorative-effect-review","path":rel,"detail":f"gradient/shadow/backdrop occurrences: {n}; 需核验是否服务层级与交互"}); counts["decorative_effect"] += n
    registry = build_registry(root)
    for name, paths in registry["duplicate_names"].items(): findings.append({"severity":"MEDIUM","rule":"duplicate-component-name","path":", ".join(paths),"detail":name})
    blocking = any(f["severity"] == "HIGH" for f in findings)
    return {"schema_version":"1.1.0","result":"FAIL" if blocking else ("PASS_WITH_WARNINGS" if findings else "PASS"),"summary":dict(counts),"findings":findings,"design_system_evidence":{"token_files":sorted(token_files),"requires_visual_review":True},"component_count":len(registry["components"]),"duplicate_component_names":registry["duplicate_names"]}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--output", default=".ai/quality/web-audit.json"); args = ap.parse_args(); root = Path(args.root).resolve(); data = audit(root); out = root / args.output; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"); print(json.dumps(data, ensure_ascii=False, indent=2)); return 1 if data["result"] == "FAIL" else 0
if __name__ == "__main__": raise SystemExit(main())
