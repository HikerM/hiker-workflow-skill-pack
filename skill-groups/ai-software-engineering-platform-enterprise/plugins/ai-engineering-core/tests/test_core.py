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
from statectl import checkpoint, update_active
from corelib import atomic_write_json
from requirements_fusion import init as init_requirements, merge as merge_requirements, validate as validate_requirements
from suite_router import route


class CoreTests(unittest.TestCase):
    def test_greenfield_router_prefers_requirements_before_scaffold(self):
        with tempfile.TemporaryDirectory() as td:
            data = route(Path(td), "从0开始开发一个自定义B/S和C/S教学系统")
            self.assertEqual("greenfield", data["project_mode"])
            self.assertEqual("greenfield-project-planning", data["selected"][0]["skill"])
            self.assertLessEqual(len(data["load"]), 2)
            common = route(Path(td), "帮我开发一个学生管理系统")
            self.assertEqual("greenfield-project-planning", common["selected"][0]["skill"])

    def test_router_lazily_loads_cs_version_router(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "App.csproj").write_text("<Project />", encoding="utf-8")
            data = route(root, "实现这个WPF客户端页面，识别现有框架和版本")
            self.assertEqual("cs", data["architecture"])
            self.assertEqual(["cs-client-router", "cs-component-implementation"], [x["skill"] for x in data["selected"]])

    def test_requirements_merge_preserves_revision_and_conflicts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); init_requirements(root, "APP", "自定义业务系统")
            first = merge_requirements(root, [{"id":"REQ-001","statement":"支持离线使用","priority":"must","acceptance":["断网可打开核心数据"]}])
            second = merge_requirements(root, [{"id":"REQ-001","statement":"支持离线使用并在联网后同步","priority":"must","acceptance":["断网可用","联网自动同步"],"conflicts_with":["REQ-002"]}])
            self.assertTrue(first["ok"]); self.assertEqual(["REQ-001"], second["updated"]); self.assertEqual(1, second["conflicts"])
            ledger = json.loads((root / ".ai/requirements/ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(ledger["requirements"][0]["history"]))
            self.assertTrue(validate_requirements(root)["ok"]); self.assertIn("REQ-001", (root / "REQUIREMENTS.md").read_text(encoding="utf-8"))
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
            root = Path(td); initialize(root); cp = checkpoint(root, "test")
            data = json.loads(cp.read_text()); self.assertIn("git", data); self.assertIn("runtime/task.json", data["files"])

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

if __name__ == "__main__": unittest.main()
