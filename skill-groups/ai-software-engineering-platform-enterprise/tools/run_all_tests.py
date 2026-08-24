from __future__ import annotations
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/".codex-output"/"test-logs"
EXCERPT_CHARS=3000


def excerpt(value:str,limit:int=EXCERPT_CHARS)->str:
    if len(value)<=limit:return value
    half=max(1,(limit-80)//2)
    return value[:half]+"\n... 中间输出已写入证据日志 ...\n"+value[-half:]


def main()->int:
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    results=[];ok=True
    for plugin in sorted((ROOT/"plugins").iterdir()):
        start=time.time();p=subprocess.run([sys.executable,"-X","utf8","-m","unittest","discover","-s",str(plugin/"tests"),"-p","test*.py","-v"],text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log=ARTIFACTS/f"{plugin.name}.log";log.write_text(p.stdout,encoding="utf-8")
        item={
            "plugin":plugin.name,"ok":p.returncode==0,"seconds":round(time.time()-start,3),
            "output_excerpt":excerpt(p.stdout),"output_chars":len(p.stdout),
            "log_path":log.relative_to(ROOT).as_posix(),
            "log_sha256":hashlib.sha256(p.stdout.encode("utf-8")).hexdigest(),
        };results.append(item);ok &= item["ok"]
        print(f"{plugin.name}: {'PASS' if item['ok'] else 'FAIL'} | {item['seconds']}s | {item['output_chars']} chars | {item['log_path']}")
        if not item["ok"]:print(item["output_excerpt"])
    (ROOT/"test-results.json").write_text(json.dumps({"ok":ok,"results":results},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
