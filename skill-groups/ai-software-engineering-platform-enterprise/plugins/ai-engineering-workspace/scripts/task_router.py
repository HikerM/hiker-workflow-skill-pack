from __future__ import annotations
import argparse,json,re
from pathlib import Path
from workspacelib import atomic_json

LANES={
"architecture":(["架构","模块边界","技术选型","adr","architecture"],"read-heavy-subagent"),
"web":(["前端","web","vue","react","页面","组件","bs"],"worktree-if-writing"),
"unity":(["unity","ugui","prefab","renderer","模型","cs客户端"],"worktree-if-writing"),
"backend":(["后端","api","数据库","service","java","python","php","server"],"worktree-if-writing"),
"qa":(["测试","验收","回归","截图","性能","qa"],"read-heavy-subagent"),
"release":(["发布","部署","迁移","回滚","打包","release"],"serial-after-quality"),
}

def route(text:str)->dict:
    low=text.lower();lanes=[]
    for name,(tokens,mode) in LANES.items():
        hits=[t for t in tokens if t.lower() in low]
        if hits:lanes.append({"lane":name,"matched":hits,"mode":mode,"status":"PLANNED","depends_on":[]})
    if not lanes:lanes=[{"lane":"general-engineering","matched":[],"mode":"coordinator-first","status":"PLANNED","depends_on":[]}]
    names={x["lane"] for x in lanes}
    for lane in lanes:
        if lane["lane"] in {"web","unity","backend"} and "architecture" in names:lane["depends_on"].append("architecture")
        if lane["lane"]=="qa":lane["depends_on"] += [x for x in ("web","unity","backend") if x in names]
        if lane["lane"]=="release":lane["depends_on"] += [x for x in ("qa",) if x in names]
    return {"schema_version":"1.0.0","request":text,"lanes":lanes,"policy":{"read_heavy":"subagent","parallel_write":"separate_git_worktree","same_file_write":"serial","main_thread":"requirements_decisions_summary"}}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--request",required=True);ap.add_argument("--output",default=".ai/workspace/task-map.json");a=ap.parse_args();root=Path(a.root).resolve();data=route(a.request);atomic_json(root/a.output,data);print(json.dumps(data,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
