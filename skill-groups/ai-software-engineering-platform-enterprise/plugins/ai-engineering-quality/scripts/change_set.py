from __future__ import annotations
import argparse,json
from pathlib import Path
from qualitylib import git,git_root,posix

def parse_name_status_z(raw:str,source:str)->list[dict]:
    parts=raw.split("\0");out=[];i=0
    while i<len(parts):
        status=parts[i];i+=1
        if not status:continue
        code=status[0]
        if code in {"R","C"}:
            if i+1>=len(parts):break
            old,new=posix(parts[i]),posix(parts[i+1]);i+=2;out.append({"path":new,"old_path":old,"status":code,"status_raw":status,"sources":[source]})
        else:
            if i>=len(parts):break
            path=posix(parts[i]);i+=1
            if path:out.append({"path":path,"status":code,"status_raw":status,"sources":[source]})
    return out
def diff_entries(root:Path,args:list[str],source:str)->list[dict]:
    p=git(root,*args,"--name-status","-z","--find-renames",check=False)
    if p.returncode!=0:raise RuntimeError(p.stderr.strip() or "git diff failed")
    return parse_name_status_z(p.stdout,source)
def numstat(root:Path,args:list[str])->dict[str,dict]:
    p=git(root,*args,"--numstat","-z","--find-renames",check=False);result={}
    if p.returncode!=0:return result
    parts=p.stdout.split("\0");i=0
    while i<len(parts):
        row=parts[i];i+=1
        if not row:continue
        cols=row.split("\t")
        if len(cols)<3:continue
        added,deleted,path=cols[0],cols[1],cols[2]
        if path=="" and i+1<len(parts):_old,new=parts[i],parts[i+1];i+=2;path=new
        result[posix(path)]={"added":None if added=="-" else int(added),"deleted":None if deleted=="-" else int(deleted),"binary":added=="-" or deleted=="-"}
    return result
def add_stats(target:dict[str,dict],incoming:dict[str,dict])->None:
    for path,stat in incoming.items():
        if path not in target:target[path]=dict(stat);continue
        cur=target[path];cur["binary"]=bool(cur.get("binary") or stat.get("binary"))
        for key in ("added","deleted"):
            a,b=cur.get(key),stat.get(key);cur[key]=None if a is None or b is None else int(a or 0)+int(b or 0)
def untracked_stat(path:Path)->dict:
    try:
        data=path.read_bytes()
        if b"\x00" in data[:8192]:return {"added":None,"deleted":None,"binary":True}
        return {"added":len(data.decode("utf-8",errors="ignore").splitlines()),"deleted":0,"binary":False}
    except OSError:return {"added":0,"deleted":0,"binary":False}
def merge(entries:list[dict],stats:dict[str,dict])->list[dict]:
    by={}
    for e in entries:
        p=e["path"]
        if p not in by:by[p]=dict(e)
        else:
            cur=by[p];cur["sources"]=sorted(set(cur.get("sources",[])+e.get("sources",[])));cur["status_raw"]="+".join(sorted(set(str(cur.get("status_raw","")).split("+")+[e.get("status_raw","")])))
            if e.get("old_path"):cur["old_path"]=e["old_path"]
            if e.get("status") in {"D","R"}:cur["status"]=e["status"]
    for p,e in by.items():e.update(stats.get(p,{"added":0,"deleted":0,"binary":False}))
    return sorted(by.values(),key=lambda x:x["path"])
def collect(root:Path,mode:str,base:str|None=None,target:str|None=None,files:list[str]|None=None)->dict:
    entries=[];stats={}
    if mode in {"all-local","staged"}:entries+=diff_entries(root,["diff","--cached"],"staged");add_stats(stats,numstat(root,["diff","--cached"]))
    if mode in {"all-local","working-tree"}:
        entries+=diff_entries(root,["diff"],"unstaged");add_stats(stats,numstat(root,["diff"]));p=git(root,"ls-files","--others","--exclude-standard","-z",check=False)
        for item in p.stdout.split("\0"):
            if item:
                rel=posix(item);entries.append({"path":rel,"status":"U","status_raw":"U","sources":["untracked"]});add_stats(stats,{rel:untracked_stat(root/rel)})
    if mode=="range":
        if not base:raise ValueError("range mode requires --base")
        spec=f"{base}...{target or 'HEAD'}";entries+=diff_entries(root,["diff",spec],"range");add_stats(stats,numstat(root,["diff",spec]))
    if mode=="files":
        for f in files or []:
            rel=posix(f);entries.append({"path":rel,"status":"M","status_raw":"M","sources":["files"]});add_stats(stats,{rel:untracked_stat(root/rel) if (root/rel).exists() else {"added":0,"deleted":0,"binary":False}})
    result=merge(entries,stats);return {"mode":mode,"base":base,"target":target,"files":result,"file_count":len(result)}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--mode",choices=["all-local","staged","working-tree","range","files"],default="all-local");ap.add_argument("--base");ap.add_argument("--target");ap.add_argument("--file",action="append",default=[]);ap.add_argument("--output");a=ap.parse_args();root=git_root(Path(a.root));data=collect(root,a.mode,a.base,a.target,a.file);text=json.dumps(data,ensure_ascii=False,indent=2)
    if a.output:Path(a.output).write_text(text+"\n",encoding="utf-8")
    print(text);return 0
if __name__=="__main__":raise SystemExit(main())
