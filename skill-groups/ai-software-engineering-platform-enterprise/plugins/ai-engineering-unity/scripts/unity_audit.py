from __future__ import annotations
import argparse,json,re
from collections import Counter
from pathlib import Path
from unitylib import asset_files,files,project_version,read_json

PATTERNS=[
("gameobject-find","HIGH",re.compile(r"\bGameObject\.Find\s*\(")),
("find-object","MEDIUM",re.compile(r"\b(?:FindObjectOfType|FindFirstObjectByType|FindAnyObjectByType)\s*<")),
("async-void","MEDIUM",re.compile(r"\basync\s+void\s+(?!OnClick|OnSubmit|OnValueChanged)[A-Za-z_]")),
("direct-sql-in-ui","HIGH",re.compile(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\s+",re.I)),
]

def audit(root:Path)->dict:
    findings=[];counts=Counter();guid_map={}
    for p in files(root,{".cs"}):
        rel=p.relative_to(root).as_posix();text=p.read_text(encoding="utf-8",errors="ignore");lines=text.count("\n")+1
        ui_path=bool(re.search(r"/(?:UI|Pages?|Views?|Renderers?)/",f"/{rel}",re.I))
        if lines>500:findings.append({"severity":"HIGH","rule":"large-csharp-file","path":rel,"detail":f"{lines} lines"})
        elif lines>300:findings.append({"severity":"MEDIUM","rule":"large-csharp-file","path":rel,"detail":f"{lines} lines"})
        update_count=len(re.findall(r"\bvoid\s+Update\s*\(",text))
        if update_count and ui_path:findings.append({"severity":"MEDIUM","rule":"ui-update-loop","path":rel,"detail":f"Update methods: {update_count}"})
        for rule,severity,pat in PATTERNS:
            if rule=="direct-sql-in-ui" and not ui_path:continue
            n=len(pat.findall(text))
            if n:findings.append({"severity":severity,"rule":rule,"path":rel,"detail":f"occurrences: {n}"});counts[rule]+=n
        plus=len(re.findall(r"\+=",text));minus=len(re.findall(r"-=",text))
        if ui_path and plus>minus+1:findings.append({"severity":"MEDIUM","rule":"event-unsubscribe-heuristic","path":rel,"detail":f"subscriptions={plus}, unsubscriptions={minus}"})
    for p in files(root,{".prefab",".unity",".asset"}):
        rel=p.relative_to(root).as_posix();text=p.read_text(encoding="utf-8",errors="ignore")
        if "m_Script: {fileID: 0}" in text:findings.append({"severity":"HIGH","rule":"missing-script","path":rel,"detail":"m_Script fileID is 0"})
        if p.stat().st_size>20*1024*1024:findings.append({"severity":"MEDIUM","rule":"large-serialized-asset","path":rel,"detail":f"{p.stat().st_size} bytes"})
    assets=root/"Assets"
    if assets.exists():
        scanned=list(asset_files(root))
        for p in scanned:
            if p.suffix==".meta":continue
            if not Path(str(p)+".meta").exists():findings.append({"severity":"HIGH","rule":"missing-meta","path":p.relative_to(root).as_posix(),"detail":"asset has no .meta"})
        for meta in (p for p in scanned if p.suffix==".meta"):
            m=re.search(r"^guid:\s*([0-9a-fA-F]+)",meta.read_text(encoding="utf-8",errors="ignore"),re.M)
            if m:guid_map.setdefault(m.group(1),[]).append(meta.relative_to(root).as_posix())
        for guid,paths in guid_map.items():
            if len(paths)>1:findings.append({"severity":"HIGH","rule":"duplicate-guid","path":", ".join(paths),"detail":guid})
    manifest=read_json(root/"Packages/manifest.json",{}) or {}; packages=manifest.get("dependencies",{}) if isinstance(manifest,dict) else {}
    result="FAIL" if any(f["severity"]=="HIGH" for f in findings) else ("PASS_WITH_WARNINGS" if findings else "PASS")
    return {"schema_version":"1.0.0","result":result,"unity_version":project_version(root),"package_count":len(packages),"summary":dict(counts),"findings":findings}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--output",default=".ai/quality/unity-audit.json");a=ap.parse_args();root=Path(a.root).resolve();data=audit(root);out=root/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps(data,ensure_ascii=False,indent=2));return 1 if data["result"]=="FAIL" else 0
if __name__=="__main__":raise SystemExit(main())
