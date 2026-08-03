from __future__ import annotations
import argparse,json
from pathlib import Path
from qualitylib import git_root,load_json,now,repo_ai,write_json

def status_of(path:Path)->str:
    data=load_json(path,{}) or {};return str(data.get("status") or data.get("result") or "MISSING").upper()
def review(root:Path)->dict:
    ai=repo_ai(root);risk=load_json(ai/"evidence"/"risk"/"latest.json",{}) or {};plan=load_json(ai/"evidence"/"test-plan"/"latest.json",{}) or {}
    evidence_dir=ai/"evidence"/"results";tests=status_of(evidence_dir/"tests.json");build=status_of(evidence_dir/"build.json");migration=status_of(evidence_dir/"migration.json");rollback=status_of(evidence_dir/"rollback.json")
    blockers=[];warnings=[];level=str(risk.get("risk",{}).get("level","UNKNOWN"))
    if not risk:blockers.append("缺少风险报告")
    if not plan:blockers.append("缺少回归测试计划")
    if tests not in {"PASS","PASSED","SUCCESS"}:blockers.append("没有通过的测试执行证据")
    if build not in {"PASS","PASSED","SUCCESS"}:blockers.append("没有通过的构建证据")
    tags=set(risk.get("risk",{}).get("tags",[]))
    if "database" in tags and migration not in {"PASS","PASSED","SUCCESS"}:blockers.append("数据库变更缺少迁移验证")
    if tags & {"database","release"} and rollback not in {"PASS","PASSED","SUCCESS"}:blockers.append("高影响变更缺少回滚验证")
    if level in {"HIGH","CRITICAL"}:warnings.append(f"当前风险等级为 {level}")
    if risk.get("evidence_gaps"):warnings.extend(risk["evidence_gaps"])
    result="BLOCKED" if blockers else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {"schema_version":1,"generated_at":now(),"result":result,"risk_level":level,"evidence":{"tests":tests,"build":build,"migration":migration,"rollback":rollback},"blockers":blockers,"warnings":warnings}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");a=ap.parse_args();root=git_root(Path(a.root));data=review(root);out=repo_ai(root)/"evidence"/"release";write_json(out/"latest.json",data);(out/"latest.md").write_text("# 发布就绪审核\n\n"+f"结果：**{data['result']}**\n\n## 阻断\n"+"\n".join(f"- {x}" for x in data["blockers"])+"\n\n## 警告\n"+"\n".join(f"- {x}" for x in data["warnings"])+"\n",encoding="utf-8");print(json.dumps(data,ensure_ascii=False,indent=2));return 1 if data["result"]=="BLOCKED" else 0
if __name__=="__main__":raise SystemExit(main())
