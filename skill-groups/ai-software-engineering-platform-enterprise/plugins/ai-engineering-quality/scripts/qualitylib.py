from __future__ import annotations
import fnmatch,hashlib,json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from typing import Any

def now()->str:return datetime.now(timezone.utc).isoformat(timespec="seconds")
def run(root:Path,*args:str,check:bool=True)->subprocess.CompletedProcess[str]:return subprocess.run(list(args),cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)
def git(root:Path,*args:str,check:bool=True)->subprocess.CompletedProcess[str]:return run(root,"git",*args,check=check)
def git_root(path:Path)->Path:return Path(git(path,"rev-parse","--show-toplevel").stdout.strip()).resolve()
def head(root:Path)->str:
    p=git(root,"rev-parse","HEAD",check=False);return p.stdout.strip() if p.returncode==0 else ""
def load_json(path:Path,default:Any=None)->Any:
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default
def write_json(path:Path,data:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");os.replace(tmp,path)
def posix(path:str)->str:
    value=path.replace("\\","/")
    while value.startswith("./"):value=value[2:]
    return value
def glob_match(path:str,pattern:str)->bool:
    p=posix(path);pat=posix(pattern);candidates={pat}
    if pat.startswith("**/"):candidates.add(pat[3:])
    if "/**/" in pat:candidates.add(pat.replace("/**/","/"))
    pp=PurePosixPath(p);return any(fnmatch.fnmatchcase(p,x) or pp.match(x) for x in candidates)
def matches_any(path:str,patterns:list[str])->bool:return any(glob_match(path,p) for p in patterns)
def repo_ai(root:Path)->Path:return root/".ai"
def markdown_table(rows:list[list[Any]],headers:list[str])->str:
    out=["| "+" | ".join(headers)+" |","|"+"|".join(["---"]*len(headers))+"|"];out += ["| "+" | ".join(str(x).replace("|","\\|") for x in row)+" |" for row in rows];return "\n".join(out)
def worktree_fingerprint(root:Path)->str:
    status=git(root,"status","--porcelain=v1","-z","--untracked-files=all",check=False).stdout;h=hashlib.sha256();parts=status.split("\0")
    for row in parts:
        if len(row)<4:continue
        raw=row[3:];path=posix(raw.split(" -> ")[-1])
        if path.startswith((".ai/","node_modules/","Library/","Temp/","dist/","build/","obj/","bin/",".venv/")):continue
        p=root/path
        h.update(row[:3].encode("utf-8",errors="ignore"));h.update(path.encode())
        try:
            st=p.stat();h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
            if p.is_file() and st.st_size<=20_000_000:
                with p.open("rb") as f:
                    for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
        except OSError:h.update(b"missing")
    return h.hexdigest()
