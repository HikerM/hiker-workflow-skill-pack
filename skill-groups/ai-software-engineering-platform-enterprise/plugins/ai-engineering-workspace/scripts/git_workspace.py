from __future__ import annotations
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
from workspacelib import atomic_json,load_state,repo_root,run,safe_branch,safe_id,state_lock,state_path

def now():return datetime.now(timezone.utc).isoformat(timespec="seconds")
def worktree_list(root:Path)->list[dict]:
    out=run(["git","worktree","list","--porcelain"],root).stdout;items=[];cur={}
    for line in out.splitlines()+[""]:
        if not line:
            if cur:items.append(cur);cur={}
            continue
        key,*rest=line.split(" ",1);value=rest[0] if rest else True
        if key=="worktree":cur["path"]=value
        elif key=="HEAD":cur["head"]=value
        elif key=="branch":cur["branch"]=str(value).removeprefix("refs/heads/")
        elif key=="detached":cur["detached"]=True
        elif key=="locked":cur["locked"]=value
    return items
def branch_exists(root:Path,branch:str)->bool:return run(["git","show-ref","--verify","--quiet",f"refs/heads/{branch}"],root,check=False).returncode==0
def current_base(root:Path)->str:
    branch=run(["git","branch","--show-current"],root,check=False).stdout.strip();return branch or "HEAD"
def status_for(path:Path)->dict:
    dirty=run(["git","status","--porcelain"],path).stdout.splitlines();branch=run(["git","branch","--show-current"],path,check=False).stdout.strip() or "DETACHED";head=run(["git","rev-parse","HEAD"],path).stdout.strip();return {"path":str(path),"branch":branch,"head":head,"dirty":dirty}
def cmd_create(root:Path,a)->dict:
    task=safe_id(a.task_id);base=a.base or current_base(root);branch=safe_branch(a.branch or f"feature/{task}");default_parent=root.parent/f"{root.name}.ai-worktrees";path=Path(a.path).expanduser().resolve() if a.path else (default_parent/task).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    with state_lock(root):
        state=load_state(root)
        if task in state.get("worktrees",{}):raise RuntimeError(f"task already has worktree: {task}")
        if branch in state.get("leases",{}) and state["leases"][branch].get("status") in {"ACTIVE","PAUSED"}:raise RuntimeError(f"branch already leased: {branch}")
        if path.exists() and any(path.iterdir()):raise RuntimeError(f"worktree path is not empty: {path}")
        if path in {Path(x["path"]).resolve() for x in worktree_list(root)}:raise RuntimeError("worktree already registered")
        cmd=["git","worktree","add"]+([str(path),branch] if branch_exists(root,branch) else ["-b",branch,str(path),base]);result=run(cmd,root)
        state.setdefault("worktrees",{})[task]={"task_id":task,"path":str(path),"branch":branch,"base":base,"status":"ACTIVE","created_at":now()};state.setdefault("leases",{})[branch]={"task_id":task,"path":str(path),"status":"ACTIVE","updated_at":now()};atomic_json(state_path(root),state)
    return {"ok":True,"command":result.args,"task_id":task,"path":str(path),"branch":branch,"base":base}
def cmd_list(root:Path)->dict:
    items=[]
    for x in worktree_list(root):
        p=Path(x["path"]);item=dict(x)
        if p.exists():
            try:item.update(status_for(p))
            except Exception as e:item["status_error"]=str(e)
        items.append(item)
    return {"ok":True,"worktrees":items,"runtime":load_state(root)}
def is_merged(root:Path,branch:str,target:str)->bool:return run(["git","merge-base","--is-ancestor",branch,target],root,check=False).returncode==0
def cmd_remove(root:Path,a)->dict:
    task=safe_id(a.task_id)
    with state_lock(root):
        state=load_state(root);entry=state.get("worktrees",{}).get(task)
        if not entry:raise RuntimeError("unknown task id")
        path=Path(entry["path"]);branch=entry["branch"]
        if path.exists():
            st=status_for(path)
            if st["dirty"] and not a.force:raise RuntimeError("worktree has uncommitted changes; use --force only after explicit review")
        if not is_merged(root,branch,a.target) and not a.force:raise RuntimeError(f"branch {branch} is not merged into {a.target}")
        if path.exists():run(["git","worktree","remove"]+(["--force"] if a.force else [])+[str(path)],root)
        state.get("worktrees",{}).pop(task,None);state.get("leases",{}).pop(branch,None);atomic_json(state_path(root),state)
    return {"ok":True,"removed":str(path),"branch_preserved":branch,"note":"branch is not deleted automatically"}
def cmd_pause(root:Path,a,status:str)->dict:
    task=safe_id(a.task_id)
    with state_lock(root):
        state=load_state(root);entry=state.get("worktrees",{}).get(task)
        if not entry:raise RuntimeError("unknown task id")
        entry["status"]=status;entry["updated_at"]=now();lease=state.get("leases",{}).get(entry["branch"],{});lease["status"]=status;lease["updated_at"]=now();atomic_json(state_path(root),state)
    return {"ok":True,"task_id":task,"status":status}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("create");p.add_argument("--task-id",required=True);p.add_argument("--base");p.add_argument("--branch");p.add_argument("--path");sub.add_parser("list")
    p=sub.add_parser("remove");p.add_argument("--task-id",required=True);p.add_argument("--target",default="main");p.add_argument("--force",action="store_true")
    p=sub.add_parser("pause");p.add_argument("--task-id",required=True);p=sub.add_parser("resume");p.add_argument("--task-id",required=True);a=ap.parse_args();root=repo_root(Path(a.root).resolve())
    try:
        result=cmd_create(root,a) if a.cmd=="create" else cmd_list(root) if a.cmd=="list" else cmd_remove(root,a) if a.cmd=="remove" else cmd_pause(root,a,"PAUSED" if a.cmd=="pause" else "ACTIVE");print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (RuntimeError,subprocess.CalledProcessError,ValueError,TimeoutError) as e:
        err=e.stderr.strip() if isinstance(e,subprocess.CalledProcessError) and e.stderr else str(e);print(json.dumps({"ok":False,"error":err},ensure_ascii=False,indent=2));return 2
if __name__=="__main__":raise SystemExit(main())
