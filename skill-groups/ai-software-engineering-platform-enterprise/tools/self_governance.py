from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchmark_product_assurance import benchmark as benchmark_product_assurance
from benchmark_governance_precision import benchmark as benchmark_governance_precision
from benchmark_delivery_velocity import benchmark as benchmark_delivery_velocity
from benchmark_router import benchmark as benchmark_router
from audit_skill_coherence import audit as audit_skill_coherence
from audit_governance_enforcement import audit as audit_governance_enforcement
from audit_resource_budgets import audit as audit_resource_budgets
from audit_static_drift import audit as audit_static_drift
from desktop_stability_gate import audit as audit_desktop_stability
from evaluate_master_progression import evaluate as evaluate_master_progression
from evaluate_router import evaluate as evaluate_router
from package_facts import audit_packages


SUITE = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SUITE.parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
from audit_public_content import audit as audit_public_content
from audit_release_facts import audit as audit_release_facts


STAGE_ORDER = (
    "architecture",
    "privacy",
    "version_facts",
    "tests",
    "performance",
    "package_facts",
)
MAX_PRODUCTION_PY_LINES = 700
MAX_HIKERCTL_LINES = 250


def _stage(name: str, ok: bool, *, errors: list[str] | None = None, facts: dict[str, Any] | None = None, seconds: float = 0.0) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if ok else "BLOCKED",
        "seconds": round(seconds, 3),
        "errors": errors or [],
        "facts": facts or {},
    }


def architecture_gate(repository_root: Path = REPOSITORY_ROOT, suite: Path = SUITE) -> dict[str, Any]:
    started = time.perf_counter()
    roots = [repository_root / "scripts", suite / "tools"] + [path / "scripts" for path in (suite / "plugins").iterdir() if path.is_dir()]
    files = sorted({path for root in roots if root.is_dir() for path in root.glob("*.py")})
    sizes = {path.relative_to(repository_root).as_posix(): len(path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()) for path in files}
    errors = [f"production Python file exceeds {MAX_PRODUCTION_PY_LINES} lines: {name} ({lines})" for name, lines in sizes.items() if lines > MAX_PRODUCTION_PY_LINES]
    hikerctl = suite / "plugins" / "ai-engineering-core" / "scripts" / "hikerctl.py"
    hikerctl_lines = len(hikerctl.read_text(encoding="utf-8").splitlines()) if hikerctl.is_file() else 0
    if not hikerctl.is_file():
        errors.append("hikerctl.py is missing")
    elif hikerctl_lines > MAX_HIKERCTL_LINES:
        errors.append(f"hikerctl.py is not a thin CLI: {hikerctl_lines} > {MAX_HIKERCTL_LINES}")
    governance = suite / "plugins" / "ai-engineering-workspace" / "scripts" / "governance_state.py"
    governance_text = governance.read_text(encoding="utf-8") if governance.is_file() else ""
    if "def save_task(" not in governance_text:
        errors.append("governance_state.py must retain the single Task domain writer")
    for extracted in ("governance_documents.py", "governance_quality.py"):
        text = (governance.parent / extracted).read_text(encoding="utf-8")
        if "def save_task(" in text or "atomic_json(task_file" in text:
            errors.append(f"{extracted} introduced a second Task domain writer")
    enforcement = audit_governance_enforcement(suite)
    errors.extend(f"governance enforcement: {item}" for item in enforcement.get("errors", []))
    resource_budgets = audit_resource_budgets(suite)
    errors.extend(f"resource budget: {item}" for item in resource_budgets.get("errors", []))
    static_drift = audit_static_drift(suite)
    errors.extend(f"static drift: {item}" for item in static_drift.get("errors", []))
    facts = {
        "production_python_files": len(files),
        "largest": sorted(({"path": name, "lines": lines} for name, lines in sizes.items()), key=lambda item: item["lines"], reverse=True)[:10],
        "hikerctl_lines": hikerctl_lines,
        "governance_state_lines": sizes.get(governance.relative_to(repository_root).as_posix()),
        "single_task_writer": not any("second Task domain writer" in item for item in errors),
        "governance_enforcement": enforcement,
        "resource_budgets": resource_budgets,
        "static_drift": static_drift,
    }
    return _stage("architecture", not errors, errors=errors, facts=facts, seconds=time.perf_counter() - started)


def privacy_gate(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    started = time.perf_counter()
    report = audit_public_content(repository_root)
    errors = [f"{item['code']}: {item['path']}:{item['line']}" for item in report.get("findings", [])]
    return _stage("privacy", bool(report.get("ok")), errors=errors, facts={"scanned": report.get("scanned_text_entries"), "findings": report.get("finding_count")}, seconds=time.perf_counter() - started)


def version_gate(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    started = time.perf_counter()
    report = audit_release_facts(repository_root, require_archives=False, require_test_report=False)
    return _stage("version_facts", bool(report.get("ok")), errors=list(report.get("errors", [])), facts={"source": report.get("version_source"), **(report.get("facts") or {})}, seconds=time.perf_counter() - started)


def tests_gate(repository_root: Path = REPOSITORY_ROOT, suite: Path = SUITE) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", str(suite / "tools" / "run_all_tests.py")],
        cwd=suite,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    facts = audit_release_facts(repository_root, require_archives=False, require_test_report=True)
    errors = []
    if completed.returncode:
        errors.append(f"run_all_tests.py failed with exit {completed.returncode}")
    errors.extend(facts.get("errors", []))
    router_eval = evaluate_router()
    progression = evaluate_master_progression()
    coherence = audit_skill_coherence(suite)
    if not router_eval.get("ok"):
        errors.append(f"router evaluation failed: {len(router_eval.get('failures', []))} scenarios")
    if not progression.get("ok"):
        errors.append("master progression evaluation failed")
    if not coherence.get("ok"):
        errors.extend(f"skill coherence: {item.get('code')} {item.get('skill')}" for item in coherence.get("errors", []))
    report_path = suite / "test-results.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return _stage(
        "tests",
        not errors and bool(report.get("ok")),
        errors=errors,
        facts={
            "test_count": report.get("test_count"),
            "source_fingerprint": report.get("source_fingerprint"),
            "router_eval": bool(router_eval.get("ok")),
            "master_progression": bool(progression.get("ok")),
            "skill_coherence": bool(coherence.get("ok")),
            "skill_count": coherence.get("skill_count"),
        },
        seconds=time.perf_counter() - started,
    )


def performance_gate(suite: Path = SUITE) -> dict[str, Any]:
    started = time.perf_counter()
    router = benchmark_router(20, 200.0)
    product = benchmark_product_assurance()
    governance = benchmark_governance_precision()
    delivery = benchmark_delivery_velocity()
    desktop = audit_desktop_stability(suite)
    errors = []
    if not router.get("ok"):
        errors.append(
            "router performance exceeds budget: "
            f"incremental P95 {router.get('p95_ms')}ms/{router.get('max_p95_ms')}ms, "
            f"raw P95 {router.get('raw_p95_ms')}ms/{router.get('max_raw_p95_ms')}ms"
        )
    errors.extend(f"product assurance: {item}" for item in product.get("errors", []))
    errors.extend(f"adaptive governance: {item}" for item in governance.get("errors", []))
    errors.extend(f"delivery velocity: {item}" for item in delivery.get("errors", []))
    errors.extend(desktop.get("errors", []))
    return _stage(
        "performance",
        not errors,
        errors=errors,
        facts={"router": router, "product_assurance": product, "adaptive_governance": governance, "delivery_velocity": delivery, "desktop": desktop.get("metrics", {})},
        seconds=time.perf_counter() - started,
    )


def package_gate(suite: Path = SUITE, archive_dir: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    report = audit_packages(suite, archive_dir)
    return _stage("package_facts", bool(report.get("ok")), errors=list(report.get("errors", [])), facts=report, seconds=time.perf_counter() - started)


def run_pipeline(
    repository_root: Path = REPOSITORY_ROOT,
    suite: Path = SUITE,
    *,
    archive_dir: Path | None = None,
    overrides: dict[str, Callable[[], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    handlers: dict[str, Callable[[], dict[str, Any]]] = {
        "architecture": lambda: architecture_gate(repository_root, suite),
        "privacy": lambda: privacy_gate(repository_root),
        "version_facts": lambda: version_gate(repository_root),
        "tests": lambda: tests_gate(repository_root, suite),
        "performance": lambda: performance_gate(suite),
        "package_facts": lambda: package_gate(suite, archive_dir),
    }
    handlers.update(overrides or {})
    stages: list[dict[str, Any]] = []
    blocked = False
    for name in STAGE_ORDER:
        if blocked:
            stages.append({"name": name, "status": "NOT_RUN", "seconds": 0.0, "errors": ["blocked by previous stage"], "facts": {}})
            continue
        try:
            result = handlers[name]()
        except Exception as exc:  # noqa: BLE001 - release gate must fail closed
            result = _stage(name, False, errors=[f"unhandled gate error: {type(exc).__name__}: {exc}"])
        if result.get("name") != name:
            result = _stage(name, False, errors=["gate returned a mismatched stage identity"])
        stages.append(result)
        blocked = result.get("status") != "PASS"
    release_gate = "BLOCKED" if blocked else ("PASS" if archive_dir is not None else "PASS_FOR_PACKAGING")
    return {
        "schema_version": "1.0.0",
        "ok": release_gate != "BLOCKED",
        "pipeline": list(STAGE_ORDER) + ["release_gate"],
        "stages": stages,
        "release_gate": release_gate,
        "blocked_stage": next((item["name"] for item in stages if item["status"] == "BLOCKED"), None),
    }


def finalize_pipeline(preflight: dict[str, Any], package_stage: dict[str, Any]) -> dict[str, Any]:
    """Bind verified candidate packages to the already-passed source gates."""
    stages = [dict(item) for item in preflight.get("stages", []) if item.get("name") != "package_facts"]
    sources_ok = len(stages) == len(STAGE_ORDER) - 1 and all(item.get("status") == "PASS" for item in stages)
    package_ok = package_stage.get("name") == "package_facts" and package_stage.get("status") == "PASS"
    stages.append(package_stage)
    ok = sources_ok and package_ok
    return {
        "schema_version": "1.0.0",
        "ok": ok,
        "pipeline": list(STAGE_ORDER) + ["release_gate"],
        "stages": stages,
        "release_gate": "PASS" if ok else "BLOCKED",
        "blocked_stage": next((item.get("name") for item in stages if item.get("status") != "PASS"), None),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker Self Governance release-blocking pipeline")
    parser.add_argument("--root", default=str(REPOSITORY_ROOT))
    parser.add_argument("--archive-dir")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    suite = root / "skill-groups" / "ai-software-engineering-platform-enterprise"
    report = run_pipeline(root, suite, archive_dir=Path(args.archive_dir).resolve() if args.archive_dir else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
