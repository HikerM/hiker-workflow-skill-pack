from __future__ import annotations
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main()->int:
    results=[];ok=True
    for plugin in sorted((ROOT/"plugins").iterdir()):
        start=time.time();p=subprocess.run([sys.executable,"-X","utf8","-m","unittest","discover","-s",str(plugin/"tests"),"-p","test*.py","-v"],text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        item={"plugin":plugin.name,"ok":p.returncode==0,"seconds":round(time.time()-start,3),"output":p.stdout};results.append(item);ok &= item["ok"]
        print(f"===== {plugin.name} =====\n{p.stdout}")
    (ROOT/"test-results.json").write_text(json.dumps({"ok":ok,"results":results},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
