from __future__ import annotations
import json,os,shutil,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PLUGIN_NAMES=[p.name for p in (ROOT/"plugins").iterdir() if p.is_dir()]
def atomic(path:Path,data:dict)->None:
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
    home=Path.home();dest=home/".codex"/"plugins";market=home/".agents"/"plugins"/"marketplace.json";stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");backup=home/".codex"/"plugins-backup"/stamp
    dest.mkdir(parents=True,exist_ok=True)
    installed=[]
    for name in PLUGIN_NAMES:
        src=ROOT/"plugins"/name;target=dest/name
        if target.exists():backup.mkdir(parents=True,exist_ok=True);shutil.copytree(target,backup/name,dirs_exist_ok=True);shutil.rmtree(target)
        tmp=dest/(name+".installing");shutil.rmtree(tmp,ignore_errors=True);shutil.copytree(src,tmp);os.replace(tmp,target);installed.append({"name":name,"path":str(target)})
    current=load(market);plugins=[x for x in current.get("plugins",[]) if x.get("name") not in PLUGIN_NAMES]
    plugins += [{"name":x["name"],"source":{"source":"local","path":f"./.codex/plugins/{x['name']}"},"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},"category":"Productivity"} for x in installed]
    merged={"name":current.get("name","personal-ai-engineering-marketplace"),"interface":current.get("interface",{"displayName":"个人插件"}),"plugins":plugins}
    if market.exists():market.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(market,market.with_suffix(f".json.{stamp}.bak"))
    atomic(market,merged);print(json.dumps({"ok":True,"installed":installed,"marketplace":str(market),"backup":str(backup) if backup.exists() else None},ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
