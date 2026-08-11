from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from closure_gate import evaluate as closure_evaluate
from file_lock import acquire, check, release
from git_workspace import cmd_adopt, cmd_close, cmd_create, cmd_inventory, cmd_list, cmd_pause, cmd_plan_close, validate_branch_policy
from governance_state import checkpoint, control, create_task, init_project, load_task, record, save_task, set_change_contract, transition, validate
from merge_guard import conflict_probe, evaluate as merge_evaluate, flow_ok
from task_router import route
from task_reconciler import reconcile
from workspacelib import common_dir, read_json, safe_branch, state_lock


def ns(**values): return argparse.Namespace(**values)


def git(root, *args): return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


class WorkspaceTests(unittest.TestCase):
    def repo(self, root: Path):
        git(root, "init", "-b", "main"); git(root, "config", "user.email", "test@example.com"); git(root, "config", "user.name", "Test")
        (root / "a.txt").write_text("a\n", encoding="utf-8"); git(root, "add", "."); git(root, "commit", "-m", "chore: initialize repository"); git(root, "branch", "develop"); git(root, "branch", "release")

    def governance(self, root: Path, task_id="KG-001", branch="feature/KG-001-login"):
        init_project(root, ns(project_id="PROJECT-A", architecture="hybrid", version="1.0.0", database_version="001", api_version="v1"))
        create_task(root, ns(task_id=task_id, goal="登录", owner_agent="Planning Agent", branch=branch, base_branch="develop", affected_files=["src/AuthService.ts"]))
        transition(root, ns(task_id=task_id, to="Planning", agent_role="Planning Agent", commit_id=None))
        set_change_contract(root, ns(task_id=task_id, agent_role="Planning Agent", allowed_files=["src/AuthService.ts", "evidence.log", "CHANGELOG.md", "ARCHITECTURE.md"], allowed_modules=None, protected_modules=None, public_contract_changes=None, behavior_invariants=["原有认证行为保持不变"], characterization_tests=[], consumer_tests=[], required_tests=["认证单测", "登录回归"], consumers=[], max_blast_radius=80, warn_lines=None, block_lines=None, warn_growth=None, block_growth=None))
        transition(root, ns(task_id=task_id, to="Development", agent_role="Developer Agent", commit_id=None))

    def test_router_forces_frontend_and_backend_for_bs_and_cs(self):
        data = route("设计 B/S 管理端和 C/S Unity 客户端，共享 NodeTS 后端")
        names = {item["lane"] for item in data["lanes"]}
        self.assertEqual("hybrid", data["architecture"])
        self.assertTrue({"bs-frontend", "cs-client", "backend-service", "contract-data", "review", "testing", "documentation", "merge"}.issubset(names))
        self.assertTrue(all(item.get("agent_role") for item in data["lanes"]))

    def test_router_recognizes_general_cs_families_and_keeps_backend_lane(self):
        for prompt, expected in [("实现Qt QML客户端", "qt"), ("开发WPF桌面程序", "dotnet-desktop"), ("Flutter移动端", "flutter"), ("Tauri客户端", "electron-tauri")]:
            with self.subTest(prompt=prompt):
                data=route(prompt); names={item["lane"] for item in data["lanes"]}
                self.assertEqual("cs",data["architecture"]);self.assertIn(expected,data["client_families"])
                self.assertTrue({"cs-client","backend-service","contract-data"}.issubset(names))

    def test_governance_state_and_human_control_documents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); self.governance(root)
            git(root, "checkout", "-b", "feature/KG-001-login", "develop")
            result = validate(root)
            self.assertTrue(result["ok"])
            state = (root / "PROJECT_STATE.md").read_text(encoding="utf-8")
            for heading in ["当前版本", "当前分支", "已完成功能", "开发中功能", "待处理问题", "数据库版本", "API版本", "风险列表"]: self.assertIn(heading, state)
            context = (root / "CURRENT_CONTEXT.md").read_text(encoding="utf-8")
            for heading in ["当前目标", "已完成修改", "未完成事项", "关键决定", "禁止事项"]: self.assertIn(heading, context)
            paused = control(root, ns(task_id="KG-001", action="pause", instruction="", new_task_id=None, branch=None, base_branch="develop")); self.assertEqual("PAUSED", paused["task"]["control_status"])
            control(root, ns(task_id="KG-001", action="resume", instruction="", new_task_id=None, branch=None, base_branch="develop"))
            inserted = control(root, ns(task_id="KG-001", action="insert", instruction="审计日志", new_task_id="KG-002", branch="feature/KG-002-audit", base_branch="develop"))
            self.assertEqual(["KG-001"], inserted["inserted_task"]["dependencies"])

    def test_file_lock_blocks_unity_and_migration_conflicts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); self.governance(root)
            create_task(root, ns(task_id="KG-002", goal="并发修改", owner_agent="Planning Agent", branch="feature/KG-002-other", base_branch="develop", affected_files=[]))
            transition(root, ns(task_id="KG-002", to="Planning", agent_role="Planning Agent", commit_id=None)); set_change_contract(root, ns(task_id="KG-002", agent_role="Planning Agent", allowed_files=["Assets/Main.unity.meta", "db/migrations/002.sql"], allowed_modules=None, protected_modules=None, public_contract_changes=None, behavior_invariants=["已有场景和迁移顺序保持不变"], characterization_tests=[], consumer_tests=[], required_tests=["场景与迁移回归"], consumers=[], max_blast_radius=80, warn_lines=None, block_lines=None, warn_growth=None, block_growth=None)); transition(root, ns(task_id="KG-002", to="Development", agent_role="Developer Agent", commit_id=None))
            acquired = acquire(root, ns(task_id="KG-001", agent_role="Developer Agent", owner="agent-a", paths=["Assets/Main.unity", "db/migrations/001.sql"]))
            self.assertEqual(2, len(acquired["acquired"]))
            result = check(root, ns(task_id="KG-002", files=["Assets/Main.unity.meta", "db/migrations/002.sql"]))
            self.assertFalse(result["ok"]); self.assertEqual(2, len(result["conflicts"]))
            release(root, ns(task_id="KG-001", paths=[]))

    def test_file_lock_handles_nested_projectsettings_and_meta_alias(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repo(root);self.governance(root)
            acquire(root,ns(task_id="KG-001",agent_role="Developer Agent",owner="agent-a",paths=["client/ProjectSettings/ProjectVersion.txt","Assets/Panel.prefab"]))
            own=check(root,ns(task_id="KG-001",files=["Assets/Panel.prefab.meta"]));self.assertTrue(own["ok"],own)
            self.assertEqual([],own["missing_required_locks"])

    def test_agent_role_cannot_forge_review_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repo(root);self.governance(root)
            with self.assertRaises(RuntimeError):record(root,ns(task_id="KG-001",kind="review",value="self review",status="PASS",command=None,reason=None,agent_role="Developer Agent"))

    def test_worktree_policy_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir(); self.repo(root); self.governance(root)
            with self.assertRaises(RuntimeError): validate_branch_policy(root, "main", "main", "Developer Agent")
            args = ns(task_id="KG-001", base="develop", branch="feature/KG-001-login", path=str(Path(td) / "wt"), agent_role="Developer Agent")
            created = cmd_create(root, args); self.assertTrue(Path(created["path"]).exists()); self.assertTrue(cmd_list(root)["worktrees"])
            cmd_pause(root, ns(task_id="KG-001"), "PAUSED")
            plan = cmd_plan_close(root, ns(path=created["path"], target="develop")); self.assertTrue(plan["plan"]["ready"])
            closed = cmd_close(root, ns(token=plan["plan"]["token"])); self.assertTrue(closed["ok"]); self.assertFalse(Path(created["path"]).exists())

    def test_inventory_adopts_legacy_worktree_without_scanning_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir(); self.repo(root)
            legacy = Path(td) / "legacy"
            git(root, "worktree", "add", "-b", "feature/legacy", str(legacy), "develop")
            quick = cmd_inventory(root, ns(mode="quick", target=None))
            self.assertEqual(2, quick["summary"]["total"]); self.assertEqual(1, quick["summary"]["unmanaged"])
            adopted = cmd_adopt(root, ns(worktree_id="WT-001", path=str(legacy), task_id=None))
            self.assertEqual("ADOPTED", adopted["adopted"]["status"])
            refreshed = cmd_inventory(root, ns(mode="quick", target=None))
            self.assertEqual(0, refreshed["summary"]["unmanaged"])

    def test_create_blocks_nested_worktree_and_uninitialized_governance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir(); self.repo(root)
            args = ns(task_id="KG-001", base="develop", branch="feature/KG-001-login", path=str(Path(td) / "wt"), agent_role="Developer Agent")
            with self.assertRaisesRegex(RuntimeError, "governance is not initialized"):
                cmd_create(root, args)
            self.governance(root)
            nested = root / "nested-wt"
            git(root, "worktree", "add", "-b", "feature/nested", str(nested), "develop")
            with self.assertRaisesRegex(RuntimeError, "nested worktree"):
                cmd_create(root, args)

    def test_merged_state_waits_for_task_worktree_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir(); self.repo(root); self.governance(root)
            task = load_task(root, "KG-001")
            task["state"] = "Testing"; task["tests"] = {"status": "PASS", "records": [{"value": "ok"}]}; task["closure"]["merge"] = "PASS"
            save_task(root, task)
            worktree = Path(td) / "task-wt"
            git(root, "worktree", "add", "-b", "feature/KG-001-login", str(worktree), "develop")
            transition(root, ns(task_id="KG-001", to="MergedPendingCleanup", agent_role="Merge Agent", commit_id="abc123"))
            with self.assertRaisesRegex(RuntimeError, "worktree to be closed"):
                transition(root, ns(task_id="KG-001", to="Merged", agent_role="Merge Agent", commit_id=None))
            git(root, "worktree", "remove", str(worktree))
            merged = transition(root, ns(task_id="KG-001", to="Merged", agent_role="Merge Agent", commit_id=None))
            self.assertEqual("Merged", merged["state"])

    def test_feature_closed_loop_and_merge_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); self.governance(root)
            git(root, "checkout", "-b", "feature/KG-001-login", "develop")
            (root / "src").mkdir(); (root / "src/AuthService.ts").write_text("export const ok = true;\n", encoding="utf-8")
            (root / "evidence.log").write_text("login e2e passed\n", encoding="utf-8")
            git(root, "add", "."); git(root, "commit", "-m", "feat(auth): implement KG-001 login")
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            record(root, ns(task_id="KG-001", kind="commit", value=head, status=None, command=None, reason=None, agent_role="Developer Agent"))
            quality_scripts = PLUGIN.parent / "ai-engineering-quality" / "scripts"
            run_guard = subprocess.run([sys.executable, str(quality_scripts / "architecture_guard.py"), "--root", str(root), "check", "--task-id", "KG-001"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, run_guard.returncode, run_guard.stdout + run_guard.stderr)
            transition(root, ns(task_id="KG-001", to="Review", agent_role="Developer Agent", commit_id=None))
            record(root, ns(task_id="KG-001", kind="review", value="independent review", status="PASS", command=None, reason=None, agent_role="Review Agent"))
            transition(root, ns(task_id="KG-001", to="Testing", agent_role="Review Agent", commit_id=None))
            record(root, ns(task_id="KG-001", kind="test", value="unit and e2e", status="PASS", command="npm test", reason=None, agent_role="Test Agent"))
            record(root, ns(task_id="KG-001", kind="artifact", value="evidence.log", status="PASS", command=None, reason=None, agent_role="Test Agent"))
            record(root, ns(task_id="KG-001", kind="document", value="CHANGELOG.md", status="UPDATED", command=None, reason=None, agent_role="Document Agent"))
            record(root, ns(task_id="KG-001", kind="document", value="ARCHITECTURE.md", status="NOT_APPLICABLE", command=None, reason="no architecture change", agent_role="Document Agent"))
            git(root, "add", "."); git(root, "commit", "-m", "docs: record KG-001 acceptance evidence")
            run_guard = subprocess.run([sys.executable, str(quality_scripts / "architecture_guard.py"), "--root", str(root), "check", "--task-id", "KG-001"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, run_guard.returncode, run_guard.stdout + run_guard.stderr)
            task = load_task(root, "KG-001"); closure = closure_evaluate(root, task, "merge"); self.assertTrue(closure["ok"], closure["failures"])
            task["closure"]["merge"] = "PASS"
            from workspacelib import atomic_json
            atomic_json(root / ".ai/tasks/KG-001.json", task)
            gate = merge_evaluate(root, "feature/KG-001-login", "develop", "KG-001")
            self.assertTrue(gate["ok"], gate.get("failures"))

    def test_branch_flow_and_conflict_probe(self):
        self.assertTrue(flow_ok("feature/KG-001-x", "develop")); self.assertFalse(flow_ok("feature/KG-001-x", "main"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); git(root, "checkout", "-b", "feature/KG-001-x", "develop"); (root / "a.txt").write_text("feature\n"); git(root, "commit", "-am", "feat: feature")
            git(root, "checkout", "develop"); (root / "a.txt").write_text("develop\n"); git(root, "commit", "-am", "fix: develop")
            self.assertTrue(conflict_probe(root, "develop", "feature/KG-001-x")["potential_conflict"])

    def test_branch_sanitization_and_stale_lock_recovery(self):
        self.assertEqual("feature/a-b/c", safe_branch("feature/a b/c"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); lock = common_dir(root) / "ai-engineering/workspace.lock"; lock.parent.mkdir(parents=True, exist_ok=True); lock.write_text('{"pid":999999,"created":0}')
            with state_lock(root, timeout=1, stale_after=0.01): pass
            self.assertFalse(lock.exists())

    def test_workspace_context_and_checkpoints_stay_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); self.governance(root)
            from workspacelib import atomic_json
            atomic_json(root / ".ai/governance/context-retention.json", {
                "schema_version": "1.0.0", "active_context_max_chars": 1800,
                "session_context_max_chars": 1200, "max_items_per_section": 3,
                "max_recent_checkpoints": 2, "max_milestone_checkpoints": 1,
                "max_ledger_entries": 3,
            })
            task = load_task(root, "KG-001"); task["completed_changes"] = [f"change-{i}" for i in range(20)]
            atomic_json(root / ".ai/tasks/KG-001.json", task)
            for i in range(6): checkpoint(root, task, f"rolling-{i}")
            for i in range(4): checkpoint(root, task, f"pause-{i}")
            context = (root / "CURRENT_CONTEXT.md").read_text(encoding="utf-8")
            self.assertIn("完整事实见", context); self.assertLessEqual(len(context), 2200)
            self.assertLessEqual(len(list((root / ".ai/runtime/checkpoints").glob("*.json"))), 3)
            ledger = read_json(root / ".ai/runtime/checkpoint-ledger.json", {})
            self.assertGreaterEqual(ledger.get("pruned_count", 0), 7); self.assertTrue(ledger.get("pruned_hash_chain"))

    def test_closed_task_index_is_bounded_without_deleting_task_facts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root)
            init_project(root, ns(project_id="PROJECT-A", architecture="bs", version="1.0.0", database_version="001", api_version="v1"))
            for i in range(205):
                save_task(root, {"schema_version":"2.0.0", "project_id":"PROJECT-A", "task_id":f"KG-{i+1:03d}", "goal":f"closed-{i}", "state":"Released", "control_status":"ACTIVE", "owner_agent":"Master Agent", "branch":f"feature/KG-{i+1:03d}", "updated_at":""})
            index = read_json(root / ".ai/governance/task-index.json", {})
            self.assertEqual(200, index.get("retained_closed_count")); self.assertEqual(5, index.get("compacted_closed_count"))
            self.assertTrue(index.get("compacted_hash_chain")); self.assertEqual(205, len(list((root / ".ai/tasks").glob("*.json"))))

    def test_parallel_write_budget_blocks_a_third_development_task(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root)
            self.governance(root, "KG-001", "feature/KG-001-a")
            self.governance(root, "KG-002", "feature/KG-002-b")
            init_project(root, ns(project_id="PROJECT-A", architecture="hybrid", version="1.0.0", database_version="001", api_version="v1"))
            create_task(root, ns(task_id="KG-003", goal="第三个并行写任务", owner_agent="Planning Agent", branch="feature/KG-003-c", base_branch="develop", affected_files=["src/C.ts"]))
            transition(root, ns(task_id="KG-003", to="Planning", agent_role="Planning Agent", commit_id=None))
            set_change_contract(root, ns(task_id="KG-003", agent_role="Planning Agent", allowed_files=["src/C.ts"], allowed_modules=None, protected_modules=None, public_contract_changes=None, behavior_invariants=["已有行为不变"], characterization_tests=[], consumer_tests=[], required_tests=["回归测试"], consumers=[], max_blast_radius=20, warn_lines=None, block_lines=None, warn_growth=None, block_growth=None))
            with self.assertRaisesRegex(RuntimeError, "parallel write budget exceeded"):
                transition(root, ns(task_id="KG-003", to="Development", agent_role="Developer Agent", commit_id=None))

    def test_total_open_task_budget_blocks_unbounded_backlog(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repo(root);init_project(root,ns(project_id="PROJECT-A",architecture="hybrid",version="1.0.0",database_version="001",api_version="v1"))
            for i in range(1,6):
                create_task(root,ns(task_id=f"KG-{i:03d}",goal=f"任务{i}",owner_agent="Planning Agent",branch=f"feature/KG-{i:03d}",base_branch="develop",affected_files=[]))
            with self.assertRaisesRegex(RuntimeError,"total open task budget exceeded"):
                create_task(root,ns(task_id="KG-006",goal="超出预算",owner_agent="Planning Agent",branch="feature/KG-006",base_branch="develop",affected_files=[]))
            self.assertTrue(validate(root)["ok"])

    def test_task_reconciler_detects_missing_branch_and_orphan_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir(); self.repo(root)
            init_project(root, ns(project_id="PROJECT-A", architecture="hybrid", version="1.0.0", database_version="001", api_version="v1"))
            create_task(root, ns(task_id="KG-001", goal="待规划任务", owner_agent="Planning Agent", branch="feature/KG-001-missing", base_branch="develop", affected_files=[]))
            transition(root, ns(task_id="KG-001", to="Planning", agent_role="Planning Agent", commit_id=None))
            orphan = Path(td) / "orphan"
            git(root, "worktree", "add", "-b", "feature/orphan", str(orphan), "develop")
            from workspacelib import atomic_json
            atomic_json(common_dir(root) / "ai-engineering/file-locks.json", {"schema_version":"1.0.0", "locks":[{"task_id":"KG-999", "path":"src/Old.ts"}]})
            report = reconcile(root)
            types = {item["type"] for item in report["findings"]}
            self.assertIn("TASK_BRANCH_MISSING", types)
            self.assertIn("ORPHAN_WORKTREE", types)
            self.assertIn("STALE_FILE_LOCK", types)
            self.assertFalse(report["ok"])
            create_report = reconcile(root, phase="create")
            orphan_finding = next(item for item in create_report["findings"] if item["type"] == "ORPHAN_WORKTREE")
            self.assertEqual("BLOCK", orphan_finding["severity"])


if __name__ == "__main__": unittest.main()
