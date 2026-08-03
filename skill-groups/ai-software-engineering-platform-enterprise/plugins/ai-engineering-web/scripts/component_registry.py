from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from weblib import digest, read_json, source_files

COMPONENT_EXT = {".vue", ".tsx", ".jsx", ".svelte"}


def component_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")[:20000]
    for pattern in [r"defineOptions\s*\(\s*\{[^}]*name\s*:\s*['\"]([^'\"]+)", r"(?:function|class)\s+([A-Z][A-Za-z0-9_]*)", r"const\s+([A-Z][A-Za-z0-9_]*)\s*="]:
        m = re.search(pattern, text, re.S)
        if m: return m.group(1)
    return path.stem


def build(root: Path) -> dict:
    components = []
    for path in source_files(root):
        if path.suffix.lower() not in COMPONENT_EXT: continue
        rel = path.relative_to(root).as_posix()
        if not any(token in rel.lower() for token in ("component", "views", "pages", "app")): continue
        components.append({"name": component_name(path), "path": rel, "sha256": digest(path), "lines": path.read_text(encoding="utf-8", errors="ignore").count("\n") + 1})
    by_name = {}
    for c in components: by_name.setdefault(c["name"].lower(), []).append(c["path"])
    duplicates = {k: v for k, v in by_name.items() if len(v) > 1}
    return {"schema_version": "1.0.0", "components": sorted(components, key=lambda x: x["path"]), "duplicate_names": duplicates}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--output", default=".ai/context/components-web.json"); args = ap.parse_args(); root = Path(args.root).resolve(); data = build(root); out = root / args.output; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"output": str(out), "count": len(data["components"]), "duplicates": len(data["duplicate_names"])}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
