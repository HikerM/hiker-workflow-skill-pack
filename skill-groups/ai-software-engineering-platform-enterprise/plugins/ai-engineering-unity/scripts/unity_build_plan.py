from __future__ import annotations
import argparse,json
from pathlib import Path
from unitylib import project_version,read_json

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--output",default=".ai/quality/unity-build-plan.json");a=ap.parse_args();root=Path(a.root).resolve();project=read_json(root/".ai/context/project.json",{}) or {};targets=project.get("target_platforms") or ["Windows","macOS","Linux"]
    items=[]
    for t in targets:items.append({"platform":t,"unity_version":project_version(root),"command":None,"status":"PLANNED_NOT_EXECUTED","required_evidence":["build log","launch smoke","UI resolution screenshots","resource load smoke"]})
    out=root/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({"schema_version":"1.0.0","plans":items,"note":"Configure a machine-local Unity executable; this template does not guess paths."},ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(out);return 0
if __name__=="__main__":raise SystemExit(main())
