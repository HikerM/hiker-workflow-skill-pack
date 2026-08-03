from __future__ import annotations
import argparse,json,os,shutil,tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PLUGIN_NAMES=[p.name for p in (ROOT/"plugins").iterdir() if p.is_dir()]
def atomic(path:Path,data:dict):
    path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def load(path:Path)->dict:
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("repository");a=ap.parse_args();repo=Path(a.repository).expanduser().resolve()
    if not repo.is_dir():raise SystemExit(f"仓库目录不存在：{repo}")
    dest=repo/"plugins";market=repo/".agents"/"plugins"/"marketplace.json";stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");backup=repo/".ai-install-backup"/stamp;dest.mkdir(parents=True,exist_ok=True)
    for name in PLUGIN_NAMES:
        target=dest/name
        if target.exists():backup.mkdir(parents=True,exist_ok=True);shutil.copytree(target,backup/name,dirs_exist_ok=True);shutil.rmtree(target)
        shutil.copytree(ROOT/"plugins"/name,target)
    current=load(market);entries=[x for x in current.get("plugins",[]) if x.get("name") not in PLUGIN_NAMES]
    entries += [{"name":name,"source":{"source":"local","path":f"./plugins/{name}"},"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},"category":"Productivity"} for name in PLUGIN_NAMES]
    merged={"name":current.get("name",f"{repo.name}-ai-engineering"),"interface":current.get("interface",{"displayName":f"{repo.name} AI工程插件"}),"plugins":entries}
    if market.exists():market.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(market,market.with_suffix(f".json.{stamp}.bak"))
    atomic(market,merged);print(json.dumps({"ok":True,"repository":str(repo),"plugins":PLUGIN_NAMES,"marketplace":str(market),"backup":str(backup) if backup.exists() else None},ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
