from __future__ import annotations
import json,os,re,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/"plugins/ai-engineering-core/scripts";WORK=ROOT/"plugins/ai-engineering-workspace/scripts";QUALITY=ROOT/"plugins/ai-engineering-quality/scripts"
sys.path.insert(0,str(ROOT))
from install_personal import enable_plugins_in_config
from tools.audit_skill_coherence import audit as coherence_audit
def child_env(extra=None):
    env=dict(os.environ);env.update(extra or {});env["PYTHONIOENCODING"]="utf-8";env["PYTHONUTF8"]="1";return env
def run(args,cwd,input_text=None,check=True):return subprocess.run(args,cwd=cwd,input=input_text,text=True,encoding="utf-8",errors="replace",env=child_env(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)
def git(root,*args):return run(["git",*args],root)
def main()->int:
    checks=[]
    coherence=coherence_audit(ROOT);checks.append(("skill-coherence",coherence.get("ok") is True and coherence.get("skill_count")==42))
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/"repo";root.mkdir();git(root,"init","-b","main");git(root,"config","user.email","test@example.com");git(root,"config","user.name","Smoke")
        (root/"package.json").write_text(json.dumps({"name":"smoke","packageManager":"pnpm@9","dependencies":{"vue":"3.5.1"},"devDependencies":{"typescript":"5.7.0"},"scripts":{"lint":"eslint .","test":"vitest run","build":"vite build"}}));(root/"src").mkdir();(root/"src/a.ts").write_text("export const a=1\n");git(root,"add",".");git(root,"commit","-m","chore: initialize smoke repository");git(root,"branch","develop");git(root,"branch","release")
        run([sys.executable,str(CORE/"bootstrap_project.py"),"--root",str(root)],root);checks.append(("bootstrap",(root/".ai/context/tech-stack.json").exists()))
        run([sys.executable,str(CORE/"statectl.py"),"--root",str(root),"task-start","--id","REQ-SMOKE-001","--goal","smoke","--scope","src"],root)
        payload=json.dumps({"cwd":str(root),"trigger":"auto","session_id":"smoke"});pc=run([sys.executable,str(CORE/"precompact_snapshot.py")],root,payload);checks.append(("precompact",json.loads(pc.stdout).get("continue") is True and any((root/".ai/runtime/checkpoints").glob("*.json"))))
        sc=run([sys.executable,str(CORE/"session_context.py")],root,json.dumps({"cwd":str(root),"source":"compact"}));session=json.loads(sc.stdout).get("hookSpecificOutput",{}).get("additionalContext","");checks.append(("recovery", "REQ-SMOKE-001" in session))
        memory=json.loads(run([sys.executable,str(CORE/"statectl.py"),"--root",str(root),"memory-status"],root).stdout).get("memory",{});checks.append(("bounded-memory",len(session)<=6501 and memory.get("active_context_chars",99999)<=12000 and (root/".ai/governance/context-retention.json").exists() and (root/".ai/runtime/checkpoint-ledger.json").exists()))
        run([sys.executable,str(WORK/"governance_state.py"),"--root",str(root),"init","--project-id","SMOKE","--architecture","bs"],root)
        run([sys.executable,str(WORK/"governance_state.py"),"--root",str(root),"task-create","--task-id","KG-001","--goal","smoke web feature","--branch","feature/KG-001-web"],root)
        run([sys.executable,str(WORK/"governance_state.py"),"--root",str(root),"transition","--task-id","KG-001","--to","Planning","--agent-role","Planning Agent"],root)
        run([sys.executable,str(WORK/"convergence_guard.py"),"--root",str(root),"--task-id","KG-001","init","--criterion","AC-001|现有行为保持可用|runtime","--strategy","最小有界改造"],root)
        run([sys.executable,str(WORK/"convergence_guard.py"),"--root",str(root),"--task-id","KG-001","route-set","--responsibility","feature-entry","--route-id","current-entry","--status","ACTIVE"],root)
        run([sys.executable,str(WORK/"convergence_guard.py"),"--root",str(root),"--task-id","KG-001","evidence-record","--criterion-id","AC-001","--level","runtime","--status","PASS","--value","smoke runtime passed","--fingerprint","smoke-runtime-v1"],root)
        convergence=json.loads(run([sys.executable,str(WORK/"convergence_guard.py"),"--root",str(root),"--task-id","KG-001","status","--phase","merge"],root).stdout);checks.append(("long-chain-convergence",convergence.get("ok") is True and convergence.get("result",{}).get("severity")=="STABLE"))
        wt=Path(td)/"web-wt";created=run([sys.executable,str(WORK/"git_workspace.py"),"--root",str(root),"create","--task-id","KG-001","--base","develop","--branch","feature/KG-001-web","--path",str(wt)],root);checks.append(("governed-worktree",json.loads(created.stdout).get("ok") is True and wt.exists()))
        (root/"migration.sql").write_text("create table x(id int);\n");git(root,"add","migration.sql");(root/"src/a.ts").write_text("export const a=2\n");(root/"auth").mkdir();(root/"auth/login.py").write_text("token='x'\n")
        risk=run([sys.executable,str(QUALITY/"risk_review.py"),"--root",str(root),"--mode","all-local"],root);rd=json.loads(risk.stdout);paths={x["path"] for x in rd["changes"]};checks.append(("complete-change-set",{"migration.sql","src/a.ts","auth/login.py"}.issubset(paths)));checks.append(("risk-tags",{"database","security"}.issubset(set(rd["risk"]["tags"]))))
        run([sys.executable,str(QUALITY/"graph_store.py"),"--root",str(root),"index"],root);imp=run([sys.executable,str(QUALITY/"graph_store.py"),"--root",str(root),"impact","--seed","src/a.ts","--depth","2","--limit","1"],root);idata=json.loads(imp.stdout);checks.append(("graph-limit",len(idata["nodes"])<=1))
        plan=run([sys.executable,str(QUALITY/"test_plan.py"),"--root",str(root)],root);pd=json.loads(plan.stdout);cmds={x["command"] for x in pd["mandatory"]+pd["recommended"]};checks.append(("real-commands",{"pnpm lint","pnpm test","pnpm build"}.issubset(cmds)))
        # Personal marketplace installation is verified in an isolated HOME.
        fake_home=Path(td)/"home";fake_home.mkdir();(fake_home/".codex").mkdir();(fake_home/".codex/AGENTS.md").write_text("# Existing rules\n\n- keep me\n",encoding="utf-8");env=child_env({"HOME":str(fake_home),"USERPROFILE":str(fake_home)})
        inst=subprocess.run([sys.executable,str(ROOT/"install_personal.py")],cwd=ROOT,env=env,text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        install_result=json.loads(inst.stdout) if inst.returncode==0 else {}
        market=json.loads((fake_home/".agents/plugins/marketplace.json").read_text(encoding="utf-8")) if inst.returncode==0 else {}
        cache_manifests=list((fake_home/".codex/plugins/cache/personal-ai-engineering-marketplace").glob("*/*+codex.*/.codex-plugin/plugin.json"))
        checks.append(("personal-install",inst.returncode==0 and install_result.get("verification",{}).get("ok") is True and all(str(x.get("source",{}).get("path","")).startswith("./.codex/plugins/") for x in market.get("plugins",[])) and len(cache_manifests)==5))
        enabled=enable_plugins_in_config(fake_home,"personal-ai-engineering-marketplace","smoke");config_path=fake_home/".codex/config.toml";config=config_path.read_text(encoding="utf-8")
        enabled_again=enable_plugins_in_config(fake_home,"personal-ai-engineering-marketplace","smoke-2")
        expected_ids={f"{name}@personal-ai-engineering-marketplace" for name in ["ai-engineering-core","ai-engineering-web","ai-engineering-unity","ai-engineering-workspace","ai-engineering-quality"]}
        valid_sections=all(len(re.findall(rf'(?m)^\[plugins\."{re.escape(name)}"\]\r?\nenabled = true$',config))==1 for name in expected_ids)
        checks.append(("config-activation-fallback",enabled["status"]=="unchanged" and enabled_again["status"]=="unchanged" and valid_sections))
        agents=(fake_home/".codex/AGENTS.md").read_text(encoding="utf-8") if inst.returncode==0 else "";forbidden_group_terms=("第一组","第二组","第三组","组别")
        checks.append(("global-auto-application","keep me" in agents and agents.count("<!-- ai-engineering-global-governance start -->")==1 and "已应用：插件中文名称｜实际加载的 Skill 中文名称" in agents and "智能工程轻量路由" in agents and not any(term in agents for term in forbidden_group_terms) and "ai-engineering-router" not in agents and "bounded-context-memory" not in agents))
        core_cache=fake_home/".codex/plugins/cache/personal-ai-engineering-marketplace/ai-engineering-core"
        for stale in ("5.3.0+codex.stale-a","5.4.0+codex.stale-b"):(core_cache/stale).mkdir(parents=True)
        inst2=subprocess.run([sys.executable,str(ROOT/"install_personal.py")],cwd=ROOT,env=env,text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        agents2=(fake_home/".codex/AGENTS.md").read_text(encoding="utf-8") if inst2.returncode==0 else "";checks.append(("global-rules-idempotent",inst2.returncode==0 and agents2.count("<!-- ai-engineering-global-governance start -->")==1))
        checks.append(("cache-retention",inst2.returncode==0 and len([p for p in core_cache.iterdir() if p.is_dir()])<=2 and bool(json.loads(inst2.stdout).get("cache_pruned"))))
        uninstall=subprocess.run([sys.executable,str(ROOT/"uninstall_personal.py"),"--yes"],cwd=ROOT,env=env,text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        after=(fake_home/".codex/AGENTS.md").read_text(encoding="utf-8") if uninstall.returncode==0 else "";checks.append(("global-rules-safe-uninstall",uninstall.returncode==0 and "keep me" in after and "ai-engineering-global-governance" not in after))
        opt_home=Path(td)/"opt-out-home";opt_home.mkdir();opt_env=child_env({"HOME":str(opt_home),"USERPROFILE":str(opt_home)})
        opt=subprocess.run([sys.executable,str(ROOT/"install_personal.py"),"--no-merge-global-agents","--no-activate-plugins"],cwd=ROOT,env=opt_env,text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        checks.append(("global-rules-opt-out",opt.returncode==0 and not (opt_home/".codex/AGENTS.md").exists()))
        repo_dest=Path(td)/"target";repo_dest.mkdir();ri=subprocess.run([sys.executable,str(ROOT/"install_repo.py"),str(repo_dest)],cwd=ROOT,text=True,encoding="utf-8",errors="replace",env=child_env(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        checks.append(("repo-install",ri.returncode==0 and (repo_dest/".agents/plugins/marketplace.json").exists()))
    failed=[name for name,value in checks if not value];print(json.dumps({"ok":not failed,"checks":[{"name":n,"ok":bool(v)} for n,v in checks],"failed":failed},ensure_ascii=False,indent=2));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
