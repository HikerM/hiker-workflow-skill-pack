from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from corelib import ai_root, read_json


MODE_BUDGETS: dict[str, dict[str, Any]] = {
    "small": {
        "max_active_skills": 2,
        "max_reference_files": 2,
        "max_source_files": 12,
        "max_tool_output_chars": 4000,
        "max_hot_context_chars": 4000,
        "max_pre_action_tool_roundtrips": 1,
        "max_single_tool_seconds": 30,
        "graph_scope": "none-unless-public-surface",
        "history_scope": "current-task-only",
    },
    "standard": {
        "max_active_skills": 2,
        "max_reference_files": 4,
        "max_source_files": 40,
        "max_tool_output_chars": 7000,
        "max_hot_context_chars": 6000,
        "max_pre_action_tool_roundtrips": 1,
        "max_single_tool_seconds": 30,
        "graph_scope": "changed-modules-and-direct-consumers",
        "history_scope": "current-task-and-current-release",
    },
    "large": {
        "max_active_skills": 2,
        "max_reference_files": 6,
        "max_source_files": 80,
        "max_tool_output_chars": 10000,
        "max_hot_context_chars": 8000,
        "max_pre_action_tool_roundtrips": 2,
        "max_single_tool_seconds": 45,
        "graph_scope": "changed-shards-and-risk-reachable-consumers",
        "history_scope": "bounded-index-only",
    },
}

HIGH_RISK_SIGNALS = {
    "cross-repository",
    "public-surface",
    "database-migration",
    "security-boundary",
    "production-release",
    "multiple-writers",
}

SCOPE_EXPANSION_SIGNALS = {
    "architecture-boundary-change",
    "database-migration",
    "deep-investigation",
    "production-release",
}


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=root, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def tracked_file_count(root: Path) -> int | None:
    if not any((candidate / ".git").exists() for candidate in (root.resolve(), *root.resolve().parents)):
        return None
    result = _run(root, "git", "ls-files", "-z")
    if result.returncode != 0:
        return None
    return sum(1 for item in result.stdout.split("\0") if item)


def closed_task_count(root: Path) -> int:
    index: Any = None
    for path in (
        ai_root(root) / "governance" / "task-index.json",
        ai_root(root) / "runtime" / "task-index.json",
    ):
        if path.is_file():
            index = read_json(path, {}) or {}
            break
    if not isinstance(index, dict):
        return 0
    closed = index.get("closed")
    if isinstance(closed, list):
        return len(closed)
    return int(index.get("closed_count") or 0)


def classify_scale(root: Path, signals: set[str] | None = None, tracked_files: int | None = None) -> dict[str, Any]:
    signals = {str(item).strip().lower() for item in (signals or set()) if str(item).strip()}
    files = tracked_files if tracked_files is not None else tracked_file_count(root)
    closed_tasks = closed_task_count(root)
    reasons: list[str] = []

    if files is not None and files >= 10_000:
        mode = "large"
        reasons.append("tracked-files-large")
    elif closed_tasks >= 1_000:
        mode = "large"
        reasons.append("long-running-history")
    elif files is not None and files <= 500 and closed_tasks <= 50:
        mode = "small"
        reasons.append("bounded-small-project")
    else:
        mode = "standard"
        reasons.append("standard-project")

    high_risk = sorted(signals & HIGH_RISK_SIGNALS)
    if high_risk and mode == "small":
        mode = "standard"
        reasons.append("risk-upgrade")
    if {"cross-repository", "multiple-writers"} & signals:
        mode = "large"
        reasons.append("coordination-upgrade")

    return {
        "mode": mode,
        "tracked_file_count": files,
        "closed_task_count": closed_tasks,
        "signals": sorted(signals),
        "reasons": reasons,
    }


def build_context_plan(
    root: Path,
    stage: str,
    changed_paths: list[str] | None = None,
    signals: set[str] | None = None,
    tracked_files: int | None = None,
    active_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scale = classify_scale(root, signals, tracked_files)
    budget = dict(MODE_BUDGETS[scale["mode"]])
    active_facts = active_facts if isinstance(active_facts, dict) else {}
    changed = [str(item).strip().replace("\\", "/")[:240] for item in (changed_paths or []) if str(item).strip()]
    reference_limit = int(budget["max_reference_files"])

    def scalar(name: str) -> str | None:
        value = active_facts.get(name)
        return str(value).strip()[:160] if isinstance(value, (str, int)) and str(value).strip() else None

    def refs(name: str) -> list[str]:
        value = active_facts.get(name)
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:240] for item in value if str(item).strip()][:reference_limit]

    working_set: dict[str, Any] = {
        "changed_paths": changed[: budget["max_source_files"]],
        "read_order": [
            "current-goal",
            "current-task",
            "changed-scope",
            "direct-dependencies",
            "relevant-contracts",
            "relevant-evidence",
        ],
        "never_default_scan": [
            ".ai/archive",
            "all-task-files",
            "all-checkpoints",
            "all-skill-bodies",
            "full-repository-history",
        ],
    }
    if changed:
        working_set["changed_path_count"] = len(changed)
    for key, value in (
        ("current_goal", scalar("current_goal")),
        ("current_task", scalar("current_task")),
        ("direct_dependencies", refs("direct_dependencies")),
        ("relevant_contracts", refs("relevant_contracts")),
        ("relevant_evidence", refs("relevant_evidence")),
    ):
        if value:
            working_set[key] = value
    scope_expansion = sorted(set(scale["signals"]) & SCOPE_EXPANSION_SIGNALS)
    if scope_expansion:
        working_set["scope_expansion"] = {"mode": "EXPLICIT", "reasons": scope_expansion}
    return {
        "schema_version": "1.0.0",
        "stage": str(stage or "unknown").strip().lower() or "unknown",
        "latency_path": "governed" if str(stage or "").lower() in {"governance", "merge", "release"} else "project",
        "scale": scale,
        "budget": budget,
        "working_set": working_set,
        "output_policy": {
            "raw_logs": "store-as-evidence",
            "conversation": "summary-failures-evidence-path",
            "repeat_receipt": False,
            "full_suite_validation": "release-only",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成有界工程上下文预算")
    parser.add_argument("--root", default=".")
    parser.add_argument("--stage", default="unknown")
    parser.add_argument("--changed", action="append", default=[])
    parser.add_argument("--signal", action="append", default=[])
    args = parser.parse_args()
    result = build_context_plan(Path(args.root).resolve(), args.stage, args.changed, set(args.signal))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
