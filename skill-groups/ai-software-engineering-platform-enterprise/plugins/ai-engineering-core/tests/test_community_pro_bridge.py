from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from community_pro_bridge import detect_pro_runtime, invoke_bridge, router_boundary_adoption
import suite_router


class CommunityProBridgeTests(unittest.TestCase):
    def test_missing_pro_runtime_falls_back_without_project_scan(self):
        with patch("community_pro_bridge.shutil.which", return_value=None):
            report = detect_pro_runtime({})
        self.assertEqual("COMMUNITY_FALLBACK", report["status"])
        self.assertEqual("PRO_RUNTIME_NOT_FOUND", report["reason"])

    def test_community_runtime_version_is_not_mistaken_for_pro(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "Hiker runtime/5.18.0 schema/3.0.0\n", "")

        report = detect_pro_runtime({"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("COMMUNITY_FALLBACK", report["status"])
        self.assertEqual("PRO_RUNTIME_INCOMPATIBLE", report["reason"])
        self.assertEqual(1, len(calls))

    def test_safe_boundary_invokes_one_pro_attach_without_forwarding_raw_session_id(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, "5.19.0-rc.6 runtime/0.1.0 schema/3.0.0\n", "")
            payload = {
                "status": "LIVE_SESSION_ADOPTED",
                "project_id": "project-1",
                "goal_id": "goal-1",
                "task_id": "task-1",
                "checkpoint_id": "checkpoint-1",
                "provider_session_fingerprint": "session-hash",
                "context_fingerprint": "context-hash",
                "context_bytes": 4096,
                "state_reads": 12,
                "state_writes": 6,
                "reasons": [],
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary),
                "attach",
                "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "raw-session-secret"},
                run,
            )
        self.assertEqual("LIVE_SESSION_ADOPTED", report["status"])
        self.assertTrue(report["adopted"])
        self.assertEqual(2, len(calls))
        self.assertEqual("attach", calls[1][1])
        self.assertIn("--boundary-proof", calls[1])
        self.assertNotIn("raw-session-secret", " ".join(calls[1]))
        self.assertNotIn("raw-session-secret", json.dumps(report))

    def test_missing_safe_boundary_never_calls_attach(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "5.19.0-rc.6 runtime/0.1.0 schema/3.0.0\n", "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary),
                "attach",
                None,
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("WAIT_SAFE_BOUNDARY", report["status"])
        self.assertEqual(1, len(calls))

    def test_provider_session_unavailable_uses_community_fallback(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "5.19.0-rc.6 runtime/0.1.0 schema/3.0.0\n", "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary),
                "attach",
                "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"},
                run,
            )
        self.assertEqual("COMMUNITY_FALLBACK", report["status"])
        self.assertEqual("PROVIDER_SESSION_UNAVAILABLE", report["reason"])
        self.assertEqual(0, len(calls))

    def test_router_boundary_adopts_without_default_prompt_and_declares_terminal_checkpoint(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, "5.19.0-rc.7 runtime/0.1.0 schema/3.0.0\n", "")
            return subprocess.CompletedProcess(command, 0, json.dumps({
                "status": "LIVE_SESSION_ADOPTED",
                "project_id": "project-1",
                "goal_id": "goal-1",
                "task_id": "task-1",
                "checkpoint_id": "checkpoint-1",
                "provider_session_fingerprint": "session-hash",
                "context_fingerprint": "context-hash",
            }), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = router_boundary_adoption(
                Path(temporary),
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("LIVE_SESSION_ADOPTED", report["status"])
        self.assertEqual("checkpoint", report["terminal_action"])
        self.assertEqual("TURN_TERMINAL", report["terminal_boundary"])
        self.assertEqual(2, len(calls))

    def test_router_boundary_fallback_adds_no_output_contract(self):
        with patch("community_pro_bridge.shutil.which", return_value=None):
            report = router_boundary_adoption(Path.cwd(), {"CODEX_THREAD_ID": "session"})
        self.assertEqual({}, report)

    def test_checkpoint_is_single_bounded_pro_action(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, "5.19.0-rc.6 runtime/0.1.0 schema/3.0.0\n", "")
            return subprocess.CompletedProcess(command, 0, json.dumps({
                "status": "TURN_CHECKPOINTED",
                "project_id": "project-1",
                "goal_id": "goal-1",
                "task_id": "task-1",
                "checkpoint_id": "checkpoint-2",
                "provider_session_fingerprint": "session-hash",
                "context_fingerprint": "context-hash",
            }), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary),
                "checkpoint",
                None,
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("TURN_CHECKPOINTED", report["status"])
        self.assertTrue(report["checkpointed"])
        self.assertEqual(2, len(calls))
        self.assertEqual("checkpoint", calls[1][1])

    def test_direct_admission_path_invokes_bridge_once(self):
        accepted = {
            "guard_decision": "ACCEPT",
            "accepted": True,
            "load": ["skill-path"],
            "receipt_required": True,
            "diagnostics": [],
        }
        adoption = {"status": "LIVE_SESSION_ADOPTED", "adopted": True, "pro_available": True}
        output = StringIO()
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            sys, "argv", ["suite_router.py", "--root", temporary, "--candidate", "backend-quality-review"]
        ), patch.object(suite_router, "route", return_value=accepted.copy()), patch.object(
            suite_router, "router_boundary_adoption", return_value=adoption
        ) as bridge, redirect_stdout(output):
            exit_code = suite_router.main()
        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(adoption, report["pro_live_adoption"])
        bridge.assert_called_once()

    def test_inspect_path_never_probes_or_adopts(self):
        output = StringIO()
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            sys, "argv", ["suite_router.py", "--root", temporary, "--inspect"]
        ), patch.object(suite_router, "inspect_project", return_value={"mode": "PROJECT"}), patch.object(
            suite_router, "router_boundary_adoption"
        ) as bridge, redirect_stdout(output):
            exit_code = suite_router.main()
        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertNotIn("pro_live_adoption", report)
        bridge.assert_not_called()

    def test_rejected_route_never_invokes_bridge(self):
        rejected = {"guard_decision": "REJECT", "accepted": False, "load": [], "diagnostics": []}
        output = StringIO()
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            sys, "argv", ["suite_router.py", "--root", temporary, "--candidate", "backend-quality-review"]
        ), patch.object(suite_router, "route", return_value=rejected), patch.object(
            suite_router, "router_boundary_adoption"
        ) as bridge, redirect_stdout(output):
            exit_code = suite_router.main()
        self.assertEqual(2, exit_code)
        bridge.assert_not_called()

    def test_pro_block_clears_skill_load_and_rejects_project_action(self):
        accepted = {
            "guard_decision": "ACCEPT",
            "accepted": True,
            "reselect_required": False,
            "load": ["skill-path"],
            "receipt_required": True,
            "diagnostics": [],
        }
        blocked = {
            "status": "WAIT_SAFE_BOUNDARY",
            "adopted": False,
            "pro_available": True,
            "reasons": ["ACTIVE_WRITER"],
        }
        with patch.object(suite_router, "router_boundary_adoption", return_value=blocked):
            suite_router._apply_route_boundary_adoption(Path.cwd(), accepted)
        self.assertEqual("REJECT", accepted["guard_decision"])
        self.assertFalse(accepted["accepted"])
        self.assertFalse(accepted["reselect_required"])
        self.assertEqual([], accepted["load"])
        self.assertFalse(accepted["receipt_required"])
        self.assertEqual(blocked, accepted["pro_live_adoption"])
        self.assertEqual("PRO_LIVE_ADOPTION_REQUIRED", accepted["diagnostics"][-1]["code"])


if __name__ == "__main__":
    unittest.main()
