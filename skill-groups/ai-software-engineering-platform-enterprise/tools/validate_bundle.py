from __future__ import annotations
import csv,json,py_compile,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from evaluate_router import evaluate as evaluate_router
from audit_skill_coherence import audit as audit_skill_coherence
from benchmark_router import benchmark as benchmark_router
from evaluate_master_progression import evaluate as evaluate_master_progression
from desktop_stability_gate import audit as audit_desktop_stability
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
    errors=[];warnings=[];skill_names={};display_names={};suite_versions=set();plugins=sorted((ROOT/"plugins").iterdir())
    unit_run=subprocess.run([sys.executable,"-X","utf8",str(ROOT/"tools/run_all_tests.py")],cwd=str(ROOT),text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    unit_report=json.loads((ROOT/"test-results.json").read_text(encoding="utf-8")) if (ROOT/"test-results.json").is_file() else {"ok":False,"results":[]}
    if unit_run.returncode!=0 or not unit_report.get("ok"):
        errors.append("完整单元测试失败；发布验证不得复用旧 test-results.json")
    if len(plugins)!=5:errors.append(f"期望5个插件，实际{len(plugins)}")
    for p in plugins:
        manifest_path=p/".codex-plugin/plugin.json"
        try:m=json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:errors.append(f"{p.name}: manifest无效 {e}");continue
        if m.get("name")!=p.name:errors.append(f"{p.name}: manifest name不一致")
        if m.get("version"):suite_versions.add(str(m["version"]))
        if not NAME_RE.match(p.name):errors.append(f"{p.name}: 非法名称")
        for key in ["displayName","shortDescription","longDescription","composerIcon","logo"]:
            if not m.get("interface",{}).get(key):errors.append(f"{p.name}: 缺少 interface.{key}")
        plugin_display=str(m.get("interface",{}).get("displayName") or "")
        if re.search(r"[A-Za-z]",plugin_display):errors.append(f"{p.name}: 用户可见插件名称必须使用中文: {plugin_display}")
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
                display_match=re.search(r'^\s*display_name:\s*["\']?([^"\'\r\n]+)',agent_text,re.M)
                display=display_match.group(1).strip() if display_match else ""
                if not display:errors.append(f"{p.name}/{dirname}: 缺少中文 display_name")
                elif re.search(r"[A-Za-z]",display):errors.append(f"{p.name}/{dirname}: 用户可见Skill名称必须使用中文: {display}")
                elif display in display_names:errors.append(f"重复用户可见Skill名称 {display}: {display_names[display]} / {p.name}/{dirname}")
                else:display_names[display]=f"{p.name}/{dirname}"
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
        for text_file in [x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in {".md",".py",".yaml",".yml",".json",".csv"}]:
            text=text_file.read_text(encoding="utf-8",errors="ignore")
            pollution_pattern="|".join(("学"+"员", "学"+"生", r"\bStu"+"dent\b"))
            if re.search(pollution_pattern,text,re.I):errors.append(f"业务域样例污染 {text_file.relative_to(ROOT)}")
    if len(suite_versions)!=1:errors.append(f"五个插件必须具有同一完整版本: {sorted(suite_versions)}")
    registry=json.loads((ROOT/"SKILL_REGISTRY.json").read_text(encoding="utf-8"));registry_names=set((registry.get("skills") or {}).keys())
    if registry_names!=set(skill_names):errors.append(f"Skill登记与目录不一致: 缺少{sorted(set(skill_names)-registry_names)} 多余{sorted(registry_names-set(skill_names))}")
    market=json.loads((ROOT/".agents/plugins/marketplace.json").read_text(encoding="utf-8"));names={x.get("name") for x in market.get("plugins",[])}
    if names!={p.name for p in plugins}:errors.append("Marketplace插件清单与plugins目录不一致")
    expected_archives={f"{p.name}-{str(json.loads((p/'.codex-plugin/plugin.json').read_text(encoding='utf-8'))['version']).split('+',1)[0]}.zip" for p in plugins}
    actual_archives={p.name for p in (ROOT/'dist').glob('*.zip')}
    if actual_archives!=expected_archives:errors.append(f"发布包目录必须只保留当前版本: 缺少{sorted(expected_archives-actual_archives)} 多余{sorted(actual_archives-expected_archives)}")
    governance_skill=(ROOT/"plugins/ai-engineering-workspace/skills/multi-agent-project-governance/SKILL.md").read_text(encoding="utf-8")
    for required in ["辅助 Skill 时，不加载", "单轮通常读取零到一份", "最多读取两份", "禁止预读全部五份"]:
        if required not in governance_skill:errors.append(f"多智能体总控缺少懒加载约束: {required}")
    if "先读取 [角色契约]" in governance_skill:errors.append("多智能体总控退化为启动时预读全部参考")
    router_eval=evaluate_router()
    if not router_eval["ok"]:errors.append(f"轻量路由行为Eval失败: {len(router_eval['failures'])} 条")
    master_progression=evaluate_master_progression()
    if not master_progression["ok"]:errors.append("总控多维推进评估失败: "+", ".join(item["scenario"] for item in master_progression["results"] if not item["ok"]))
    router_performance=benchmark_router(20,200.0)
    if not router_performance["ok"]:errors.append(f"轻量路由性能失败: P95 {router_performance['p95_ms']}ms > {router_performance['max_p95_ms']}ms")
    coherence=audit_skill_coherence(ROOT)
    if not coherence["ok"]:errors.extend(f"Skill一致性审核: {item['code']} {item['skill']} {item['message']}" for item in coherence["errors"])
    warnings.extend(f"Skill一致性审核: {item['code']} {item['skill']} {item['message']}" for item in coherence["warnings"])
    desktop_stability=audit_desktop_stability(ROOT)
    if not desktop_stability["ok"]:errors.extend(f"桌面稳定性: {item}" for item in desktop_stability["errors"])
    warnings.extend(f"桌面稳定性: {item}" for item in desktop_stability["warnings"])
    report={"ok":not errors,"plugin_count":len(plugins),"skill_count":len(skill_names),"unit_tests":{"ok":bool(unit_report.get("ok")),"plugin_results":[{"plugin":item.get("plugin"),"ok":item.get("ok"),"seconds":item.get("seconds")} for item in unit_report.get("results",[])]},"router_eval":router_eval,"master_progression":master_progression,"router_performance":router_performance,"skill_coherence":coherence,"desktop_stability":desktop_stability,"errors":errors,"warnings":warnings}
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if not errors else 2
if __name__=="__main__":raise SystemExit(main())
