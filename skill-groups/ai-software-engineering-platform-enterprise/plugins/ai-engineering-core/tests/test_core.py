from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from bootstrap_project import initialize
from detect_project import detect
from runtime_control import classify
from statectl import checkpoint, record_routing, update_active
from corelib import atomic_write_json
from requirements_fusion import init as init_requirements, merge as merge_requirements, validate as validate_requirements
from brownfield_reconcile import initialize as init_brownfield, set_baseline, reconcile, validate as validate_brownfield
from suite_router import inspect_project, route


def model_proposal(*skills: str, stage: str = "development", architecture: str = "unknown", mode: str = "existing", **extra):
    data = {
        "project_mode": mode,
        "architecture": architecture,
        "stage": stage,
        "current_action": extra.pop("current_action", "处理当前阶段目标"),
        "confidence": extra.pop("confidence", "high"),
        "candidates": list(skills),
    }
    data.update(extra)
    return data


class CoreTests(unittest.TestCase):
    def test_router_requires_chatgpt_proposal_and_never_keyword_selects(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for request in (
                "这不是C/S项目，禁止Android，只修改Web页面",
                "不要创建Worktree，也不要merge",
                "解释为什么插件选择Skill会走偏",
            ):
                data = route(root, request)
                self.assertEqual("PROPOSAL_REQUIRED", data["guard_decision"])
                self.assertEqual([], data["selected"])
                self.assertEqual("chatgpt-semantic-selection", data["routing_authority"])

    def test_router_accepts_model_candidates_and_keeps_bounded_queue(self):
        with tempfile.TemporaryDirectory() as td:
            proposal = model_proposal(
                "multi-agent-project-governance", "workspace-task-router",
                stage="governance", architecture="hybrid",
                deferred=["regression-test-planner", "full-change-risk-review", "release-readiness-review"],
                future_terms=["测试", "审核", "发布"],
            )
            data = route(Path(td), proposal)
            self.assertEqual("ACCEPT", data["guard_decision"])
            self.assertEqual(2, len(data["selected"]))
            self.assertEqual(3, len(data["deferred"]))
            self.assertLessEqual(len(data["load"]), 2)
            self.assertTrue(data["phase_transition_required"])
            self.assertEqual(2, data["max_loaded_atomic_skills"])
            self.assertFalse(data["router_counts_toward_limit"])

    def test_router_rejects_more_than_two_candidates_without_substitution(self):
        with tempfile.TemporaryDirectory() as td:
            proposal = model_proposal(
                "bounded-context-memory", "context-recovery", "interruptible-task-control",
                stage="governance",
            )
            data = route(Path(td), proposal)
            self.assertEqual("REJECT", data["guard_decision"])
            self.assertEqual([], data["selected"])
            self.assertEqual([], data["load"])
            self.assertIn("ATOMIC_SKILL_LIMIT", {item["code"] for item in data["diagnostics"]})

    def test_model_selected_semantic_skills_keep_chinese_receipts(self):
        cases = (
            ("plugin-application-receipt", "governance", "插件应用回执"),
            ("bounded-context-memory", "governance", "有界上下文记忆"),
            ("architecture-decision-challenge", "planning", "架构决策挑战与补全"),
            ("interaction-conflict-governance", "review", "交互状态与冲突治理"),
            ("long-chain-change-convergence", "governance", "长链路变更收敛"),
            ("greenfield-project-planning", "planning", "0→1需求融合与选型"),
        )
        with tempfile.TemporaryDirectory() as td:
            for skill, stage, display in cases:
                data = route(Path(td), model_proposal(skill, stage=stage, mode="greenfield" if skill == "greenfield-project-planning" else "unknown"))
                self.assertTrue(data["accepted"], data["diagnostics"])
                self.assertEqual(display, data["selected"][0]["skill"])
                self.assertIsNone(__import__("re").search(r"[A-Za-z]", data["selected"][0]["skill"]))
                self.assertIsNone(__import__("re").search(r"[A-Za-z]", data["selected"][0]["plugin"]))

    def test_router_preserves_negated_and_future_terms_without_interpreting_them(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), model_proposal(
                "web-component-implementation", stage="development", architecture="bs",
                negated_terms=["不是C/S", "禁止Android", "不要Worktree"],
                future_terms=["完成后测试和发布"],
            ))
            self.assertTrue(data["accepted"])
            self.assertEqual(["不是C/S", "禁止Android", "不要Worktree"], data["intent"]["negated_terms"])
            self.assertEqual(["浏览器端组件与页面实现"], [item["skill"] for item in data["selected"]])

    def test_router_accepts_brownfield_reconciliation_selected_by_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "package.json").write_text('{"name":"partial-app"}', encoding="utf-8")
            data = route(root, model_proposal(
                "project-bootstrap", "brownfield-requirement-reconciliation",
                stage="planning", mode="brownfield",
            ))
            self.assertTrue(data["accepted"], data["diagnostics"])
            self.assertEqual(["项目智能初始化", "存量源码需求对账"], [item["skill"] for item in data["selected"]])

    def test_router_checks_manifest_architecture_not_prompt_keywords(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); nested = root / "apps/api"; nested.mkdir(parents=True)
            (nested / "package.json").write_text(json.dumps({"dependencies": {"express": "5.0.0"}}), encoding="utf-8")
            accepted = route(root, model_proposal(
                "backend-technology-router", "backend-component-implementation",
                stage="development", architecture="backend",
            ))
            self.assertTrue(accepted["accepted"], accepted["diagnostics"])
            rejected = route(root, model_proposal(
                "cs-client-router", "cs-component-implementation",
                stage="development", architecture="cs",
                negated_terms=["禁止把服务端误判为客户端"],
            ))
            self.assertFalse(rejected["accepted"])
            self.assertIn("ARCHITECTURE_CONFLICT", {item["code"] for item in rejected["diagnostics"]})

    def test_router_ignores_nested_worktree_manifests_and_blocks_source_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"; root.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "package.json").write_text(json.dumps({"dependencies": {"vue": "3.5.0"}}), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True); subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
            nested = root / "old-worktree"
            subprocess.run(["git", "worktree", "add", "-b", "feature/old", str(nested)], cwd=root, check=True, stdout=subprocess.PIPE)
            (nested / "legacy" ).mkdir(); (nested / "legacy/package.json").write_text(json.dumps({"dependencies": {"express": "5"}}), encoding="utf-8")
            blocked = route(root, model_proposal("web-component-implementation", stage="development", architecture="bs"))
            self.assertFalse(blocked["accepted"])
            data = route(root, model_proposal("worktree-safe-convergence", stage="governance", architecture="bs"))
            self.assertTrue(data["accepted"], data["diagnostics"])
            self.assertEqual("工作目录安全收敛", data["selected"][0]["skill"])
            self.assertEqual(1, data["source_identity"]["nested_worktree_count"])
            self.assertTrue(all("old-worktree" not in path for path in data["project_evidence"]))

    def test_inspection_distinguishes_web_backend_and_client_manifests(self):
        cases = (
            ({"dependencies": {"react": "19.0.0", "express": "5.1.0"}}, {"bs", "backend"}),
            ({"dependencies": {"react": "19.0.0", "react-native": "0.80.0"}}, {"cs"}),
            ({"dependencies": {"fastify": "5.2.0"}}, {"backend"}),
        )
        for package, expected in cases:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
                facts = set(inspect_project(root)["project_facts"]["architectures"])
                self.assertEqual(expected, facts)

    def test_brownfield_baseline_and_delta_are_evidence_backed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "src").mkdir(); (root / "src/CoreService.ts").write_text("export class CoreService {}", encoding="utf-8")
            init_brownfield(root, "APP", "扩展现有业务系统")
            self.assertFalse((root / ".ai/context/greenfield.json").exists())
            baseline = set_baseline(root, {"capabilities": [{
                "id": "CAP-001", "statement": "已有核心服务", "evidence": ["src/CoreService.ts"],
                "modules": ["core-service"], "tests": []
            }], "unknowns": ["数据库约束待确认"]})
            self.assertTrue(baseline["ok"])
            result = reconcile(root, {"requirements": [{
                "id": "REQ-001", "statement": "增加业务数据批量导入", "priority": "must",
                "acceptance": ["合法表格可导入并返回逐行结果"], "change_type": "modify",
                "targets": ["CAP-001"], "impact": {"modules": ["core-service"], "tests": ["batch-import"]}
            }]})
            self.assertTrue(result["ok"]); self.assertEqual("READY_FOR_PLANNING", result["status"])
            self.assertTrue((root / "REQUIREMENT_DELTA.md").is_file()); self.assertTrue(validate_brownfield(root)["ok"])

    def test_requirements_merge_preserves_revision_and_conflicts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); init_requirements(root, "APP", "自定义业务系统")
            context = json.loads((root / ".ai/context/greenfield.json").read_text(encoding="utf-8"))
            self.assertEqual("automatic_non_blocking", context["decision_mode"])
            self.assertEqual("AUTO_RECORD_REQUIRED", context["checkpoint_status"])
            first = merge_requirements(root, [{"id":"REQ-001","statement":"支持离线使用","priority":"must","acceptance":["断网可打开核心数据"]}])
            second = merge_requirements(root, [{"id":"REQ-001","statement":"支持离线使用并在联网后同步","priority":"must","acceptance":["断网可用","联网自动同步"],"conflicts_with":["REQ-002"]}])
            self.assertTrue(first["ok"]); self.assertEqual(["REQ-001"], second["updated"]); self.assertEqual(1, second["conflicts"])
            ledger = json.loads((root / ".ai/requirements/ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(ledger["requirements"][0]["history"]))
            self.assertTrue(validate_requirements(root)["ok"]); self.assertIn("REQ-001", (root / "REQUIREMENTS.md").read_text(encoding="utf-8"))

    def test_legacy_pending_decision_state_is_migrated_without_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / ".ai/context").mkdir(parents=True); (root / ".ai/requirements").mkdir(parents=True)
            atomic_write_json(root / ".ai/context/greenfield.json", {
                "schema_version": "1.0.0", "project_id": "APP", "goal": "旧项目", "mode": "greenfield",
                "stage": "REQUIREMENTS", "checkpoint_status": "PENDING", "locked_decisions": [], "unknowns": []
            })
            init_requirements(root, "APP", "旧项目")
            context = json.loads((root / ".ai/context/greenfield.json").read_text(encoding="utf-8"))
            self.assertEqual("automatic_non_blocking", context["decision_mode"])
            self.assertEqual("AUTO_RECORD_REQUIRED", context["checkpoint_status"])

    def test_brownfield_checkpoint_is_automatic_and_non_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "src").mkdir(); (root / "src/Api.ts").write_text("export const api = true", encoding="utf-8")
            init_brownfield(root, "APP", "调整公共接口")
            set_baseline(root, {"capabilities": [{"id": "CAP-001", "statement": "现有接口", "evidence": ["src/Api.ts"]}]})
            result = reconcile(root, {"requirements": [{
                "id": "REQ-001", "statement": "调整公共接口", "priority": "must", "acceptance": ["新旧客户端兼容"],
                "change_type": "modify", "targets": ["CAP-001"], "impact": {"apis": ["public-api"]}
            }]})
            context = json.loads((root / ".ai/context/requirement-reconciliation.json").read_text(encoding="utf-8"))
            self.assertTrue(result["checkpoint_required"])
            self.assertEqual("automatic_non_blocking", result["checkpoint_mode"])
            self.assertEqual("AUTO_RECORDED", context["checkpoint_status"])
            self.assertIn("非阻塞继续", (root / "REQUIREMENT_DELTA.md").read_text(encoding="utf-8"))
    def test_ignored_dependency_manifest_not_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"node_modules/dependency").mkdir(parents=True);(root/"node_modules/dependency/package.json").write_text(json.dumps({"name":"dependency","dependencies":{"react":"19"}}))
            data=detect(root);self.assertTrue(data["unknown"]);self.assertEqual([],data["projects"])
    def test_checkpoint_label_cannot_escape_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/".ai/runtime").mkdir(parents=True);(root/".ai/schema.json").write_text(json.dumps({"version":"1.0.0"}));p=checkpoint(root,"../../outside",event="manual");self.assertTrue(os.path.samefile(p.parent,root/".ai/runtime/checkpoints"));self.assertNotIn("..",p.name)
    def test_detect_monorepo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            web = root / "web"; web.mkdir(); (web / "package.json").write_text(json.dumps({"name":"web","dependencies":{"vue":"3.5.1"},"devDependencies":{"typescript":"5.7.0"},"scripts":{"test":"vitest","build":"vite build"}}), encoding="utf-8"); (web / "tsconfig.json").write_text("{}")
            unity = root / "unity"; (unity / "ProjectSettings").mkdir(parents=True); (unity / "Packages").mkdir(); (unity / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.62f1\n"); (unity / "Packages" / "manifest.json").write_text(json.dumps({"dependencies":{"com.unity.ugui":"1.0.0"}}))
            data = detect(root)
            kinds = {p["kind"] for p in data["projects"]}
            self.assertIn("web-node", kinds); self.assertIn("unity", kinds); self.assertTrue(data["monorepo"]); web_project=next(x for x in data["projects"] if x["kind"]=="web-node"); self.assertEqual("5.7.0",web_project["languages"][0]["version"])

    def test_detect_pyproject_on_python_310_compatible_path(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"pyproject.toml").write_text('[project]\nname="demo"\nrequires-python=">=3.10"\ndependencies=["FastAPI>=0.100"]\n',encoding="utf-8")
            data=detect(root);project=data["projects"][0];self.assertEqual("python",project["kind"]);self.assertEqual(">=3.10",project["languages"][0]["version"]);self.assertIn("FastAPI",project["frameworks"])

    def test_detect_general_cs_frameworks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"desktop").mkdir();(root/"desktop/App.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0-windows</TargetFramework><UseWPF>true</UseWPF></PropertyGroup></Project>',encoding="utf-8")
            (root/"qt").mkdir();(root/"qt/CMakeLists.txt").write_text('cmake_minimum_required(VERSION 3.24)\nfind_package(Qt6 6.7 REQUIRED COMPONENTS Quick)\nqt_add_executable(app main.cpp)\n',encoding="utf-8")
            (root/"mobile").mkdir();(root/"mobile/package.json").write_text(json.dumps({"name":"mobile","dependencies":{"react-native":"0.80.0"}}),encoding="utf-8")
            projects=detect(root)["projects"]
            names={f["name"] for p in projects for f in p.get("frameworks",[]) if isinstance(f,dict)}
            self.assertTrue({"WPF","Qt","React Native"}.issubset(names))
            versions={f["name"]:f.get("version") for p in projects for f in p.get("frameworks",[]) if isinstance(f,dict)}
            self.assertEqual("net8.0-windows",versions["WPF"]);self.assertEqual("6.7",versions["Qt"]);self.assertEqual("0.80.0",versions["React Native"])

    def test_bootstrap_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "package.json").write_text('{"name":"x"}')
            initialize(root); first = json.loads((root / ".ai/schema.json").read_text()); initialize(root); second = json.loads((root / ".ai/schema.json").read_text())
            self.assertEqual(first["created_at"], second["created_at"]); self.assertTrue((root / ".ai/runtime/task.json").exists())

    def test_control_classification(self):
        self.assertEqual(classify("先暂停当前任务，我要调整"), "PAUSE")
        self.assertEqual(classify("继续执行"), "RESUME")
        self.assertEqual(classify("调整方向：改成Renderer模式"), "ADJUST")
        self.assertIsNone(classify("实现用户列表"))

    def test_checkpoint_records_git_or_non_git(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root); (root/"CURRENT_CONTEXT.md").write_text("# 当前上下文\n\n- KG-001\n",encoding="utf-8"); cp = checkpoint(root, "test")
            data = json.loads(cp.read_text()); self.assertIn("git", data); self.assertIn("runtime/task.json", data["files"]);self.assertIn("root/CURRENT_CONTEXT.md",data["files"])

    def test_session_recovery_prefers_workspace_current_context(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);initialize(root);(root/".ai/governance/project-state.json").write_text(json.dumps({"project_id":"APP"}));(root/"CURRENT_CONTEXT.md").write_text("# 当前上下文\n\n- Task ID：KG-999\n",encoding="utf-8")
            result=subprocess.run([sys.executable,str(PLUGIN/"scripts/session_context.py")],cwd=root,input=json.dumps({"cwd":str(root),"source":"compact"}),text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
            context=json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"];self.assertIn("KG-999",context);self.assertIn("CURRENT_CONTEXT.md",context)

    def test_bounded_context_and_checkpoint_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            atomic_write_json(root / ".ai/governance/context-retention.json", {
                "schema_version": "1.0.0", "active_context_max_chars": 1800,
                "session_context_max_chars": 1200, "max_items_per_section": 3,
                "max_recent_checkpoints": 2, "max_milestone_checkpoints": 1,
                "max_ledger_entries": 3,
            })
            task = json.loads((root / ".ai/runtime/task.json").read_text(encoding="utf-8"))
            task.update({"id": "KG-001", "goal": "长期多会话开发", "completed": [f"完成-{i}" for i in range(20)], "pending": [f"待办-{i}" for i in range(20)]})
            update_active(root, task)
            active = (root / ".ai/runtime/active-context.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(active), 1801); self.assertIn("完整事实见", active)
            for i in range(6): checkpoint(root, f"rolling-{i}", event="auto")
            for i in range(4): checkpoint(root, f"complete-{i}", event="manual")
            files = list((root / ".ai/runtime/checkpoints").glob("*.json"))
            self.assertLessEqual(len(files), 3)
            ledger = json.loads((root / ".ai/runtime/checkpoint-ledger.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(ledger["pruned_count"], 7); self.assertLessEqual(len(ledger["recent_pruned"]), 3)
            self.assertTrue(ledger["pruned_hash_chain"])
            self.assertTrue(list((root / ".ai/archive/checkpoints").rglob("*.zip")))

    def test_skill_route_state_is_bounded_and_checkpointed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            routing = record_routing(
                root, "development", ["客户端技术路由", "客户端组件实现"], ["回归测试规划"],
                loaded_skills=["客户端技术路由", "客户端组件实现"],
            )
            self.assertEqual(2, len(routing["active_atomic_skills"]))
            self.assertEqual("skill-loader-telemetry", routing["receipt_source"])
            self.assertEqual("已应用：03 客户端工程｜客户端技术路由；03 客户端工程｜客户端组件实现", routing["application_receipt"])
            update_active(root, json.loads((root / ".ai/runtime/task.json").read_text(encoding="utf-8")))
            self.assertIn("回归测试规划", (root / ".ai/runtime/active-context.md").read_text(encoding="utf-8"))
            cp = checkpoint(root, "routing")
            snapshot = json.loads(cp.read_text(encoding="utf-8"))
            self.assertTrue(snapshot["files"]["runtime/skill-routing.json"]["exists"])
            with self.assertRaises(ValueError):
                record_routing(root, "development", ["一", "二", "三"], [])
            with self.assertRaisesRegex(ValueError, "exactly match"):
                record_routing(root, "testing", ["回归测试规划"], [], loaded_skills=["完整变更风险评估"])

    def test_model_proposal_separates_current_stage_from_follow_up_actions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"dependencies": {"express": "5.0.0"}}), encoding="utf-8")
            develop = route(root, model_proposal(
                "backend-technology-router", "database-migration-governance",
                stage="development", architecture="backend",
                current_action="修复数据库迁移",
                follow_up_actions=["testing", "review", "release"],
            ))
            self.assertEqual("development", develop["stage"])
            self.assertEqual(["服务端技术路由", "数据库迁移治理"], [item["skill"] for item in develop["selected"]])
            self.assertEqual(["testing", "review", "release"], develop["intent"]["follow_up_actions"])
            self.assertTrue(develop["phase_transition_required"])

    def test_router_uses_structured_client_evidence_not_manifest_substrings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({
                "description": "Web service can send links to Android clients",
                "dependencies": {"vue": "3.5.0", "express": "5.0.0"},
            }), encoding="utf-8")
            facts = inspect_project(root)["project_facts"]
            self.assertNotIn("cs", facts["architectures"])
            data = route(root, model_proposal("cs-client-router", "cs-component-implementation", stage="development", architecture="cs"))
            self.assertFalse(data["accepted"])
            self.assertEqual([], data["selected"])

    def test_router_declares_loader_telemetry_and_phase_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), model_proposal(
                "backend-component-implementation", stage="development", architecture="backend",
                future_terms=["完成后验证回归"], follow_up_actions=["testing"],
            ))
            self.assertEqual("skill-loader-telemetry", data["receipt_source"])
            self.assertTrue(data["phase_transition_required"])

    def test_router_rejects_stage_skill_conflicts_instead_of_rewriting_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wrong = route(root, model_proposal("release-readiness-review", stage="development"))
            self.assertFalse(wrong["accepted"])
            self.assertIn("STAGE_SKILL_CONFLICT", {item["code"] for item in wrong["diagnostics"]})
            merge = route(root, model_proposal("change-ownership-merge", stage="merge"))
            self.assertTrue(merge["accepted"], merge["diagnostics"])
            release = route(root, model_proposal("release-readiness-review", stage="release"))
            self.assertTrue(release["accepted"], release["diagnostics"])

if __name__ == "__main__": unittest.main()
