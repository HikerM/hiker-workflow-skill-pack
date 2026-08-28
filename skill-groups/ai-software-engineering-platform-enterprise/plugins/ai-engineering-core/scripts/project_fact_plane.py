from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from engineering_manifests import DiscoveryBudget, discover_engineering_manifests
from source_identity import context_fresh, identify


FRONTEND_DEPENDENCIES = {
    "@angular/core": "angular",
    "next": "next",
    "nuxt": "nuxt",
    "react": "react",
    "svelte": "svelte",
    "vite": "vite",
    "vue": "vue",
}
BACKEND_DEPENDENCIES = {
    "@hapi/hapi": "hapi",
    "@nestjs/core": "nestjs",
    "express": "express",
    "fastify": "fastify",
    "hapi": "hapi",
    "koa": "koa",
}
CLIENT_DEPENDENCIES = {
    "@tauri-apps/api": "tauri",
    "@tauri-apps/cli": "tauri",
    "electron": "electron",
    "electron-builder": "electron",
    "react-native": "react-native",
}
DATABASE_DEPENDENCIES = {
    "@prisma/client": "prisma",
    "drizzle-orm": "drizzle",
    "knex": "knex",
    "mongoose": "mongodb",
    "mysql": "mysql",
    "mysql2": "mysql",
    "pg": "postgresql",
    "prisma": "prisma",
    "sequelize": "sequelize",
    "sqlite3": "sqlite",
    "typeorm": "typeorm",
}


def _fact(value: Any, authority: str, fingerprint: str, generation: int = 0, freshness: str = "CURRENT") -> dict[str, Any]:
    return {
        "value": value,
        "authority": authority,
        "source_fingerprint": fingerprint,
        "generation": generation,
        "freshness": freshness,
        "lifecycle": "CURRENT",
    }


def _package_dependencies(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    return {
        str(name).strip().lower()
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        for name in (payload.get(section) or {})
        if isinstance(payload.get(section), dict)
    }


def _root_for_manifest(path: str) -> str:
    parent = Path(path).parent.as_posix()
    if path.endswith("Packages/manifest.json"):
        parent = Path(path).parent.parent.as_posix()
    return "." if parent in {"", "."} else parent


def _append_unique(values: list[str], items: Iterable[str], limit: int = 32) -> None:
    for item in items:
        normalized = str(item).strip().replace("\\", "/").strip("/") or "."
        if normalized not in values:
            values.append(normalized)
        if len(values) >= limit:
            return


def _structured_context(root: Path, identity: dict[str, Any], trusted: bool) -> dict[str, Any]:
    path = root / ".ai" / "context" / "tech-stack.json"
    ready = trusted and (
        context_fresh(path, identity.get("branch") or "", identity.get("head") or "")
        if identity.get("is_git") else path.is_file()
    )
    if not ready:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")[:64 * 1024])
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    allowed: dict[str, Any] = {}
    for key in (
        "architecture", "project_architecture", "framework", "frameworks", "frontend",
        "backend", "client", "database", "runtime", "application_roots", "service_roots",
        "frontend_roots", "backend_roots",
    ):
        if key in payload:
            allowed[key] = payload[key]
    allowed["source"] = str(path)
    allowed["fingerprint"] = hashlib.sha256(json.dumps(allowed, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return allowed


def _tokens(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    if isinstance(value, dict):
        return {str(key).strip().lower() for key, item in value.items() if item not in (None, False, "")}
    return set()


def _pro_fact(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else payload
    value = facts.get(name) if isinstance(facts, dict) else None
    if not isinstance(value, dict) or not value.get("value"):
        return None
    return value


def _pro_scalar(payload: dict[str, Any] | None, name: str) -> Any:
    if not isinstance(payload, dict):
        return None
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else payload
    return facts.get(name) if isinstance(facts, dict) else None


def _architecture(frontend: list[str], backend: list[str], client: list[str], context: dict[str, Any]) -> str | None:
    context_architecture = str(context.get("project_architecture") or context.get("architecture") or "").strip().lower()
    if context_architecture in {"bs", "cs", "backend", "hybrid"}:
        return context_architecture
    if client and (frontend or backend):
        return "hybrid"
    if client:
        return "cs"
    if frontend:
        return "bs"
    if backend:
        return "backend"
    return None


def build_project_fact_plane(
    root: Path,
    identity: dict[str, Any] | None = None,
    state_consistency: dict[str, Any] | None = None,
    pro_payload: dict[str, Any] | None = None,
    budget: DiscoveryBudget | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    identity = identity or identify(root)
    trusted_state = bool((state_consistency or {}).get("execution_policy", {}).get("trusted_ai_state"))
    context = _structured_context(root, identity, trusted_state)
    pro_roots = _pro_scalar(pro_payload, "verified_topology_roots") or []
    discovery = discover_engineering_manifests(
        root,
        identity.get("trusted_markers") or [],
        pro_roots if isinstance(pro_roots, list) else [],
        identity.get("nested_worktrees") or [],
        budget,
    )
    application_roots: list[str] = []
    service_roots: list[str] = []
    frontend_roots: list[str] = []
    backend_roots: list[str] = []
    client_roots: list[str] = []
    frameworks: list[str] = []
    databases: list[str] = []
    runtimes: list[str] = []
    authorities: set[str] = set()

    for manifest in discovery["manifests"]:
        path = str(manifest["path"])
        content = str(manifest["content"])
        lower = content.lower()
        name = Path(path).name
        root_name = _root_for_manifest(path)
        authorities.add(str(manifest["authority"]))
        frontend = backend = client = False
        if name == "package.json":
            try:
                package = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                package = {}
            dependencies = _package_dependencies(package)
            react_native = "react-native" in dependencies
            for dependency, framework in FRONTEND_DEPENDENCIES.items():
                if dependency in dependencies and not (dependency == "react" and react_native):
                    frontend = True
                    _append_unique(frameworks, [framework])
            for dependency, framework in BACKEND_DEPENDENCIES.items():
                if dependency in dependencies:
                    backend = True
                    _append_unique(frameworks, [framework])
            for dependency, framework in CLIENT_DEPENDENCIES.items():
                if dependency in dependencies:
                    client = True
                    _append_unique(frameworks, [framework])
            _append_unique(databases, (value for key, value in DATABASE_DEPENDENCIES.items() if key in dependencies))
            engines = package.get("engines") if isinstance(package, dict) else None
            if isinstance(engines, dict):
                _append_unique(runtimes, (f"{key}:{value}" for key, value in engines.items()))
        elif name in {"pyproject.toml", "requirements.txt"}:
            backend = any(token in lower for token in ("fastapi", "django", "flask", "litestar", "sanic"))
            _append_unique(frameworks, (token for token in ("fastapi", "django", "flask", "litestar", "sanic") if token in lower))
            _append_unique(databases, (token for token in ("sqlalchemy", "alembic", "psycopg", "pymysql") if token in lower))
            _append_unique(runtimes, ["python"])
        elif name == "composer.json":
            backend = True
            _append_unique(frameworks, ["laravel" if "laravel/framework" in lower else "php"])
            _append_unique(runtimes, ["php"])
        elif name == "Gemfile":
            backend = True
            _append_unique(frameworks, ["rails" if "rails" in lower else "ruby"])
            _append_unique(runtimes, ["ruby"])
        elif name in {"go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts"}:
            backend = True
            _append_unique(runtimes, [{"go.mod": "go", "Cargo.toml": "rust", "pom.xml": "jvm"}.get(name, "jvm")])
        elif name == "ProjectVersion.txt" or path.endswith("Packages/manifest.json"):
            client = True
            _append_unique(frameworks, ["unity"])
            match = re.search(r"m_EditorVersion:\s*([^\r\n]+)", content)
            _append_unique(runtimes, [f"unity:{match.group(1).strip()}" if match else "unity"])
        elif name == "CMakeLists.txt" or Path(path).suffix.lower() in {".sln", ".csproj"}:
            qt = bool(re.search(r"\bqt[56]?\b|find_package\s*\(\s*qt", lower))
            dotnet_client = any(token in lower for token in ("<usewpf>true", "<usewindowsforms>true", "avalonia", "windowsappsdk"))
            dotnet_backend = any(token in lower for token in ("microsoft.net.sdk.web", "aspnetcore"))
            client = qt or dotnet_client
            backend = dotnet_backend
            if qt:
                _append_unique(frameworks, ["qt"])
            if dotnet_client or dotnet_backend:
                _append_unique(runtimes, ["dotnet"])
        elif name in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            _append_unique(runtimes, ["container"])

        if frontend or backend or client:
            _append_unique(application_roots, [root_name])
        if frontend:
            _append_unique(frontend_roots, [root_name])
        if backend:
            _append_unique(backend_roots, [root_name])
            _append_unique(service_roots, [root_name])
        if client:
            _append_unique(client_roots, [root_name])

    context_frontend = _tokens(context.get("frontend"))
    context_backend = _tokens(context.get("backend"))
    context_client = _tokens(context.get("client"))
    _append_unique(frameworks, _tokens(context.get("framework")) | _tokens(context.get("frameworks")))
    _append_unique(databases, _tokens(context.get("database")))
    _append_unique(runtimes, _tokens(context.get("runtime")))
    _append_unique(application_roots, _tokens(context.get("application_roots")))
    _append_unique(service_roots, _tokens(context.get("service_roots")))
    _append_unique(frontend_roots, _tokens(context.get("frontend_roots")))
    _append_unique(backend_roots, _tokens(context.get("backend_roots")))
    if context_frontend and not frontend_roots:
        _append_unique(frontend_roots, ["."])
    if context_backend and not backend_roots:
        _append_unique(backend_roots, ["."])
        _append_unique(service_roots, ["."])
    if context_client and not client_roots:
        _append_unique(client_roots, ["."])

    local_architecture = _architecture(frontend_roots, backend_roots, client_roots, context)
    local_authority = (
        "CURRENT_WORKSPACE_MANIFEST"
        if "CURRENT_WORKSPACE_MANIFEST" in authorities
        else "VERIFIED_DERIVED"
        if discovery["manifests"] or context
        else "CURRENT_RUNTIME_OBSERVATION"
    )
    local_fingerprint = discovery["fingerprint"]
    pro_architecture = _pro_fact(pro_payload, "project_architecture")
    selected_architecture = local_architecture
    architecture_fact = _fact(local_architecture, local_authority, local_fingerprint) if local_architecture else None
    if pro_architecture:
        pro_value = str(pro_architecture.get("value") or "").lower()
        if not local_architecture or pro_value == local_architecture or (pro_value == "bs" and local_architecture == "backend"):
            selected_architecture = pro_value
            architecture_fact = pro_architecture
        elif pro_value == "backend" and local_architecture == "bs":
            selected_architecture = "bs"
        elif pro_value == "hybrid":
            selected_architecture = "hybrid"
            architecture_fact = pro_architecture

    pro_facts = pro_payload.get("facts") if isinstance(pro_payload, dict) and isinstance(pro_payload.get("facts"), dict) else {}
    project_id = pro_facts.get("project_id") or identity.get("repo_id")
    generation = int(pro_facts.get("project_generation") or 0)
    plane_basis = {
        "project_id": project_id,
        "repo_id": identity.get("repo_id"),
        "architecture": selected_architecture,
        "applications": application_roots,
        "services": service_roots,
        "frontend": frontend_roots,
        "backend": backend_roots,
        "client": client_roots,
        "manifest_fingerprint": local_fingerprint,
        "pro_generation": generation,
    }
    plane_fingerprint = hashlib.sha256(json.dumps(plane_basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": "1.0.0",
        "project_identity": _fact(project_id, "PRO_STATE_PLANE" if pro_facts else "CURRENT_RUNTIME_OBSERVATION", plane_fingerprint, generation),
        "project_topology": _fact(
            {
                "application_roots": application_roots,
                "service_roots": service_roots,
                "frontend_roots": frontend_roots,
                "backend_roots": backend_roots,
                "client_roots": client_roots,
            },
            local_authority,
            local_fingerprint,
            generation,
        ),
        "project_architecture": architecture_fact,
        "framework_facts": _fact(frameworks, local_authority, local_fingerprint, generation),
        "database_facts": _fact(databases, local_authority, local_fingerprint, generation),
        "runtime_facts": _fact(runtimes, local_authority, local_fingerprint, generation),
        "current_goal": pro_facts.get("current_goal"),
        "current_task": pro_facts.get("current_task"),
        "current_goal_revision": pro_facts.get("current_goal_revision", 0),
        "current_stage": pro_facts.get("current_stage"),
        "current_changed_scope": pro_facts.get("current_changed_scope", []),
        "environment_profile": pro_facts.get("environment_profile"),
        "authority": "PRO_STATE_PLANE" if pro_facts else local_authority,
        "source_fingerprint": plane_fingerprint,
        "generation": generation,
        "context_source_trusted": bool(context),
        "manifest_discovery": {
            "sources": [item["path"] for item in discovery["manifests"]],
            "authorities": [item["authority"] for item in discovery["manifests"]],
            "declared_roots": discovery["declared_roots"],
            "budget": discovery["budget"],
            "metrics": discovery["metrics"],
        },
        "source_identity": {
            "repo_root": identity.get("repo_root"),
            "worktree_root": identity.get("worktree_root"),
            "branch": identity.get("branch"),
            "head": identity.get("head"),
            "repo_id": identity.get("repo_id"),
            "source_conflicts": bool(identity.get("nested_worktrees")),
            "nested_worktree_count": len(identity.get("nested_worktrees") or []),
            "tracked_file_count": identity.get("tracked_file_count"),
        },
    }
