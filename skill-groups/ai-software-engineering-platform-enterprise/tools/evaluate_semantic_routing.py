from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "ai-engineering-core"
DEFAULT_EVAL = CORE / "evals" / "semantic-routing"
sys.path.insert(0, str(CORE / "scripts"))

from suite_router import PLUGIN_FOR, route


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _index(items: Any, source: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError(f"{source} entries must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not str(item.get("id", "")).strip():
            raise ValueError(f"{source} contains an entry without an id")
        case_id = str(item["id"])
        if case_id in result:
            raise ValueError(f"duplicate {source} id: {case_id}")
        result[case_id] = item
    return result


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guard_check(case: dict[str, Any], prediction: dict[str, Any]) -> tuple[bool, str]:
    candidates = list(prediction.get("candidates") or [])
    if prediction.get("disposition") != "SELECT":
        with tempfile.TemporaryDirectory() as td:
            result = route(Path(td), str(case.get("request", "")))
        safe = result.get("guard_decision") == "PROPOSAL_REQUIRED" and not result.get("selected")
        return safe, result.get("guard_decision", "MISSING")
    context = case.get("context") or {}
    proposal = {
        "project_mode": prediction.get("project_mode", context.get("project_mode", "unknown")),
        "architecture": prediction.get("architecture", context.get("architecture", "unknown")),
        "stage": prediction.get("stage", context.get("stage", "unknown")),
        "current_action": prediction.get("current_action") or "执行当前语义评估用例",
        "confidence": prediction.get("confidence", "high"),
        "candidates": candidates,
        "deferred": list(prediction.get("deferred") or []),
        "negated_terms": list(prediction.get("negated_terms") or []),
        "future_terms": list(prediction.get("future_terms") or []),
    }
    with tempfile.TemporaryDirectory() as td:
        result = route(Path(td), proposal)
    accepted_ids = [item.get("id") for item in result.get("selected", [])]
    safe = bool(result.get("accepted")) and accepted_ids == candidates
    diagnostics = ",".join(item.get("code", "") for item in result.get("diagnostics", []))
    return safe, diagnostics or result.get("guard_decision", "MISSING")


def evaluate(cases_path: Path, gold_path: Path, predictions_path: Path) -> dict[str, Any]:
    cases_doc = _load_json(cases_path)
    gold_doc = _load_json(gold_path)
    predictions_doc = _load_json(predictions_path)
    benchmark_ids = {
        str(cases_doc.get("benchmark_id", "")),
        str(gold_doc.get("benchmark_id", "")),
        str(predictions_doc.get("benchmark_id", "")),
    }
    if len(benchmark_ids) != 1 or not next(iter(benchmark_ids)):
        raise ValueError("cases, gold and predictions must share one benchmark_id")
    cases = _index(cases_doc.get("cases"), "cases")
    labels = _index(gold_doc.get("labels"), "labels")
    predictions = _index(predictions_doc.get("predictions"), "predictions")
    if cases.keys() != labels.keys() or cases.keys() != predictions.keys():
        raise ValueError("cases, labels and predictions must contain exactly the same ids")
    forbidden_case_fields = {"category", "expected", "top1", "allowed_skills", "required_top2"}
    leaked = sorted(case_id for case_id, item in cases.items() if forbidden_case_fields & item.keys())
    if leaked:
        raise ValueError(f"selection input contains answer fields: {leaked}")
    category_by_id: dict[str, str] = {}
    for category, case_ids in (gold_doc.get("categories") or {}).items():
        for case_id in case_ids:
            if case_id in category_by_id:
                raise ValueError(f"case appears in multiple categories: {case_id}")
            category_by_id[str(case_id)] = str(category)
    if category_by_id.keys() != cases.keys():
        raise ValueError("gold categories must classify every case exactly once")

    select_total = top1_hits = required_total = required_hits = 0
    selected_total = wrong_plugin = unnecessary = overload_cases = forbidden_hits = 0
    specializations_total = unnecessary_specializations = 0
    nonselect_total = nonselect_hits = false_rejections = 0
    deferred_total = deferred_hits = guard_hits = 0
    failures: list[dict[str, Any]] = []
    categories: dict[str, list[bool]] = defaultdict(list)

    for case_id, case in cases.items():
        label = labels[case_id]
        prediction = predictions[case_id]
        expected = str(label.get("disposition"))
        actual = str(prediction.get("disposition"))
        selected = list(prediction.get("candidates") or [])
        specializations = list(prediction.get("specializations") or [])
        deferred = list(prediction.get("deferred") or [])
        allowed = set(label.get("allowed_skills") or [])
        forbidden = set(label.get("forbidden_skills") or [])
        allowed_specializations = set(label.get("allowed_specializations") or [])
        forbidden_specializations = set(label.get("forbidden_specializations") or [])
        required = set(label.get("required_top2") or [])
        required_deferred = set(label.get("required_deferred") or [])
        max_selected = int(label.get("max_selected", 0))

        selected_total += len(selected)
        unnecessary += sum(skill not in allowed for skill in selected)
        forbidden_hits += len(forbidden.intersection(selected))
        specializations_total += len(specializations)
        unnecessary_specializations += sum(item not in allowed_specializations for item in specializations)
        forbidden_hits += len(forbidden_specializations.intersection(specializations))
        if len(selected) > max_selected or len(selected) > 2:
            overload_cases += 1
        allowed_plugins = {PLUGIN_FOR[skill] for skill in allowed if skill in PLUGIN_FOR}
        wrong_plugin += sum(PLUGIN_FOR.get(skill) not in allowed_plugins for skill in selected)

        case_ok = actual == expected
        if expected == "SELECT":
            select_total += 1
            if actual in {"NONE", "UNKNOWN", "REJECT"}:
                false_rejections += 1
            acceptable_top1 = set(label.get("acceptable_top1") or [])
            top1_ok = bool(selected) and selected[0] in acceptable_top1
            top1_hits += int(top1_ok)
            required_total += len(required)
            required_hits += len(required.intersection(selected[:2]))
            deferred_total += len(required_deferred)
            deferred_hits += len(required_deferred.intersection(deferred))
            case_ok = case_ok and top1_ok and required.issubset(set(selected[:2]))
            case_ok = case_ok and not (set(selected) - allowed)
            case_ok = case_ok and not forbidden.intersection(selected)
            case_ok = case_ok and not (set(specializations) - allowed_specializations)
            case_ok = case_ok and not forbidden_specializations.intersection(specializations)
            case_ok = case_ok and required_deferred.issubset(set(deferred))
        else:
            nonselect_total += 1
            no_load = not selected and not specializations
            nonselect_hits += int(actual == expected and no_load)
            case_ok = case_ok and no_load

        guard_ok, guard_detail = _guard_check(case, prediction)
        guard_hits += int(guard_ok)
        case_ok = case_ok and guard_ok
        category = category_by_id[case_id]
        categories[category].append(case_ok)
        if not case_ok:
            failures.append({
                "id": case_id,
                "category": category,
                "expected": expected,
                "actual": actual,
                "selected": selected,
                "guard": guard_detail,
            })

    case_total = len(cases)
    metrics = {
        "top1_accuracy": _ratio(top1_hits, select_total),
        "top2_recall": _ratio(required_hits, required_total),
        "wrong_plugin_rate": _ratio(wrong_plugin, selected_total),
        "overload_rate": _ratio(overload_cases, case_total),
        "unnecessary_skill_rate": _ratio(unnecessary, selected_total),
        "unnecessary_specialization_rate": _ratio(unnecessary_specializations, specializations_total),
        "reject_unknown_quality": _ratio(nonselect_hits, nonselect_total),
        "false_rejection_rate": _ratio(false_rejections, select_total),
        "deferred_recall": _ratio(deferred_hits, deferred_total),
        "guard_conservation_rate": _ratio(guard_hits, case_total),
    }
    provenance_valid = (
        predictions_doc.get("selection_authority") == "current-chatgpt-codex-host"
        and predictions_doc.get("external_model_calls") == 0
        and predictions_doc.get("gold_labels_in_selection_payload") is False
    )
    thresholds = gold_doc.get("thresholds") or {}
    ok = (
        metrics["top1_accuracy"] >= float(thresholds.get("min_top1_accuracy", 0.85))
        and metrics["top2_recall"] >= float(thresholds.get("min_top2_recall", 0.90))
        and metrics["wrong_plugin_rate"] <= float(thresholds.get("max_wrong_plugin_rate", 0.02))
        and metrics["overload_rate"] <= float(thresholds.get("max_overload_rate", 0.0))
        and metrics["unnecessary_skill_rate"] <= float(thresholds.get("max_unnecessary_skill_rate", 0.05))
        and metrics["reject_unknown_quality"] >= float(thresholds.get("min_reject_unknown_quality", 0.85))
        and metrics["deferred_recall"] >= float(thresholds.get("min_deferred_recall", 1.0))
        and metrics["guard_conservation_rate"] == 1.0
        and forbidden_hits == 0
        and provenance_valid
        and not failures
    )
    return {
        "ok": ok,
        "benchmark_id": next(iter(benchmark_ids)),
        "selection_authority": predictions_doc.get("selection_authority"),
        "blindness_level": predictions_doc.get("blindness_level"),
        "external_model_calls": predictions_doc.get("external_model_calls"),
        "gold_labels_in_selection_payload": predictions_doc.get("gold_labels_in_selection_payload"),
        "provenance_valid": provenance_valid,
        "case_count": case_total,
        "select_case_count": select_total,
        "nonselect_case_count": nonselect_total,
        "metrics": metrics,
        "forbidden_selection_count": forbidden_hits,
        "category_accuracy": {
            name: {"passed": sum(values), "total": len(values), "accuracy": _ratio(sum(values), len(values))}
            for name, values in sorted(categories.items())
        },
        "input_fingerprints": {
            "cases_sha256": _sha256(cases_path),
            "gold_sha256": _sha256(gold_path),
            "predictions_sha256": _sha256(predictions_path),
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score host-selected Skill routing without semantic keyword routing")
    parser.add_argument("--cases", type=Path, default=DEFAULT_EVAL / "cases.json")
    parser.add_argument("--gold", type=Path, default=DEFAULT_EVAL / "gold.json")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_EVAL / "host-baseline.json")
    args = parser.parse_args()
    try:
        result = evaluate(args.cases, args.gold, args.predictions)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
