from __future__ import annotations
import contextlib,fnmatch,json,os,re,subprocess,tempfile,time
from pathlib import Path
from typing import Any,Iterator

def run(cmd:list[str],cwd:Path,check:bool=True)->subprocess.CompletedProcess[str]:return subprocess.run(cmd,cwd=str(cwd),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)
def repo_root(path:Path)->Path:return Path(run(["git","rev-parse","--show-toplevel"],path).stdout.strip()).resolve()
def common_dir(path:Path)->Path:
    root=repo_root(path);raw=run(["git","rev-parse","--git-common-dir"],root).stdout.strip();p=Path(raw);return (root/p).resolve() if not p.is_absolute() else p.resolve()
def atomic_json(path:Path,data:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def read_json(path:Path,default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default
def glob_match(path:str,pattern:str)->bool:
    path=path.replace("\\","/");pattern=pattern.replace("\\","/")
    return fnmatch.fnmatchcase(path,pattern) or ("/**/" in pattern and fnmatch.fnmatchcase(path,pattern.replace("/**/","/"))) or (pattern.startswith("**/") and fnmatch.fnmatchcase(path,pattern[3:]))
def safe_id(value:str)->str:
    value=re.sub(r"[^A-Za-z0-9._-]+","-",value.strip()).strip("-.")
    if not value:raise ValueError("empty id")
    return value[:100]
def safe_branch(value:str)->str:return "/".join(safe_id(x) for x in value.split("/") if x.strip())
def pid_alive(pid:int)->bool:
    if pid<=0:return False
    try:os.kill(pid,0);return True
    except OSError:return False
@contextlib.contextmanager
def state_lock(root:Path,timeout:float=15.0,stale_after:float=120.0)->Iterator[None]:
    d=common_dir(root)/"ai-engineering";d.mkdir(parents=True,exist_ok=True);lock=d/"workspace.lock";start=time.time();fd=None
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps({"pid":os.getpid(),"created":time.time()}).encode());break
        except FileExistsError:
            info=read_json(lock,{}) or {};age=time.time()-float(info.get("created",lock.stat().st_mtime));pid=int(info.get("pid",0) or 0)
            if age>stale_after and not pid_alive(pid):
                try:lock.unlink();continue
                except FileNotFoundError:continue
            if time.time()-start>timeout:raise TimeoutError(f"workspace state lock timeout; owner pid={pid}, age={round(age,1)}s")
            time.sleep(0.1)
    try:yield
    finally:
        if fd is not None:os.close(fd)
        try:lock.unlink()
        except FileNotFoundError:pass
def state_path(root:Path)->Path:return common_dir(root)/"ai-engineering/workspace.json"
def load_state(root:Path)->dict:return read_json(state_path(root),{"schema_version":"1.0.0","worktrees":{},"leases":{}}) or {"schema_version":"1.0.0","worktrees":{},"leases":{}}
