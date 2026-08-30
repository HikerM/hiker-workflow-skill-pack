from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
from qualitylib import git_root,load_json,markdown_table,now,repo_ai,write_json
CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from resource_budget import effective_budget
from evidence_cache import minimum_verification_set
SKIP={"node_modules",".git",".ai","dist","build","Library","Temp","obj","bin",".venv","venv"}
def walk_project_files(root:Path,max_depth:int=6):
    limits=effective_budget("source_scan",{"max_depth":max_depth});max_depth=limits["max_depth"];max_files=limits["max_files"];emitted=0
    for dirpath,dirnames,filenames in os.walk(root):
        current=Path(dirpath);depth=len(current.relative_to(root).parts)
        if depth>=max_depth:dirnames[:]=[]
        else:dirnames[:]=[name for name in dirnames if name not in SKIP]
        for filename in filenames:
            if emitted>=max_files:return
            emitted+=1;yield current/filename

def manifests(root:Path,name:str,max_depth:int=6)->list[Path]:
    return sorted(p for p in walk_project_files(root,max_depth) if p.name==name)

def suffix_files(root:Path,suffixes:set[str],max_depth:int=6)->list[Path]:
    return sorted(p for p in walk_project_files(root,max_depth) if p.suffix.lower() in suffixes)
def relevant(changes:list[str],project:Path,root:Path)->bool:
    if not changes:return True
    rel=project.relative_to(root).as_posix();return rel=="." or any(p==rel or p.startswith(rel+"/") for p in changes)
def package_commands(root:Path,changes:list[str])->list[dict]:
    out=[]
    for p in manifests(root,"package.json"):
        project=p.parent
        if not relevant(changes,project,root):continue
        data=load_json(p,{}) or {};scripts=data.get("scripts",{}) if isinstance(data,dict) else {};raw=str(data.get("packageManager","")).split("@")[0];pm=raw or ("pnpm" if (project/"pnpm-lock.yaml").exists() else "yarn" if (project/"yarn.lock").exists() else "bun" if (project/"bun.lockb").exists() else "npm");prefix={"npm":"npm run","pnpm":"pnpm","yarn":"yarn","bun":"bun run"}.get(pm,f"{pm} run")
        for name in ["lint","typecheck","test","test:unit","test:e2e","build"]:
            if name in scripts:out.append({"name":name,"command":f"{prefix} {name}","cwd":project.relative_to(root).as_posix() or ".","source":p.relative_to(root).as_posix(),"status":"PLANNED"})
    return out
def python_commands(root:Path,changes:list[str])->list[dict]:
    out=[];projects={p.parent for name in ["pyproject.toml","pytest.ini","tox.ini","setup.cfg"] for p in manifests(root,name)}
    for project in sorted(projects):
        if relevant(changes,project,root):out.append({"name":"python-tests","command":"python -m pytest","cwd":project.relative_to(root).as_posix() or ".","source":"pytest-config","status":"PLANNED"})
    return out
def dotnet_commands(root:Path,changes:list[str])->list[dict]:
    out=[]
    for suffix in ({".sln"},{".csproj"}):
        for target in suffix_files(root,suffix):
            if not relevant(changes,target.parent,root):continue
            out.append({"name":"dotnet-tests","command":f'dotnet test "{target.name}"',"cwd":target.parent.relative_to(root).as_posix() or ".","source":target.relative_to(root).as_posix(),"status":"PLANNED"})
        if out:break
    return out
def unity_commands(root:Path,changes:list[str])->list[dict]:
    out=[]
    for pv in manifests(root,"ProjectVersion.txt"):
        if pv.parent.name!="ProjectSettings":continue
        project=pv.parent.parent
        if not relevant(changes,project,root):continue
        cwd=project.relative_to(root).as_posix() or ".";out += [{"name":"unity-editmode","command":"${UNITY_EDITOR} -batchmode -quit -projectPath . -runTests -testPlatform EditMode -testResults .ai/evidence/unity-editmode.xml","cwd":cwd,"source":"Unity Test Framework","status":"REQUIRES_ENV"},{"name":"unity-playmode","command":"${UNITY_EDITOR} -batchmode -quit -projectPath . -runTests -testPlatform PlayMode -testResults .ai/evidence/unity-playmode.xml","cwd":cwd,"source":"Unity Test Framework","status":"REQUIRES_ENV"}]
    return out
def _verification_id(command:dict)->str:
    basis=f"{command.get('cwd')}\0{command.get('command')}"
    return "VERIFY-"+hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

def _verification_scope(command:dict,impact_scope:list[str])->list[str]:
    cwd=str(command.get("cwd") or ".").strip("/") or "."
    if cwd==".":return list(dict.fromkeys(impact_scope))[:64] or ["."]
    scoped=[path for path in impact_scope if path==cwd or path.startswith(cwd+"/")]
    return list(dict.fromkeys(scoped))[:64] or [cwd]

def _reuse_minimum(mandatory:list[dict],risk:dict,impact_scope:list[str])->tuple[list[dict],list[dict]]:
    identity=risk.get("verification_identity") if isinstance(risk.get("verification_identity"),dict) else {}
    required=("source_fingerprint","contract_fingerprint","dependency_fingerprint")
    checks=[]
    for command in mandatory:
        item=dict(command);item["verification_id"]=_verification_id(item);item["affected_scope"]=_verification_scope(item,impact_scope);checks.append(item)
    if not checks:return [],[]
    if not all(identity.get(field) for field in required):return [{**item,"reuse_status":"NOT_ELIGIBLE"} for item in checks],[]
    records=risk.get("verification_records") if isinstance(risk.get("verification_records"),list) else []
    result=minimum_verification_set(checks,records,{field:value for field,value in identity.items() if field!="affected_scope"})
    return result["execute"],result["reused"]

def plan(root:Path,risk:dict)->dict:
    changes=[x.get("path","") for x in risk.get("changes",[]) if x.get("path")];graph=risk.get("graph") if isinstance(risk.get("graph"),dict) else {};impact_nodes=graph.get("nodes",[]) if not graph.get("stale") and not graph.get("truncated") else [];impact_scope=list(dict.fromkeys([*changes,*[str(item) for item in impact_nodes if str(item).strip()]]));tags=set(risk.get("risk",{}).get("tags",[]));level=str(risk.get("risk",{}).get("level") or "MEDIUM").upper();governance=risk.get("semantic_assessment",{}) if isinstance(risk.get("semantic_assessment"),dict) else {};activation=str(governance.get("activation") or ("NONE" if level=="LOW" else "TARGETED" if level=="MEDIUM" else "GOVERNED"));commands=package_commands(root,impact_scope)+python_commands(root,impact_scope)+dotnet_commands(root,impact_scope)+unity_commands(root,impact_scope);seen=set();commands=[x for x in commands if not ((x["cwd"],x["command"]) in seen or seen.add((x["cwd"],x["command"])))]
    mandatory=[];recommended=[];manual=[]
    if level=="LOW" and activation=="NONE":
        priority={"test:unit":0,"python-tests":0,"dotnet-tests":0,"unity-editmode":0,"test":1,"lint":2,"typecheck":3,"build":4}
        selected={}
        for command in sorted(commands,key=lambda item:(item["cwd"],priority.get(item["name"],9),item["name"])):
            selected.setdefault(command["cwd"],command)
        mandatory=list(selected.values());recommended=[command for command in commands if command not in mandatory]
    elif level=="MEDIUM":
        for command in commands:(mandatory if command["name"] in {"lint","typecheck","test","test:unit","python-tests","dotnet-tests","unity-editmode"} else recommended).append(command)
    else:
        mandatory=list(commands)
    mandatory,reused=_reuse_minimum(mandatory,risk,impact_scope)
    if "database" in tags:manual.append("在可回滚副本上执行迁移、降级和数据一致性验证")
    if "security" in tags:manual.append("验证认证、授权、越权、会话失效和敏感信息路径")
    if "contracts" in tags:manual.append("验证 API/DTO 向后兼容和所有消费者")
    if "release" in tags:manual.append("在目标环境执行安装、升级、健康检查和回滚演练")
    if any(p.endswith((".prefab",".unity",".asset",".asmdef")) for p in changes):manual.append("使用 Unity Editor 检查 Missing Reference、序列化、Prefab和场景依赖")
    gaps=[]
    if not commands:gaps.append("没有从受影响子项目的真实配置发现测试或构建命令")
    if not (repo_ai(root)/"quality/test-map.json").exists():gaps.append("没有项目级需求/模块到测试用例映射")
    return {"schema_version":3,"generated_at":now(),"risk_level":level,"governance_activation":activation,"scope_mode":governance.get("scope_mode","AFFECTED_SCOPE" if changes else "PROJECT_CONFIG"),"verification_scope":impact_scope[:64],"mandatory":mandatory,"reused":reused,"recommended":recommended,"manual":manual,"gaps":gaps,"full_rerun":bool(not changes and level in {"HIGH","CRITICAL"}),"note":"只执行未被当前同指纹PASS覆盖的最低充分验证；复用证据不替代受影响范围的新验证。"}
def to_md(data:dict)->str:
    rows=lambda xs:markdown_table([[x.get("name"),x.get("cwd"),x.get("command"),x.get("status"),x.get("source")] for x in xs],["名称","目录","命令","状态","来源"]) if xs else "无。"
    return "\n".join(["# 回归测试范围规划","",f"风险等级：**{data.get('risk_level')}**","","## 必须执行",rows(data["mandatory"]),"","## 复用的当前证据",rows(data.get("reused",[])),"","## 建议执行",rows(data["recommended"]),"","## 人工验证",*(f"- {x}" for x in data["manual"]),"","## 未映射缺口",*(f"- {x}" for x in data["gaps"]),"",data["note"]])+"\n"
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--risk");a=ap.parse_args();root=git_root(Path(a.root));risk=load_json(Path(a.risk),{}) if a.risk else load_json(repo_ai(root)/"evidence/risk/latest.json",{})
    if not risk:raise SystemExit("缺少风险报告，请先运行 risk_review.py")
    data=plan(root,risk);out=repo_ai(root)/"evidence/test-plan";write_json(out/"latest.json",data);(out/"latest.md").write_text(to_md(data),encoding="utf-8");print(json.dumps(data,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
