from __future__ import annotations
import csv,json,py_compile,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NAME_RE=re.compile(r"^[a-z0-9][a-z0-9-]*$")
def frontmatter(path:Path)->dict:
    text=path.read_text(encoding="utf-8");m=re.match(r"^---\n(.*?)\n---\n",text,re.S)
    if not m:return {}
    out={}
    for line in m.group(1).splitlines():
        if ":" in line:
            k,v=line.split(":",1);out[k.strip()]=v.strip().strip('"').strip("'")
    return out
def main()->int:
    errors=[];warnings=[];skill_names={};plugins=sorted((ROOT/"plugins").iterdir())
    if len(plugins)!=5:errors.append(f"期望5个插件，实际{len(plugins)}")
    for p in plugins:
        manifest_path=p/".codex-plugin/plugin.json"
        try:m=json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:errors.append(f"{p.name}: manifest无效 {e}");continue
        if m.get("name")!=p.name:errors.append(f"{p.name}: manifest name不一致")
        if not NAME_RE.match(p.name):errors.append(f"{p.name}: 非法名称")
        for key in ["displayName","shortDescription","longDescription","composerIcon","logo"]:
            if not m.get("interface",{}).get(key):errors.append(f"{p.name}: 缺少 interface.{key}")
        for key in ["composerIcon","logo"]:
            rel=m.get("interface",{}).get(key);target=p/str(rel).removeprefix("./")
            if not target.is_file():errors.append(f"{p.name}: 缺少资源 {rel}")
        for field in ["skills"]:
            if m.get(field) and (not str(m[field]).startswith("./") or ".." in Path(str(m[field])).parts):errors.append(f"{p.name}: {field} 路径必须以 ./ 开头且位于插件内")
        if "hooks" in m:errors.append(f"{p.name}: plugin.json 不接受 hooks 字段；状态脚本必须由 Skill 或外部编排显式调用")
        skills=sorted((p/"skills").glob("*/SKILL.md"))
        if not skills:errors.append(f"{p.name}: 没有Skill")
        for s in skills:
            meta=frontmatter(s);dirname=s.parent.name
            if meta.get("name")!=dirname:errors.append(f"{p.name}/{dirname}: frontmatter name不一致")
            if not meta.get("description"):errors.append(f"{p.name}/{dirname}: 缺少description")
            if len(f"{p.name}:{dirname}")>64:errors.append(f"{p.name}/{dirname}: 插件与Skill组合标识超过64字符")
            if dirname in skill_names:errors.append(f"重复Skill名称 {dirname}: {skill_names[dirname]} / {p.name}")
            skill_names[dirname]=p.name
            if not (s.parent/"agents/openai.yaml").is_file():errors.append(f"{p.name}/{dirname}: 缺少agents/openai.yaml")
            else:
                agent_text=(s.parent/"agents/openai.yaml").read_text(encoding="utf-8")
                expected="true" if dirname=="ai-engineering-router" else "false"
                if f"allow_implicit_invocation: {expected}" not in agent_text:errors.append(f"{p.name}/{dirname}: 轻量路由策略要求allow_implicit_invocation: {expected}")
        ev=p/"evals/prompts.csv"
        if not ev.is_file():errors.append(f"{p.name}: 缺少evals/prompts.csv")
        else:
            rows=list(csv.DictReader(ev.open(encoding="utf-8")))
            if len(rows)<10:errors.append(f"{p.name}: Eval样例少于10条")
            if not any(str(r.get("should_trigger","")).lower()=="false" for r in rows):errors.append(f"{p.name}: 缺少负向Eval")
        for js in p.rglob("*.json"):
            try:json.loads(js.read_text(encoding="utf-8"))
            except Exception as e:errors.append(f"JSON无效 {js.relative_to(ROOT)}: {e}")
        for py in p.rglob("*.py"):
            try:py_compile.compile(str(py),doraise=True)
            except Exception as e:errors.append(f"Python编译失败 {py.relative_to(ROOT)}: {e}")
    market=json.loads((ROOT/".agents/plugins/marketplace.json").read_text(encoding="utf-8"));names={x.get("name") for x in market.get("plugins",[])}
    if names!={p.name for p in plugins}:errors.append("Marketplace插件清单与plugins目录不一致")
    report={"ok":not errors,"plugin_count":len(plugins),"skill_count":len(skill_names),"errors":errors,"warnings":warnings}
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if not errors else 2
if __name__=="__main__":raise SystemExit(main())
