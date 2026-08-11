from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FAMILY_MARKERS = [
    ("unity", {"unity"}),
    ("qt", {"qt", "pyqt", "pyside"}),
    ("dotnet-desktop", {"wpf", "winui", "winforms", "avalonia", ".net maui", "maui"}),
    ("electron-tauri", {"electron", "tauri"}),
    ("flutter", {"flutter"}),
    ("android", {"android", "jetpack compose"}),
    ("apple-native", {"swiftui", "uikit", "appkit"}),
    ("react-native", {"react native", "react-native"}),
    ("java-desktop", {"javafx", "swing"}),
    ("embedded-hmi", {"lvgl", "embedded hmi"}),
]


def strings(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif value is not None:
        yield str(value)


def classify(data: dict[str, Any]) -> dict[str, Any]:
    projects = data.get("projects", []) if isinstance(data, dict) else []
    evidence = " ".join(strings(projects)).lower()
    matches = []
    for family, markers in FAMILY_MARKERS:
        hit = sorted(marker for marker in markers if marker in evidence)
        if hit:
            matches.append({"family": family, "markers": hit})
    family = matches[0]["family"] if len(matches) == 1 else "hybrid-client" if matches else "unknown"
    technologies = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        for kind in ("languages", "runtimes", "frameworks"):
            values = project.get(kind, [])
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict) and item.get("name"):
                    technologies.append({"kind": kind[:-1], "name": item.get("name"), "version": item.get("version"), "evidence": item.get("evidence") or project.get("manifest")})
        build = project.get("build_system")
        if isinstance(build, dict) and build.get("name"):
            technologies.append({"kind": "build-system", "name": build.get("name"), "version": build.get("version"), "evidence": project.get("manifest")})
    version_gaps = sorted({str(x.get("name")) for x in technologies if not x.get("version")})
    return {
        "schema_version": "1.0.0",
        "family": family,
        "matches": matches,
        "technologies": technologies,
        "version_gaps": version_gaps,
        "project_count": len(projects),
        "backend_contract_required": family != "unknown",
        "routing": {
            "design": "unity-ui-design" if family == "unity" else "cs-ui-design",
            "implementation": "unity-component-implementation" if family == "unity" else "cs-component-implementation",
            "review": "unity-quality-review" if family == "unity" else "cs-quality-review",
        },
        "performance_policy": "load-one-phase-and-one-family-only",
        "uncertainties": (["未从tech-stack.json识别客户端框架；需要最小项目清单证据"] if not matches else []) + (["以下技术缺少精确版本证据：" + ", ".join(version_gaps)] if version_gaps else []),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--output")
    args = ap.parse_args()
    path = Path(args.root).resolve() / ".ai" / "context" / "tech-stack.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    result = classify(data)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
