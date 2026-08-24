from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
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
from context_budget import build_context_plan
from state_consistency import assess as assess_state_consistency, repair as repair_state_consistency
from requirements_fusion import init as init_requirements, merge as merge_requirements, validate as validate_requirements
from brownfield_reconcile import initialize as init_brownfield, set_baseline, reconcile, validate as validate_brownfield
from suite_router import inspect_project, route
from session_epoch import assess as assess_epoch, record as record_epoch, rotate as rotate_epoch
from bounded_run import run_bounded
from suite_version import inspect_suite


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
    def test_five_plugins_share_one_exact_suite_version(self):
        report = inspect_suite()
        self.assertTrue(report["consistent"], report)
        self.assertEqual(5, len(report["versions"]))

    def test_session_epoch_concurrent_records_do_not_lose_counts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); initialize(root)
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _:record_epoch(root,tool_calls=1),range(40)))
            self.assertEqual(40,assess_epoch(root)["counters"]["tool_calls"])

    def test_session_epoch_rotates_only_after_checkpointed_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            report = record_epoch(root, substantive_turns=40, tool_calls=2, tool_output_chars=1000, compactions=0, stage_transitions=1)
            self.assertTrue(report["rotation_required"])
            self.assertIn("substantive_turns", report["reasons"])
            with self.assertRaises(RuntimeError):
                rotate_epoch(root, "")
            rotated = rotate_epoch(root, "CP-EPOCH-001")
            self.assertFalse(rotated["rotation_required"])
            self.assertEqual(2, rotated["epoch"])
            self.assertEqual("CP-EPOCH-001", assess_epoch(root)["last_checkpoint_id"])

    def test_session_epoch_soft_limit_recommends_checkpoint_without_forcing_rotation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            report = record_epoch(root, substantive_turns=15)
            self.assertTrue(report["checkpoint_recommended"])
            self.assertFalse(report["rotation_required"])
            self.assertTrue(report["continuation_allowed"])
            self.assertEqual("WARNING", report["risk"])

    def test_legacy_epoch_policy_is_tightened_and_blocks_continuation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);initialize(root)
            policy=root/".ai/governance/context-retention.json"
            data=json.loads(policy.read_text(encoding="utf-8"));data.update({
                "schema_version":"1.0.0","max_session_epoch_turns":40,
                "max_session_epoch_tool_calls":80,"max_session_epoch_tool_output_chars":120000,
                "max_session_epoch_compactions":2,
            });policy.write_text(json.dumps(data),encoding="utf-8")
            report=record_epoch(root,compactions=1)
            self.assertTrue(report["rotation_required"]);self.assertFalse(report["continuation_allowed"])
            self.assertEqual("CRITICAL",report["risk"]);self.assertEqual(1,report["limits"]["compactions"])

    def test_bounded_run_keeps_large_output_out_of_conversation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            report = run_bounded(root, "TEST-LARGE", [sys.executable, "-c", "print('x' * 8000)"], max_chars=800)
            self.assertEqual(0, report["exit_code"])
            self.assertTrue(report["truncated"])
            self.assertLess(len(report["stdout_excerpt"]), 1200)
            evidence = root / report["evidence_path"]
            self.assertTrue(evidence.is_file())
            self.assertGreater(evidence.stat().st_size, 7000)

    def test_session_recovery_prefers_bound_task_context_over_master_summary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            (root / ".ai/governance/project-state.json").write_text(json.dumps({"project_id": "APP"}), encoding="utf-8")
            (root / "CURRENT_CONTEXT.md").write_text("# 总控\n\n- OTHER\n", encoding="utf-8")
            task_context = root / ".ai/runtime/task-contexts/KG-123.md"
            task_context.parent.mkdir(parents=True, exist_ok=True)
            task_context.write_text("# 任务上下文\n\n- BOUND-KG-123\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(PLUGIN / "scripts/session_context.py")], cwd=root, input=json.dumps({"cwd": str(root), "source": "test", "taskId": "kg-123", "roleFamily": "writer", "ownershipLane": "frontend"}), text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("BOUND-KG-123", context)
            self.assertNotIn("OTHER", context)
            self.assertIn("Lane=frontend", context)

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
            initialize(Path(td))
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
            self.assertIn("admission_cache", data)

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
            initialize(Path(td))
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
            subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
            (root / "package.json").write_text(json.dumps({"dependencies": {"vue": "3.5.0"}}), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True); subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
            initialize(root)
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

    def test_context_budget_scales_without_loading_history_or_skill_bodies(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
            (root / "README.md").write_text("# Hiker\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            plan = build_context_plan(root, "development", [f"src/f{i}.ts" for i in range(20)])
            self.assertEqual("small", plan["scale"]["mode"])
            self.assertEqual(2, plan["budget"]["max_active_skills"])
            self.assertEqual(12, len(plan["working_set"]["changed_paths"]))
            self.assertIn("all-skill-bodies", plan["working_set"]["never_default_scan"])
            upgraded = build_context_plan(root, "review", [], {"public-surface"})
            self.assertEqual("standard", upgraded["scale"]["mode"])

    def test_context_budget_uses_bounded_task_index_for_long_running_projects(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
            (root / ".ai/runtime").mkdir(parents=True)
            (root / ".ai/runtime/task-index.json").write_text(json.dumps({"closed_count": 1000}), encoding="utf-8")
            plan = build_context_plan(root, "governance")
            self.assertEqual("large", plan["scale"]["mode"])
            self.assertEqual("bounded-index-only", plan["budget"]["history_scope"])

    def test_state_consistency_repairs_incremental_and_material_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "hiker"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Hiker"], cwd=root, check=True)
            (root / "README.md").write_text("# Hiker\n", encoding="utf-8")
            (root / "package.json").write_text('{"name":"hiker"}', encoding="utf-8")
            subprocess.run(["git", "add", "README.md", "package.json"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "feat: initialize"], cwd=root, check=True, stdout=subprocess.PIPE)
            first = repair_state_consistency(root)
            self.assertTrue(first["repaired"])
            self.assertTrue(assess_state_consistency(root)["ok"])

            (root / "README.md").write_text("# Hiker\n\nupdated\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "docs: update"], cwd=root, check=True, stdout=subprocess.PIPE)
            self.assertEqual("L1", assess_state_consistency(root)["recovery_level"])
            repair_state_consistency(root)

            (root / "package.json").write_text('{"name":"hiker","version":"2"}', encoding="utf-8")
            subprocess.run(["git", "add", "package.json"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "feat: update manifest"], cwd=root, check=True, stdout=subprocess.PIPE)
            self.assertEqual("L2", assess_state_consistency(root)["recovery_level"])

    def test_state_consistency_detects_local_repository_identity_drift_without_remote(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            first = base / "first"; second = base / "second"; first.mkdir(); second.mkdir()
            for root in (first, second):
                subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
            repair_state_consistency(first)
            stored = json.loads((first / ".ai/governance/source-provenance.json").read_text(encoding="utf-8"))
            (second / ".ai/governance").mkdir(parents=True)
            (second / ".ai/governance/source-provenance.json").write_text(json.dumps(stored), encoding="utf-8")
            report = assess_state_consistency(second)
            self.assertEqual("L4", report["recovery_level"])
            self.assertEqual("PROJECT_IDENTITY_DRIFT", report["status"])

    def test_projects_without_ai_use_stateless_current_request_policy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = assess_state_consistency(root)
            self.assertTrue(report["ok"])
            self.assertEqual("STATELESS_UNMANAGED", report["status"])
            self.assertEqual("CURRENT_REQUEST_AND_GIT_ONLY", report["execution_policy"]["mode"])
            self.assertFalse(report["execution_policy"]["trusted_ai_state"])
            self.assertFalse(report["execution_policy"]["requires_state_recovery"])
            routed = route(root, model_proposal("web-component-implementation", stage="development", architecture="bs"))
            self.assertTrue(routed["accepted"], routed["diagnostics"])
            first_governance = route(root, model_proposal("workspace-task-router", stage="governance"))
            self.assertTrue(first_governance["accepted"], first_governance["diagnostics"])

    def test_legacy_ai_without_provenance_is_quarantined_and_cannot_be_auto_trusted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".ai/runtime").mkdir(parents=True)
            (root / ".ai/runtime/task.json").write_text(json.dumps({"id": "OLD", "status": "Development"}), encoding="utf-8")
            report = assess_state_consistency(root)
            self.assertEqual("UNTRUSTED_AI_STATE", report["status"])
            self.assertEqual("QUARANTINE_AI_STATE", report["execution_policy"]["mode"])
            self.assertFalse(report["execution_policy"]["may_resume_old_tasks"])
            repaired = repair_state_consistency(root)
            self.assertTrue(repaired["repair_blocked"])
            self.assertFalse((root / ".ai/governance/source-provenance.json").exists())
            with self.assertRaisesRegex(RuntimeError, "untrusted"):
                initialize(root)
            blocked = route(root, model_proposal("workspace-task-router", stage="governance"))
            self.assertFalse(blocked["accepted"])
            self.assertIn("STALE_AI_STATE_DEPENDENCY", {item["code"] for item in blocked["diagnostics"]})
            stateless = route(root, model_proposal("backend-component-implementation", stage="development", architecture="backend"))
            self.assertTrue(stateless["accepted"], stateless["diagnostics"])
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
            self.assertTrue(routing["suite_version"])
            self.assertTrue(routing["suite_fingerprint"])
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

    def test_router_blocks_old_suite_state_until_recovery_skill_migrates_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); initialize(root)
            route_state = root / ".ai/runtime/skill-routing.json"
            route_state.write_text(json.dumps({"route_fingerprint": "old", "suite_fingerprint": "old-suite"}), encoding="utf-8")
            blocked = route(root, model_proposal("backend-component-implementation", stage="development", architecture="backend"))
            self.assertFalse(blocked["accepted"])
            self.assertIn("PLUGIN_VERSION_DRIFT", {item["code"] for item in blocked["diagnostics"]})
            recovery = route(root, model_proposal("context-recovery", stage="governance"))
            self.assertTrue(recovery["accepted"], recovery["diagnostics"])
            self.assertTrue(recovery["version_gate"]["drift"])

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

    def test_router_fingerprint_changes_with_goal_revision_and_action(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = route(root, model_proposal("bounded-context-memory", stage="governance", goal_revision="7", current_action="压缩当前工作集"))
            same = route(root, model_proposal("bounded-context-memory", stage="governance", goal_revision="7", current_action="压缩当前工作集"))
            changed = route(root, model_proposal("bounded-context-memory", stage="governance", goal_revision="8", current_action="压缩当前工作集"))
            redirected = route(root, model_proposal("bounded-context-memory", stage="governance", goal_revision="7", current_action="轮换总控纪元"))
            self.assertEqual(first["route_fingerprint"], same["route_fingerprint"])
            self.assertNotEqual(first["route_fingerprint"], changed["route_fingerprint"])
            self.assertNotEqual(first["route_fingerprint"], redirected["route_fingerprint"])

    def test_router_rejects_stage_skill_conflicts_instead_of_rewriting_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            initialize(root)
            wrong = route(root, model_proposal("release-readiness-review", stage="development"))
            self.assertFalse(wrong["accepted"])
            self.assertIn("STAGE_SKILL_CONFLICT", {item["code"] for item in wrong["diagnostics"]})
            merge = route(root, model_proposal("change-ownership-merge", stage="merge"))
            self.assertTrue(merge["accepted"], merge["diagnostics"])
            release = route(root, model_proposal("release-readiness-review", stage="release"))
            self.assertTrue(release["accepted"], release["diagnostics"])

if __name__ == "__main__": unittest.main()
