from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


SUITE = Path(__file__).resolve().parents[1]
QUALITY_SCRIPTS = SUITE / "plugins" / "ai-engineering-quality" / "scripts"
sys.path.insert(0, str(QUALITY_SCRIPTS))

from component_registry_v2 import component_fingerprint, empty_registry, registry_fingerprint, validate as validate_registry
from product_model_common import model_fingerprint
from product_release_gate import evaluate as evaluate_release
from runtime_ui_evidence import bind_artifact, objective_checks
from ui_design_model import default_model


def _timings(operation: Callable[[], Any], runs: int) -> dict[str, float]:
    values: list[float] = []
    for _ in range(max(3, runs)):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(ordered), 3),
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _registry(count: int) -> dict[str, Any]:
    registry = empty_registry("performance-registry", {"mode": "EXPLICIT", "refs": ["affected-scope"]})
    for index in range(count):
        component_id = f"bs:src/components/Component{index}.tsx#Component{index}"
        component = {
            "component_id": component_id,
            "semantic_role": {"status": "OBSERVED", "value": "bounded runtime surface", "source_refs": ["design:main"]},
            "design_component": {"status": "OBSERVED", "value": f"Component{index}", "source_refs": ["design:main"]},
            "code_component": {"status": "OBSERVED", "value": {"path": f"src/components/Component{index}.tsx", "symbol": f"Component{index}", "source_fingerprint": f"source-{index}"}, "source_refs": [f"src/components/Component{index}.tsx"]},
            "variants": [], "states": ["default"], "tokens": [], "accessibility": ["named"],
            "platform": "BS", "usage_rules": [],
            "technology_adapter": {"status": "OBSERVED", "value": {"family": "project-native", "version": "observed"}, "source_refs": ["project:manifest"]},
            "implementation_layer": "project_native",
        }
        component["fingerprint"] = component_fingerprint(component)
        registry["components"].append(component)
    registry["fingerprint"] = registry_fingerprint(registry)
    return registry


def _snapshot(element_count: int) -> dict[str, Any]:
    elements = []
    columns = 32
    for index in range(element_count):
        elements.append({
            "component_id": f"runtime:{index}",
            "rect": {"x": (index % columns) * 20, "y": (index // columns) * 20, "width": 10, "height": 10},
            "tokens": {},
        })
    return bind_artifact({
        "capture_id": "CAP-PERF", "screen_id": "main", "state": "default", "architecture": "BS",
        "technology": "project-native", "source_commit": "performance-candidate", "workspace_fingerprint": None,
        "source_fingerprint": "source", "design_fingerprint": "design", "registry_fingerprint": "registry",
        "viewport": {"width": 640, "height": 640, "device_scale_factor": 1}, "elements": elements,
    }, None)


def benchmark(
    runs: int = 30,
    cold_records: int = 1000,
    component_count: int = 500,
    element_count: int = 512,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="hiker-product-performance-") as temporary:
        root = Path(temporary)
        legacy_result = evaluate_release(root)
        legacy = _timings(lambda: evaluate_release(root), runs)

        ui = root / ".ai" / "ui"
        design = default_model("performance-project", "BS")
        design["fingerprint"] = model_fingerprint(design)
        _write(ui / "project-ui.json", design)
        _write(ui / "evidence" / "index.json", {"records": []})
        hot_result = evaluate_release(root)
        hot = _timings(lambda: evaluate_release(root), runs)
        hot_files = [path for path in ui.rglob("*") if path.is_file() and "archive" not in path.parts]
        hot_bytes = sum(path.stat().st_size for path in hot_files)

        archive = ui / "evidence" / "archive"
        for index in range(cold_records):
            _write(archive / f"segment-{index:05d}.json", {"id": index, "status": "COLD"})
        cold_result = evaluate_release(root)
        cold = _timings(lambda: evaluate_release(root), runs)

        registry = _registry(component_count)
        registry_result = validate_registry(registry, release=True)
        registry_timing = _timings(lambda: validate_registry(registry, release=True), runs)
        snapshot = _snapshot(element_count)
        expected = [item["component_id"] for item in snapshot["elements"]]
        runtime_result = objective_checks(snapshot, expected, "default")
        runtime_timing = _timings(lambda: objective_checks(snapshot, expected, "default"), runs)

    cold_delta = round(cold["p95_ms"] - hot["p95_ms"], 3)
    errors: list[str] = []
    if legacy_result.get("status") != "NOT_APPLICABLE" or legacy_result.get("reads") != 1:
        errors.append("legacy project fast path changed")
    if hot_result.get("reads") != 9 or cold_result.get("reads") != 9 or cold_result.get("cold_history_scanned") is not False:
        errors.append("product release gate did not stay on the bounded hot index")
    if hot["p95_ms"] > 25.0:
        errors.append(f"hot-state release P95 exceeds 25ms: {hot['p95_ms']}ms")
    if cold_delta > max(5.0, hot["p95_ms"]):
        errors.append(f"cold history caused non-bounded release latency: +{cold_delta}ms")
    if registry_result.get("status") != "PASS" or registry_timing["p95_ms"] > 100.0:
        errors.append(f"bounded registry validation exceeds budget: {registry_timing['p95_ms']}ms")
    if runtime_result.get("status") != "PASS" or runtime_timing["p95_ms"] > 150.0:
        errors.append(f"bounded runtime validation exceeds budget: {runtime_timing['p95_ms']}ms")
    return {
        "ok": not errors,
        "runs": max(3, runs),
        "legacy_no_ui": {**legacy, "reads": legacy_result.get("reads"), "writes": 0},
        "active_hot_index": {**hot, "reads": hot_result.get("reads"), "writes": 0, "bytes": hot_bytes},
        "cold_history": {**cold, "records": cold_records, "p95_delta_ms": cold_delta, "scanned": cold_result.get("cold_history_scanned")},
        "component_registry": {**registry_timing, "components": component_count},
        "runtime_objective": {**runtime_timing, "elements": element_count, "finding_budget": 256},
        "default_prompt_or_skill_bytes_added": 0,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark bounded Hiker 5.18 product assurance paths")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--cold-records", type=int, default=1000)
    parser.add_argument("--components", type=int, default=500)
    parser.add_argument("--elements", type=int, default=512)
    args = parser.parse_args()
    report = benchmark(args.runs, args.cold_records, args.components, args.elements)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
