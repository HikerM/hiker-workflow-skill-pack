from __future__ import annotations
import argparse, json
from pathlib import Path
from weblib import read_json
from web_audit import audit

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--output",default=".ai/quality/web-visual-plan.json"); ap.add_argument("--mode",choices=["review","release"],default="review"); args=ap.parse_args(); root=Path(args.root).resolve(); stack=read_json(root/".ai/context/tech-stack.json",{}) or {}; plans=[]
    viewports=[{"width":390,"height":844},{"width":1440,"height":900}]
    if args.mode=="release":viewports=[{"width":390,"height":844},{"width":768,"height":1024},{"width":1366,"height":768},{"width":1920,"height":1080},{"width":2560,"height":1440}]
    source_fingerprint=audit(root,"auto","quick")["source_fingerprint"]
    for p in stack.get("projects",[]):
        if p.get("kind")!="web-node": continue
        scripts=p.get("scripts",{}) if isinstance(p.get("scripts"),dict) else {}; test_script=next((k for k in ("test:e2e","e2e","playwright","test") if k in scripts),None)
        plans.append({"root":p.get("root"),"package_manager":p.get("package_manager"),"available_test_script":test_script,"viewports":viewports,"states":["default","changed-hidden-or-failure-state"],"environment":{"device_scale_factor":1,"browser_zoom":"100%","animations":"disabled","data":"fixed fixtures"},"status":"PLANNED_NOT_EXECUTED"})
    evidence_template={"source_fingerprint":source_fingerprint,"screenshots":[],"states":[],"reviewed_findings":[],"status":"NOT_EXECUTED"}
    out=root/args.output; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({"schema_version":"2.0.0","mode":args.mode,"plans":plans,"evidence_output":".ai/quality/web-visual-evidence.json","evidence_template":evidence_template},ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(out); return 0
if __name__=="__main__": raise SystemExit(main())
