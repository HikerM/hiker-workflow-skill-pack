from __future__ import annotations
import argparse,json,re
from pathlib import Path
from workspacelib import glob_match,read_json,repo_root,run

def branch_ok(root:Path,name:str)->bool:return run(["git","rev-parse","--verify","--quiet",name],root,check=False).returncode==0

def changed(root:Path,target:str,source:str)->list[dict]:
    out=run(["git","diff","--name-status","-M",f"{target}...{source}"],root).stdout;items=[]
    for line in out.splitlines():
        parts=line.split("\t");status=parts[0]
        if status.startswith("R") and len(parts)>=3:items.append({"status":status,"old_path":parts[1],"path":parts[2]})
        elif len(parts)>=2:items.append({"status":status,"path":parts[1]})
    return items

def owners(root:Path,items:list[dict])->list[dict]:
    cfg=read_json(root/".ai/governance/ownership.json",{}) or {};rules=cfg.get("rules",[]);out=[]
    for item in items:
        path=item["path"];matched=[]
        for r in rules:
            if glob_match(path,str(r.get("glob",""))):matched.append({"owner":r.get("owner"),"allowed_roles":r.get("allowed_roles",[]),"glob":r.get("glob")})
        out.append({"path":path,"owners":matched,"status":"OWNED" if matched else "UNOWNED"})
    return out

def conflict_probe(root:Path,target:str,source:str)->dict:
    base=run(["git","merge-base",target,source],root).stdout.strip();res=run(["git","merge-tree",base,target,source],root,check=False);text=res.stdout+"\n"+res.stderr
    markers=[line for line in text.splitlines() if "<<<<<<<" in line or "changed in both" in line or "CONFLICT" in line]
    return {"merge_base":base,"potential_conflict":bool(markers),"markers":markers[:50],"command_returncode":res.returncode}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--source",required=True);ap.add_argument("--target",default="main");ap.add_argument("--output");a=ap.parse_args();root=repo_root(Path(a.root).resolve())
    missing=[x for x in (a.source,a.target) if not branch_ok(root,x)]
    if missing:data={"ok":False,"result":"BLOCKED","missing_branches":missing}
    else:
        items=changed(root,a.target,a.source);probe=conflict_probe(root,a.target,a.source);ownership=owners(root,items);critical=[x for x in items if re.search(r"(?:migration|schema|auth|permission|package-lock|pnpm-lock|ProjectSettings|Packages/manifest|\.asmdef$)",x["path"],re.I)];unowned=[x for x in ownership if x["status"]=="UNOWNED"]
        result="FAIL" if probe["potential_conflict"] else ("PASS_WITH_WARNINGS" if critical or unowned else "PASS")
        data={"ok":True,"result":result,"source":a.source,"target":a.target,"changes":items,"ownership":ownership,"critical_changes":critical,"conflict_probe":probe,"merge_executed":False,"requirements":["quality report","test evidence","review approval"]}
    text=json.dumps(data,ensure_ascii=False,indent=2);print(text)
    if a.output:Path(a.output).write_text(text+"\n",encoding="utf-8")
    return 1 if data.get("result")=="FAIL" else (2 if data.get("result")=="BLOCKED" else 0)
if __name__=="__main__":raise SystemExit(main())
