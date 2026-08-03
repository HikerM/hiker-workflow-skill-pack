from __future__ import annotations
import json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/"plugins/ai-engineering-core/scripts";WORK=ROOT/"plugins/ai-engineering-workspace/scripts";QUALITY=ROOT/"plugins/ai-engineering-quality/scripts"
def run(args,cwd,input_text=None,check=True):return subprocess.run(args,cwd=cwd,input=input_text,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)
def git(root,*args):return run(["git",*args],root)
def main()->int:
    checks=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/"repo";root.mkdir();git(root,"init","-b","main");git(root,"config","user.email","test@example.com");git(root,"config","user.name","Smoke")
        (root/"package.json").write_text(json.dumps({"name":"smoke","packageManager":"pnpm@9","dependencies":{"vue":"3.5.1"},"devDependencies":{"typescript":"5.7.0"},"scripts":{"lint":"eslint .","test":"vitest run","build":"vite build"}}));(root/"src").mkdir();(root/"src/a.ts").write_text("export const a=1\n");git(root,"add",".");git(root,"commit","-m","init")
        run([sys.executable,str(CORE/"bootstrap_project.py"),"--root",str(root)],root);checks.append(("bootstrap",(root/".ai/context/tech-stack.json").exists()))
        run([sys.executable,str(CORE/"statectl.py"),"--root",str(root),"task-start","--id","REQ-SMOKE-001","--goal","smoke","--scope","src"],root)
        payload=json.dumps({"cwd":str(root),"trigger":"auto","session_id":"smoke"});pc=run([sys.executable,str(CORE/"precompact_snapshot.py")],root,payload);checks.append(("precompact",json.loads(pc.stdout).get("continue") is True and any((root/".ai/runtime/checkpoints").glob("*.json"))))
        sc=run([sys.executable,str(CORE/"session_context.py")],root,json.dumps({"cwd":str(root),"source":"compact"}));checks.append(("recovery", "REQ-SMOKE-001" in json.loads(sc.stdout).get("hookSpecificOutput",{}).get("additionalContext","")))
        wt=Path(td)/"web-wt";created=run([sys.executable,str(WORK/"git_workspace.py"),"--root",str(root),"create","--task-id","web","--base","main","--branch","feature/web","--path",str(wt)],root);checks.append(("worktree",json.loads(created.stdout).get("ok") is True and wt.exists()))
        (root/"migration.sql").write_text("create table x(id int);\n");git(root,"add","migration.sql");(root/"src/a.ts").write_text("export const a=2\n");(root/"auth").mkdir();(root/"auth/login.py").write_text("token='x'\n")
        risk=run([sys.executable,str(QUALITY/"risk_review.py"),"--root",str(root),"--mode","all-local"],root);rd=json.loads(risk.stdout);paths={x["path"] for x in rd["changes"]};checks.append(("complete-change-set",{"migration.sql","src/a.ts","auth/login.py"}.issubset(paths)));checks.append(("risk-tags",{"database","security"}.issubset(set(rd["risk"]["tags"]))))
        run([sys.executable,str(QUALITY/"graph_store.py"),"--root",str(root),"index"],root);imp=run([sys.executable,str(QUALITY/"graph_store.py"),"--root",str(root),"impact","--seed","src/a.ts","--depth","2","--limit","1"],root);idata=json.loads(imp.stdout);checks.append(("graph-limit",len(idata["nodes"])<=1))
        plan=run([sys.executable,str(QUALITY/"test_plan.py"),"--root",str(root)],root);pd=json.loads(plan.stdout);cmds={x["command"] for x in pd["mandatory"]+pd["recommended"]};checks.append(("real-commands",{"pnpm lint","pnpm test","pnpm build"}.issubset(cmds)))
        # Personal marketplace installation is verified in an isolated HOME.
        fake_home=Path(td)/"home";fake_home.mkdir();env=dict(os.environ);env["HOME"]=str(fake_home);env["USERPROFILE"]=str(fake_home)
        inst=subprocess.run([sys.executable,str(ROOT/"install_personal.py")],cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        market=json.loads((fake_home/".agents/plugins/marketplace.json").read_text()) if inst.returncode==0 else {}
        checks.append(("personal-install",inst.returncode==0 and all(str(x.get("source",{}).get("path","")).startswith("./.codex/plugins/") for x in market.get("plugins",[]))))
        repo_dest=Path(td)/"target";repo_dest.mkdir();ri=subprocess.run([sys.executable,str(ROOT/"install_repo.py"),str(repo_dest)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        checks.append(("repo-install",ri.returncode==0 and (repo_dest/".agents/plugins/marketplace.json").exists()))
    failed=[name for name,value in checks if not value];print(json.dumps({"ok":not failed,"checks":[{"name":n,"ok":bool(v)} for n,v in checks],"failed":failed},ensure_ascii=False,indent=2));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
