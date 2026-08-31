from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ENGINEERING_MANIFEST_NAMES = frozenset({
    "package.json", "pnpm-workspace.yaml", "pnpm-workspace.yml", "lerna.json", "turbo.json",
    "composer.json", "go.mod", "Cargo.toml", "pyproject.toml", "requirements.txt", "Gemfile",
    "pom.xml", "build.gradle", "build.gradle.kts", "CMakeLists.txt", "ProjectVersion.txt",
    "Package.swift", "pubspec.yaml", "project.pbxproj", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yml", "compose.yaml",
})
ENGINEERING_MANIFEST_SUFFIXES = frozenset({".sln", ".csproj", ".pro"})
LOWER_ENGINEERING_MANIFEST_NAMES = frozenset(name.lower() for name in ENGINEERING_MANIFEST_NAMES)
PACKAGE_MANAGER_LOCKS = (
    ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"),
    ("bun.lockb", "bun"), ("package-lock.json", "npm"),
)
STATE_FINGERPRINT_NAMES = frozenset({
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "pyproject.toml",
    "poetry.lock", "requirements.txt", "pom.xml", "build.gradle", "build.gradle.kts",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "manifest.json", "ProjectVersion.txt",
})
PROJECT_MARKER_PATHS = ENGINEERING_MANIFEST_NAMES | frozenset({"Packages/manifest.json"})

NODE_FRAMEWORK_PACKAGES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "@angular/core": ("angular", "Angular", ("frontend",)),
    "next": ("next", "Next.js", ("frontend",)),
    "nuxt": ("nuxt", "Nuxt", ("frontend",)),
    "react": ("react", "React", ("frontend",)),
    "svelte": ("svelte", "Svelte", ("frontend",)),
    "vite": ("vite", "Vite", ("frontend",)),
    "vue": ("vue", "Vue", ("frontend",)),
    "@hapi/hapi": ("hapi", "Hapi", ("backend",)),
    "@nestjs/core": ("nestjs", "NestJS", ("backend",)),
    "express": ("express", "Express", ("backend",)),
    "fastify": ("fastify", "Fastify", ("backend",)),
    "hapi": ("hapi", "Hapi", ("backend",)),
    "koa": ("koa", "Koa", ("backend",)),
    "@tauri-apps/api": ("tauri", "Tauri", ("client",)),
    "@tauri-apps/cli": ("tauri", "Tauri", ("client",)),
    "electron": ("electron", "Electron", ("client",)),
    "electron-builder": ("electron", "Electron", ("client",)),
    "react-native": ("react-native", "React Native", ("client",)),
}
NODE_DATABASE_PACKAGES = {
    "@prisma/client": "prisma", "drizzle-orm": "drizzle", "knex": "knex", "mongoose": "mongodb",
    "mysql": "mysql", "mysql2": "mysql", "pg": "postgresql", "prisma": "prisma",
    "sequelize": "sequelize", "sqlite3": "sqlite", "typeorm": "typeorm",
}


def is_engineering_manifest(path: Path) -> bool:
    normalized = path.as_posix()
    return (
        path.name.lower() in LOWER_ENGINEERING_MANIFEST_NAMES
        or path.suffix.lower() in ENGINEERING_MANIFEST_SUFFIXES
        or normalized.endswith("Packages/manifest.json")
    )


def _package_dependencies(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    return {
        str(name).strip().lower()
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        for name in (payload.get(section) or {})
        if isinstance(payload.get(section), dict)
    }


def manifest_signals(path: str | Path, content: str) -> dict[str, list[str]]:
    """Return bounded technology signals from one known engineering manifest."""
    path = Path(str(path).replace("\\", "/"))
    name = path.name
    lower = content.lower()
    roles: set[str] = set()
    frameworks: set[str] = set()
    databases: set[str] = set()
    runtimes: set[str] = set()

    if name == "package.json":
        try:
            package = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            package = {}
        dependencies = _package_dependencies(package)
        react_native = "react-native" in dependencies
        for dependency, (framework_id, _display, framework_roles) in NODE_FRAMEWORK_PACKAGES.items():
            if dependency not in dependencies or (dependency == "react" and react_native):
                continue
            frameworks.add(framework_id)
            roles.update(framework_roles)
        databases.update(value for key, value in NODE_DATABASE_PACKAGES.items() if key in dependencies)
        engines = package.get("engines") if isinstance(package, dict) else None
        if isinstance(engines, dict):
            runtimes.update(f"{key}:{value}" for key, value in engines.items())
    elif name in {"pyproject.toml", "requirements.txt"}:
        detected = {token for token in ("fastapi", "django", "flask", "litestar", "sanic") if token in lower}
        if detected:
            roles.add("backend")
        frameworks.update(detected)
        databases.update(token for token in ("sqlalchemy", "alembic", "psycopg", "pymysql") if token in lower)
        runtimes.add("python")
    elif name == "composer.json":
        roles.add("backend"); frameworks.add("laravel" if "laravel/framework" in lower else "php"); runtimes.add("php")
    elif name == "Gemfile":
        roles.add("backend"); frameworks.add("rails" if "rails" in lower else "ruby"); runtimes.add("ruby")
    elif name in {"go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts"}:
        roles.add("backend"); runtimes.add({"go.mod": "go", "Cargo.toml": "rust", "pom.xml": "jvm"}.get(name, "jvm"))
    elif name == "ProjectVersion.txt" or path.as_posix().endswith("Packages/manifest.json"):
        roles.add("client"); frameworks.add("unity")
        match = re.search(r"m_EditorVersion:\s*([^\r\n]+)", content)
        runtimes.add(f"unity:{match.group(1).strip()}" if match else "unity")
    elif name == "CMakeLists.txt" or path.suffix.lower() in {".sln", ".csproj", ".pro"}:
        qt = path.suffix.lower() == ".pro" or bool(re.search(r"\bqt[56]?\b|find_package\s*\(\s*qt", lower))
        dotnet_client = any(token in lower for token in ("<usewpf>true", "<usewindowsforms>true", "avalonia", "windowsappsdk"))
        dotnet_backend = any(token in lower for token in ("microsoft.net.sdk.web", "aspnetcore"))
        if qt or dotnet_client:
            roles.add("client")
        if dotnet_backend:
            roles.add("backend")
        if qt:
            frameworks.add("qt")
        if dotnet_client or dotnet_backend:
            runtimes.add("dotnet")
    elif name in {"Package.swift", "project.pbxproj"}:
        roles.add("client"); frameworks.add("apple-native"); runtimes.add("swift")
    elif name == "pubspec.yaml":
        roles.add("client")
        if "flutter:" in lower:
            frameworks.add("flutter")
        runtimes.add("dart")
    elif name in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        runtimes.add("container")

    return {
        "roles": sorted(roles), "frameworks": sorted(frameworks),
        "databases": sorted(databases), "runtimes": sorted(runtimes),
    }
