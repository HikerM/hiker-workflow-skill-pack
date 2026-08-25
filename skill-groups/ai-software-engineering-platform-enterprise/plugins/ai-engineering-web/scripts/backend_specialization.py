from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from backend_guard import detect as detect_backend


SKIP = {".git", ".ai", "node_modules", "vendor", "dist", "build", "coverage", ".venv", "venv", "tmp", "storage"}
SOURCE_SUFFIXES = {".php", ".ts", ".mts", ".cts", ".js", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".xml", ".sql"}


def bounded_files(root: Path, max_depth: int = 7, max_files: int = 4000) -> tuple[list[Path], bool]:
    root = root.resolve(); found: list[Path] = []; truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath); rel = current.relative_to(root)
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP)
        if len(rel.parts) >= max_depth:
            dirnames[:] = []
        for name in sorted(filenames):
            path = current / name
            if path.suffix.lower() in SOURCE_SUFFIXES or name in {"composer.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", ".nvmrc", ".node-version"}:
                found.append(path)
                if len(found) >= max_files:
                    truncated = True
                    return found, truncated
    return found, truncated


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def rels(paths: Iterable[Path], root: Path, limit: int = 80) -> list[str]:
    return [path.relative_to(root).as_posix() for path in list(paths)[:limit]]


def fingerprint(paths: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            pass
    return digest.hexdigest()


def dimension(evidence: Iterable[Path], findings: list[dict[str, str]] | None = None, required: bool = False, note: str | None = None, root: Path | None = None) -> dict[str, Any]:
    items = list(evidence); issues = findings or []
    status = "FAIL" if any(item.get("severity") == "HIGH" for item in issues) else "PASS" if items and not issues else "GAP"
    if required and not items:
        status = "BLOCKED"
    result: dict[str, Any] = {"status": status, "evidence": rels(items, root) if root else [], "findings": issues}
    if note:
        result["note"] = note
    return result


def finding(rule: str, path: Path, root: Path, severity: str = "MEDIUM") -> dict[str, str]:
    return {"severity": severity, "rule": rule, "path": path.relative_to(root).as_posix()}


def json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def result(profile: str, root: Path, files: list[Path], truncated: bool, identity: dict[str, Any], dimensions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    statuses = {item["status"] for item in dimensions.values()}
    overall = "BLOCKED" if "BLOCKED" in statuses else "FAIL" if "FAIL" in statuses else "PASS_WITH_GAPS" if "GAP" in statuses else "PASS"
    return {
        "schema_version": "1.0.0", "profile": profile, "result": overall, "identity": identity,
        "dimensions": dimensions, "source_fingerprint": fingerprint(files, root),
        "bounded_scan": {"max_depth": 7, "max_files": 4000, "scanned_files": len(files), "truncated": truncated},
        "storage_policy": "paths-versions-status-hashes-only",
    }


def laravel_audit(root: Path) -> dict[str, Any]:
    root = root.resolve(); files, truncated = bounded_files(root)
    composer = root / "composer.json"; lock = root / "composer.lock"
    declared = json_file(composer); locked = json_file(lock)
    require = declared.get("require") or {}; declared_version = str(require.get("laravel/framework") or "unknown")
    resolved_version = "unknown"
    for package in (locked.get("packages") or []):
        if isinstance(package, dict) and package.get("name") == "laravel/framework":
            resolved_version = str(package.get("version") or "unknown")
    php_version = str(require.get("php") or "unknown")
    identity_files = [path for path in (composer, lock) if path.is_file()]
    identity = {"family": "laravel-php", "php": php_version, "framework_declared": declared_version, "framework_resolved": resolved_version}
    php_files = [path for path in files if path.suffix.lower() == ".php"]
    routes = [path for path in php_files if "routes" in {part.lower() for part in path.relative_to(root).parts[:-1]}]
    controllers = [path for path in php_files if "controller" in path.name.lower() or "controllers" in {part.lower() for part in path.parts}]
    services = [path for path in php_files if {"services", "domain", "repositories", "actions"}.intersection(part.lower() for part in path.relative_to(root).parts)]
    boundary_findings = []
    for path in controllers:
        text = read_text(path)
        if re.search(r"\bDB::|::query\s*\(|->(?:save|create|update|delete)\s*\(", text):
            boundary_findings.append(finding("controller-persistence-leak", path, root, "HIGH"))
    migrations = [path for path in php_files if "migrations" in {part.lower() for part in path.relative_to(root).parts}]
    indexes = [path for path in migrations if re.search(r"->(?:index|unique|primary|fullText)\s*\(|\bINDEX\b", read_text(path), re.I)]
    transactions = [path for path in php_files if re.search(r"\bDB::transaction\s*\(|\bbeginTransaction\s*\(", read_text(path))]
    validation = [path for path in php_files if "requests" in {part.lower() for part in path.relative_to(root).parts} or re.search(r"\b(?:FormRequest|Validator::make|->validate)\b", read_text(path))]
    dto = [path for path in php_files if "dto" in path.name.lower() or "data" in {part.lower() for part in path.relative_to(root).parts}]
    queue = [path for path in php_files if {"jobs", "listeners"}.intersection(part.lower() for part in path.relative_to(root).parts) or "ShouldQueue" in read_text(path)]
    auth = [path for path in php_files if {"policies", "middleware"}.intersection(part.lower() for part in path.relative_to(root).parts) or re.search(r"\b(?:Auth::|Gate::|authorize\s*\()", read_text(path))]
    tests = [path for path in php_files if "tests" in {part.lower() for part in path.relative_to(root).parts}]
    phpunit = [path for path in files if path.name in {"phpunit.xml", "phpunit.xml.dist"}]
    scripts = declared.get("scripts") or {}; test_command = next((name for name in scripts if "test" in name.lower()), None)
    dimensions = {
        "identity": dimension(identity_files if "laravel/framework" in require else [], required=True, note="composer.lock supplies the resolved framework version", root=root),
        "route_controller_service_boundary": dimension(routes + controllers + services, boundary_findings, required=True, root=root),
        "migration_and_index": dimension(migrations + indexes, note=f"migrations={len(migrations)}, index_evidence={len(indexes)}", root=root),
        "transaction": dimension(transactions, note="required for multi-write paths; absence remains an evidence gap", root=root),
        "validation_and_dto": dimension(validation + dto, root=root),
        "queue": dimension(queue, note="absence means queue behavior is not evidenced, not that a queue is required", root=root),
        "auth": dimension(auth, root=root),
        "test_evidence": dimension(tests + phpunit, required=True, note=f"composer_test_script={test_command or 'missing'}", root=root),
    }
    if not routes or not controllers or not services:
        dimensions["route_controller_service_boundary"]["status"] = "GAP" if dimensions["route_controller_service_boundary"]["status"] != "FAIL" else "FAIL"
        dimensions["route_controller_service_boundary"]["note"] = f"routes={len(routes)}, controllers={len(controllers)}, services={len(services)}"
    if not migrations or not indexes:
        dimensions["migration_and_index"]["status"] = "GAP"
    if not validation or not dto:
        dimensions["validation_and_dto"]["status"] = "GAP"
        dimensions["validation_and_dto"]["note"] = f"validation={len(validation)}, dto={len(dto)}"
    if not test_command and dimensions["test_evidence"]["status"] != "BLOCKED":
        dimensions["test_evidence"]["status"] = "GAP"
    if resolved_version == "unknown":
        dimensions["identity"]["status"] = "GAP" if dimensions["identity"]["status"] != "BLOCKED" else "BLOCKED"
        dimensions["identity"]["findings"].append({"severity": "MEDIUM", "rule": "missing-resolved-framework-version", "path": "composer.lock"})
    return result("laravel-php", root, files, truncated, identity, dimensions)


def node_audit(root: Path) -> dict[str, Any]:
    root = root.resolve(); files, truncated = bounded_files(root)
    package = root / "package.json"; data = json_file(package); stacks = detect_backend(root).get("stacks", [])
    stack = next((item for item in stacks if item.get("family") == "node-typescript"), {})
    locks = [root / name for name in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock") if (root / name).is_file()]
    runtime_files = [root / name for name in (".nvmrc", ".node-version") if (root / name).is_file()]
    runtime = str((data.get("engines") or {}).get("node") or "unknown")
    tsconfigs = [path for path in files if path.name.startswith("tsconfig") and path.suffix == ".json"]
    identity = {"family": "node-typescript", "framework": stack.get("framework", "unknown"), "framework_version": stack.get("framework_version", "unknown"), "runtime": runtime, "package_manager": stack.get("package_manager", "unknown")}
    source = [path for path in files if path.suffix.lower() in {".ts", ".mts", ".cts", ".js", ".mjs", ".cjs"}]
    modules = [path for path in source if re.search(r"(?:module|controller|service|repository|route)\.(?:ts|js)$", path.name, re.I)]
    boundary_findings = []
    for path in source:
        if "controller" in path.name.lower() and re.search(r"\b(?:prisma|sequelize|typeorm|knex|db)\s*\.|\bSELECT\b", read_text(path), re.I):
            boundary_findings.append(finding("controller-database-leak", path, root, "HIGH"))
    async_files = [path for path in source if re.search(r"\basync\b|\.then\s*\(", read_text(path))]
    error_boundaries = [path for path in source if re.search(r"\b(?:ExceptionFilter|ErrorRequestHandler|errorHandler|setErrorHandler|catch\s*\()", read_text(path))]
    async_findings = [finding("empty-catch", path, root, "HIGH") for path in source if re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", read_text(path), re.S)]
    contracts = [path for path in files if path.name.lower() in {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml", "schema.graphql"}]
    dependencies = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    db_dependency = any(name in dependencies for name in ("prisma", "@prisma/client", "typeorm", "sequelize", "knex", "mongoose", "pg", "mysql2"))
    db_files = [path for path in files if {"migrations", "prisma", "database", "db"}.intersection(part.lower() for part in path.relative_to(root).parts)]
    scripts = data.get("scripts") or {}
    build_scripts = [name for name in scripts if any(token in name.lower() for token in ("build", "typecheck", "lint"))]
    test_scripts = [name for name in scripts if "test" in name.lower()]
    tests = [path for path in source if re.search(r"\.(?:spec|test)\.(?:ts|js)$", path.name) or "tests" in {part.lower() for part in path.relative_to(root).parts}]
    dimensions = {
        "identity_and_lock": dimension(([package] if stack else []) + locks + runtime_files, required=True, note=f"runtime={runtime}; lockfiles={len(locks)}", root=root),
        "typescript_config": dimension(tsconfigs, required=True, root=root),
        "module_boundary": dimension(modules, boundary_findings, required=True, root=root),
        "async_and_error_handling": dimension(async_files + error_boundaries, async_findings, required=True, root=root),
        "api_contract": dimension(contracts, root=root),
        "database": dimension(db_files, note=f"database_dependency_detected={db_dependency}", root=root),
        "build_and_test": dimension(tests, required=True, note=f"build_scripts={build_scripts}; test_scripts={test_scripts}", root=root),
    }
    controller_files = [path for path in modules if "controller" in path.name.lower() or "route" in path.name.lower()]
    service_files = [path for path in modules if "service" in path.name.lower()]
    if not controller_files or not service_files:
        dimensions["module_boundary"]["status"] = "GAP" if dimensions["module_boundary"]["status"] != "FAIL" else "FAIL"
        dimensions["module_boundary"]["note"] = f"controllers_or_routes={len(controller_files)}, services={len(service_files)}"
    if async_files and not error_boundaries and dimensions["async_and_error_handling"]["status"] != "FAIL":
        dimensions["async_and_error_handling"]["status"] = "GAP"
        dimensions["async_and_error_handling"]["note"] = "async code exists without a detected error boundary"
    if not locks:
        dimensions["identity_and_lock"]["status"] = "BLOCKED"
        dimensions["identity_and_lock"]["findings"].append({"severity": "HIGH", "rule": "missing-package-lock", "path": "package.json"})
    if runtime == "unknown" and not runtime_files:
        dimensions["identity_and_lock"]["status"] = "GAP" if dimensions["identity_and_lock"]["status"] != "BLOCKED" else "BLOCKED"
    if not build_scripts or not test_scripts:
        dimensions["build_and_test"]["status"] = "GAP" if dimensions["build_and_test"]["status"] != "BLOCKED" else "BLOCKED"
    return result("node-typescript", root, files, truncated, identity, dimensions)


def audit(root: Path, family: str) -> dict[str, Any]:
    if family == "laravel":
        return laravel_audit(root)
    if family == "node-ts":
        return node_audit(root)
    raise ValueError(f"unsupported family: {family}")


def main() -> int:
    parser = argparse.ArgumentParser(description="On-demand backend specialization evidence audit")
    parser.add_argument("--root", default=".")
    parser.add_argument("--family", required=True, choices=["laravel", "node-ts"])
    parser.add_argument("--output")
    args = parser.parse_args(); data = audit(Path(args.root), args.family)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 2 if data["result"] in {"BLOCKED", "FAIL"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
