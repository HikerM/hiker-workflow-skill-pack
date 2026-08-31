from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from bootstrap_project import initialize, prepare_for_new_session
from community_pro_bridge import router_boundary_adoption
from state_consistency import recover_for_new_session


def _envelope(command: str, status: str, *, ok: bool, exit_code: int, pro_state: str, **values) -> str:
    return json.dumps({
        "contract_version": "hiker-cli/v1",
        "command": command,
        "ok": ok,
        "status": status,
        "exit_code": exit_code,
        "pro_state": pro_state,
        **values,
    })


def _version() -> str:
    return _envelope(
        "version", "VERSION", ok=True, exit_code=0, pro_state="PRO_ACTIVE",
        product_version="5.19.0-rc.fixture", runtime_api_version="0.1.0",
        live_adoption_protocol=2, state_schema_version="3.0.0",
    )


def _adopted() -> str:
    return _envelope(
        "attach", "LIVE_SESSION_ADOPTED", ok=True, exit_code=0, pro_state="PRO_ACTIVE",
        project_id="PROJECT-FIXTURE", goal_id="GOAL-FIXTURE", task_id="TASK-FIXTURE",
        checkpoint_id="CHECKPOINT-FIXTURE", provider_session_fingerprint="b" * 64,
        context_fingerprint="c" * 64, context_bytes=512, state_reads=6, state_writes=1,
        reasons=[],
    )


class NewSessionRecoveryFieldTests(unittest.TestCase):
    def _project(self, root: Path) -> None:
        (root / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")

    def _git_project(self, root: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "fixture.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
        self._project(root)
        subprocess.run(["git", "add", "package.json"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _authority(self, root: Path, tasks: int = 1) -> None:
        ai = root / ".ai"
        (ai / "governance").mkdir(parents=True, exist_ok=True)
        (ai / "tasks").mkdir(parents=True, exist_ok=True)
        goal = {
            "status": "ACTIVE", "goal_id": "GOAL-CURRENT", "revision": 2,
            "outcome": "Continue the bounded current goal", "fingerprint": "a" * 64,
        }
        (ai / "governance/goal-contract.json").write_text(json.dumps(goal), encoding="utf-8")
        summaries = []
        for number in range(tasks):
            task_id = f"TASK-{number + 1}"
            summaries.append({"task_id": task_id, "state": "Development"})
            task = {
                "task_id": task_id, "goal": f"Continue slice {number + 1}", "state": "Development",
                "history": [{"event": "CREATED"}],
                "goal_binding": {
                    "scope": "project", "goal_id": "GOAL-CURRENT", "revision": 2,
                    "fingerprint": "a" * 64,
                },
            }
            (ai / "tasks" / f"{task_id}.json").write_text(json.dumps(task), encoding="utf-8")
        (ai / "governance/task-index.json").write_text(json.dumps({"tasks": summaries}), encoding="utf-8")

    def _adoption_runner(self, calls: list[list[str]]):
        def run(command, **_kwargs):
            calls.append(command)
            payload = _version() if command[1] == "version" else _adopted()
            return subprocess.CompletedProcess(command, 0, payload, "")
        return run

    def test_existing_project_valid_ai_new_session_automatic_attach(self):
        calls: list[list[str]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); initialize(root)
            report = router_boundary_adoption(
                root, {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "new-session"},
                self._adoption_runner(calls),
            )
        self.assertTrue(report["adopted"])
        self.assertEqual("READY", report["new_session_recovery"]["project_usability"])
        self.assertEqual(["version", "attach"], [call[1] for call in calls])

    def test_existing_project_without_ai_automatically_bootstraps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root)
            report = prepare_for_new_session(root)
            self.assertEqual("NO_AI_DIRECTORY", report["classification"])
            self.assertEqual("NONE", report["user_action_required"])
            self.assertTrue((root / ".ai/schema.json").is_file())
            self.assertTrue((root / ".ai/governance/source-provenance.json").is_file())

    def test_legacy_ai_without_provenance_is_quarantined_but_project_is_usable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root)
            (root / ".ai/runtime").mkdir(parents=True)
            (root / ".ai/runtime/task.json").write_text(json.dumps({"id": "OLD", "status": "Development"}), encoding="utf-8")
            report = prepare_for_new_session(root)
            self.assertEqual("LEGACY_AI_WITHOUT_PROVENANCE", report["classification"])
            self.assertEqual("READY", report["project_usability"])
            self.assertEqual("NONE", report["user_action_required"])
            self.assertNotEqual("OLD", json.loads((root / ".ai/runtime/task.json").read_text(encoding="utf-8"))["id"])
            self.assertTrue(list((root / ".ai/recovery/quarantine").glob("*/runtime/task.json")))

    def test_partial_ai_rebuilds_missing_derived_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); initialize(root)
            (root / ".ai/context/tech-stack.json").unlink()
            report = prepare_for_new_session(root)
            self.assertEqual("PARTIAL_AI", report["classification"])
            self.assertTrue((root / ".ai/context/tech-stack.json").is_file())
            self.assertFalse(report["full_ai_scan"])

    def test_incremental_and_material_drift_refresh_only_affected_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._git_project(root); initialize(root)
            task_before = (root / ".ai/runtime/task.json").read_bytes()
            (root / "README.md").write_text("bounded docs change\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "docs"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            incremental = prepare_for_new_session(root)
            self.assertEqual("INCREMENTAL_DRIFT", incremental["classification"])
            self.assertEqual(task_before, (root / ".ai/runtime/task.json").read_bytes())
            (root / "package.json").write_text('{"name":"fixture","version":"2"}', encoding="utf-8")
            subprocess.run(["git", "add", "package.json"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "manifest"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            material = prepare_for_new_session(root)
            self.assertEqual("MATERIAL_DRIFT", material["classification"])
            self.assertEqual(task_before, (root / ".ai/runtime/task.json").read_bytes())
            self.assertIn("REFRESH_AFFECTED_SOURCE_PROVENANCE", material["automatic_action_taken"])

    def test_corrupted_derived_file_is_preserved_and_regenerated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); initialize(root)
            (root / ".ai/context/tech-stack.json").write_text("{broken", encoding="utf-8")
            report = prepare_for_new_session(root)
            self.assertEqual("CORRUPTED_DERIVED_FILE", report["classification"])
            self.assertIsInstance(json.loads((root / ".ai/context/tech-stack.json").read_text(encoding="utf-8")), dict)
            self.assertTrue(list((root / ".ai/recovery/quarantine").glob("*/context/tech-stack.json")))

    def test_corrupted_authority_only_disables_old_resume_and_keeps_project_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); initialize(root)
            (root / ".ai/governance/goal-contract.json").write_text("{broken", encoding="utf-8")
            report = prepare_for_new_session(root)
            self.assertEqual("CORRUPTED_AUTHORITY_FILE", report["classification"])
            self.assertEqual("READY", report["project_usability"])
            self.assertEqual("QUARANTINED", report["old_state_resumability"])
            self.assertEqual("NONE", report["user_action_required"])
            self.assertFalse((root / ".ai/governance/goal-contract.json").exists())
            self.assertTrue(list((root / ".ai/recovery/quarantine").glob("*/governance/goal-contract.json")))

    def test_foreign_ai_authority_is_not_adopted_and_current_project_is_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); first = base / "first"; second = base / "second"; first.mkdir(); second.mkdir()
            self._git_project(first); self._git_project(second); initialize(first)
            (second / ".ai/governance").mkdir(parents=True)
            shutil.copy2(first / ".ai/governance/source-provenance.json", second / ".ai/governance/source-provenance.json")
            report = prepare_for_new_session(second)
            current = json.loads((second / ".ai/governance/source-provenance.json").read_text(encoding="utf-8"))
            foreign = json.loads((first / ".ai/governance/source-provenance.json").read_text(encoding="utf-8"))
            self.assertEqual("FOREIGN_AI", report["classification"])
            self.assertEqual("READY", report["project_usability"])
            self.assertNotEqual(foreign["repo_id"], current["repo_id"])
            self.assertEqual("QUARANTINED", report["old_state_resumability"])

    def test_new_provider_session_attaches_without_reusing_old_session_identity(self):
        calls: list[list[str]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); initialize(root)
            report = router_boundary_adoption(
                root, {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "new-provider-session"},
                self._adoption_runner(calls),
            )
        self.assertTrue(report["adopted"])
        self.assertFalse(any("new-provider-session" in part for call in calls for part in call))

    def test_repeat_recovery_has_zero_duplicate_authority_and_zero_state_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); self._authority(root)
            first = prepare_for_new_session(root)
            snapshots = list((root / ".ai/recovery/snapshots").glob("*.json"))
            second = recover_for_new_session(root)
            self.assertEqual("REBINDABLE", first["old_state_resumability"])
            self.assertEqual("REBINDABLE", second["old_state_resumability"])
            self.assertEqual(0, second["state_writes"])
            self.assertEqual(len(snapshots), len(list((root / ".ai/recovery/snapshots").glob("*.json"))))
            self.assertEqual(1, len(list((root / ".ai/recovery").glob("current-authority-candidate.json"))))

    def test_pro_unavailable_uses_community_then_live_adopts_without_duplicate_authority(self):
        calls: list[list[str]] = []
        fallback = {"status": "COMMUNITY_FALLBACK", "pro_state": "COMMUNITY_FALLBACK", "pro_available": False}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root)
            first = router_boundary_adoption(root, {"CODEX_THREAD_ID": "session-a"}, detected=fallback)
            second = router_boundary_adoption(
                root, {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session-b"},
                self._adoption_runner(calls),
            )
            snapshots = list((root / ".ai/recovery/snapshots").glob("*.json")) if (root / ".ai/recovery/snapshots").is_dir() else []
        self.assertTrue(first["community_safe_mode"])
        self.assertEqual("NONE", first["user_action_required"])
        self.assertTrue(second["adopted"])
        self.assertLessEqual(len(snapshots), 1)

    def test_ambiguous_old_tasks_do_not_block_current_project_or_trigger_establishment(self):
        calls: list[list[str]] = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1] == "version":
                return subprocess.CompletedProcess(command, 0, _version(), "")
            return subprocess.CompletedProcess(
                command, 2,
                _envelope("attach", "TASK_ADOPTION_REQUIRED", ok=False, exit_code=2, pro_state="PRO_DEGRADED", reasons=[]),
                "",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); self._authority(root, tasks=2)
            report = router_boundary_adoption(
                root, {"HIKER_EXECUTABLE": "C:/fixture/hiker.exe", "CODEX_THREAD_ID": "session"}, run,
            )
        self.assertEqual("COMMUNITY_SAFE_MODE", report["status"])
        self.assertTrue(report["project_ready"])
        self.assertEqual("NONE", report["user_action_required"])
        self.assertEqual("SELECT_AUTHORITY", report["old_state_resume_user_action"])
        self.assertEqual(["version", "attach"], [call[1] for call in calls])

    def test_known_old_schema_migrates_copy_on_write_and_repeats_with_zero_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); (root / ".ai").mkdir()
            (root / ".ai/schema.json").write_text(json.dumps({"version": "2.0.0", "created_at": "legacy"}), encoding="utf-8")
            first = prepare_for_new_session(root)
            second = recover_for_new_session(root)
            schema = json.loads((root / ".ai/schema.json").read_text(encoding="utf-8"))
            self.assertIn("COPY_ON_WRITE_SCHEMA_MIGRATION", first["automatic_action_taken"])
            self.assertEqual("1.0.0", schema["version"])
            self.assertTrue(list((root / ".ai/recovery/quarantine").glob("*/schema.json")))
            self.assertEqual(0, second["state_writes"])

    def test_oversized_cold_history_never_enters_startup_working_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self._project(root); initialize(root)
            archive = root / ".ai/archive/events"; archive.mkdir(parents=True)
            (archive / "cold.bin").write_bytes(b"x" * (2 * 1024 * 1024))
            report = recover_for_new_session(root)
            self.assertFalse(report["full_ai_scan"])
            self.assertFalse(report["cold_history_scanned"])
            self.assertLessEqual(report["state_reads"], 32)
            self.assertEqual(0, report["state_writes"])


if __name__ == "__main__":
    unittest.main()
