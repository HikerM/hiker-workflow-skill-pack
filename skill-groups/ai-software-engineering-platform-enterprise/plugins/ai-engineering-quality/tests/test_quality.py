from __future__ import annotations
import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
PLUGIN=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PLUGIN/"scripts"))
SUITE=PLUGIN.parents[1];sys.path.insert(0,str(SUITE/"tools"))
from change_set import collect
from architecture_guard import evaluate as architecture_evaluate
from graph_store import connect,impact,index
from qualitylib import glob_match,worktree_fingerprint
from risk_review import review
from release_review import review as release_review
from test_plan import plan
from interaction_guard import evaluate as interaction_evaluate, run as interaction_run
from audit_skill_coherence import audit as coherence_audit
from harness_preflight import preflight
from handoff_redactor import redact_text, scan as redaction_scan

def git(root,*args,check=True):return subprocess.run(["git",*args],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)
def repo(root:Path):
    git(root,"init","-b","main");git(root,"config","user.email","test@example.com");git(root,"config","user.name","Test");(root/"README.md").write_text("init\n");git(root,"add",".");git(root,"commit","-m","init")

class QualityTests(unittest.TestCase):
    def test_skill_coherence_audits_every_skill_and_detects_receipt_distortion(self):
        current=coherence_audit(SUITE);self.assertTrue(current["ok"],current["errors"]);self.assertEqual(42,current["skill_count"]);self.assertEqual(42,len(current["audited_skills"]))
        with tempfile.TemporaryDirectory() as td:
            copied=Path(td)/"suite";shutil.copytree(SUITE,copied,ignore=shutil.ignore_patterns("dist","__pycache__","*.pyc"))
            target=copied/"plugins/ai-engineering-workspace/skills/plugin-application-receipt/agents/openai.yaml"
            text=target.read_text(encoding="utf-8").replace("只展示本轮实际应用的插件中文名和Skill中文名", "展示本轮项目、模式和触发原因")
            target.write_text(text,encoding="utf-8")
            distorted=coherence_audit(copied);self.assertFalse(distorted["ok"]);self.assertIn("RECEIPT_SCOPE_CONFLICT",{item["code"] for item in distorted["errors"]})

    def test_interaction_guard_is_zero_config_and_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data=interaction_run(root,None,"review");self.assertEqual("NOT_APPLICABLE",data["status"])
            interactions=[]
            for i in range(500):
                interactions.append({"id":f"INT-MODULE-{i}","owner":"module","scope":f"module-{i}","surface":"button","initial_state":"idle","states":["idle","done"],"transitions":[{"event":"activate","from":"idle","to":"done"}],"evidence":["test"]})
            started=__import__("time").perf_counter();result=interaction_evaluate({"interactions":interactions},"review");elapsed=(__import__("time").perf_counter()-started)*1000
            self.assertEqual("PASS",result["status"]);self.assertLess(elapsed,100)
    def test_interaction_guard_detects_hidden_state_and_runtime_conflicts(self):
        contract={"interactions":[
            {"id":"INT-SEARCH-SELECT","owner":"search","scope":"page","surface":"combobox","initial_state":"closed","states":["closed","open","loading","loaded","ghost"],"transitions":[{"event":"open","from":"closed","to":"open"},{"event":"search","from":"open","to":"loading","async":True},{"event":"loaded","from":"loading","to":"loaded"}],"overlay":{"kind":"combobox","group":"page","priority_token":999},"shortcuts":[{"keys":"Ctrl+K","scope":"page"}]},
            {"id":"INT-ACTION","owner":"action","scope":"page","surface":"button","initial_state":"idle","states":["idle","saving"],"transitions":[{"event":"save","from":"idle","to":"saving","async":True,"destructive":True,"policy":"latest-wins","cancel_on":[]}],"shortcuts":[{"keys":"Ctrl+K","scope":"page"}],"evidence":["test"]}
        ]}
        result=interaction_evaluate(contract,"review");codes={x["code"] for x in result["errors"]}
        self.assertEqual("BLOCKED",result["status"]);self.assertTrue({"MISSING_ASYNC_POLICY","UNSAFE_DESTRUCTIVE_ACTION","UNREACHABLE_STATE","RAW_OVERLAY_PRIORITY","SHORTCUT_CONFLICT","HIDDEN_SURFACE_EVIDENCE"}<=codes)
    def test_all_local_includes_staged_unstaged_untracked(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"staged.sql").write_text("create table x(id int);\n");git(root,"add","staged.sql");(root/"README.md").write_text("changed\n");(root/"new.py").write_text("print('x')\n")
            data=collect(root,"all-local");paths={x["path"] for x in data["files"]};self.assertEqual({"staged.sql","README.md","new.py"},paths)
    def test_generated_patterns_are_ignored_and_root_glob_matches(self):
        self.assertTrue(glob_match("src/a.ts","src/**/*.ts"));self.assertTrue(glob_match("auth/login.py","**/auth/**"));self.assertTrue(glob_match(".github/workflows/ci.yml","**/.github/workflows/**"))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"build").mkdir();(root/"build/out.js").write_text("x");(root/"auth").mkdir();(root/"auth/login.py").write_text("x")
            data=review(root,files=["build/out.js","auth/login.py"],mode="files");self.assertEqual(1,data["summary"]["files"]);self.assertIn("security",data["risk"]["tags"])
    def test_rename_and_delete(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"old.txt").write_text("x");git(root,"add",".");git(root,"commit","-m","add");git(root,"mv","old.txt","new.txt")
            data=collect(root,"all-local");self.assertEqual("R",data["files"][0]["status"])
    def test_high_finding_sets_high_overall_risk(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"old.txt").write_text("x\n");git(root,"add","old.txt");git(root,"commit","-m","add file");(root/"old.txt").unlink()
            data=review(root);self.assertEqual("HIGH",data["risk"]["level"]);self.assertTrue(any(x["type"]=="deletion" for x in data["findings"]))
    def test_architecture_guard_blocks_large_file_and_preserves_zero_config(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"src").mkdir();source=root/"src/CoreService.ts";source.write_text("\n".join(f"export const v{i}={i};" for i in range(900))+"\n");git(root,"add",".");git(root,"commit","-m","add core service")
            (root/".ai/governance").mkdir(parents=True);(root/".ai/tasks").mkdir(parents=True)
            (root/".ai/governance/project-state.json").write_text(json.dumps({"project_id":"APP"}))
            (root/".ai/tasks/KG-001.json").write_text(json.dumps({"project_id":"APP","task_id":"KG-001","base_branch":"main","branch":"main","change_contract":{"allowed_files":["src/CoreService.ts"],"allowed_modules":[],"protected_modules":[],"public_contract_changes":[],"behavior_invariants":["现有调用行为不变"],"required_tests":["核心服务回归"],"characterization_tests":[],"consumer_tests":[],"max_blast_radius":80}}))
            text=source.read_text();source.write_text(text.replace("v899=899","v899=900"))
            data=review(root,task_id="KG-001");self.assertEqual("HIGH",data["risk"]["level"]);self.assertEqual("BLOCKED",data["architecture_guard"]["result"]);self.assertTrue(any("文件超过阻断预算" in x for x in data["architecture_guard"]["blockers"]))
            self.assertEqual([],data["architecture_guard"]["dependency_violations"])
    def test_graph_limit_applies_to_seeds_and_stale(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);db=root/"g.db";c=connect(db)
            with c:
                for i in range(500):c.execute("INSERT INTO nodes(path,kind,language,module,sha256,mtime_ns,size,commit_sha,indexed_at) VALUES(?,?,?,?,?,?,?,?,?)",(f"f{i}.py","file","python","m","",0,0,"old","now"))
                c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('commit_sha','old')")
            c.close();data=impact(db,[f"f{i}.py" for i in range(500)],2,300,"both","new");self.assertEqual(300,len(data["nodes"]));self.assertTrue(data["truncated"]);self.assertTrue(data["stale"])
    def test_graph_incremental_health(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"a.py").write_text("import b\n");(root/"b.py").write_text("x=1\n");db=root/"graph.db";meta=index(root,db,[]);self.assertGreaterEqual(meta["node_count"],2)
    def test_graph_resolves_unity_guid_and_dotnet_project_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root)
            assets=root/"Assets";assets.mkdir();guid="0123456789abcdef0123456789abcdef"
            (assets/"Shared.mat").write_text("Material\n",encoding="utf-8");(assets/"Shared.mat.meta").write_text(f"fileFormatVersion: 2\nguid: {guid}\n",encoding="utf-8")
            (assets/"Panel.prefab").write_text(f"m_Material: {{fileID: 2100000, guid: {guid}, type: 2}}\n",encoding="utf-8")
            app=root/"App";lib=root/"Lib";app.mkdir();lib.mkdir();(lib/"Lib.csproj").write_text("<Project />",encoding="utf-8");(app/"App.csproj").write_text('<Project><ItemGroup><ProjectReference Include="..\\Lib\\Lib.csproj" /></ItemGroup></Project>',encoding="utf-8")
            db=root/"graph.db";index(root,db,[]);c=connect(db)
            try:edges={(src,dst,rel) for src,dst,rel in c.execute("SELECT src,dst,relation FROM edges")}
            finally:c.close()
            self.assertIn(("Assets/Panel.prefab","Assets/Shared.mat","references_asset"),edges)
            self.assertIn(("App/App.csproj","Lib/Lib.csproj","depends_on_project"),edges)
    def test_graph_semantic_index_is_incremental(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);assets=root/"Assets";assets.mkdir();guid="0123456789abcdef0123456789abcdef"
            (assets/"Shared.mat").write_text("Material\n",encoding="utf-8");(assets/"Shared.mat.meta").write_text(f"guid: {guid}\n",encoding="utf-8");prefab=assets/"Panel.prefab";prefab.write_text(f"guid: {guid}\n",encoding="utf-8")
            db=root/"graph.db";first=index(root,db,[]);second=index(root,db,[])
            self.assertTrue(first["semantic_full_rebuild"]);self.assertFalse(second["semantic_full_rebuild"]);self.assertEqual(0,second["semantic_sources_updated"])
            prefab.write_text(f"name: changed\nguid: {guid}\n",encoding="utf-8");third=index(root,db,[])
            self.assertFalse(third["semantic_full_rebuild"]);self.assertEqual(1,third["semantic_sources_updated"])
    def test_graph_and_test_plan_ignore_dependency_caches(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"node_modules/pkg").mkdir(parents=True);(root/"node_modules/pkg/package.json").write_text(json.dumps({"scripts":{"test":"bad"}}));(root/"node_modules/pkg/x.ts").write_text("export const x=1")
            db=root/"g.db";meta=index(root,db,[]);self.assertEqual(0,meta["node_count"]);data=plan(root,{"risk":{"level":"LOW","tags":[]},"changes":[]});self.assertFalse(any(x.get("source","").startswith("node_modules/") for x in data["mandatory"]+data["recommended"]))
    def test_graph_clean_after_own_metadata_write(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"a.py").write_text("x=1\n");git(root,"add",".");git(root,"commit","-m","a");db=root/".ai/knowledge/engineering.db";index(root,db,[]);data=impact(db,["a.py"],2,10,"both",git(root,"rev-parse","HEAD").stdout.strip(),worktree_fingerprint(root));self.assertFalse(data["stale"])
    def test_graph_detects_dirty_change_same_head(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"a.py").write_text("x=1\n");git(root,"add",".");git(root,"commit","-m","a");db=root/"g.db";index(root,db,[]);(root/"a.py").write_text("x=2\n")
            data=impact(db,["a.py"],2,10,"both",git(root,"rev-parse","HEAD").stdout.strip(),worktree_fingerprint(root));self.assertTrue(data["stale_worktree"])
    def test_untracked_lines_and_staged_plus_unstaged_sum(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"README.md").write_text("one\n");git(root,"add","README.md");(root/"README.md").write_text("one\ntwo\n");(root/"u.txt").write_text("a\nb\n")
            data=collect(root,"all-local");by={x["path"]:x for x in data["files"]};self.assertGreaterEqual(by["README.md"]["added"],2);self.assertEqual(2,by["u.txt"]["added"])
    def test_architecture_guard_handles_utf8_history_and_skips_binary_growth(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);source=root/"说明.txt";source.write_text("中文历史\n",encoding="utf-8");git(root,"add",".");git(root,"commit","-m","docs: 中文历史")
            source.write_text("中文历史\n新增内容\n",encoding="utf-8");(root/"bundle.zip").write_bytes(b"PK\x03\x04\x00\xff\x80\x00"*1000);git(root,"add",".");git(root,"commit","-m","docs: 更新")
            data=architecture_evaluate(root,mode="range",base="HEAD~1",target="HEAD")
            by={item["path"]:item for item in data["file_growth"]}
            self.assertEqual("binary",by["bundle.zip"]["skipped"]);self.assertEqual(1,by["说明.txt"]["growth"])
            self.assertFalse(any("bundle.zip" in item for item in data["blockers"]+data["warnings"]))
    def test_test_plan_monorepo_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);web=root/"web";web.mkdir();(web/"package.json").write_text(json.dumps({"packageManager":"pnpm@9","scripts":{"test":"vitest run"}}));data=plan(root,{"risk":{"level":"MEDIUM","tags":[]},"changes":[{"path":"web/src/a.ts"}]});self.assertTrue(any(x.get("cwd")=="web" and x["command"]=="pnpm test" for x in data["mandatory"]))
    def test_test_plan_uses_real_package_scripts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);(root/"package.json").write_text(json.dumps({"packageManager":"pnpm@9","scripts":{"lint":"eslint .","build":"vite build"}}));data=plan(root,{"risk":{"level":"MEDIUM","tags":[]},"changes":[]});commands={x["command"] for x in data["mandatory"]+data["recommended"]};self.assertIn("pnpm lint",commands);self.assertIn("pnpm build",commands);self.assertNotIn("npm test -- --runInBand",commands)
    def test_release_review_requires_governed_merged_task_and_docs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root);data=release_review(root,"KG-001");self.assertEqual("BLOCKED",data["result"])
            self.assertTrue(any("发布状态文档缺失" in x for x in data["blockers"]));self.assertTrue(any("项目状态" in x or "任务状态" in x for x in data["blockers"]))

    def test_large_matrix_requires_harness_self_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo(root)
            invalid=preflight(root,{"mandatory":[],"recommended":[]},{"groups":[{"id":"g1","declared_count":2,"cases":["a"],"mutation_required":True}]})
            self.assertEqual("INVALID",invalid["result"]);self.assertFalse(invalid["full_matrix_allowed"])
            valid=preflight(root,{"mandatory":[],"recommended":[]},{"groups":[{"id":"g1","declared_count":1,"cases":["a"],"mutation_required":True,"mutation_evidence":"before!=after","sample_pass":"pass","sample_fail":"fail"}]})
            self.assertEqual("PASS",valid["result"])

    def test_handoff_redaction_blocks_raw_secret_and_emits_safe_copy(self):
        redacted,findings=redact_text("账号 user 密码 123132\nAuthorization: Bearer abcdefghijklmnop")
        self.assertEqual(2,len(findings));self.assertNotIn("123132",redacted);self.assertNotIn("abcdefghijklmnop",redacted)
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"thread.txt";source.write_text("password: secret123",encoding="utf-8")
            raw=redaction_scan(source,None);self.assertEqual("BLOCK",raw["result"]);self.assertFalse(raw["export_allowed"])
            target=Path(td)/"safe.txt";safe=redaction_scan(source,target);self.assertTrue(safe["export_allowed"]);self.assertNotIn("secret123",target.read_text(encoding="utf-8"))
if __name__=="__main__":unittest.main()
