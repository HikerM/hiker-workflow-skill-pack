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


def audit(root: Path) -> dict:
    findings = []
    counts = Counter()
    for path in source_files(root):
        rel = path.relative_to(root).as_posix(); text = path.read_text(encoding="utf-8", errors="ignore"); lines = text.count("\n") + 1
        if lines > 500: findings.append({"severity":"HIGH","rule":"large-file","path":rel,"detail":f"{lines} lines"}); counts["large_file"] += 1
        elif lines > 300: findings.append({"severity":"MEDIUM","rule":"large-file","path":rel,"detail":f"{lines} lines"}); counts["large_file"] += 1
        lower = rel.lower()
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
    registry = build_registry(root)
    for name, paths in registry["duplicate_names"].items(): findings.append({"severity":"MEDIUM","rule":"duplicate-component-name","path":", ".join(paths),"detail":name})
    blocking = any(f["severity"] == "HIGH" for f in findings)
    return {"schema_version":"1.0.0","result":"FAIL" if blocking else ("PASS_WITH_WARNINGS" if findings else "PASS"),"summary":dict(counts),"findings":findings,"component_count":len(registry["components"]),"duplicate_component_names":registry["duplicate_names"]}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--output", default=".ai/quality/web-audit.json"); args = ap.parse_args(); root = Path(args.root).resolve(); data = audit(root); out = root / args.output; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"); print(json.dumps(data, ensure_ascii=False, indent=2)); return 1 if data["result"] == "FAIL" else 0
if __name__ == "__main__": raise SystemExit(main())
