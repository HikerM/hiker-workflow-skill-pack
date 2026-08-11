from __future__ import annotations
import argparse,hashlib,json,os,posixpath,re,sqlite3
from contextlib import contextmanager
from collections import deque
from pathlib import Path
from qualitylib import git_root,head,matches_any,now,posix,repo_ai,worktree_fingerprint,write_json
SCHEMA="""
PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS nodes(path TEXT PRIMARY KEY,kind TEXT,language TEXT,module TEXT,sha256 TEXT,mtime_ns INTEGER,size INTEGER,commit_sha TEXT,indexed_at TEXT);
CREATE TABLE IF NOT EXISTS edges(src TEXT,dst TEXT,relation TEXT,source TEXT,commit_sha TEXT,PRIMARY KEY(src,dst,relation));
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src); CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
"""
EXT={".ts":"typescript",".tsx":"typescript",".js":"javascript",".jsx":"javascript",".vue":"vue",".py":"python",".cs":"csharp",".java":"java",".kt":"kotlin",".go":"go",".rs":"rust",".php":"php",".cpp":"cpp",".cc":"cpp",".c":"c",".h":"header",".hpp":"header",".shader":"shader",".compute":"shader",".asmdef":"unity",".prefab":"unity",".unity":"unity",".asset":"unity",".mat":"unity",".controller":"unity",".anim":"unity",".meta":"unity-meta",".proto":"protobuf",".graphql":"graphql",".gql":"graphql",".sql":"sql"}
def connect(db:Path)->sqlite3.Connection:db.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(db);c.executescript(SCHEMA);return c
@contextmanager
def dbconn(db:Path):
    c=connect(db)
    try:yield c;c.commit()
    finally:c.close()
def module_of(path:str)->str:
    parts=posix(path).split("/");return "/".join(parts[:2]) if len(parts)>1 else parts[0]
def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
BASE_SKIP={".git",".ai","node_modules","Library","Temp","Logs","obj","bin","dist","build","Build","Builds",".venv","venv","__pycache__","coverage",".next",".nuxt"}
def candidates(root:Path,excluded:list[str])->list[Path]:
    out=[]
    for dirpath,dirnames,filenames in os.walk(root):
        current=Path(dirpath)
        rel_dir=posix(str(current.relative_to(root))) if current!=root else ""
        kept=[]
        for name in dirnames:
            child=posix(f"{rel_dir}/{name}" if rel_dir else name)
            if name in BASE_SKIP or matches_any(child,excluded) or matches_any(child+"/placeholder",excluded):continue
            kept.append(name)
        dirnames[:] = kept
        for filename in filenames:
            p=current/filename;rel=posix(str(p.relative_to(root)))
            if matches_any(rel,excluded):continue
            if p.suffix.lower() in EXT or p.name in {"package.json","pyproject.toml","pom.xml","build.gradle","build.gradle.kts","go.mod","Cargo.toml","composer.json","manifest.json","ProjectVersion.txt"} or p.suffix.lower()==".csproj":out.append(p)
    return out
def import_tokens(path:Path,language:str)->set[str]:
    if path.stat().st_size>1_500_000 or path.suffix.lower() in {".prefab",".unity",".asset",".mat",".controller",".anim",".meta"}:return set()
    try:text=path.read_text(encoding="utf-8",errors="ignore")
    except Exception:return set()
    pats=[]
    if language in {"typescript","javascript","vue"}:pats=[r"(?:from|import)\s*[\(]?['\"]([^'\"]+)['\"]",r"require\(['\"]([^'\"]+)['\"]\)"]
    elif language=="python":pats=[r"^\s*from\s+([\w\.]+)\s+import",r"^\s*import\s+([\w\.]+)"]
    elif language in {"csharp","java","kotlin"}:pats=[r"^\s*using\s+([\w\.]+)",r"^\s*import\s+([\w\.]+)"]
    elif language=="protobuf":pats=[r"^\s*import\s+(?:public\s+|weak\s+)?['\"]([^'\"]+)['\"]"]
    out=set()
    for pat in pats:out.update(m.group(1) for m in re.finditer(pat,text,re.MULTILINE))
    return out
def resolve_token(src:str,token:str,paths:set[str])->str|None:
    if token.startswith("."):
        raw=posixpath.normpath(posixpath.join(posixpath.dirname(src),token));probes=[raw,*(raw+x for x in [".ts",".tsx",".js",".jsx",".vue",".py"]),*(f"{raw}/index{x}" for x in [".ts",".tsx",".js",".jsx"])]
        return next((x for x in probes if x in paths),None)
    direct=posixpath.normpath(posixpath.join(posixpath.dirname(src),token))
    if direct in paths:return direct
    normalized=token.replace(".","/");matches=[p for p in paths if p.endswith("/"+normalized+Path(p).suffix) or p.endswith("/"+normalized+".py") or Path(p).stem==token.split(".")[-1]]
    return matches[0] if len(matches)==1 else None

def rebuild_semantic_edges(c:sqlite3.Connection,current:dict[str,Path],commit:str)->None:
    c.execute("DELETE FROM edges WHERE source IN ('unity-guid','project-reference')")
    guid_targets={}
    for rel,p in current.items():
        if p.suffix.lower()!=".meta" or p.stat().st_size>2_000_000:continue
        match=re.search(r"^guid:\s*([0-9a-fA-F]{32})\s*$",p.read_text(encoding="utf-8",errors="ignore"),re.MULTILINE)
        asset=rel[:-5]
        if match and asset in current:guid_targets[match.group(1).lower()]=asset
    unity_sources={".prefab",".unity",".asset",".mat",".controller",".anim"}
    for rel,p in current.items():
        suffix=p.suffix.lower()
        if suffix in unity_sources and p.stat().st_size<=8_000_000:
            text=p.read_text(encoding="utf-8",errors="ignore")
            for guid in set(re.findall(r"guid:\s*([0-9a-fA-F]{32})",text)):
                dst=guid_targets.get(guid.lower())
                if dst and dst!=rel:c.execute("INSERT OR REPLACE INTO edges(src,dst,relation,source,commit_sha) VALUES(?,?,?,?,?)",(rel,dst,"references_asset","unity-guid",commit))
        if suffix==".csproj" and p.stat().st_size<=2_000_000:
            text=p.read_text(encoding="utf-8",errors="ignore")
            for token in re.findall(r"<ProjectReference\s+[^>]*Include\s*=\s*['\"]([^'\"]+)['\"]",text,re.IGNORECASE):
                dst=posixpath.normpath(posixpath.join(posixpath.dirname(rel),posix(token)))
                if dst in current and dst!=rel:c.execute("INSERT OR REPLACE INTO edges(src,dst,relation,source,commit_sha) VALUES(?,?,?,?,?)",(rel,dst,"depends_on_project","project-reference",commit))
def index(root:Path,db:Path,excluded:list[str])->dict:
    commit=head(root);fingerprint=worktree_fingerprint(root);files=candidates(root,excluded);current={posix(str(p.relative_to(root))):p for p in files};changed=[];removed=[]
    with dbconn(db) as c:
        old={r[0]:(r[1],r[2],r[3]) for r in c.execute("SELECT path,mtime_ns,size,sha256 FROM nodes")}
        for rel,p in current.items():
            st=p.stat();oldrow=old.get(rel)
            if oldrow and oldrow[0]==st.st_mtime_ns and oldrow[1]==st.st_size:continue
            sha=digest(p);language=EXT.get(p.suffix.lower(),"config");c.execute("INSERT INTO nodes(path,kind,language,module,sha256,mtime_ns,size,commit_sha,indexed_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET kind=excluded.kind,language=excluded.language,module=excluded.module,sha256=excluded.sha256,mtime_ns=excluded.mtime_ns,size=excluded.size,commit_sha=excluded.commit_sha,indexed_at=excluded.indexed_at",(rel,"file",language,module_of(rel),sha,st.st_mtime_ns,st.st_size,commit,now()));changed.append(rel)
        for rel in set(old)-set(current):c.execute("DELETE FROM edges WHERE src=? OR dst=?",(rel,rel));c.execute("DELETE FROM nodes WHERE path=?",(rel,));removed.append(rel)
        paths=set(current)
        for rel in changed:
            c.execute("DELETE FROM edges WHERE src=? AND source='import'",(rel,));p=current[rel];lang=EXT.get(p.suffix.lower(),"config")
            for token in import_tokens(p,lang):
                dst=resolve_token(rel,token,paths)
                if dst and dst!=rel:c.execute("INSERT OR REPLACE INTO edges(src,dst,relation,source,commit_sha) VALUES(?,?,?,?,?)",(rel,dst,"depends_on","import",commit))
        rebuild_semantic_edges(c,current,commit)
        for k,v in {"commit_sha":commit,"worktree_fingerprint":fingerprint,"updated_at":now()}.items():c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",(k,v))
        node_count=c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0];edge_count=c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    meta={"schema_version":1,"last_indexed_commit":commit,"worktree_fingerprint":fingerprint,"updated_at":now(),"node_count":node_count,"edge_count":edge_count,"changed_count":len(changed),"removed_count":len(removed)};write_json(repo_ai(root)/"knowledge/metadata.json",meta);return meta
def impact(db:Path,seeds:list[str],depth:int,limit:int,direction:str,current_commit:str="",current_fingerprint:str="")->dict:
    limit=max(1,limit);depth=max(0,depth);seed_unique=list(dict.fromkeys(posix(s) for s in seeds));truncated=len(seed_unique)>limit;seed_unique=seed_unique[:limit];visited=set(seed_unique);q=deque((s,0) for s in seed_unique);edges=[];edge_limit=max(10,limit*6)
    with dbconn(db) as c:
        meta={k:v for k,v in c.execute("SELECT key,value FROM meta")}
        while q and len(visited)<limit:
            node,d=q.popleft()
            if d>=depth:continue
            rows=[]
            if direction in {"downstream","both"}:rows += list(c.execute("SELECT src,dst,relation FROM edges WHERE src=?",(node,)))
            if direction in {"upstream","both"}:rows += list(c.execute("SELECT src,dst,relation FROM edges WHERE dst=?",(node,)))
            for src,dst,rel in rows:
                if len(edges)>=edge_limit:truncated=True;break
                nxt=dst if src==node else src;edges.append({"src":src,"dst":dst,"relation":rel})
                if nxt not in visited:
                    if len(visited)>=limit:truncated=True;break
                    visited.add(nxt);q.append((nxt,d+1))
            if len(edges)>=edge_limit:break
        if q:truncated=True
    indexed=meta.get("commit_sha","");indexed_fp=meta.get("worktree_fingerprint","");stale_commit=bool(current_commit and indexed and current_commit!=indexed);stale_worktree=bool(current_fingerprint and indexed_fp and current_fingerprint!=indexed_fp)
    return {"seeds":seed_unique,"nodes":sorted(visited),"edges":edges,"depth":depth,"limit":limit,"direction":direction,"truncated":truncated,"indexed_commit":indexed,"current_commit":current_commit,"indexed_worktree_fingerprint":indexed_fp,"stale_commit":stale_commit,"stale_worktree":stale_worktree,"stale":stale_commit or stale_worktree}
def health(db:Path,current_commit:str="",current_fingerprint:str="")->dict:
    with dbconn(db) as c:
        nodes=c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0];edges=c.execute("SELECT COUNT(*) FROM edges").fetchone()[0];orphan=c.execute("SELECT COUNT(*) FROM edges e LEFT JOIN nodes a ON a.path=e.src LEFT JOIN nodes b ON b.path=e.dst WHERE a.path IS NULL OR b.path IS NULL").fetchone()[0];dup=c.execute("SELECT COUNT(*) FROM (SELECT src,dst,relation,COUNT(*) n FROM edges GROUP BY src,dst,relation HAVING n>1)").fetchone()[0];meta={k:v for k,v in c.execute("SELECT key,value FROM meta")}
    stale=bool(current_commit and meta.get("commit_sha") and current_commit!=meta.get("commit_sha")) or bool(current_fingerprint and meta.get("worktree_fingerprint") and current_fingerprint!=meta.get("worktree_fingerprint"));return {"node_count":nodes,"edge_count":edges,"orphan_edges":orphan,"duplicate_edges":dup,"indexed_commit":meta.get("commit_sha",""),"current_commit":current_commit,"stale":stale,"healthy":orphan==0 and dup==0 and not stale}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--db");sp=ap.add_subparsers(dest="cmd",required=True);ix=sp.add_parser("index");ix.add_argument("--exclude",action="append",default=[]);im=sp.add_parser("impact");im.add_argument("--seed",action="append",required=True);im.add_argument("--depth",type=int,default=2);im.add_argument("--limit",type=int,default=300);im.add_argument("--direction",choices=["both","upstream","downstream"],default="both");sp.add_parser("health");a=ap.parse_args();root=git_root(Path(a.root));db=Path(a.db) if a.db else repo_ai(root)/"knowledge/engineering.db";fp=worktree_fingerprint(root)
    data=index(root,db,a.exclude) if a.cmd=="index" else impact(db,a.seed,a.depth,a.limit,a.direction,head(root),fp) if a.cmd=="impact" else health(db,head(root),fp);print(json.dumps(data,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
