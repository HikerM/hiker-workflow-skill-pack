from __future__ import annotations
import argparse,json
from pathlib import Path
from change_set import collect
from graph_store import impact
from qualitylib import git_root,head,load_json,matches_any,markdown_table,now,posix,repo_ai,worktree_fingerprint,write_json

PLUGIN=Path(__file__).resolve().parents[1]
def policy(root:Path,explicit:str|None)->dict:
    base=load_json(PLUGIN/"references"/"default-risk-policy.json",{})
    custom=load_json(Path(explicit),{}) if explicit else load_json(repo_ai(root)/"quality"/"policy.json",{})
    if isinstance(custom,dict):
        for k,v in custom.items():
            if isinstance(v,dict) and isinstance(base.get(k),dict):base[k].update(v)
            elif v not in (None,[],{}):base[k]=v
    if isinstance(custom,dict):
        if custom.get("max_graph_depth") is not None:base.setdefault("graph",{})["max_depth"]=custom["max_graph_depth"]
        if custom.get("max_graph_nodes") is not None:base.setdefault("graph",{})["max_nodes"]=custom["max_graph_nodes"]
        if custom.get("auto_merge") is not None:base.setdefault("merge_gate",{})["enabled"]=bool(custom["auto_merge"])
    return base

def review(root:Path,mode:str="all-local",base:str|None=None,target:str|None=None,files:list[str]|None=None,policy_path:str|None=None)->dict:
    pol=policy(root,policy_path);changes=collect(root,mode,base,target,files);generated=pol.get("generated_patterns",[])
    kept=[];ignored=[]
    for f in changes["files"]:
        (ignored if matches_any(f["path"],generated) else kept).append(f)
    score=0;findings=[];tags=set();line_total=0;unknown_lines=0
    for f in kept:
        p=f["path"];status=f["status"];added=f.get("added");deleted=f.get("deleted")
        if added is None or deleted is None:unknown_lines+=1
        else:line_total+=added+deleted
        if status=="D":score+=8;findings.append({"severity":"HIGH","type":"deletion","path":p,"evidence":"文件删除"})
        if status=="R":score+=5;findings.append({"severity":"MEDIUM","type":"rename","path":p,"evidence":f"从 {f.get('old_path','?')} 重命名"})
        if f.get("binary") or Path(p).suffix.lower() in pol.get("binary_extensions",[]):score+=3;tags.add("binary")
        for tag,patterns in pol.get("critical_patterns",{}).items():
            if matches_any(p,patterns):
                weight={"database":20,"security":24,"release":16,"contracts":14,"unity-assets":8}.get(tag,10);severity="HIGH" if weight>=14 else "MEDIUM";score+=weight;tags.add(tag);findings.append({"severity":severity,"type":tag,"path":p,"evidence":"命中关键路径规则"})
    th=pol.get("thresholds",{})
    if len(kept)>=int(th.get("large_change_files",40)):score+=15;tags.add("large-change")
    if line_total>=int(th.get("large_change_lines",1500)):score+=15;tags.add("large-change")
    ownership=load_json(repo_ai(root)/"governance"/"ownership.json",{}) or {};rules=ownership.get("rules",[]) if isinstance(ownership,dict) else []
    uncovered=[]
    for f in kept:
        if rules and not any(matches_any(f["path"],r.get("patterns",[]) or ([r.get("glob")] if r.get("glob") else [])) for r in rules if isinstance(r,dict)):uncovered.append(f["path"])
    if uncovered:score+=min(12,len(uncovered));findings.append({"severity":"MEDIUM","type":"ownership-gap","paths":uncovered[:25],"evidence":"变更未匹配代码所有权"})
    graph_info=None;db=repo_ai(root)/"knowledge"/"engineering.db";gp=pol.get("graph",{})
    if db.exists() and kept:
        graph_info=impact(db,[f["path"] for f in kept],int(gp.get("max_depth",2)),int(gp.get("max_nodes",300)),str(gp.get("direction","both")),head(root),worktree_fingerprint(root))
        extra=max(0,len(graph_info["nodes"])-len(graph_info["seeds"]));score+=min(20,extra//5)
        if graph_info["truncated"]:findings.append({"severity":"MEDIUM","type":"graph-truncated","evidence":"图谱查询达到节点上限，结果不完整"})
        if graph_info["stale"]:findings.append({"severity":"HIGH","type":"graph-stale","evidence":"图谱索引与当前提交或工作区内容不一致"})
    thresholds=th;level="LOW"
    if score>=int(thresholds.get("critical",75)):level="CRITICAL"
    elif score>=int(thresholds.get("high",45)):level="HIGH"
    elif score>=int(thresholds.get("medium",20)):level="MEDIUM"
    evidence=0;possible=5
    if kept:evidence+=1
    if (repo_ai(root)/"context"/"project.json").exists():evidence+=1
    if rules and not uncovered:evidence+=1
    if graph_info and not graph_info.get("stale"):evidence+=1
    if unknown_lines==0:evidence+=1
    confidence=round(evidence/possible,2)
    gaps=[]
    if not kept:gaps.append("未发现有效变更，需确认输入模式是否正确")
    if not rules:gaps.append("没有有效代码所有权映射")
    if not graph_info:gaps.append("没有可用工程图谱，影响范围仅基于路径规则")
    elif graph_info.get("stale"):gaps.append("工程图谱已过期")
    if unknown_lines:gaps.append(f"{unknown_lines} 个二进制或未知行数文件")
    return {"schema_version":1,"generated_at":now(),"repository":str(root),"head":head(root),"change_mode":mode,"risk":{"score":score,"level":level,"confidence":confidence,"tags":sorted(tags)},"summary":{"files":len(kept),"ignored_generated":len(ignored),"changed_lines":line_total,"unknown_line_files":unknown_lines},"changes":kept,"ignored":ignored,"findings":findings,"ownership":{"uncovered":uncovered},"graph":graph_info,"evidence_gaps":gaps,"controls":{"auto_merge":False,"recommendation":"先执行回归计划并补齐关键证据" if level in {"HIGH","CRITICAL"} else "按风险范围执行验证"}}

def to_md(data:dict)->str:
    r=data["risk"];rows=[[f.get("severity"),f.get("type"),f.get("path") or ", ".join(f.get("paths",[])[:3]),f.get("evidence")] for f in data["findings"]]
    return "\n".join(["# 工程变更风险报告","",f"- 风险等级：**{r['level']}**",f"- 风险分数：{r['score']}",f"- 置信度：{r['confidence']}",f"- 有效文件：{data['summary']['files']}",f"- 忽略生成文件：{data['summary']['ignored_generated']}","","## 风险证据",markdown_table(rows,["等级","类型","位置","证据"]) if rows else "未发现规则型风险。","","## 证据缺口",*(f"- {x}" for x in data["evidence_gaps"]),"","## 控制建议",f"- {data['controls']['recommendation']}","- 本报告未执行测试，也不会自动合并代码。"])+"\n"
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--mode",choices=["all-local","staged","working-tree","range","files"],default="all-local");ap.add_argument("--base");ap.add_argument("--target");ap.add_argument("--file",action="append",default=[]);ap.add_argument("--policy")
    a=ap.parse_args();root=git_root(Path(a.root));data=review(root,a.mode,a.base,a.target,a.file,a.policy);out=repo_ai(root)/"evidence"/"risk";write_json(out/"latest.json",data);(out/"latest.md").write_text(to_md(data),encoding="utf-8");print(json.dumps(data,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
