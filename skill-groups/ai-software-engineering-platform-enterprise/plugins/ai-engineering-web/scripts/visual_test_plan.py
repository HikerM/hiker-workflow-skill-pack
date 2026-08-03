from __future__ import annotations
import argparse, json
from pathlib import Path
from weblib import read_json

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--output",default=".ai/quality/web-visual-plan.json"); args=ap.parse_args(); root=Path(args.root).resolve(); stack=read_json(root/".ai/context/tech-stack.json",{}) or {}; plans=[]
    for p in stack.get("projects",[]):
        if p.get("kind")!="web-node": continue
        scripts=p.get("scripts",{}) if isinstance(p.get("scripts"),dict) else {}; test_script=next((k for k in ("test:e2e","e2e","playwright","test") if k in scripts),None)
        plans.append({"root":p.get("root"),"package_manager":p.get("package_manager"),"available_test_script":test_script,"viewports":[{"width":1366,"height":768},{"width":1440,"height":900},{"width":1920,"height":1080},{"width":2560,"height":1440}],"environment":{"device_scale_factor":1,"browser_zoom":"100%","animations":"disabled","data":"fixed fixtures"},"status":"PLANNED_NOT_EXECUTED"})
    out=root/args.output; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({"schema_version":"1.0.0","plans":plans},ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(out); return 0
if __name__=="__main__": raise SystemExit(main())
