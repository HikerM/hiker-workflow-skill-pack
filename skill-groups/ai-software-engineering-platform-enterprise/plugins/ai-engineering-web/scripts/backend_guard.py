from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))
from resource_budget import effective_budget  # noqa: E402
from source_surface import TraversalBudget, read_bounded_bytes, walk_source_files  # noqa: E402
from source_surface import read_bounded_text  # noqa: E402


SKIP = {".git", ".ai", "node_modules", "dist", "build", "obj", "bin", ".venv", "venv", "vendor", "target", "coverage"}
MARKERS = {"package.json", "pyproject.toml", "requirements.txt", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml", "composer.json", "Gemfile"}
CONTRACT_NAMES = {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml", "schema.graphql"}
NODE_FRAMEWORKS = (("@nestjs/core", "NestJS"), ("fastify", "Fastify"), ("express", "Express"), ("koa", "Koa"), ("@hapi/hapi", "Hapi"), ("hapi", "Hapi"), ("@adonisjs/core", "AdonisJS"), ("egg", "Egg.js"))
PYTHON_FRAMEWORKS = (("django", "Django"), ("fastapi", "FastAPI"), ("flask", "Flask"), ("litestar", "Litestar"), ("sanic", "Sanic"), ("falcon", "Falcon"), ("tornado", "Tornado"))


def bounded_text(path: Path) -> str:
    value, truncated = read_bounded_text(path, 8 * 1024 * 1024)
    return "" if truncated else value


def clean_version(value: object) -> str:
    text = str(value or "unknown").strip()
    match = re.search(r"\d+(?:\.\d+){0,3}(?:[-+][0-9A-Za-z.-]+)?", text)
    return match.group(0) if match else "unknown"


def sibling_package_manager(path: Path, declared: object) -> str:
    if declared: return str(declared)
    for filename, manager in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package-lock.json", "npm"), ("bun.lock", "bun"), ("bun.lockb", "bun")):
        if (path.parent / filename).is_file(): return manager
    return "unknown"


def bounded_files(root: Path, max_depth: int = 4, max_dirs: int = 240) -> list[Path]:
    limits = effective_budget("source_scan", {"max_depth": max_depth, "max_dirs": max_dirs})
    max_depth, max_dirs = limits["max_depth"], limits["max_dirs"]
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
    try: data = json.loads(bounded_text(path))
    except Exception: return {}
    deps = {str(k).lower(): v for section in ("dependencies", "devDependencies") for k, v in (data.get(section) or {}).items()}
    selected = next(((key, label) for key, label in NODE_FRAMEWORKS if key in deps), None)
    if not selected: return {}
    key, framework = selected
    return {"family": "node-typescript", "framework": framework, "framework_version": clean_version(deps[key]), "runtime": str((data.get("engines") or {}).get("node") or "unknown"), "package_manager": sibling_package_manager(path, data.get("packageManager")), "source": str(path)}


def python_signal(path: Path) -> dict:
    text = bounded_text(path); runtime = "unknown"
    if path.name == "pyproject.toml":
        match = re.search(r'^\s*requires-python\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match: runtime = match.group(1)
    low = text.lower(); selected = next(((key, label) for key, label in PYTHON_FRAMEWORKS if re.search(rf"(?m)(?:^|[\s\"']){re.escape(key)}(?:\[[^\]]+\])?\s*(?:[=<>~!^]+\s*)?[0-9*]*", low)), None)
    if not selected: return {}
    key, framework = selected
    version_match = re.search(rf"{re.escape(key)}(?:\[[^\]]+\])?\s*(?:[=<>~!^]+\s*)?([0-9]+(?:\.[0-9]+){{0,3}}(?:[-+][\w.-]+)?)", low)
    return {"family": "python", "framework": framework, "framework_version": version_match.group(1) if version_match else "unknown", "runtime": runtime, "package_manager": "pyproject" if path.name == "pyproject.toml" else "requirements", "source": str(path)}


def dotnet_signal(path: Path) -> dict:
    try:
        text = bounded_text(path); root = ET.fromstring(text); values = [x.text for x in root.iter() if x.tag.split("}")[-1] in {"TargetFramework", "TargetFrameworks"} and x.text]
        runtime = ";".join(values) or "unknown"
    except Exception: return {}
    low = text.lower(); sdk = str(root.attrib.get("Sdk") or root.attrib.get("sdk") or "").lower()
    packages = {str(x.attrib.get("Include") or x.attrib.get("Update") or "").lower(): x.attrib.get("Version") for x in root.iter() if x.tag.split("}")[-1] == "PackageReference"}
    if "microsoft.net.sdk.web" not in sdk and "microsoft.aspnetcore" not in low and "include=\"aspnetcore\"" not in low: return {}
    explicit = next((version for name, version in packages.items() if name.startswith("microsoft.aspnetcore") and version), None)
    return {"family": "dotnet", "framework": "ASP.NET Core", "framework_version": clean_version(explicit), "runtime": runtime, "package_manager": "NuGet", "source": str(path)}


def generic_signal(path: Path) -> dict:
    low = bounded_text(path).lower(); name = path.name
    if name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
        candidates = (("spring", "Spring Boot"), ("quarkus", "Quarkus"), ("micronaut", "Micronaut")); selected = next(((token, label) for token, label in candidates if token in low), None)
        if not selected: return {}
        _, framework = selected; family, manager = "jvm", "Maven" if name == "pom.xml" else "Gradle"
    elif name == "go.mod":
        family, manager = "go", "Go Modules"; framework = next((label for token, label in (("github.com/gin-gonic/gin", "Gin"), ("github.com/labstack/echo", "Echo"), ("github.com/gofiber/fiber", "Fiber"), ("github.com/go-chi/chi", "Chi")) if token in low), "Go HTTP")
    elif name == "Cargo.toml":
        family, manager = "rust", "Cargo"; framework = next((label for token, label in (("actix-web", "Actix Web"), ("axum", "Axum"), ("rocket", "Rocket"), ("warp", "Warp")) if token in low), "Rust HTTP")
    elif name == "composer.json":
        if not any(x in low for x in ("laravel", "symfony", "slim/", "cakephp")): return {}
        family, manager = "php", "Composer"; framework = "Laravel" if "laravel" in low else "Symfony" if "symfony" in low else "Slim" if "slim/" in low else "CakePHP"
    else:
        if not any(x in low for x in ("rails", "sinatra", "hanami")): return {}
        family, manager = "ruby", "Bundler"; framework = "Rails" if "rails" in low else "Sinatra" if "sinatra" in low else "Hanami"
    runtime = next(iter(re.findall(r"(?:java|go|rust-version|php|ruby)[\s\"':=><~^]+([0-9][^\s\"',<]*)", low)), "unknown")
    framework_token = framework.lower().replace(" ", "[-_. ]?")
    framework_match = re.search(framework_token + r"[^\d]{0,24}(\d+(?:\.\d+){0,3})", low)
    return {"family": family, "framework": framework, "framework_version": framework_match.group(1) if framework_match else "unknown", "runtime": runtime, "package_manager": manager, "source": str(path)}


def digest(paths: list[Path], root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.relative_to(root).as_posix().encode())
        try: h.update(read_bounded_bytes(path,8*1024*1024)[0])
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
    migrations,_=walk_source_files(root,TraversalBudget(max_depth=5,max_directories=500,max_entries=50000,max_files=20000,max_observed_bytes=2*1024*1024*1024,max_elapsed_ms=10000),ignored_directories=frozenset(name.casefold() for name in SKIP),include=lambda path:any(token in {part.lower() for part in path.relative_to(root).parts[:-1]} for token in {"migration","migrations","migrate"}) and path.suffix.lower() in {".sql",".py",".ts",".js",".cs",".java"})
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
