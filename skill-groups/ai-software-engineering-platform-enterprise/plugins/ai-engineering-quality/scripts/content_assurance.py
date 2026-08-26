from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from qualitylib import load_json, write_json


CONTENT_CASES = {
    "normal", "long", "very_long", "empty", "null", "large_number", "large_dataset",
    "special_character", "Chinese", "English", "mixed", "URL", "email",
}
FAILURE_METRICS = {
    "text_overflow", "clipping", "overlap", "offscreen", "button_wrap_failure",
    "tab_overflow", "table_overflow", "dialog_overflow", "popover_overflow",
}
MAX_RESULTS = 5000


def plan(applicable_cases: list[str], surfaces: list[str]) -> dict[str, Any]:
    unknown = sorted(set(applicable_cases) - CONTENT_CASES)
    if unknown:
        raise ValueError(f"unknown content cases: {unknown}")
    return {
        "schema_version": "1.0.0",
        "cases": list(dict.fromkeys(applicable_cases)),
        "surfaces": list(dict.fromkeys(surfaces)),
        "policy": "runtime-measurement-not-character-limits",
    }


def evaluate(test_plan: Any, runtime_results: Any) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if not isinstance(test_plan, dict) or not isinstance(runtime_results, dict):
        return {"status": "BLOCKED", "findings": [{"code": "INVALID_CONTENT_EVIDENCE"}]}
    required_cases = set(test_plan.get("cases", []))
    required_surfaces = set(test_plan.get("surfaces", []))
    rows = runtime_results.get("results", [])
    if not isinstance(rows, list):
        return {"status": "BLOCKED", "findings": [{"code": "INVALID_RUNTIME_RESULTS"}]}
    covered: set[tuple[str, str]] = set()
    for index, row in enumerate(rows[:MAX_RESULTS]):
        if not isinstance(row, dict):
            findings.append({"code": "INVALID_RUNTIME_RESULT", "index": index})
            continue
        case = str(row.get("case") or "")
        surface = str(row.get("surface") or "")
        if case not in CONTENT_CASES:
            findings.append({"code": "UNKNOWN_CONTENT_CASE", "case": case})
            continue
        covered.add((case, surface))
        measurements = row.get("measurements")
        if not isinstance(measurements, dict):
            findings.append({"code": "MISSING_RUNTIME_MEASUREMENTS", "case": case, "surface": surface})
            continue
        for metric in FAILURE_METRICS:
            if measurements.get(metric) is True:
                findings.append({"code": metric.upper(), "case": case, "surface": surface, "evidence_ref": row.get("evidence_ref")})
        if not row.get("evidence_ref"):
            findings.append({"code": "MISSING_RUNTIME_EVIDENCE_REF", "case": case, "surface": surface})
    for case in required_cases:
        for surface in required_surfaces:
            if (case, surface) not in covered:
                findings.append({"code": "MISSING_CONTENT_CASE", "case": case, "surface": surface})
    if len(rows) > MAX_RESULTS:
        findings.append({"code": "CONTENT_RESULT_BUDGET_EXCEEDED"})
    return {
        "status": "BLOCKED" if findings else "PASS",
        "findings": findings,
        "summary": {"required": len(required_cases) * len(required_surfaces), "covered": len(covered), "results": len(rows)},
        "policy": "runtime-measurement-not-character-limits",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hiker runtime content stress assurance")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate(load_json(Path(args.plan).resolve()), load_json(Path(args.results).resolve()))
    if args.output:
        write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
