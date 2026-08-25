from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1]
CORE = PLUGIN.parent / "ai-engineering-core"
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(CORE / "scripts"))

import control_trace  # noqa: E402
import control_trace_batch  # noqa: E402
import event_budget  # noqa: E402
from control_event_archive import (  # noqa: E402
    EventArchiveError,
    archive_index_file,
    archive_root,
    read_archive_segment,
)
from control_trace import event_file, status as trace_status  # noqa: E402
from control_trace_batch import record_event_batch  # noqa: E402
from control_trace_store import TraceWriteError  # noqa: E402
from desktop_turn_lifecycle import guard_turn_dispatch  # noqa: E402
from dispatch_state import dispatch_file, load_dispatch  # noqa: E402
from event_budget import (  # noqa: E402
    EVENT_CLASSES,
    action_allowed,
    classify_native_event,
    collect_metrics,
    load_runtime,
    observe_budget,
    record_stream_activity,
)
from governance_state import load_task  # noqa: E402
from turn_summary import read_turn_summary, write_turn_summary  # noqa: E402
from workspacelib import atomic_json  # noqa: E402


def initialize_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
    atomic_json(root / ".ai" / "governance" / "project-state.json", {
        "project_id": "PROJECT-A",
        "session_budget": {"max_active_turns": 2},
    })
    atomic_json(root / ".ai" / "tasks" / "KG-001.json", {
        "task_id": "KG-001", "state": "Development", "control_status": "ACTIVE", "history": [],
    })


def entries(count: int, prefix: str = "EVENT") -> list[dict[str, str]]:
    return [
        {"event_type": "synthetic", "summary_code": "CONTROL_EVENT", "result": "PASS", "operation_id": f"{prefix}-{i}"}
        for i in range(count)
    ]


def percentile_95(values: list[float]) -> float:
    return sorted(values)[max(0, round(len(values) * 0.95) - 1)]


class EventLifecycleTests(unittest.TestCase):
    def project(self):
        project = tempfile.TemporaryDirectory()
        state = tempfile.TemporaryDirectory()
        root = Path(project.name)
        initialize_repo(root)
        return project, state, root

    def test_event_classes_are_explicit_and_trace_is_metadata_only(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}):
            record_event_batch(root, import_id="CLASS-1", entries=entries(1, "CLASS"))
            event = json.loads(event_file(root).read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual({"STATE_EVENT", "CONTROL_EVENT", "TRACE_EVENT", "STREAM_EVENT"}, EVENT_CLASSES)
            self.assertEqual("TRACE_EVENT", event["event_class"])
            self.assertEqual("METADATA_ONLY", event["privacy_class"])

    def test_10001_events_rotate_and_hot_query_p95_stays_bounded(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}):
            before = []
            for _ in range(30):
                started = time.perf_counter(); trace_status(root); before.append((time.perf_counter() - started) * 1000)
            result = record_event_batch(root, import_id="STRESS-10001", entries=entries(10_001, "STRESS"))
            after = []
            for _ in range(30):
                started = time.perf_counter(); trace_status(root); after.append((time.perf_counter() - started) * 1000)
            report = trace_status(root)
            self.assertEqual(10_001, result["committed_count"])
            self.assertLessEqual(report["index"]["segment_count"], control_trace.MAX_SEGMENTS)
            self.assertGreater(report["archive"]["archived_segment_count"], 0)
            self.assertLessEqual(percentile_95(after), max(10.0, percentile_95(before) * 8))

    def test_rotation_archive_can_be_restored_explicitly(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}), patch.object(control_trace, "MAX_SEGMENT_BYTES", 8 * 1024), patch.object(control_trace, "MAX_SEGMENTS", 2):
            record_event_batch(root, import_id="ROTATE-1", entries=entries(80, "ROTATE"))
            index = json.loads(archive_index_file(root).read_text(encoding="utf-8"))
            segment_id = index["recent_segments"][-1]["segment_id"]
            restored = read_archive_segment(root, segment_id)
            self.assertGreater(len(restored), 0)
            self.assertTrue(all(item["event_class"] == "TRACE_EVENT" for item in restored))

    def test_hot_status_does_not_read_damaged_cold_history(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}), patch.object(control_trace, "MAX_SEGMENT_BYTES", 8 * 1024), patch.object(control_trace, "MAX_SEGMENTS", 2):
            record_event_batch(root, import_id="HOT-ONLY", entries=entries(80, "HOT"))
            archive = next(archive_root(root).glob("*.jsonl.gz"))
            archive.write_bytes(b"damaged-cold-segment")
            report = trace_status(root)
            metrics = collect_metrics(root, load_dispatch(root), "KG-001")
            self.assertGreater(report["archive"]["archived_segment_count"], 0)
            self.assertGreaterEqual(metrics["total_event_count"], 80)

    def test_stream_events_are_aggregated_then_removed_on_turn_summary(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}):
            record_stream_activity(root, "thread-a", "KG-001", 10_001, 2_000_000, "STREAM-1")
            summary = write_turn_summary(root, {
                "thread_key": "thread-a", "turn_attempt_id": "TURN-1", "task_id": "KG-001",
                "operation_id": "OP-1", "message_digest": "a" * 64, "status": "CONFIRMED",
                "reserved_at": "2026-01-01T00:00:00+00:00", "confirmed_at": "2026-01-01T00:01:00+00:00",
            }, checkpoint_id="CP-1", changed_surfaces=["src-a.py"], evidence_refs=["TEST-1"])
            restored = read_turn_summary(root, "TURN-1")
            self.assertEqual(10_001, summary["stream_summary"]["event_count"])
            self.assertFalse(summary["stream_summary"]["content_stored"])
            self.assertEqual({}, load_runtime(root)["stream_turns"])
            self.assertEqual(summary["summary_hash"], restored["summary_hash"])

    def test_soft_budget_enters_yellow_and_reduces_concurrency(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}):
            record_stream_activity(root, "thread-a", "KG-001", 5_000, 10_000, "SOFT-STREAM")
            report = observe_budget(root, load_dispatch(root), "KG-001", "ALIVE", "SOFT-OBS")
            self.assertEqual("YELLOW", report["state"])
            self.assertEqual(1, report["max_active_turns"])

    def test_hard_budget_enters_draining_when_stream_is_active(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}):
            record_stream_activity(root, "thread-a", "KG-001", 10_001, 10_000, "HARD-STREAM")
            record_stream_activity(root, "thread-b", "KG-001", 1, 1, "SECOND-STREAM")
            with self.assertRaisesRegex(RuntimeError, "stream Turn budget exceeded"):
                record_stream_activity(root, "thread-c", "KG-001", 1, 1, "THIRD-STREAM")
            report = observe_budget(root, load_dispatch(root), "KG-001", "ALIVE", "HARD-OBS")
            self.assertEqual("DRAINING", report["state"])
            self.assertIn("largest_stream_events", report["reasons"])
            self.assertTrue(report["blocks_new_dispatch"])

    def test_red_pressure_blocks_new_dispatch(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}), patch.dict(event_budget.HARD_LIMITS, {"hot_event_bytes": 1}):
            dispatch = load_dispatch(root)
            pressure = observe_budget(root, dispatch, "KG-001", "ALIVE", "RED-OBS")
            self.assertEqual("RED", pressure["state"])
            dispatch["desktop_pressure"] = pressure; atomic_json(dispatch_file(root), dispatch)
            result = guard_turn_dispatch(
                root, "thread-a", "IDLE", "COMPLETED", "old", "OP-RED",
                hashlib.sha256(b"red-intent").hexdigest(), True, "KG-001", "DISPATCH-RED",
            )
            self.assertEqual("DRAIN_DESKTOP_PRESSURE", result["action"])
            self.assertFalse(result["send_allowed"])

    def test_draining_allows_only_convergence_actions(self):
        pressure = {"state": "DRAINING"}
        self.assertTrue(action_allowed(pressure, "checkpoint"))
        self.assertTrue(action_allowed(pressure, "verify"))
        self.assertTrue(action_allowed(pressure, "archive"))
        self.assertTrue(action_allowed(pressure, "release"))
        self.assertTrue(action_allowed(pressure, "recovery"))
        self.assertFalse(action_allowed(pressure, "dispatch"))

    def test_crash_after_segment_commit_does_not_duplicate_import(self):
        project, state, root = self.project()
        calls = 0
        real_save = control_trace_batch._save_journal

        def fail_after_index(project_root, journal):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected journal failure after segment index commit")
            return real_save(project_root, journal)

        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}):
            with patch.object(control_trace_batch, "_save_journal", side_effect=fail_after_index):
                with self.assertRaises(TraceWriteError):
                    record_event_batch(root, import_id="CRASH-IMPORT", entries=entries(200, "CRASH"))
            recovered = record_event_batch(root, import_id="CRASH-IMPORT", entries=entries(200, "CRASH"))
            self.assertEqual(200, trace_status(root)["index"]["total_event_count"])
            self.assertEqual(200, recovered["committed_count"])

    def test_damaged_archive_segment_fails_closed_on_explicit_read(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}), patch.object(control_trace, "MAX_SEGMENT_BYTES", 8 * 1024), patch.object(control_trace, "MAX_SEGMENTS", 2):
            record_event_batch(root, import_id="DAMAGE-1", entries=entries(80, "DAMAGE"))
            index = json.loads(archive_index_file(root).read_text(encoding="utf-8"))
            segment_id = index["recent_segments"][-1]["segment_id"]
            (archive_root(root) / f"{segment_id}.jsonl.gz").write_bytes(b"damaged")
            with self.assertRaises(EventArchiveError):
                read_archive_segment(root, segment_id)

    def test_event_archive_never_becomes_task_state_authority(self):
        project, state, root = self.project()
        with project, state, patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state.name}), patch.object(control_trace, "MAX_SEGMENT_BYTES", 8 * 1024), patch.object(control_trace, "MAX_SEGMENTS", 2):
            record_event_batch(root, import_id="TASK-FACT", entries=entries(80, "TASK"))
            archive = next(archive_root(root).glob("*.jsonl.gz")); archive.write_bytes(b"damaged")
            task = load_task(root, "KG-001")
            self.assertEqual("Development", task["state"])
            self.assertEqual("ACTIVE", task["control_status"])
            self.assertEqual("STATE_EVENT", classify_native_event("TASK", "STATE:Planning->Development"))
            self.assertEqual("CONTROL_EVENT", classify_native_event("TASK", "CONTROL:pause"))


if __name__ == "__main__":
    unittest.main()
