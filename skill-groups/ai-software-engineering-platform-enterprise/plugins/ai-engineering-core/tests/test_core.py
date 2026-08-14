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
from suite_router import route


class CoreTests(unittest.TestCase):
    def test_router_receipt_wording_and_atomic_quota_contract(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "会话最开始显示使用到的插件名和 Skill 名")
            self.assertEqual(["插件应用回执"], [item["skill"] for item in data["selected"]])
            self.assertEqual(2, data["max_loaded_atomic_skills"])
            self.assertFalse(data["router_counts_toward_limit"])

    def test_router_defers_third_skill_instead_of_dropping_it(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "大型项目多Agent跨模块实现、测试并发布")
            self.assertEqual(2, len(data["selected"]))
            self.assertTrue(data["deferred"])
            self.assertTrue(data["next_gate"])
            self.assertLessEqual(len(data["load"]), 2)

    def test_ultra_long_single_session_routes_to_bounded_memory(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "我经常一个会话超长处理，经历超多轮上下文压缩，也不能丢内容")
            self.assertIn("有界上下文记忆", [item["skill"] for item in data["selected"]])

    def test_architecture_idea_is_challenged_without_expanding_normal_requests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proposal = route(root, "我提供了系统架构思路，请找出毛病、遗漏并给出更好的替代方案")
            names = [item["skill"] for item in proposal["selected"]]
            self.assertIn("架构决策挑战与补全", names)
            self.assertLessEqual(len(proposal["load"]), 2)
            ordinary = route(root, "解释一下什么是B/S架构")
            self.assertNotIn("架构决策挑战与补全", [item["skill"] for item in ordinary["selected"]])

    def test_router_lazily_selects_interaction_conflict_governance(self):
        with tempfile.TemporaryDirectory() as td:
            data=route(Path(td),"检查大型项目的下拉框、弹窗、快捷键和请求乱序交互冲突")
            self.assertEqual(["交互状态与冲突治理"],[x["skill"] for x in data["selected"]])
            self.assertLessEqual(len(data["load"]),2)

    def test_router_escalates_generic_long_chain_without_case_specific_terms(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = route(root, "这个跨仓库复杂链路已经多轮修复并回滚，继续修改测试后再上线")
            names = [item["skill"] for item in data["selected"]]
            self.assertEqual("长链路变更收敛", names[0])
            self.assertLessEqual(len(data["load"]), 2)
            ordinary = route(root, "修改一个本地按钮文案")
            self.assertNotIn("长链路变更收敛", [item["skill"] for item in ordinary["selected"]])
    def test_greenfield_router_prefers_requirements_before_scaffold(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "从0开始开发一个自定义B/S和C/S教学系统")
            self.assertEqual("greenfield", data["project_mode"])
            self.assertEqual("0→1需求融合与选型", data["selected"][0]["skill"])
            self.assertLessEqual(len(data["load"]), 2)
            common = route(Path(td), "帮我开发一个通用业务管理系统")
            self.assertEqual("0→1需求融合与选型", common["selected"][0]["skill"])

    def test_router_lazily_loads_cs_version_router(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "App.csproj").write_text("<Project />", encoding="utf-8")
            data = route(root, "实现这个WPF客户端页面，识别现有框架和版本")
            self.assertEqual("cs", data["architecture"])
            self.assertEqual(["客户端技术路由", "客户端组件实现"], [x["skill"] for x in data["selected"]])
            self.assertEqual(["03 客户端工程", "03 客户端工程"], [x["plugin"] for x in data["selected"]])

    def test_brownfield_router_reconciles_before_implementation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "package.json").write_text('{"name":"partial-app"}', encoding="utf-8")
            data = route(root, "已有一部分工程源码，继续融合自定义需求")
            self.assertEqual("brownfield", data["project_mode"])
            self.assertEqual(["项目智能初始化", "存量源码需求对账"], [x["skill"] for x in data["selected"]])
            self.assertLessEqual(len(data["load"]), 2)

    def test_router_detects_nested_existing_project_and_backend(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);nested=root/"apps/api";nested.mkdir(parents=True);(nested/"package.json").write_text(json.dumps({"dependencies":{"express":"5.0.0"}}),encoding="utf-8")
            existing=route(root,"开发一个自定义服务");self.assertNotEqual("greenfield",existing["project_mode"])
            backend=route(root,"修改现有NodeTS后端核心服务");names=[x["skill"] for x in backend["selected"]]
            self.assertIn("服务端技术路由",names);self.assertIn("服务端功能实现",names)

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
            data = route(root, "修改当前前端页面")
            self.assertEqual("多工作目录任务管理", data["selected"][0]["skill"])
            self.assertEqual(1, data["source_identity"]["nested_worktree_count"])
            self.assertTrue(all("old-worktree" not in path for path in data["project_evidence"]))

    def test_worktree_pileup_routes_to_safe_convergence(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "清理长期堆积的历史 Worktree")
            self.assertEqual("工作目录安全收敛", data["selected"][0]["skill"])

    def test_plugin_enhancement_is_not_misrouted_to_cs_desktop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / ".git").mkdir()
            data = route(root, "增强 然后审核 推送仓库 本地chatgpt桌面端重新安装生效")
            names = [item["skill"] for item in data["selected"]]
            self.assertEqual("tooling", data["architecture"])
            self.assertIn("完整变更风险评估", names)
            self.assertIn("代码所有权与合并控制", names)
            self.assertNotIn("客户端质量审核", names)

    def test_backend_routes_to_atomic_backend_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"dependencies": {"fastify": "5.2.0"}}), encoding="utf-8")
            data = route(root, "修改已有NodeTS服务端功能并保持接口兼容")
            names = [item["skill"] for item in data["selected"]]
            self.assertEqual(["服务端技术路由", "服务端功能实现"], names)
            self.assertTrue(all(item["plugin"] == "02 浏览器端与服务端工程" for item in data["selected"]))

    def test_router_distinguishes_web_api_desktop_and_react_native(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Api.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>', encoding="utf-8")
            api = route(root, "修改登录逻辑")
            self.assertEqual("backend", api["architecture"])
            self.assertEqual(["服务端技术路由", "服务端功能实现"], [x["skill"] for x in api["selected"]])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"dependencies": {"react": "19.0.0", "react-native": "0.80.0"}}), encoding="utf-8")
            mobile = route(root, "修改登录逻辑")
            self.assertEqual("cs", mobile["architecture"])
            self.assertEqual(["客户端技术路由", "客户端组件实现"], [x["skill"] for x in mobile["selected"]])

    def test_router_handles_fastify_hybrid_and_plugin_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"dependencies": {"fastify": "5.2.0"}}), encoding="utf-8")
            data = route(root, "修改登录逻辑")
            self.assertEqual("backend", data["architecture"])
            self.assertEqual(["服务端技术路由", "服务端功能实现"], [x["skill"] for x in data["selected"]])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"dependencies": {"react": "19.0.0", "express": "5.1.0"}}), encoding="utf-8")
            data = route(root, "修改登录功能，包含前端页面和后端接口")
            self.assertEqual("hybrid", data["architecture"])
            self.assertEqual(["任务分流与会话规划"], [x["skill"] for x in data["selected"]])
            self.assertEqual("medium", data["confidence"])
        for request in ("检查桌面端插件为什么选择很慢", "Skill 是否会走偏和变慢"):
            data = route(Path(td), request)
            self.assertEqual("tooling", data["architecture"])
            self.assertEqual("完整变更风险评估", data["selected"][0]["skill"])

    def test_router_selects_master_governance_for_session_runtime_sprawl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for request in (
                "总控每次派发任务都创建新会话和Worktree，导致会话堆积和线程没关闭",
                "让总控复用固定角色槽位并在终态自动验证运行时释放",
            ):
                data = route(root, request)
                self.assertEqual("大型工程多智能体总控", data["selected"][0]["skill"])

    def test_router_receipt_uses_chinese_names_without_consuming_functional_slot(self):
        with tempfile.TemporaryDirectory() as td:
            data=route(Path(td),"大型项目风险审核，并告诉我用了什么插件")
            self.assertEqual(2,len(data["selected"]));self.assertEqual("完整变更风险评估",data["selected"][0]["skill"])
            for item in data["selected"]:
                self.assertIsNone(__import__("re").search(r"[A-Za-z]",item["skill"]));self.assertIsNone(__import__("re").search(r"[A-Za-z]",item["plugin"]))

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

    def test_router_primary_action_beats_risk_and_validation_qualifiers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({"dependencies": {"express": "5.0.0"}}), encoding="utf-8")
            develop = route(root, "开发 PostgreSQL 迁移风险修复")
            self.assertEqual("development", develop["stage"])
            self.assertEqual("development", develop["intent"]["primary_action"])
            self.assertEqual(["服务端技术路由", "数据库迁移治理"], [item["skill"] for item in develop["selected"]])
            repair = route(root, "修复 PostgreSQL 数据库迁移并验证回滚")
            self.assertEqual("development", repair["stage"])
            self.assertIn("testing", repair["intent"]["follow_up_actions"])
            review = route(root, "审核 PostgreSQL 迁移风险")
            self.assertEqual("review", review["stage"])
            verify = route(root, "验证 PostgreSQL 迁移回滚")
            self.assertEqual("testing", verify["stage"])

    def test_router_uses_structured_client_evidence_not_manifest_substrings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(json.dumps({
                "description": "Web service can send links to Android clients",
                "dependencies": {"vue": "3.5.0", "express": "5.0.0"},
            }), encoding="utf-8")
            data = route(root, "实现当前功能")
            self.assertNotEqual("cs", data["architecture"])
            self.assertNotIn("客户端技术路由", [item["skill"] for item in data["selected"]])

    def test_router_declares_loader_telemetry_and_phase_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "修复接口并验证回归")
            self.assertEqual("skill-loader-telemetry", data["receipt_source"])
            self.assertTrue(data["phase_transition_required"])
            self.assertEqual("development", data["intent"]["primary_action"])

    def test_router_understands_completed_qualifiers_and_governance_actions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual("development", route(root, "按已审核设计实现Avalonia设置窗口")["stage"])
            self.assertEqual("merge", route(root, "检查feature/web合并main的冲突和所有权")["stage"])
            self.assertEqual("release", route(root, "根据真实测试和构建证据审核发布")["stage"])
            self.assertEqual("review", route(root, "分析feature分支相对main的风险")["stage"])

if __name__ == "__main__": unittest.main()
