from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
PLUGIN=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PLUGIN/"scripts"))
from git_workspace import cmd_create,cmd_list,cmd_pause,cmd_remove
from merge_guard import changed,conflict_probe
from task_router import route
from workspacelib import safe_branch,state_lock,common_dir

class A:pass

def git(root,*args):return subprocess.run(["git",*args],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)

class WorkspaceTests(unittest.TestCase):
    def repo(self,root:Path):
        git(root,"init","-b","main");git(root,"config","user.email","test@example.com");git(root,"config","user.name","Test");(root/"a.txt").write_text("a\n");git(root,"add",".");git(root,"commit","-m","init")
    def test_router(self):
        data=route("设计架构并实现Web和Unity，最后测试发布");names={x["lane"] for x in data["lanes"]};self.assertTrue({"architecture","web","unity","qa","release"}.issubset(names))
    def test_worktree_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"repo";root.mkdir();self.repo(root);a=A();a.task_id="web";a.base="main";a.branch="feature/web";a.path=str(Path(td)/"wt")
            created=cmd_create(root,a);self.assertTrue(Path(created["path"]).exists());self.assertTrue(cmd_list(root)["worktrees"]);p=A();p.task_id="web";cmd_pause(root,p,"PAUSED")
            # Fast-forward-compatible empty branch is an ancestor of main, so safe remove.
            r=A();r.task_id="web";r.target="main";r.force=False;removed=cmd_remove(root,r);self.assertTrue(removed["ok"])
    def test_branch_sanitization_and_stale_lock_recovery(self):
        self.assertEqual("feature/a-b/c",safe_branch("feature/a b/c"))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repo(root);lock=common_dir(root)/"ai-engineering/workspace.lock";lock.parent.mkdir(parents=True,exist_ok=True);lock.write_text('{"pid":999999,"created":0}')
            with state_lock(root,timeout=1,stale_after=0.01):pass
            self.assertFalse(lock.exists())
    def test_merge_probe_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.repo(root);git(root,"checkout","-b","feature");(root/"a.txt").write_text("feature\n");git(root,"commit","-am","feature");git(root,"checkout","main");(root/"a.txt").write_text("main\n");git(root,"commit","-am","main")
            probe=conflict_probe(root,"main","feature");self.assertTrue(probe["potential_conflict"])
if __name__=="__main__":unittest.main()
