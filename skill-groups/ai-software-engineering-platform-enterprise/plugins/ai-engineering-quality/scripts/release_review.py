from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from qualitylib import git_root,load_json,now,repo_ai,write_json
from delivery_hygiene import audit as delivery_hygiene_audit

def status_of(path:Path)->str:
    data=load_json(path,{}) or {};return str(data.get("status") or data.get("result") or "MISSING").upper()
def plan_fingerprint(plan:dict)->str:
    payload={key:value for key,value in plan.items() if key!="generated_at"}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
def full_test_blockers(plan:dict,tests_payload:dict,task:dict,safe_task:str)->list[str]:
    blockers=[];passing={"PASS","PASSED","SUCCESS"}
    if str(tests_payload.get("scope") or "").upper()!="FULL":blockers.append("测试证据不是 FULL 完整范围")
    expected_fingerprint=plan_fingerprint(plan) if plan else ""
    if not expected_fingerprint or tests_payload.get("plan_fingerprint")!=expected_fingerprint:blockers.append("测试证据未绑定当前回归计划")
    if tests_payload.get("task_id")!=safe_task:blockers.append("测试证据未绑定当前 Task ID")
    merge_commit=str(task.get("merge_commit") or "")
    if not merge_commit or tests_payload.get("source_commit")!=merge_commit:blockers.append("完整测试未在当前 merge commit 上执行")
    executed=tests_payload.get("commands") if isinstance(tests_payload.get("commands"),list) else []
    command_status={(str(item.get("cwd") or "."),str(item.get("command") or "")):str(item.get("status") or "").upper() for item in executed if isinstance(item,dict)}
    missing_commands=[]
    for item in plan.get("mandatory",[]) if isinstance(plan,dict) else []:
        key=(str(item.get("cwd") or "."),str(item.get("command") or ""))
        if command_status.get(key) not in passing:missing_commands.append(f"{key[0]}::{key[1]}")
    if missing_commands:blockers.append("当前计划的必须测试未全部通过: "+", ".join(missing_commands[:8]))
    requirements=tests_payload.get("requirements") if isinstance(tests_payload.get("requirements"),list) else []
    requirement_status={str(item.get("name")):str(item.get("status") or "").upper() for item in requirements if isinstance(item,dict)}
    missing_requirements=[name for name in (task.get("change_contract",{}).get("required_tests",[]) or []) if requirement_status.get(str(name)) not in passing]
    if missing_requirements:blockers.append("变更契约要求的测试未全部通过: "+", ".join(map(str,missing_requirements[:8])))
    manual=tests_payload.get("manual_checks") if isinstance(tests_payload.get("manual_checks"),list) else []
    manual_status={str(item.get("name")):str(item.get("status") or "").upper() for item in manual if isinstance(item,dict)}
    missing_manual=[name for name in plan.get("manual",[]) if manual_status.get(str(name)) not in passing]
    if missing_manual:blockers.append("发布计划中的人工/环境验证未全部通过: "+", ".join(map(str,missing_manual[:8])))
    if plan.get("gaps"):blockers.append("回归测试计划仍有未关闭映射缺口: "+", ".join(map(str,plan.get("gaps",[])[:8])))
    return blockers
def review(root:Path,task_id:str|None=None)->dict:
    ai=repo_ai(root);risk=load_json(ai/"evidence"/"risk"/"latest.json",{}) or {};plan=load_json(ai/"evidence"/"test-plan"/"latest.json",{}) or {}
    evidence_dir=ai/"evidence"/"results";tests_payload=load_json(evidence_dir/"tests.json",{}) or {};tests=status_of(evidence_dir/"tests.json");build=status_of(evidence_dir/"build.json");migration=status_of(evidence_dir/"migration.json");rollback=status_of(evidence_dir/"rollback.json")
    blockers=[];warnings=[];level=str(risk.get("risk",{}).get("level","UNKNOWN"));project=load_json(ai/"governance"/"project-state.json",{}) or {}
    safe_task="".join(ch for ch in str(task_id or "").upper() if ch.isalnum() or ch in "-._")
    task=load_json(ai/"tasks"/f"{safe_task}.json",{}) if safe_task else {}
    if not risk:blockers.append("缺少风险报告")
    if not plan:blockers.append("缺少回归测试计划")
    if tests not in {"PASS","PASSED","SUCCESS"}:blockers.append("没有通过的测试执行证据")
    if build not in {"PASS","PASSED","SUCCESS"}:blockers.append("没有通过的构建证据")
    tags=set(risk.get("risk",{}).get("tags",[]))
    if "database" in tags and migration not in {"PASS","PASSED","SUCCESS"}:blockers.append("数据库变更缺少迁移验证")
    if tags & {"database","release"} and rollback not in {"PASS","PASSED","SUCCESS"}:blockers.append("高影响变更缺少回滚验证")
    required_docs=["PROJECT_STATE.md","CHANGELOG.md","ARCHITECTURE.md"]
    missing_docs=[name for name in required_docs if not (root/name).is_file() or not (root/name).read_text(encoding="utf-8",errors="ignore").strip()]
    if missing_docs:blockers.append("发布状态文档缺失或为空: "+", ".join(missing_docs))
    if not project:blockers.append("缺少 .ai/governance/project-state.json")
    if not safe_task:blockers.append("发布审核必须指定 Task ID")
    elif not task:blockers.append(f"找不到任务状态: {safe_task}")
    else:
        if task.get("project_id")!=project.get("project_id"):blockers.append("任务与项目状态的 project_id 不一致")
        if task.get("state")!="Merged":blockers.append("Task 必须处于 Merged")
        if not task.get("merge_commit"):blockers.append("Task 缺少 merge commit")
        if task.get("closure",{}).get("merge")!="PASS":blockers.append("Feature Closed Loop 合并门禁未通过")
        blockers.extend(full_test_blockers(plan,tests_payload,task,safe_task))
    evidence_payloads=[load_json(evidence_dir/name,{}) or {} for name in ("tests.json","build.json","migration.json","rollback.json")]
    mismatched=[x.get("project_id") for x in [risk,plan,*evidence_payloads] if x.get("project_id") and x.get("project_id")!=project.get("project_id")]
    if mismatched:blockers.append("发布证据混入其他项目上下文")
    hygiene=delivery_hygiene_audit(root,"release")
    if not hygiene["ok"]:blockers.append("正式交付仍包含占位、演示、Mock或内部诊断残留")
    elif hygiene["status"]=="WARN":warnings.append("正式交付存在需要确认的界面文案或内部信息残留")
    if level in {"HIGH","CRITICAL"}:warnings.append(f"当前风险等级为 {level}")
    if risk.get("evidence_gaps"):warnings.extend(risk["evidence_gaps"])
    result="BLOCKED" if blockers else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {"schema_version":3,"generated_at":now(),"result":result,"task_id":safe_task or None,"project_id":project.get("project_id"),"source_commit":task.get("merge_commit") if isinstance(task,dict) else None,"risk_level":level,"evidence":{"tests":tests,"test_scope":tests_payload.get("scope"),"test_plan_fingerprint":tests_payload.get("plan_fingerprint"),"build":build,"migration":migration,"rollback":rollback},"delivery_hygiene":hygiene,"blockers":list(dict.fromkeys(blockers)),"warnings":warnings}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--task-id",required=True);a=ap.parse_args();root=git_root(Path(a.root));data=review(root,a.task_id);out=repo_ai(root)/"evidence"/"release";write_json(out/"latest.json",data);(out/"latest.md").write_text("# 发布就绪审核\n\n"+f"结果：**{data['result']}**\n\n## 阻断\n"+"\n".join(f"- {x}" for x in data["blockers"])+"\n\n## 警告\n"+"\n".join(f"- {x}" for x in data["warnings"])+"\n",encoding="utf-8");print(json.dumps(data,ensure_ascii=False,indent=2));return 1 if data["result"]=="BLOCKED" else 0
if __name__=="__main__":raise SystemExit(main())
