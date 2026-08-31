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

from community_pro_bridge import (
    detect_pro_runtime,
    establish_current_authority,
    invoke_bridge,
    normalize_current_authority_facts,
    query_project_facts,
    resolve_local_current_authority,
    router_boundary_adoption,
)
import suite_router


def _envelope(
    command: str,
    status: str,
    *,
    ok: bool = True,
    exit_code: int = 0,
    pro_state: str = "PRO_ACTIVE",
    **payload,
) -> str:
    return json.dumps({
        "contract_version": "hiker-cli/v1",
        "command": command,
        "ok": ok,
        "status": status,
        "pro_state": pro_state,
        "exit_code": exit_code,
        **payload,
    })


def _protocol_version(product: str = "5.19.0-rc.8", protocol: int = 2, runtime: str = "0.1.0", schema: str = "3.0.0") -> str:
    return _envelope(
        "version",
        "READY",
        product_version=product,
        runtime_api_version=runtime,
        state_schema_version=schema,
        live_adoption_protocol=protocol,
    )


def _adoption(command: str = "attach", status: str = "LIVE_SESSION_ADOPTED") -> str:
    return _envelope(
        command,
        status,
        project_id="project-1",
        goal_id="goal-1",
        task_id="task-1",
        checkpoint_id="checkpoint-1",
        provider_session_fingerprint="session-hash",
        context_fingerprint="context-hash",
        context_bytes=4096,
        state_reads=12,
        state_writes=6,
        reasons=[],
    )


def _authority_facts() -> dict:
    return {
        "goal": {
            "statement": "Keep the current business goal active",
            "state": "ACTIVE",
            "authority_source": "CONTROLLER_CURRENT_GOAL",
            "authority_generation": 7,
        },
        "task": {
            "statement": "Continue the unique active execution unit",
            "state": "IN_PROGRESS",
            "authority_source": "CONTROLLER_CURRENT_ACTIVE_TASK",
            "authority_generation": 3,
        },
    }


def _authority_establishment(status: str = "ESTABLISHED", *, ok: bool = True, exit_code: int = 0) -> str:
    return _envelope(
        "establish-current-authority",
        status,
        ok=ok,
        exit_code=exit_code,
        pro_state="PRO_ACTIVE" if ok else "PRO_REQUIRED_BLOCKED",
        project_id="project-1",
        goal_id="goal-1",
        task_id="task-1",
        goal_authority_source="CONTROLLER_CURRENT_GOAL",
        task_authority_source="CONTROLLER_CURRENT_ACTIVE_TASK",
        provider_session_fingerprint="session-hash",
        operation_id="current-authority-operation",
        safe_boundary=True,
        state_generation_before=10,
        state_generation_after=11,
        state_reads=8,
        state_writes=2 if status == "ESTABLISHED" else 0,
        idempotent_replay=status == "ALREADY_ESTABLISHED",
        reasons=[],
    )


class CommunityProBridgeTests(unittest.TestCase):
    def _write_current_authority(self, root: Path, *, tasks: int = 1) -> None:
        ai = root / ".ai"; (ai / "governance").mkdir(parents=True); (ai / "tasks").mkdir()
        goal = {"status": "ACTIVE", "goal_id": "GOAL-CURRENT", "revision": 4, "outcome": "Continue current bounded delivery", "fingerprint": "a" * 64}
        (ai / "governance/goal-contract.json").write_text(json.dumps(goal), encoding="utf-8")
        summaries = []
        for number in range(1, tasks + 1):
            task_id = f"KG-{number:03d}"; summaries.append({"task_id": task_id, "state": "Development"})
            task = {"task_id": task_id, "goal": f"Implement slice {number}", "state": "Development", "history": [{"event": "CREATED"}], "goal_binding": {"scope": "project", "goal_id": "GOAL-CURRENT", "revision": 4, "fingerprint": "a" * 64}}
            (ai / f"tasks/{task_id}.json").write_text(json.dumps(task), encoding="utf-8")
        (ai / "governance/task-index.json").write_text(json.dumps({"tasks": summaries}), encoding="utf-8")

    def test_unique_local_goal_and_task_authority_resolve_without_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._write_current_authority(root)
            facts, error, reads = resolve_local_current_authority(root)
        self.assertIsNone(error)
        self.assertEqual("Continue current bounded delivery", facts["goal"]["statement"])
        self.assertEqual("Implement slice 1", facts["task"]["statement"])
        self.assertLessEqual(len(reads), 5)

    def test_multiple_local_current_tasks_remain_authority_ambiguity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._write_current_authority(root, tasks=2)
            facts, error, reads = resolve_local_current_authority(root)
        self.assertIsNone(facts)
        self.assertEqual("MULTIPLE_CURRENT_TASK_AUTHORITIES", error)
        self.assertEqual(4, len(reads))

    def test_current_authority_facts_are_bounded_and_deterministically_fingerprinted(self):
        first, error = normalize_current_authority_facts(_authority_facts())
        second, second_error = normalize_current_authority_facts(_authority_facts())
        self.assertIsNone(error)
        self.assertIsNone(second_error)
        self.assertEqual(first, second)
        self.assertEqual(64, len(first["goal"]["source_fingerprint"]))
        self.assertEqual(64, len(first["task"]["source_fingerprint"]))

    def test_untrusted_authority_source_fails_closed(self):
        facts = _authority_facts()
        facts["task"]["authority_source"] = "MODEL_FREE_SUMMARY"
        normalized, error = normalize_current_authority_facts(facts)
        self.assertIsNone(normalized)
        self.assertEqual("TASK_AUTHORITY_SOURCE_UNTRUSTED", error)

    def test_missing_authority_facts_keeps_current_project_in_community_safe_mode(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            return subprocess.CompletedProcess(
                command,
                2,
                _envelope(
                    "attach", "GOAL_ADOPTION_REQUIRED", ok=False, exit_code=2,
                    pro_state="PRO_DEGRADED", reasons=["NO_PROVABLE_CURRENT_GOAL"],
                ),
                "",
            )

        with tempfile.TemporaryDirectory() as temporary:
            report = router_boundary_adoption(
                Path(temporary),
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("COMMUNITY_SAFE_MODE", report["status"])
        self.assertEqual("CURRENT_AUTHORITY_FACTS_REQUIRED", report["reason"])
        self.assertTrue(report["project_ready"])
        self.assertEqual("NONE", report["user_action_required"])
        self.assertFalse(report["manual_recovery_prompt_required"])
        self.assertEqual(2, len(calls))

    def test_brownfield_authority_establishes_then_existing_attach_live_adopts(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            if command[1] == "establish-current-authority":
                return subprocess.CompletedProcess(command, 0, _authority_establishment(), "")
            if sum(call[1] == "attach" for call in calls) == 1:
                return subprocess.CompletedProcess(
                    command,
                    2,
                    _envelope(
                        "attach", "GOAL_ADOPTION_REQUIRED", ok=False, exit_code=2,
                        pro_state="PRO_DEGRADED", reasons=["NO_PROVABLE_CURRENT_GOAL"],
                    ),
                    "",
                )
            return subprocess.CompletedProcess(command, 0, _adoption(), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = router_boundary_adoption(
                Path(temporary),
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "raw-session"},
                run,
                authority_facts=_authority_facts(),
            )
        self.assertEqual("LIVE_SESSION_ADOPTED", report["status"])
        self.assertEqual("ESTABLISHED", report["authority_establishment"]["status"])
        self.assertEqual(["version", "attach", "establish-current-authority", "attach"], [call[1] for call in calls])
        self.assertNotIn("raw-session", json.dumps(report))
        self.assertNotIn(_authority_facts()["goal"]["statement"], json.dumps(report))
        self.assertNotIn(_authority_facts()["task"]["statement"], json.dumps(report))

    def test_unique_local_authority_auto_converges_to_live_adoption(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            if command[1] == "establish-current-authority":
                return subprocess.CompletedProcess(command, 0, _authority_establishment(), "")
            if sum(call[1] == "attach" for call in calls) == 1:
                return subprocess.CompletedProcess(command, 2, _envelope("attach", "GOAL_ADOPTION_REQUIRED", ok=False, exit_code=2, pro_state="PRO_DEGRADED", reasons=["NO_PROVABLE_CURRENT_GOAL"]), "")
            return subprocess.CompletedProcess(command, 0, _adoption(), "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._write_current_authority(root)
            report = router_boundary_adoption(
                root,
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("LIVE_SESSION_ADOPTED", report["status"])
        self.assertFalse(report["manual_recovery_prompt_required"])
        self.assertEqual("RESOLVED", report["authority_resolution"]["status"])
        self.assertEqual(["DETECT", "CLASSIFY", "RECONCILE", "ESTABLISH_AUTHORITY", "ATTACH", "ADOPT", "RESUME"], report["adoption_flow"])
        self.assertEqual(["version", "attach", "establish-current-authority", "attach"], [call[1] for call in calls])

    def test_ambiguous_local_authority_only_blocks_old_task_resume(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            return subprocess.CompletedProcess(command, 2, _envelope("attach", "TASK_ADOPTION_REQUIRED", ok=False, exit_code=2, pro_state="PRO_DEGRADED", reasons=["NO_PROVABLE_CURRENT_TASK"]), "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._write_current_authority(root, tasks=2)
            report = router_boundary_adoption(
                root,
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("COMMUNITY_SAFE_MODE", report["status"])
        self.assertFalse(report["manual_recovery_prompt_required"])
        self.assertEqual("SELECT_AUTHORITY", report["old_state_resume_user_action"])
        self.assertEqual("NONE", report["user_action_required"])
        self.assertEqual("OLD_STATE_AUTHORITY_QUARANTINED", report["authority_resolution"]["reason"])
        self.assertEqual("AMBIGUOUS", report["new_session_recovery"]["old_state_resumability"])
        self.assertEqual(["version", "attach"], [call[1] for call in calls])

    def test_authority_ambiguity_never_continues_to_attach(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            if command[1] == "attach":
                return subprocess.CompletedProcess(
                    command,
                    2,
                    _envelope(
                        "attach", "TASK_ADOPTION_REQUIRED", ok=False, exit_code=2,
                        pro_state="PRO_DEGRADED", reasons=["NO_PROVABLE_CURRENT_TASK"],
                    ),
                    "",
                )
            return subprocess.CompletedProcess(
                command,
                2,
                _authority_establishment("AUTHORITY_AMBIGUOUS", ok=False, exit_code=2),
                "",
            )

        with tempfile.TemporaryDirectory() as temporary:
            report = router_boundary_adoption(
                Path(temporary),
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
                authority_facts=_authority_facts(),
            )
        self.assertEqual("AUTHORITY_AMBIGUOUS", report["status"])
        self.assertEqual(["version", "attach", "establish-current-authority"], [call[1] for call in calls])

    def test_establishment_invokes_formal_machine_operation_without_manual_ids(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            output = _protocol_version() if command[1] == "version" else _authority_establishment()
            return subprocess.CompletedProcess(command, 0, output, "")

        with tempfile.TemporaryDirectory() as temporary:
            report = establish_current_authority(
                Path(temporary),
                "NEW_TASK",
                _authority_facts(),
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "raw-session"},
                run,
            )
        self.assertTrue(report["authority_established"])
        self.assertNotIn("--project-id", calls[1])
        self.assertNotIn("--goal-id", calls[1])
        self.assertNotIn("--task-id", calls[1])
        self.assertNotIn("--provider-session-id", calls[1])
        self.assertNotIn("raw-session", " ".join(calls[1]))
    def test_missing_pro_runtime_falls_back_without_project_scan(self):
        with patch("community_pro_bridge.shutil.which", return_value=None):
            report = detect_pro_runtime({})
        self.assertEqual("COMMUNITY_FALLBACK", report["status"])
        self.assertEqual("COMMUNITY_FALLBACK", report["pro_state"])
        self.assertEqual("PRO_RUNTIME_NOT_FOUND", report["reason"])

    def test_product_version_is_informational_when_capability_contract_matches(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, _protocol_version("5.18.0"), "")

        report = detect_pro_runtime({"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("PRO_RUNTIME_DETECTED", report["status"])
        self.assertTrue(report["pro_available"])
        self.assertEqual("5.18.0", report["product_version"])
        self.assertEqual({"machine_json": True, "live_adoption": True}, report["feature_availability"])
        self.assertEqual(1, len(calls))

    def test_non_semantic_future_product_label_uses_runtime_capabilities(self):
        def run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, _protocol_version("future-channel"), "")

        report = detect_pro_runtime({"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("PRO_RUNTIME_DETECTED", report["status"])
        self.assertEqual("future-channel", report["product_version"])

    def test_runtime_api_capability_floor_fails_closed(self):
        def run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, _protocol_version(runtime="0.0.9"), "")

        report = detect_pro_runtime({"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("COMMUNITY_FALLBACK", report["status"])
        self.assertEqual("PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE", report["reason"])

    def test_bridge_has_no_product_version_execution_gate(self):
        source = (PLUGIN / "scripts" / "community_pro_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("MINIMUM_PRO_VERSION", source)
        self.assertNotIn("product_version[:", source)

    def test_versioned_runtime_locator_wins_over_stale_path_without_directory_scan(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, _protocol_version(), "")

        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            home = local / "install"
            executable = home / "bin" / ("hiker.exe" if sys.platform == "win32" else "hiker")
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"launcher")
            locator = local / "Hiker" / "pro-runtime.json"
            locator.parent.mkdir(parents=True)
            locator.write_text(json.dumps({
                "contract_version": "hiker-pro-locator/v1",
                "hiker_home": str(home.resolve()),
                "executable": str(executable.resolve()),
                "runtime_identity": "runtime-new",
                "install_generation": 2,
                "activation_epoch": "epoch",
            }), encoding="utf-8")
            with patch("community_pro_bridge.shutil.which", return_value="C:/stale/hiker.exe"):
                report = detect_pro_runtime({"LOCALAPPDATA": str(local)}, run)

        self.assertTrue(report["pro_available"])
        self.assertEqual("PRO_RUNTIME_LOCATOR", report["detection_source"])
        self.assertEqual(str(executable.resolve()), calls[0][0])

    def test_invalid_locator_is_ignored_and_path_fallback_remains_observable(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, _protocol_version(), "")

        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            locator = local / "Hiker" / "pro-runtime.json"
            locator.parent.mkdir(parents=True)
            locator.write_text('{"contract_version":"unknown","executable":"C:/untrusted.exe"}', encoding="utf-8")
            with patch("community_pro_bridge.shutil.which", return_value="C:/path/hiker.exe"):
                report = detect_pro_runtime({"LOCALAPPDATA": str(local)}, run)

        self.assertTrue(report["pro_available"])
        self.assertEqual("PATH", report["detection_source"])
        self.assertEqual("C:/path/hiker.exe", calls[0][0])

    def test_old_pro_runtime_without_machine_contract_falls_back_observably(self):
        def run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, "5.19.0-rc.7 runtime/0.1.0 schema/3.0.0\n", "")

        report = detect_pro_runtime({"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("COMMUNITY_FALLBACK", report["pro_state"])
        self.assertEqual("PRO_MACHINE_CONTRACT_INCOMPATIBLE", report["reason"])

    def test_wrong_live_adoption_protocol_falls_back(self):
        def run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, _protocol_version(protocol=1), "")

        report = detect_pro_runtime({"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("COMMUNITY_FALLBACK", report["status"])
        self.assertEqual("PRO_LIVE_ADOPTION_PROTOCOL_INCOMPATIBLE", report["reason"])

    def test_safe_boundary_invokes_one_machine_attach_without_forwarding_raw_session_id(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            output = _protocol_version() if command[1] == "version" else _adoption()
            return subprocess.CompletedProcess(command, 0, output, "")

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
        self.assertEqual("hiker-cli/v1", report["machine_contract"])
        self.assertEqual(2, len(calls))
        self.assertEqual(["C:/fixture/hiker.exe", "version", "--json"], calls[0])
        self.assertIn("--json", calls[1])
        self.assertIn("--boundary-proof", calls[1])
        self.assertNotIn("raw-session-secret", " ".join(calls[1]))
        self.assertNotIn("raw-session-secret", json.dumps(report))

    def test_missing_safe_boundary_never_calls_attach(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, _protocol_version(), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary),
                "attach",
                None,
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("WAIT_SAFE_BOUNDARY", report["status"])
        self.assertEqual("PRO_DEGRADED", report["pro_state"])
        self.assertEqual(1, len(calls))

    def test_provider_session_unavailable_uses_community_fallback(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, _protocol_version(), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary),
                "attach",
                "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"},
                run,
            )
        self.assertEqual("COMMUNITY_FALLBACK", report["pro_state"])
        self.assertEqual("PROVIDER_SESSION_UNAVAILABLE", report["reason"])
        self.assertEqual(0, len(calls))

    def test_stderr_diagnostic_does_not_break_bridge(self):
        def run(command, **_kwargs):
            output = _protocol_version() if command[1] == "version" else _adoption()
            return subprocess.CompletedProcess(command, 0, output, "hiker: diagnostic only\n")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary), "attach", "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"}, run,
            )
        self.assertTrue(report["adopted"])
        self.assertTrue(report["stderr_diagnostic"])

    def test_primary_json_on_stderr_is_rejected(self):
        def run(command, **_kwargs):
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            payload = _adoption()
            return subprocess.CompletedProcess(command, 0, payload, payload)

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary), "attach", "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"}, run,
            )
        self.assertEqual("PRO_REQUIRED_BLOCKED", report["pro_state"])
        self.assertEqual("PRIMARY_PAYLOAD_ON_STDERR", report["diagnostic"])

    def test_exit_code_contract_mismatch_is_rejected(self):
        def run(command, **_kwargs):
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            return subprocess.CompletedProcess(command, 2, _adoption(), "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary), "attach", "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"}, run,
            )
        self.assertEqual("EXIT_CODE_CONTRACT_MISMATCH", report["diagnostic"])

    def test_blocked_command_has_deterministic_exit_code(self):
        def run(command, **_kwargs):
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            output = _envelope(
                "attach", "AUTHORITY_CONFLICT", ok=False, exit_code=2,
                pro_state="PRO_REQUIRED_BLOCKED", reasons=["AUTHORITY_CONFLICT"],
            )
            return subprocess.CompletedProcess(command, 2, output, "hiker: AUTHORITY_CONFLICT\n")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary), "attach", "NEW_TASK",
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"}, run,
            )
        self.assertEqual(2, report["exit_code"])
        self.assertEqual("PRO_REQUIRED_BLOCKED", report["pro_state"])

    def test_project_facts_are_parsed_through_same_contract(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _protocol_version(), "")
            output = _envelope(
                "project-facts", "READY",
                facts={"project_id": "project-1", "project_architecture": {"value": "bs", "authority": "AUTHORITATIVE_CURRENT"}},
            )
            return subprocess.CompletedProcess(command, 0, output, "")

        with tempfile.TemporaryDirectory() as temporary:
            report = query_project_facts(Path(temporary), {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe"}, run)
        self.assertEqual("bs", report["facts"]["project_architecture"]["value"])
        self.assertIn("--json", calls[1])

    def test_router_boundary_adopts_and_declares_terminal_checkpoint(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            output = _protocol_version() if command[1] == "version" else _adoption()
            return subprocess.CompletedProcess(command, 0, output, "")

        with tempfile.TemporaryDirectory() as temporary:
            report = router_boundary_adoption(
                Path(temporary),
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"},
                run,
            )
        self.assertEqual("LIVE_SESSION_ADOPTED", report["status"])
        self.assertEqual("checkpoint", report["terminal_action"])
        self.assertEqual("TURN_TERMINAL", report["terminal_boundary"])
        self.assertTrue(report["terminal_contract"]["required"])
        self.assertEqual("BEFORE_FINAL_RESPONSE", report["terminal_contract"]["execute_at"])
        self.assertEqual(
            ["TURN_CHECKPOINTED", "ALREADY_CHECKPOINTED"],
            report["terminal_contract"]["success_statuses"],
        )
        self.assertEqual("checkpoint", report["terminal_contract"]["command"][-1])
        self.assertEqual(str(Path(temporary).resolve()), report["terminal_contract"]["command"][-3])
        self.assertEqual(2, len(calls))

    def test_router_boundary_fallback_is_machine_observable(self):
        with tempfile.TemporaryDirectory() as temporary, patch("community_pro_bridge.shutil.which", return_value=None):
            report = router_boundary_adoption(Path(temporary), {"CODEX_THREAD_ID": "session"})
        self.assertEqual("COMMUNITY_FALLBACK", report["pro_state"])
        self.assertFalse(report["pro_available"])

    def test_checkpoint_is_single_bounded_pro_action(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            output = _protocol_version() if command[1] == "version" else _adoption("checkpoint", "TURN_CHECKPOINTED")
            return subprocess.CompletedProcess(command, 0, output, "")

        with tempfile.TemporaryDirectory() as temporary:
            report = invoke_bridge(
                Path(temporary), "checkpoint", None,
                {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"}, run,
            )
        self.assertEqual("TURN_CHECKPOINTED", report["status"])
        self.assertTrue(report["checkpointed"])
        self.assertEqual(2, len(calls))
        self.assertEqual("checkpoint", calls[1][1])
        self.assertIn("--json", calls[1])

    def test_direct_admission_path_invokes_bridge_once(self):
        accepted = {
            "guard_decision": "ACCEPT", "accepted": True, "load": ["skill-path"],
            "receipt_required": True, "diagnostics": [],
        }
        adoption = {"status": "LIVE_SESSION_ADOPTED", "pro_state": "PRO_ACTIVE", "adopted": True, "pro_available": True}
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
            "guard_decision": "ACCEPT", "accepted": True, "reselect_required": False,
            "load": ["skill-path"], "receipt_required": True, "diagnostics": [],
        }
        blocked = {
            "status": "WAIT_SAFE_BOUNDARY", "pro_state": "PRO_DEGRADED",
            "adopted": False, "pro_available": True, "reasons": ["ACTIVE_WRITER"],
        }
        with patch.object(suite_router, "router_boundary_adoption", return_value=blocked):
            suite_router._apply_route_boundary_adoption(Path.cwd(), accepted)
        self.assertEqual("REJECT", accepted["guard_decision"])
        self.assertFalse(accepted["accepted"])
        self.assertEqual([], accepted["load"])
        self.assertEqual("PRO_DEGRADED", accepted["pro_state"])
        self.assertEqual("PRO_LIVE_ADOPTION_REQUIRED", accepted["diagnostics"][-1]["code"])

    def test_community_fallback_does_not_block_selected_skill(self):
        accepted = {
            "guard_decision": "ACCEPT", "accepted": True, "reselect_required": False,
            "load": ["skill-path"], "receipt_required": True, "diagnostics": [],
        }
        fallback = {"status": "COMMUNITY_FALLBACK", "pro_state": "COMMUNITY_FALLBACK", "pro_available": False}
        with patch.object(suite_router, "router_boundary_adoption", return_value=fallback):
            suite_router._apply_route_boundary_adoption(Path.cwd(), accepted)
        self.assertEqual("ACCEPT", accepted["guard_decision"])
        self.assertEqual(["skill-path"], accepted["load"])
        self.assertEqual("COMMUNITY_FALLBACK", accepted["pro_state"])


if __name__ == "__main__":
    unittest.main()
