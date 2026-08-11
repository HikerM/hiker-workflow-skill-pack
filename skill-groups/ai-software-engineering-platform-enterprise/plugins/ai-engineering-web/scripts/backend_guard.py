from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path


SKIP = {".git", ".ai", "node_modules", "dist", "build", "obj", "bin", ".venv", "venv", "vendor", "target", "coverage"}
MARKERS = {"package.json", "pyproject.toml", "requirements.txt", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml", "composer.json", "Gemfile"}
CONTRACT_NAMES = {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml", "schema.graphql"}


def bounded_files(root: Path, max_depth: int = 4, max_dirs: int = 240) -> list[Path]:
    root = root.resolve(); queue = deque([(root, 0)]); out: list[Path] = []; visited = 0
    while queue and visited < max_dirs:
        current, depth = queue.popleft(); visited += 1
        try: entries = list(current.iterdir())
        except OSError: continue
        for entry in entries:
            if entry.is_file() and (entry.name in MARKERS or entry.name.lower() in CONTRACT_NAMES or entry.suffix.lower() in {".csproj", ".proto", ".graphql", ".gql"}): out.append(entry)
        if depth >= max_depth: continue
        children = [p for p in entries if p.is_dir() and p.name not in SKIP]
        queue.extend((p, depth + 1) for p in sorted(children)[:64])
    return list(dict.fromkeys(out))


def package_signal(path: Path) -> dict:
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}
    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}; names = " ".join(deps).lower()
    framework = next((value for key, value in (("@nestjs/", "NestJS"), ("fastify", "Fastify"), ("express", "Express"), ("koa", "Koa"), ("hapi", "Hapi")) if key in names), "Node.js")
    return {"family": "node-typescript", "framework": framework, "runtime": str((data.get("engines") or {}).get("node") or "unknown"), "package_manager": str(data.get("packageManager") or "unknown"), "source": str(path)}


def python_signal(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore"); runtime = "unknown"
    if path.name == "pyproject.toml":
        match = re.search(r'^\s*requires-python\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match: runtime = match.group(1)
    low = text.lower(); framework = "Django" if "django" in low else "FastAPI" if "fastapi" in low else "Flask" if "flask" in low else "Python"
    return {"family": "python", "framework": framework, "runtime": runtime, "package_manager": "pyproject" if path.name == "pyproject.toml" else "requirements", "source": str(path)}


def dotnet_signal(path: Path) -> dict:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore")); values = [x.text for x in root.iter() if x.tag.split("}")[-1] in {"TargetFramework", "TargetFrameworks"} and x.text]
        runtime = ";".join(values) or "unknown"
    except Exception: runtime = "unknown"
    return {"family": "dotnet", "framework": "ASP.NET Core", "runtime": runtime, "package_manager": "NuGet", "source": str(path)}


def generic_signal(path: Path) -> dict:
    low = path.read_text(encoding="utf-8", errors="ignore").lower(); name = path.name
    if name in {"pom.xml", "build.gradle", "build.gradle.kts"}: family, framework, manager = "jvm", "Spring Boot" if "spring" in low else "JVM", "Maven" if name == "pom.xml" else "Gradle"
    elif name == "go.mod": family, framework, manager = "go", "Go", "Go Modules"
    elif name == "Cargo.toml": family, framework, manager = "rust", "Rust", "Cargo"
    elif name == "composer.json": family, framework, manager = "php", "Laravel" if "laravel" in low else "PHP", "Composer"
    else: family, framework, manager = "ruby", "Rails" if "rails" in low else "Ruby", "Bundler"
    runtime = next(iter(re.findall(r"(?:java|go|rust-version|php|ruby)[\s\"':=><~^]+([0-9][^\s\"',<]*)", low)), "unknown")
    return {"family": family, "framework": framework, "runtime": runtime, "package_manager": manager, "source": str(path)}


def digest(paths: list[Path], root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.relative_to(root).as_posix().encode())
        try: h.update(path.read_bytes())
        except OSError: pass
    return h.hexdigest()


def detect(root: Path) -> dict:
    root = root.resolve(); files = bounded_files(root); stacks = []
    for path in files:
        if path.name == "package.json": signal = package_signal(path)
        elif path.name in {"pyproject.toml", "requirements.txt"}: signal = python_signal(path)
        elif path.suffix.lower() == ".csproj": signal = dotnet_signal(path)
        elif path.name in {"pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml", "composer.json", "Gemfile"}: signal = generic_signal(path)
        else: continue
        if signal and not any(x["family"] == signal["family"] and x["source"] == signal["source"] for x in stacks): stacks.append(signal)
    contracts = [p for p in files if p.name.lower() in CONTRACT_NAMES or p.suffix.lower() in {".proto", ".graphql", ".gql"}]
    migrations = []; visited_dirs = 0
    for dirpath, dirnames, filenames in os.walk(root):
        visited_dirs += 1
        if visited_dirs > 500:
            dirnames[:] = []; break
        rel = Path(dirpath).relative_to(root); dirnames[:] = [d for d in dirnames if d not in SKIP]
        if len(rel.parts) > 5: dirnames[:] = []
        if any(token in {x.lower() for x in rel.parts} for token in {"migration", "migrations", "migrate"}):
            migrations.extend(Path(dirpath) / name for name in filenames[:200] if Path(name).suffix.lower() in {".sql", ".py", ".ts", ".js", ".cs", ".java"})
    unknown = [x["family"] for x in stacks if x["runtime"] == "unknown"]
    return {"schema_version": "1.0.0", "root": str(root), "stacks": stacks, "contracts": [p.relative_to(root).as_posix() for p in contracts], "migrations": [p.relative_to(root).as_posix() for p in migrations[:200]], "contract_fingerprint": digest(contracts, root), "unknown_runtime_families": unknown, "bounded_scan": {"manifest_max_depth": 4, "manifest_max_dirs": 240, "migration_max_dirs": 500}}


def audit(root: Path) -> dict:
    data = detect(root); blockers = []; warnings = []
    if not data["stacks"]: blockers.append("未识别到服务端工程清单，禁止猜测技术栈")
    if data["unknown_runtime_families"]: warnings.append("部分服务端运行时版本缺少工程证据")
    if not data["contracts"]: warnings.append("未发现版本化API或事件契约；若存在跨端消费者需补充契约证据")
    if data["migrations"] and not any("rollback" in x.lower() or "down" in x.lower() for x in data["migrations"]): warnings.append("发现数据库迁移但未识别到回滚证据")
    data.update({"result": "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if warnings else "PASS", "blockers": blockers, "warnings": warnings})
    return data


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("command", choices=["detect", "audit"]); args = parser.parse_args()
    data = detect(Path(args.root)) if args.command == "detect" else audit(Path(args.root)); print(json.dumps(data, ensure_ascii=False, indent=2)); return 2 if data.get("result") == "BLOCKED" else 0


if __name__ == "__main__": raise SystemExit(main())
