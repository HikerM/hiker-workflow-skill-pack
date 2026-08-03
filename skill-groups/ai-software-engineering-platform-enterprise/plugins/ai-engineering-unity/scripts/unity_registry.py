from __future__ import annotations
import argparse,json,re
from pathlib import Path
from unitylib import files,project_version,read_json

def build(root:Path)->dict:
    prefabs=[];scripts=[];scenes=[]
    for p in files(root,{".prefab",".unity",".cs",".uxml",".uss"}):
        rel=p.relative_to(root).as_posix()
        if p.suffix==".prefab":prefabs.append({"name":p.stem,"path":rel,"bytes":p.stat().st_size})
        elif p.suffix==".unity":scenes.append({"name":p.stem,"path":rel,"bytes":p.stat().st_size})
        elif p.suffix==".cs":
            text=p.read_text(encoding="utf-8",errors="ignore")[:20000]
            classes=re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",text)
            role="page" if re.search(r"Page|Renderer|View",p.stem,re.I) else "component"
            scripts.append({"name":p.stem,"path":rel,"classes":classes[:20],"role":role,"lines":text.count("\n")+1})
    manifest=read_json(root/"Packages/manifest.json",{}) or {}
    return {"schema_version":"1.0.0","unity_version":project_version(root),"packages":manifest.get("dependencies",{}),"prefabs":prefabs,"scenes":scenes,"scripts":scripts}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--output",default=".ai/context/components-unity.json");a=ap.parse_args();root=Path(a.root).resolve();data=build(root);out=root/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps({"output":str(out),"prefabs":len(data["prefabs"]),"scenes":len(data["scenes"]),"scripts":len(data["scripts"])},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
