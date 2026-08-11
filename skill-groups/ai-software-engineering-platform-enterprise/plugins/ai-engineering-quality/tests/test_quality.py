from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
PLUGIN=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PLUGIN/"scripts"))
from change_set import collect
from graph_store import connect,impact,index
from qualitylib import glob_match,worktree_fingerprint
from risk_review import review
from release_review import review as release_review
from test_plan import plan

def git(root,*args,check=True):return subprocess.run(["git",*args],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)
def repo(root:Path):
    git(root,"init","-b","main");git(root,"config","user.email","test@example.com");git(root,"config","user.name","Test");(root/"README.md").write_text("init\n");git(root,"add",".");git(root,"commit","-m","init")

class QualityTests(unittest.TestCase):
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
if __name__=="__main__":unittest.main()
