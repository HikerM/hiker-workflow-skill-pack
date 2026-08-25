from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(PLUGIN.parent / "ai-engineering-core" / "scripts"))

from control_kernel import operation_file  # noqa: E402
from desktop_pressure import active_lease_count as active_turn_count  # noqa: E402
from desktop_turn_lifecycle import (  # noqa: E402
    acknowledge_turn_dispatch,
    confirm_turn,
    guard_turn_dispatch,
    heartbeat_turn,
    observe_desktop_pressure,
    probe_interrupted_dispatch,
    probe_turn_host,
)
from dispatch_state import dispatch_file, load_dispatch  # noqa: E402
from event_budget import load_runtime as load_event_runtime  # noqa: E402
from event_budget import record_stream_activity  # noqa: E402
from file_lock import lock_file, release as release_file_locks  # noqa: E402
from session_pool import bind as bind_session  # noqa: E402
from session_pool import complete as complete_session  # noqa: E402
from session_pool import status as session_status  # noqa: E402
from turn_lease import active_lease_count, lease_file  # noqa: E402
from turn_summary import read_turn_summary  # noqa: E402
from workspacelib import atomic_json  # noqa: E402


def ns(**values):
    return argparse.Namespace(**values)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def initialize_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
    (root / ".ai" / "governance").mkdir(parents=True)
    atomic_json(root / ".ai" / "governance" / "project-state.json", {
        "project_id": "PROJECT-A",
        "session_budget": {"max_active_turns": 2},
    })


def write_task(root: Path, control_status: str = "ACTIVE") -> None:
    atomic_json(root / ".ai" / "tasks" / "KG-001.json", {
        "task_id": "KG-001",
        "state": "Development",
        "control_status": control_status,
        "history": [],
    })


def seed_operation(root: Path, operation_id: str, status: str, before: str = "before-1") -> None:
    committed = "after-1" if status in {"DOMAIN_COMMITTED", "TRACE_PENDING", "COMPLETE"} else None
    atomic_json(operation_file(root), {
        "schema_version": "2.0.0",
        "revision": 1,
        "operations": {
            operation_id: {
                "operation_id": operation_id,
                "operation_type": "test-domain-change",
                "task_id": "KG-001",
                "status": status,
                "before_fingerprint": before,
                "intended_after_fingerprint": "intended-1",
                "committed_after_fingerprint": committed,
                "trace_status": "COMMITTED" if status == "COMPLETE" else "PENDING",
                "retry_count": 0,
            }
        },
    })


def reserve_and_start(
    root: Path,
    thread_id: str,
    operation_id: str,
    *,
    task_id: str | None = "KG-001",
    dispatch_id: str | None = None,
    host_pid: int | None = None,
) -> None:
    reserved = guard_turn_dispatch(
        root, thread_id, "IDLE", "COMPLETED", f"old-{thread_id}", operation_id,
        digest(operation_id), True, task_id, dispatch_id or operation_id, host_pid,
    )
    if not reserved["send_allowed"]:
        raise AssertionError(reserved)
    acknowledge_turn_dispatch(root, thread_id, operation_id, True)
    active = guard_turn_dispatch(
        root, thread_id, "ACTIVE", "RUNNING", f"new-{thread_id}", operation_id,
        digest(operation_id), False, task_id, dispatch_id or operation_id,
    )
    if active["turn_state"] != "ACTIVE":
        raise AssertionError(active)


def interrupt_backend(root: Path) -> None:
    result = observe_desktop_pressure(root, ns(
        active_tasks=12,
        streaming_tasks=7,
        active_turns=9,
        loaded_projects=1700,
        incremental_events=64000,
        largest_task_bytes=71 * 1024 * 1024,
        backend_status="MISSING",
        observation_id="OBS-MISSING",
    ))
    if not result["interrupted_dispatches"]:
        raise AssertionError(result)


class DesktopLifecycleTests(unittest.TestCase):
    def test_case_1_normal_task_turn_operation_completion_and_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root); seed_operation(root, "OP-1", "COMPLETE")
            bind_session(root, "PROJECT-A", "KG-001", "Developer Agent", str(root), "base-a", "thread-a", None, "RUNNING")
            reserve_and_start(root, "thread-a", "OP-1", host_pid=os.getpid())
            active_turn = next(iter(load_dispatch(root)["turn_leases"].values()))
            record_stream_activity(root, active_turn["thread_key"], "KG-001", 1_000, 64_000, "STREAM-OP-1")
            completing = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "new-thread-a", task_id="KG-001")
            self.assertEqual("COMPLETING", completing["turn_state"])
            confirmed = confirm_turn(root, "thread-a", "OP-1", "CP-1")
            self.assertEqual("CONFIRMED", confirmed["turn_state"])
            summary = read_turn_summary(root, active_turn["turn_attempt_id"])
            self.assertEqual(1_000, summary["stream_summary"]["event_count"])
            self.assertFalse(summary["stream_summary"]["content_stored"])
            self.assertEqual({}, load_event_runtime(root)["stream_turns"])
            self.assertEqual(0, active_lease_count(root))
            atomic_json(lock_file(root), {"schema_version": "2.0.0", "locks": [{"task_id": "KG-001", "path": "src/a.py"}]})
            release_file_locks(root, ns(task_id="KG-001", paths=[]))
            completed = complete_session(root, "PROJECT-A", "KG-001", "Developer Agent", str(root), "PASS", "CP-1", True, True, "CLEAN")
            self.assertTrue(completed["ok"])
            self.assertEqual("IDLE_REUSABLE", completed["slot"]["state"])
            dispatch = load_dispatch(root)
            self.assertEqual(0, active_turn_count(dispatch))
            self.assertEqual({}, dispatch["turn_leases"])
            self.assertEqual("CONFIRMED", dispatch["turn_archive"][-1]["status"])
            self.assertEqual(0, active_lease_count(root))
            self.assertEqual({"IDLE_REUSABLE": 1}, session_status(root, "PROJECT-A")["counts"])

    def test_case_2_backend_dies_before_domain_commit_is_retryable_but_not_auto_resent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root); seed_operation(root, "OP-2", "FAILED_BEFORE_COMMIT")
            reserve_and_start(root, "thread-a", "OP-2")
            interrupt_backend(root)
            result = probe_interrupted_dispatch(root, "thread-a", "OP-2")
            self.assertEqual("RETRYABLE", result["turn_state"])
            self.assertTrue(result["new_turn_allowed"])
            self.assertFalse(result["automatic_resend"])

    def test_case_3_backend_dies_after_domain_commit_recovers_without_replay(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root); seed_operation(root, "OP-3", "DOMAIN_COMMITTED")
            reserve_and_start(root, "thread-a", "OP-3")
            interrupt_backend(root)
            checkpoint = root / ".ai/runtime/checkpoints/cp-3.json"
            atomic_json(checkpoint, {"operation_id": "OP-3", "task": {"task_id": "KG-001"}})
            result = probe_interrupted_dispatch(root, "thread-a", "OP-3", checkpoint_path=".ai/runtime/checkpoints/cp-3.json")
            self.assertEqual("RECOVERED", result["turn_state"])
            self.assertFalse(result["new_turn_allowed"])
            self.assertEqual("VALID", result["checkpoint"]["status"])
            self.assertTrue(result["checkpoint"]["operation_recorded"])
            journal = json.loads(operation_file(root).read_text(encoding="utf-8"))
            self.assertEqual(0, journal["operations"]["OP-3"]["retry_count"])
            duplicate = guard_turn_dispatch(root, "thread-b", "IDLE", "COMPLETED", "old-b", "OP-3", digest("OP-3"), True, "KG-001", "OP-3")
            self.assertEqual("BLOCK_DUPLICATE_DISPATCH", duplicate["action"])

    def test_case_4_ambiguous_prepared_operation_requires_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root); seed_operation(root, "OP-4", "PREPARED")
            reserve_and_start(root, "thread-a", "OP-4")
            interrupt_backend(root)
            result = probe_interrupted_dispatch(root, "thread-a", "OP-4", current_domain_fingerprint="different")
            self.assertEqual("REVIEW_REQUIRED", result["turn_state"])
            blocked = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", operation_id="OP-4", message_digest=digest("OP-4"), task_id="KG-001", dispatch_id="OP-4")
            self.assertEqual("RECOVERY_PROBE_REQUIRED", blocked["action"])

    def test_case_5_renderer_duplicate_dispatch_cannot_create_two_active_turns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root)
            first = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "old-a", "OP-5", digest("same-intent"), True, "KG-001", "DISPATCH-5")
            second = guard_turn_dispatch(root, "thread-b", "IDLE", "COMPLETED", "old-b", "OP-5", digest("same-intent"), True, "KG-001", "DISPATCH-5")
            self.assertEqual("DISPATCH_RESERVED", first["action"])
            self.assertEqual("BLOCK_DUPLICATE_DISPATCH", second["action"])
            self.assertEqual(1, active_turn_count(load_dispatch(root)))

    def test_case_6_expired_lease_does_not_interrupt_a_live_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root)
            reserved = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "old-a", "OP-6", digest("intent-6"), True, "KG-001", "DISPATCH-6", os.getpid())
            path = lease_file(root, reserved["thread_key"])
            lease = json.loads(path.read_text(encoding="utf-8")); lease["expires_epoch"] = 0; atomic_json(path, lease)
            probe = probe_turn_host(root, "thread-a")
            self.assertEqual("ALIVE", probe["owner_status"])
            self.assertTrue(probe["expired_hint"])
            self.assertEqual("RESERVED", probe["turn_state"])

    def test_case_7_pid_reuse_is_identity_mismatch_not_live_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root)
            reserved = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "old-a", "OP-7", digest("intent-7"), True, "KG-001", "DISPATCH-7", os.getpid())
            path = lease_file(root, reserved["thread_key"])
            lease = json.loads(path.read_text(encoding="utf-8")); lease["owner_identity"]["process_fingerprint"] = "f" * 64; atomic_json(path, lease)
            probe = probe_turn_host(root, "thread-a")
            self.assertEqual("IDENTITY_CHANGED", probe["lease"]["owner_status"])
            self.assertEqual("INTERRUPTED_UNKNOWN", probe["turn_state"])

    def test_case_8_app_server_restart_requires_old_turn_recovery_before_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root)
            reserved = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "old-a", "OP-8", digest("intent-8"), True, "KG-001", "DISPATCH-8", os.getpid())
            path = lease_file(root, reserved["thread_key"])
            lease = json.loads(path.read_text(encoding="utf-8")); lease["owner_identity"]["process_fingerprint"] = "e" * 64; atomic_json(path, lease)
            probe_turn_host(root, "thread-a")
            replacement = guard_turn_dispatch(root, "thread-b", "IDLE", "COMPLETED", "old-b", "OP-8", digest("intent-8"), True, "KG-001", "DISPATCH-8", os.getpid())
            self.assertEqual("BLOCK_DUPLICATE_DISPATCH", replacement["action"])
            self.assertFalse(replacement["send_allowed"])

    def test_case_9_pause_blocks_dispatch_and_resume_keeps_same_task(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root, "PAUSED")
            paused = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", task_id="KG-001", operation_id="OP-9", message_digest=digest("intent-9"), dispatch_id="DISPATCH-9", reserve=True)
            self.assertEqual("BLOCK_TASK_CONTROL", paused["action"])
            write_task(root, "ACTIVE")
            resumed = guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", task_id="KG-001", operation_id="OP-9", message_digest=digest("intent-9"), dispatch_id="DISPATCH-9", reserve=True)
            self.assertEqual("DISPATCH_RESERVED", resumed["action"])
            self.assertEqual("KG-001", load_dispatch(root)["turn_leases"][resumed["thread_key"]]["task_id"])

    def test_case_10_release_fails_closed_until_turn_lease_and_lock_are_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root); seed_operation(root, "OP-10", "COMPLETE")
            bind_session(root, "PROJECT-A", "KG-001", "Developer Agent", str(root), "base-a", "thread-a", None, "RUNNING")
            reserve_and_start(root, "thread-a", "OP-10")
            atomic_json(lock_file(root), {"schema_version": "2.0.0", "locks": [{"task_id": "KG-001", "path": "src/a.py"}]})
            blocked = complete_session(root, "PROJECT-A", "KG-001", "Developer Agent", str(root), "PASS", "CP-10", True, True, "CLEAN")
            self.assertIn("Turn is not confirmed or recovered", blocked["blockers"])
            self.assertIn("file locks remain registered", blocked["blockers"])
            guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "new-thread-a", task_id="KG-001")
            confirm_turn(root, "thread-a", "OP-10", "CP-10")
            release_file_locks(root, ns(task_id="KG-001", paths=[]))
            released = complete_session(root, "PROJECT-A", "KG-001", "Developer Agent", str(root), "PASS", "CP-10", True, True, "CLEAN")
            self.assertTrue(released["ok"])
            self.assertEqual("IDLE_REUSABLE", released["slot"]["state"])
            self.assertEqual(1, released["slot"]["terminal_task_count"])

    def test_heartbeat_is_coalesced_and_does_not_write_trace_or_dispatch_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root)
            reserve_and_start(root, "thread-a", "OP-HB", host_pid=os.getpid())
            turn = next(iter(load_dispatch(root)["turn_leases"].values()))
            lease_path = lease_file(root, turn["thread_key"])
            before = (dispatch_file(root).stat().st_mtime_ns, lease_path.stat().st_mtime_ns)
            result = heartbeat_turn(root, "thread-a", os.getpid())
            self.assertFalse(result["write_performed"])
            self.assertEqual("ALIVE", result["owner_status"])
            self.assertEqual(before, (dispatch_file(root).stat().st_mtime_ns, lease_path.stat().st_mtime_ns))

    def test_raw_turn_message_cannot_be_persisted_as_a_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize_repo(root); write_task(root)
            with self.assertRaisesRegex(ValueError, "raw message content is forbidden"):
                guard_turn_dispatch(root, "thread-a", "IDLE", "COMPLETED", "old", "OP-RAW", "raw prompt text", True, "KG-001", "DISPATCH-RAW")
            self.assertEqual({}, load_dispatch(root)["turn_leases"])


if __name__ == "__main__":
    unittest.main()
