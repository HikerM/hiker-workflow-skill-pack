from __future__ import annotations
import contextlib,fnmatch,functools,hashlib,json,os,re,subprocess,sys,tempfile,threading,time
from pathlib import Path
from typing import Any,Iterator

CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from process_identity import owner_status,process_identity
from resource_budget import DEFAULT_BUDGETS as RESOURCE_DEFAULT_BUDGETS,HARD_MAX as RESOURCE_HARD_MAX,effective_budget,effective_value

def run(cmd:list[str],cwd:Path,check:bool=True)->subprocess.CompletedProcess[str]:
    safe=list(cmd)
    if len(safe)>1 and safe[0]=="git" and safe[1]=="status" and "--" not in safe:safe.extend(["--",".",":(exclude).ai/**"])
    return bounded_process_run(safe,cwd,check=check)
def _repository_marker(path:Path)->str:
    resolved=path.resolve()
    for candidate in (resolved,*resolved.parents):
        marker=candidate/".git"
        if marker.exists():return str(marker)
    return ""
@functools.lru_cache(maxsize=256)
def _repo_root_cached(path_text:str,repository_marker:str)->Path:return Path(run(["git","rev-parse","--show-toplevel"],Path(path_text)).stdout.strip()).resolve()
def repo_root(path:Path)->Path:
    resolved=path.resolve();return _repo_root_cached(str(resolved),_repository_marker(resolved))
@functools.lru_cache(maxsize=256)
def _common_dir_cached(root_text:str)->Path:
    root=Path(root_text);raw=run(["git","rev-parse","--git-common-dir"],root).stdout.strip();p=Path(raw);return (root/p).resolve() if not p.is_absolute() else p.resolve()
def common_dir(path:Path)->Path:
    root=repo_root(path);return _common_dir_cached(str(root))
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
def worktree_fingerprint(root:Path)->str:
    h=hashlib.sha256()
    try:
        for row in iter_git_nul_records(root,["status","--porcelain=v1","-z","--untracked-files=all","--",".",":(exclude).ai/**"]):
            if len(row)<4:continue
            raw=row[3:];path=raw.split(" -> ")[-1].replace("\\","/")
            if path in {"PROJECT_STATE.md","CURRENT_CONTEXT.md"} or path.startswith(("node_modules/","Library/","Temp/","dist/","build/","obj/","bin/",".venv/")):continue
            target=root/path;h.update(row[:3].encode("utf-8",errors="ignore"));h.update(path.encode("utf-8",errors="ignore"))
            try:
                stat=target.stat();h.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
                if target.is_file() and stat.st_size<=20_000_000 and not is_reserved_source_path(root,target):h.update(read_bounded_bytes(target,20_000_000)[0])
            except OSError:h.update(b"missing")
    except (RuntimeError,TraversalLimitReached):return hashlib.sha256(b"TRAVERSAL_LIMIT_REACHED").hexdigest()
    return h.hexdigest()
_LOCK_LOCAL=threading.local();_PROCESS_LOCKS_GUARD=threading.Lock();_PROCESS_LOCKS:dict[str,threading.RLock]={}
def _process_lock(key:str)->threading.RLock:
    with _PROCESS_LOCKS_GUARD:return _PROCESS_LOCKS.setdefault(key,threading.RLock())
@contextlib.contextmanager
def state_lock(root:Path,timeout:float=15.0,stale_after:float=120.0)->Iterator[None]:
    d=common_dir(root)/"ai-engineering";d.mkdir(parents=True,exist_ok=True);lock=d/"workspace.lock";key=str(lock.resolve()).casefold()
    process_lock=_process_lock(key);process_lock.acquire()
    try:
        held=getattr(_LOCK_LOCAL,"held",{})
        if held.get(key,0):
            held[key]+=1;_LOCK_LOCAL.held=held
            try:yield
            finally:held[key]-=1
            return
        start=time.time();fd=None
        while True:
            try:
                fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps({"pid":os.getpid(),"created":time.time(),"runtime_identity":process_identity(os.getpid())}).encode());break
            except FileExistsError:
                info=read_json(lock,{}) or {};age=time.time()-float(info.get("created",lock.stat().st_mtime));pid=int(info.get("pid",0) or 0)
                if age>stale_after and owner_status(info) in {"DEAD","IDENTITY_CHANGED"}:
                    try:lock.unlink();continue
                    except FileNotFoundError:continue
                if time.time()-start>timeout:raise TimeoutError(f"workspace state lock timeout; owner pid={pid}, age={round(age,1)}s")
                time.sleep(0.1)
        held[key]=1;_LOCK_LOCAL.held=held
        try:yield
        finally:
            held.pop(key,None)
            if fd is not None:os.close(fd)
            try:lock.unlink()
            except FileNotFoundError:pass
    finally:
        process_lock.release()
def locked_state(fn):
    @functools.wraps(fn)
    def wrapped(root:Path,*args,**kwargs):
        with state_lock(root):return fn(root,*args,**kwargs)
    return wrapped
def state_path(root:Path)->Path:return common_dir(root)/"ai-engineering/workspace.json"
def load_state(root:Path)->dict:return read_json(state_path(root),{"schema_version":"1.0.0","worktrees":{},"leases":{}}) or {"schema_version":"1.0.0","worktrees":{},"leases":{}}
