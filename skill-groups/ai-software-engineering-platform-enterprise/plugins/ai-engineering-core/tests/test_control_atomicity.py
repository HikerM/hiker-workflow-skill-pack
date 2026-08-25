from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import control_kernel
import control_trace
import process_identity
from control_kernel import execute_operation, operation_file
from control_trace import control_root, record_event
from control_trace_store import TraceStateError, trace_lock
from corelib import atomic_write_json


def file_fingerprint(path: Path) -> str:
    payload = path.read_bytes() if path.is_file() else b"MISSING"
    return hashlib.sha256(payload).hexdigest()


class DomainHarness:
    def __init__(self, root: Path, operation_id: str, target: str):
        self.root = root
        self.operation_id = operation_id
        self.target = target
        self.path = root / "domain.json"
        self.commit_calls = 0
        self.trace_calls = 0
        self.crash_before_commit = False
        self.crash_after_domain_commit = False

    def prepare(self) -> dict[str, str]:
        before = file_fingerprint(self.path)
        intended = hashlib.sha256(f"{before}|{self.target}".encode("ascii")).hexdigest()
        return {"before_fingerprint": before, "intended_after_fingerprint": intended}

    def result(self, recovered: bool) -> dict[str, object]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "domain_result": {
                "task_id": "KG-001",
                "state": data["state"],
                "mutation_count": data["mutation_count"],
                "recovered_after_interruption": recovered,
            },
            "committed_after_fingerprint": file_fingerprint(self.path),
        }

    def commit(self) -> dict[str, object]:
        self.commit_calls += 1
        if self.crash_before_commit:
            self.crash_before_commit = False
            raise SystemExit("injected PREPARED crash")
        prior = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        atomic_write_json(self.path, {
            "operation_id": self.operation_id,
            "state": self.target,
            "mutation_count": int(prior.get("mutation_count") or 0) + 1,
        })
        return self.result(False)

    def recover(self, entry: dict[str, object]) -> dict[str, object]:
        current = file_fingerprint(self.path)
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("operation_id") == self.operation_id:
                return {"status": "COMMITTED", **self.result(True)}
        return {"status": "NOT_COMMITTED", "current_fingerprint": current}

    def trace(self, _: dict[str, object]) -> dict[str, object]:
        self.trace_calls += 1
        if self.crash_after_domain_commit:
            self.crash_after_domain_commit = False
            raise SystemExit("injected DOMAIN_COMMITTED crash")
        return record_event(
            self.root,
            event_type="state-transition",
            summary_code="STATE_TRANSITIONED",
            result="PASS",
            operation_id=self.operation_id,
        )

    def execute(self) -> dict[str, object]:
        return execute_operation(
            self.root,
            operation_id=self.operation_id,
            command="transition",
            payload={"task_id": "KG-001", "target": self.target},
            prepare=self.prepare,
            commit_domain=self.commit,
            recover_domain=self.recover,
            commit_trace=self.trace,
        )


class ControlAtomicityTests(unittest.TestCase):
    def test_live_owner_is_never_reclaimed_by_age(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                lock = control_root(root) / "trace.lock"
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text(json.dumps({
                    "pid": os.getpid(), "created": time.time() - 3600, "token": "live",
                    "runtime_identity": process_identity.process_identity(os.getpid()),
                }), encoding="ascii")
                with self.assertRaises(TimeoutError):
                    with trace_lock(root, timeout=0.05, stale_after=0.01):
                        pass
                self.assertTrue(lock.is_file())

    def test_dead_owner_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                lock = control_root(root) / "trace.lock"
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text(json.dumps({"pid": 999_999_999, "created": time.time() - 1, "token": "dead"}), encoding="ascii")
                with trace_lock(root, timeout=0.2):
                    self.assertTrue(lock.is_file())
                self.assertFalse(lock.exists())

    def test_pid_reuse_identity_mismatch_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                lock = control_root(root) / "trace.lock"
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text(json.dumps({
                    "pid": os.getpid(), "created": time.time() - 1, "token": "reused",
                    "runtime_identity": {"identity_version": "pid-start-v1", "pid": os.getpid(), "process_fingerprint": "f" * 64},
                }), encoding="ascii")
                replacement = {"identity_version": "pid-start-v1", "pid": os.getpid(), "process_fingerprint": "e" * 64}
                with patch.object(process_identity, "pid_presence", return_value=True), patch.object(process_identity, "process_identity", return_value=replacement):
                    with trace_lock(root, timeout=0.2):
                        self.assertTrue(lock.is_file())
                self.assertFalse(lock.exists())

    def test_damaged_lock_requires_controlled_recovery(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                lock = control_root(root) / "trace.lock"
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text("{damaged", encoding="ascii")
                with self.assertRaises(TraceStateError):
                    with trace_lock(root, timeout=0.05, stale_after=0.01):
                        pass
                self.assertEqual("{damaged", lock.read_text(encoding="ascii"))

    def test_domain_commit_then_trace_failure_returns_business_success_and_retry_only_traces(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            harness = DomainHarness(root, "OP-TRACE-PENDING", "Development")
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                with patch.object(control_trace, "_append", side_effect=OSError("injected append failure")):
                    pending = harness.execute()
                self.assertTrue(pending["business_committed"])
                self.assertEqual("TRACE_PENDING", pending["operation_status"])
                self.assertEqual("PENDING", pending["trace_status"])
                recovered = harness.execute()
                journal = json.loads(operation_file(root).read_text(encoding="utf-8"))
                entry = journal["operations"]["OP-TRACE-PENDING"]
            self.assertEqual(1, harness.commit_calls)
            self.assertEqual(1, recovered["mutation_count"])
            self.assertEqual("COMPLETE", recovered["operation_status"])
            self.assertEqual("COMPLETE", entry["status"])
            self.assertEqual("COMMITTED", entry["trace_status"])
            self.assertEqual(1, entry["retry_count"])
            for field in ("before_fingerprint", "intended_after_fingerprint", "committed_after_fingerprint", "domain_commit_timestamp"):
                self.assertTrue(entry[field])

    def test_trace_commit_then_final_journal_failure_recovers_without_domain_replay(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            harness = DomainHarness(root, "OP-FINALIZE-PENDING", "Testing")
            writes = 0
            real_write = control_kernel.atomic_write_json

            def fail_final(path: Path, data: dict[str, object]) -> None:
                nonlocal writes
                writes += 1
                if writes == 3:
                    raise OSError("injected final journal failure")
                real_write(path, data)

            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                with patch.object(control_kernel, "atomic_write_json", side_effect=fail_final):
                    pending = harness.execute()
                self.assertEqual("FINALIZE_PENDING", pending["journal_status"])
                recovered = harness.execute()
            self.assertEqual(1, harness.commit_calls)
            self.assertEqual(1, recovered["mutation_count"])
            self.assertEqual("COMPLETE", recovered["operation_status"])
            self.assertTrue(recovered["trace"]["idempotent_replay"])

    def test_prepared_crash_can_continue_once(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            harness = DomainHarness(root, "OP-PREPARED-CRASH", "Development")
            harness.crash_before_commit = True
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                with self.assertRaises(SystemExit):
                    harness.execute()
                prepared = json.loads(operation_file(root).read_text(encoding="utf-8"))
                self.assertEqual("PREPARED", prepared["operations"]["OP-PREPARED-CRASH"]["status"])
                recovered = harness.execute()
            self.assertEqual(2, harness.commit_calls)
            self.assertEqual(1, recovered["mutation_count"])

    def test_domain_committed_crash_never_replays_domain(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            harness = DomainHarness(root, "OP-DOMAIN-CRASH", "Review")
            harness.crash_after_domain_commit = True
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                with self.assertRaises(SystemExit):
                    harness.execute()
                committed = json.loads(operation_file(root).read_text(encoding="utf-8"))
                self.assertEqual("DOMAIN_COMMITTED", committed["operations"]["OP-DOMAIN-CRASH"]["status"])
                recovered = harness.execute()
            self.assertEqual(1, harness.commit_calls)
            self.assertEqual(1, recovered["mutation_count"])
            self.assertEqual("COMPLETE", recovered["operation_status"])


if __name__ == "__main__":
    unittest.main()
