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
from git_workspace import cmd_create, cmd_list, cmd_pause, cmd_remove, validate_branch_policy
from governance_state import control, create_task, init_project, load_task, record, transition, validate
from merge_guard import conflict_probe, evaluate as merge_evaluate, flow_ok
from task_router import route
from workspacelib import common_dir, safe_branch, state_lock


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
        transition(root, ns(task_id=task_id, to="Development", agent_role="Developer Agent", commit_id=None))

    def test_router_forces_frontend_and_backend_for_bs_and_cs(self):
        data = route("设计 B/S 管理端和 C/S Unity 客户端，共享 NodeTS 后端")
        names = {item["lane"] for item in data["lanes"]}
        self.assertEqual("hybrid", data["architecture"])
        self.assertTrue({"bs-frontend", "bs-backend", "cs-client", "cs-backend", "contract-data", "review", "testing", "documentation", "merge"}.issubset(names))
        self.assertTrue(all(item.get("agent_role") for item in data["lanes"]))

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
            transition(root, ns(task_id="KG-002", to="Planning", agent_role="Planning Agent", commit_id=None)); transition(root, ns(task_id="KG-002", to="Development", agent_role="Developer Agent", commit_id=None))
            acquired = acquire(root, ns(task_id="KG-001", agent_role="Developer Agent", owner="agent-a", paths=["Assets/Main.unity", "db/migrations/001.sql"]))
            self.assertEqual(2, len(acquired["acquired"]))
            result = check(root, ns(task_id="KG-002", files=["Assets/Main.unity.meta", "db/migrations/002.sql"]))
            self.assertFalse(result["ok"]); self.assertEqual(2, len(result["conflicts"]))
            release(root, ns(task_id="KG-001", paths=[]))

    def test_worktree_policy_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir(); self.repo(root)
            with self.assertRaises(RuntimeError): validate_branch_policy(root, "main", "main", "Developer Agent")
            args = ns(task_id="KG-001", base="develop", branch="feature/KG-001-login", path=str(Path(td) / "wt"), agent_role="Developer Agent")
            created = cmd_create(root, args); self.assertTrue(Path(created["path"]).exists()); self.assertTrue(cmd_list(root)["worktrees"])
            cmd_pause(root, ns(task_id="KG-001"), "PAUSED")
            remove = ns(task_id="KG-001", target="develop", force=False); self.assertTrue(cmd_remove(root, remove)["ok"])

    def test_feature_closed_loop_and_merge_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.repo(root); self.governance(root)
            git(root, "checkout", "-b", "feature/KG-001-login", "develop")
            (root / "src").mkdir(); (root / "src/AuthService.ts").write_text("export const ok = true;\n", encoding="utf-8")
            (root / "evidence.log").write_text("login e2e passed\n", encoding="utf-8")
            git(root, "add", "."); git(root, "commit", "-m", "feat(auth): implement KG-001 login")
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            record(root, ns(task_id="KG-001", kind="commit", value=head, status=None, command=None, reason=None, agent_role="Developer Agent"))
            transition(root, ns(task_id="KG-001", to="Review", agent_role="Developer Agent", commit_id=None))
            record(root, ns(task_id="KG-001", kind="review", value="independent review", status="PASS", command=None, reason=None, agent_role="Review Agent"))
            transition(root, ns(task_id="KG-001", to="Testing", agent_role="Review Agent", commit_id=None))
            record(root, ns(task_id="KG-001", kind="test", value="unit and e2e", status="PASS", command="npm test", reason=None, agent_role="Test Agent"))
            record(root, ns(task_id="KG-001", kind="artifact", value="evidence.log", status="PASS", command=None, reason=None, agent_role="Test Agent"))
            record(root, ns(task_id="KG-001", kind="document", value="CHANGELOG.md", status="UPDATED", command=None, reason=None, agent_role="Document Agent"))
            record(root, ns(task_id="KG-001", kind="document", value="ARCHITECTURE.md", status="NOT_APPLICABLE", command=None, reason="no architecture change", agent_role="Document Agent"))
            git(root, "add", "."); git(root, "commit", "-m", "docs: record KG-001 acceptance evidence")
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


if __name__ == "__main__": unittest.main()
