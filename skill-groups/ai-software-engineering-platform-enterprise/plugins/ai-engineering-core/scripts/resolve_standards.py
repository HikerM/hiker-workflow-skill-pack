from __future__ import annotations
import argparse,json
from pathlib import Path
from corelib import ai_root,atomic_write_json,atomic_write_text,read_json,utc_now

def flatten(stack:dict)->list[tuple[str,str|None,str]]:
    out=[]
    for project in stack.get("projects",[]):
        for group,kind in [("languages","language"),("runtimes","runtime"),("frameworks","framework")]:
            for item in project.get(group,[]):
                if isinstance(item,str):out.append((item,None,kind))
                elif isinstance(item,dict):out.append((str(item.get("name")),item.get("version"),kind))
        for ui in project.get("ui_systems",[]):out.append((str(ui),None,"ui"))
        pm=project.get("package_manager")
        if isinstance(pm,dict) and pm.get("name"):out.append((str(pm["name"]),pm.get("version"),"package-manager"))
        build=project.get("build_system")
        if isinstance(build,dict) and build.get("name"):out.append((str(build["name"]),build.get("version"),"build-system"))
    return out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--registry",required=True);a=ap.parse_args();root=Path(a.root).resolve();stack=read_json(ai_root(root)/"context/tech-stack.json",{});registry=read_json(Path(a.registry),{});targets=[]
    for name,version,kind in flatten(stack):
        low=name.lower()
        for entry in registry.get("entries",[]):
            if any(token.lower() in low or low in token.lower() for token in entry.get("match",[])):
                targets.append({"technology":name,"kind":kind,"detected_version":version,"official_domains":entry.get("domains",[]),"search_query":entry.get("query","").format(version=version or "detected version"),"verification_status":"PENDING_ONLINE_VERIFICATION"});break
    unique=[];seen=set()
    for item in targets:
        key=(item["technology"],item["detected_version"],item["kind"])
        if key not in seen:seen.add(key);unique.append(item)
    out={"schema_version":"1.0.0","status":"PENDING_ONLINE_VERIFICATION","generated_at":utc_now(),"targets":unique,"sources":[],"rules":[],"unresolved":[x for x in unique if not x.get("detected_version")]}
    atomic_write_json(ai_root(root)/"context/standards.json",out);lines=["# 项目编码规范（待官方文档核验）","","> 离线解析器只生成官方检索计划；尚未声称已经查阅在线手册。","","## 检测技术"]
    for item in unique:lines += [f"- {item['technology']} {item['detected_version'] or '版本待确认'}（{item['kind']}）",f"  - 官方域名：{', '.join(item['official_domains'])}",f"  - 建议检索：{item['search_query']}"]
    lines += ["","## 项目硬规则","","- 现有 ADR、锁定决策和实际构建配置优先。","- 不因通用最佳实践擅自替换语言、框架或组件库。","- 在线核验后记录文档版本、来源、访问日期和适用范围。"]
    atomic_write_text(root/"docs/engineering/PROJECT_CODING_STANDARD.md","\n".join(lines));print(json.dumps(out,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
