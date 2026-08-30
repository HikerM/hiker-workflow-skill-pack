from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "hiker-resource-budget/v1"

HARD_MAX: dict[str, dict[str, int]] = {
    "execution": {
        "max_resident_slots": 6,
        "max_pending_creates": 1,
        "max_writer_slots": 2,
        "max_active_turns": 2,
    },
    "task": {
        "max_active_write_tasks": 2,
        "max_total_active_tasks": 5,
        "max_merge_debt": 2,
        "max_planned_lanes": 8,
    },
    "context": {
        "active_context_max_chars": 12_000,
        "session_context_max_chars": 6_500,
        "max_items_per_section": 12,
        "max_recent_checkpoints": 12,
        "max_milestone_checkpoints": 8,
        "max_ledger_entries": 32,
        "max_task_index_closed": 200,
        "max_task_history_events": 40,
        "max_task_history_ledger_entries": 20,
        "max_session_epoch_turns": 40,
        "max_session_epoch_tool_calls": 80,
        "max_session_epoch_tool_output_chars": 120_000,
        "max_session_epoch_compactions": 2,
    },
    "event": {
        "task_hot_events": 64,
        "turn_hot_events": 32,
        "hot_event_bytes": 2 * 1024 * 1024,
        "trace_segment_bytes": 384 * 1024,
        "growth_per_minute": 5_000,
        "active_turns": 3,
        "streaming_turns": 2,
        "largest_stream_events": 10_000,
        "max_observations": 32,
        "max_observation_ids": 64,
    },
    "manifest_scan": {
        "max_depth": 8,
        "max_dirs": 256,
        "max_manifests": 128,
        "max_bytes": 4 * 1024 * 1024,
        "max_entries_per_dir": 512,
    },
    "source_scan": {
        "max_depth": 9,
        "max_dirs": 500,
        "max_files": 6_000,
    },
    "input": {
        "project_fact_file_bytes": 1024 * 1024,
        "runtime_locator_bytes": 64 * 1024,
    },
    "implementation_registry": {
        "max_capabilities": 128,
        "max_implementations": 256,
        "max_boundary_values": 64,
        "max_comparisons": 32_768,
        "max_file_bytes": 1024 * 1024,
    },
    "output": {
        "admission_output_chars": 4_000,
        "command_output_chars": 120_000,
        "artifact_spool_bytes": 128 * 1024 * 1024,
    },
}

DEFAULT_BUDGETS: dict[str, dict[str, int]] = {
    "execution": dict(HARD_MAX["execution"]),
    "task": {
        "max_active_write_tasks": 2, "max_total_active_tasks": 5,
        "max_merge_debt": 2, "max_planned_lanes": 8,
    },
    "context": {
        "active_context_max_chars": 8_000,
        "session_context_max_chars": 4_000,
        "max_items_per_section": 8,
        "max_recent_checkpoints": 8,
        "max_milestone_checkpoints": 6,
        "max_ledger_entries": 24,
        "max_task_index_closed": 120,
        "max_task_history_events": 40,
        "max_task_history_ledger_entries": 20,
        "max_session_epoch_turns": 20,
        "max_session_epoch_tool_calls": 40,
        "max_session_epoch_tool_output_chars": 60_000,
        "max_session_epoch_compactions": 1,
    },
    "event": dict(HARD_MAX["event"]),
    "manifest_scan": {
        "max_depth": 4, "max_dirs": 96, "max_manifests": 48,
        "max_bytes": 512 * 1024, "max_entries_per_dir": 512,
    },
    "source_scan": dict(HARD_MAX["source_scan"]),
    "input": dict(HARD_MAX["input"]),
    "implementation_registry": {
        "max_capabilities": 64, "max_implementations": 128,
        "max_boundary_values": 32, "max_comparisons": 8_192,
        "max_file_bytes": 512 * 1024,
    },
    "output": {"admission_output_chars": 4_000, "command_output_chars": 4_000, "artifact_spool_bytes": 16 * 1024 * 1024},
}


def effective_budget(domain: str, requested: Mapping[str, Any] | None = None) -> dict[str, int]:
    if domain not in HARD_MAX:
        raise KeyError(f"unknown resource budget domain: {domain}")
    requested = requested or {}
    defaults = DEFAULT_BUDGETS[domain]
    result: dict[str, int] = {}
    for key, hard_max in HARD_MAX[domain].items():
        raw = requested.get(key, defaults[key])
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = defaults[key]
        if value <= 0:
            value = defaults[key]
        result[key] = min(value, hard_max)
    return result


def effective_value(domain: str, key: str, requested: Any = None) -> int:
    values = {} if requested is None else {key: requested}
    return effective_budget(domain, values)[key]


def authority_receipt() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "hard_max": {domain: dict(values) for domain, values in HARD_MAX.items()},
        "rule": "EFFECTIVE_BUDGET_LESS_THAN_OR_EQUAL_TO_HARD_MAX",
    }
