from __future__ import annotations

import argparse
import json
import os
import re
from collections import deque
from functools import lru_cache
from pathlib import Path


PLUGIN_FOR = {
    "greenfield-project-planning": "ai-engineering-core",
    "brownfield-requirement-reconciliation": "ai-engineering-core",
    "project-bootstrap": "ai-engineering-core",
    "bounded-context-memory": "ai-engineering-core",
    "interruptible-task-control": "ai-engineering-core",
    "context-recovery": "ai-engineering-core",
    "official-standards-resolver": "ai-engineering-core",
    "web-ui-design": "ai-engineering-web",
    "web-component-implementation": "ai-engineering-web",
    "web-quality-review": "ai-engineering-web",
    "backend-technology-router": "ai-engineering-web",
    "api-event-contract-design": "ai-engineering-web",
    "backend-component-implementation": "ai-engineering-web",
    "database-migration-governance": "ai-engineering-web",
    "backend-quality-review": "ai-engineering-web",
    "cs-client-router": "ai-engineering-unity",
    "cs-ui-design": "ai-engineering-unity",
    "cs-component-implementation": "ai-engineering-unity",
    "cs-quality-review": "ai-engineering-unity",
    "unity-ui-design": "ai-engineering-unity",
    "unity-component-implementation": "ai-engineering-unity",
    "unity-quality-review": "ai-engineering-unity",
    "workspace-task-router": "ai-engineering-workspace",
    "multi-agent-project-governance": "ai-engineering-workspace",
    "change-ownership-merge": "ai-engineering-workspace",
    "regression-test-planner": "ai-engineering-quality",
    "full-change-risk-review": "ai-engineering-quality",
    "release-readiness-review": "ai-engineering-quality",
    "design-readiness-review": "ai-engineering-quality",
    "knowledge-graph-maintenance": "ai-engineering-quality",
    "feature-acceptance-closure": "ai-engineering-workspace",
    "file-lock-manager": "ai-engineering-workspace",
    "multi-project-portfolio-manager": "ai-engineering-workspace",
    "plugin-application-receipt": "ai-engineering-workspace",
    "project-state-manager": "ai-engineering-workspace",
    "task-lifecycle-manager": "ai-engineering-workspace",
    "worktree-task-manager": "ai-engineering-workspace",
}

PROJECT_MARKERS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "CMakeLists.txt", "Packages/manifest.json")
IGNORED_DIRS = {".git", ".ai", "node_modules", "Library", "Temp", "obj", "bin", "dist", "build", ".venv", "venv", "Pods", "DerivedData"}
FRONTEND_TOKENS = ("vue", "react", "next.js", "next", "nuxt", "angular", "svelte", "vite", "web-node")
BACKEND_TOKENS = ("nestjs", "express", "fastapi", "django", "flask", "spring boot", "asp.net", "laravel", "rails", "backend", "server")
CLIENT_TOKENS = ("unity", "wpf", "winui", "winforms", "avalonia", "maui", "qt", "qml", "electron", "tauri", "flutter", "android", "swiftui", "uikit", "appkit", "react native", "javafx", "swing", "lvgl")
PLUGIN_DISPLAY = {
    "ai-engineering-core": "01 智能工程核心",
    "ai-engineering-web": "02 浏览器端与服务端工程",
    "ai-engineering-unity": "03 客户端工程",
    "ai-engineering-workspace": "04 工作区与多会话协作",
    "ai-engineering-quality": "05 质量、风险与发布",
}


def bounded_marker_paths(root: Path, max_depth: int = 3, max_dirs: int = 160) -> list[Path]:
    """Find only shallow project manifests; never turn routing into a repository scan."""
    root = root.resolve(); found: list[Path] = []; queue = deque([(root, 0)]); visited = 0
    while queue and visited < max_dirs:
        current, depth = queue.popleft(); visited += 1
        for marker in PROJECT_MARKERS:
            path = current / marker
            if path.is_file(): found.append(path)
        found.extend(sorted(current.glob("*.sln"))[:4]); found.extend(sorted(current.glob("*.csproj"))[:8])
        if depth >= max_depth: continue
        try: children = [p for p in current.iterdir() if p.is_dir() and p.name not in IGNORED_DIRS]
        except OSError: children = []
        queue.extend((child, depth + 1) for child in sorted(children)[:64])
    return list(dict.fromkeys(found))


def project_signals(root: Path) -> dict:
    context = root / ".ai" / "context" / "tech-stack.json"; sources: list[str] = []; evidence = ""
    if context.is_file():
        try: evidence = json.dumps(json.loads(context.read_text(encoding="utf-8")), ensure_ascii=False).lower(); sources.append(str(context))
        except (OSError, json.JSONDecodeError): pass
    markers = bounded_marker_paths(root)
    for marker in markers:
        sources.append(str(marker))
        if marker.name == "package.json":
            try: evidence += " " + marker.read_text(encoding="utf-8", errors="ignore")[:120_000].lower()
            except OSError: pass
        evidence += " " + marker.as_posix().lower()
    return {
        "existing": bool(markers or context.is_file()),
        "bs": any(token in evidence for token in FRONTEND_TOKENS),
        "backend": any(token in evidence for token in BACKEND_TOKENS),
        "cs": any(token in evidence for token in CLIENT_TOKENS) or any(path.lower().endswith((".sln", ".csproj")) for path in sources),
        "unity": "unity" in evidence or "packages/manifest.json" in evidence,
        "context_ready": context.is_file(),
        "sources": sources[:12],
    }


def has_project_evidence(root: Path) -> bool:
    return project_signals(root)["existing"]


@lru_cache(maxsize=64)
def locate(skill: str) -> str | None:
    plugin = PLUGIN_FOR[skill]
    here = Path(__file__).resolve().parents[1]
    candidates = [
        here.parent / plugin / "skills" / skill / "SKILL.md",
        Path.home() / ".codex" / "plugins" / plugin / "skills" / skill / "SKILL.md",
    ]
    cache = Path.home() / ".codex" / "plugins" / "cache"
    if cache.is_dir():
        candidates.extend(sorted(cache.glob(f"*/{plugin}/*/skills/{skill}/SKILL.md"), reverse=True))
    return str(next((p.resolve() for p in candidates if p.is_file()), candidates[0].resolve()))


@lru_cache(maxsize=64)
def skill_display(skill: str) -> str:
    skill_file = Path(locate(skill) or "")
    yaml_file = skill_file.parent / "agents" / "openai.yaml"
    if yaml_file.is_file():
        try:
            match = re.search(r'^\s*display_name:\s*["\']?([^"\'\r\n]+)', yaml_file.read_text(encoding="utf-8"), re.M)
            if match: return match.group(1).strip()
        except OSError: pass
    return "未命名工程能力"


def route(root: Path, request: str) -> dict:
    root = root.resolve(); text = request.lower(); signals = project_signals(root); existing = signals["existing"]
    plugin_engineering = any(x in text for x in ("插件", "skill", "marketplace", "codex扩展", "chatgpt桌面")) and any(
        x in text for x in ("增强", "升级", "更新", "开发", "修改", "修复", "审核", "验证", "安装", "重新安装", "推送", "发布")
    )
    explicit_greenfield = any(x in text for x in ("从0", "从零", "空项目", "空目录", "新项目", "greenfield", "从头开发", "初始化一个项目"))
    create_intent = any(x in text for x in ("开发一个", "创建一个", "新建一个", "搭建一个", "做一个系统", "做一套"))
    greenfield = (explicit_greenfield or create_intent) and not existing
    brownfield_words = any(x in text for x in (
        "已有一部分", "部分源码", "已有源码", "现有源码", "半成品", "遗留系统",
        "二次开发", "接着开发", "继续开发", "基于现有", "接手项目", "存量项目",
        "在现有工程", "增量需求",
    ))
    brownfield_intent = brownfield_words
    explicit_bs = any(x in text for x in ("b/s", "bs架构", "web", "网页", "前端", "浏览器", "后台页面", "saas", "网站", "官网", "响应式", "运营工作台", "vue", "react", "angular", "svelte"))
    explicit_unity = any(x in text for x in ("unity", "ugui", "prefab", "missing script", "guid"))
    explicit_cs = not plugin_engineering and (explicit_unity or any(x in text for x in ("c/s", "cs架构", "桌面", "客户端", "wpf", "winui", "winforms", "avalonia", "maui", "qt", "qml", "electron", "tauri", "flutter", "android", "ios", "macos", "swiftui", "react native", "javafx", "swing", "lvgl", "嵌入式hmi")))
    explicit_backend = any(x in text for x in ("后端", "服务端", "服务器", "nodets", "node.ts", "nestjs", "express", "fastapi", "django", "spring", "asp.net", "laravel", "数据库", "migration", "service.ts", "api接口", "接口契约"))
    explicit_architecture = explicit_bs or explicit_cs or explicit_backend
    bs = explicit_bs or (not explicit_architecture and signals["bs"])
    cs = explicit_cs or (not explicit_architecture and signals["cs"])
    backend = explicit_backend or (not explicit_architecture and signals["backend"])
    unity = explicit_unity or (cs and signals["unity"])
    unsafe_shortcut = any(x in text for x in ("假装", "不看证据直接", "直接宣布", "强制合并并删除", "升级到最新大版本", "迁移成", "迁移到", "解释什么是", "解释一下", "架构概念"))
    implementation = any(x in text for x in ("实现", "增加", "新增", "修改", "复用已有", "按现有", "按已通过", "继续")) and not unsafe_shortcut
    design = any(x in text for x in ("设计", "ui", "视觉", "交互", "原型")) and not implementation
    review = any(x in text for x in ("审核", "审查", "复审", "评估", "检查", "判断", "只读", "review", "风险"))
    if implementation and any(x in text for x in ("按已审核", "按已通过")): review = False
    test = any(x in text for x in ("测试", "回归", "验证"))
    release = any(x in text for x in ("发布前", "发布审核", "审核发布", "发布就绪", "准备发布", "能否发布", "上线", "release"))
    merge = any(x in text for x in ("合并", "merge", "冲突", "pull request", " pr", "推送", "push"))
    recovery = any(x in text for x in ("新会话恢复", "恢复上一个任务", "压缩后核对", "锁定决策和下一步"))
    long_context = any(x in text for x in ("多会话", "长会话", "上下文压缩", "不会丢", "越来越重", "压缩前", "checkpoint数量", "恢复回执"))
    pause = any(x in text for x in ("可中断", "暂停", "继续执行", "恢复执行", "调整方向", "插入需求"))
    multi = any(x in text for x in ("多agent", "多 agent", "worktree", "多仓库", "大型项目", "任务拆解", "分流", "subagent", "主线程只保留决策"))
    bootstrap = any(x in text for x in ("首次接管", "识别真实技术", "识别技术栈", "技术栈和版本", "初始化 .ai", "初始化.ai", "建立项目上下文"))
    standards = any(x in text for x in ("官方规范", "官方文档", "编码规范", "标准解析"))
    graph = any(x in text for x in ("知识图谱", "工程图谱", "依赖图", "影响图谱", "两跳", "节点分析影响"))
    worktree = any(x in text for x in ("worktree", "工作树", "多工作目录"))
    file_lock = any(x in text for x in ("文件锁", "锁定文件", "锁冲突", "prefab锁", "migration锁"))
    task_state = any(x in text for x in ("项目状态", "project_state", "current_context", "状态文档"))
    lifecycle = any(x in text for x in ("任务生命周期", "task id", "task状态", "任务状态流转")) or bool(re.search(r"创建\s*[A-Z]{1,8}-\d{3,}", request, re.I))
    closure = any(x in text for x in ("验收闭环", "feature closed loop", "功能闭环", "截图/日志证明")) or ("闭环" in text and all(x in text for x in ("测试", "日志", "文档", "状态")))
    portfolio = any(x in text for x in ("多项目", "多个仓库", "项目组合", "仓库隔离")) or bool(re.search(r"(?:两|三|四|五|六|七|八|九|十|\d+)个\s*(?:git)?仓库", text))
    receipt = any(x in text for x in ("插件应用回执", "用了什么插件", "用了哪些插件", "实际用了哪些插件", "应用了什么skill", "应用了什么 skill", "插件和skill"))
    workspace_route = any(x in text for x in ("分流", "subagent", "哪些任务适合", "哪些必须串行", "主线程只保留决策"))
    project_governance = multi and not (review or test or release or merge) and any(x in text for x in ("长期接管", "大型项目", "大型工程", "多agent", "多 agent"))
    design_review = review and ("设计" in text or "编码前" in text or any(x in text for x in ("p0", "p1", "p2", "bootstrap式", "可验收", "验收深度", "数据、命令、并发")))
    full_risk = review and any(x in text for x in ("暂存", "未跟踪", "feature分支", "相对main", "迁移和权限", "全部修改", "受影响设计层", "重跑设计复审", "prefab、scene", "packages变更"))
    regression = not unsafe_shortcut and any(x in text for x in ("最低回归范围", "风险报告生成", "真实scripts", "测试命令", "项目实际命令"))
    visual_review = review and "编码前" not in text and any(x in text for x in ("视觉回归", "硬编码样式", "bootstrap风格", "指标卡模板", "所有区域都做成卡片", "单调等权", "微交互"))
    unity_review = review and any(x in text for x in ("missing script", "guid", "arm64", "prefab", "scene", "packages"))
    cs_review = review and any(x in text for x in ("ipc", "生命周期", "api兼容", "打包证据", "swiftui客户端", "electron客户端"))
    backend_contract = backend and any(x in text for x in ("api契约", "接口契约", "事件契约", "openapi", "protobuf", "graphql", "错误模型", "幂等"))
    database_change = backend and any(x in text for x in ("数据库迁移", "migration", "schema变更", "表结构", "回滚脚本"))
    selected: list[tuple[str, str]] = []

    def add(skill: str, reason: str) -> None:
        if len(selected) < 2 and skill not in {x[0] for x in selected}:
            selected.append((skill, reason))

    if plugin_engineering:
        mode = "existing" if (root / ".git").exists() else "unknown"
        stage = "review" if review and not implementation else "development"
        add("full-change-risk-review", "插件增强需要核对完整源码、清单、测试与安装契约")
        if merge:
            add("change-ownership-merge", "推送前需要核对分支、提交范围与质量证据")
    elif greenfield:
        add("greenfield-project-planning", "空项目需要先融合自定义需求并锁定关键技术决策")
        mode, stage = "greenfield", "planning"
    elif brownfield_intent:
        mode, stage = "brownfield", "planning"
        add("project-bootstrap", "先从现有工程证据识别真实技术、版本和项目边界")
        add("brownfield-requirement-reconciliation", "建立现有能力基线，并把自定义需求对账为新增、修改、替换或移除")
    else:
        mode = "existing" if existing else "unknown"
        stage = "release" if release else "review" if review else "testing" if test else "design" if design else "development"
        if bootstrap:
            add("project-bootstrap", "需要从工程证据识别真实技术与版本")
        elif standards:
            add("official-standards-resolver", "需要按已识别的真实版本解析官方规范")
        elif recovery:
            add("context-recovery", "新会话或压缩后必须从正式状态恢复并核对锁定决定")
        elif long_context:
            add("bounded-context-memory", "长期多会话只注入有界工作集")
        elif pause and not worktree:
            add("interruptible-task-control", "控制指令必须先保存检查点")
        elif portfolio:
            add("multi-project-portfolio-manager", "多个仓库必须保持项目身份与上下文隔离")
        elif worktree:
            add("worktree-task-manager", "并行写任务需要受治理的独立工作目录")
        elif file_lock:
            add("file-lock-manager", "高冲突文件需要显式互斥和锁验证")
        elif task_state:
            add("project-state-manager", "需要维护有界项目状态与当前上下文")
        elif lifecycle:
            add("task-lifecycle-manager", "需要验证任务状态、角色和证据流转")
        elif closure:
            add("feature-acceptance-closure", "需要执行功能、测试、证据、文档和状态闭环")
        elif graph:
            add("knowledge-graph-maintenance", "大型工程需要增量关系图谱与影响查询")
        elif project_governance:
            add("multi-agent-project-governance", "长期大型工程需要项目状态、任务、角色、Git与验收治理")
            add("workspace-task-router", "跨技术栈工作需要拆成独立且可合并的执行通道")
        elif workspace_route:
            add("workspace-task-router", "需要在主会话、子智能体和工作区之间进行有边界的任务分流")
        elif full_risk:
            add("full-change-risk-review", "需要审核完整变更集及其设计和公共能力影响")
        elif visual_review:
            add("web-quality-review", "需要只读审核Web视觉、组件复用和反模板质量")
        elif design_review:
            add("design-readiness-review", "编码前设计、视觉与契约需要独立就绪复审")
        elif regression:
            add("regression-test-planner", "需要从真实变更风险与项目脚本计算最低回归范围")
        elif release and not unsafe_shortcut:
            add("release-readiness-review", "发布前需要独立门禁证据")
        elif merge and not unsafe_shortcut:
            add("change-ownership-merge", "合并前需要所有权、冲突与证据检查")
        elif test and not review and not unsafe_shortcut:
            add("regression-test-planner", "按变更风险生成最低必要回归范围")
        elif review:
            if unity_review or unity: add("unity-quality-review", "当前请求是游戏引擎专项只读质量审核")
            elif cs_review or cs: add("cs-quality-review", "当前请求是客户端专项只读质量审核")
            elif bs and not backend: add("web-quality-review", "当前请求是浏览器端只读质量审核")
            elif backend: add("backend-quality-review", "当前请求是服务端、契约与数据变更的独立审核")
            elif not unsafe_shortcut: add("full-change-risk-review", "当前请求是只读质量审核")
        elif cs and not unsafe_shortcut:
            add("cs-client-router", "先识别C/S客户端语言、框架、SDK和版本证据")
            add("unity-ui-design" if unity and design else "unity-component-implementation" if unity else "cs-ui-design" if design else "cs-component-implementation", "按已识别客户端技术处理当前阶段")
        elif bs and not unsafe_shortcut:
            add("web-ui-design" if design else "web-component-implementation", "按现有Web技术和设计系统处理当前阶段")
        elif backend:
            if not signals["context_ready"]: add("backend-technology-router", "后端任务先识别真实语言、框架、运行时和版本证据")
            if database_change: add("database-migration-governance", "数据库变化需要迁移、兼容和回滚治理")
            elif backend_contract: add("api-event-contract-design", "公共API或事件需要版本化契约和消费者兼容设计")
            else: add("backend-component-implementation", "在现有服务端技术栈内实现并验证当前功能")
        elif multi:
            add("workspace-task-router", "任务跨模块或需要工作区编排")
    if recovery:
        add("context-recovery", "新会话或压缩后必须从正式状态恢复并核对锁定决定")
    elif long_context:
        add("bounded-context-memory", "长期多会话只注入有界工作集")
    elif pause:
        add("interruptible-task-control", "控制指令必须先保存检查点")
    if multi and len(selected) < 2:
        add("multi-agent-project-governance", "大型工程需要任务、Git与Agent治理")
    if receipt and not selected:
        add("plugin-application-receipt", "用户只要求展示本轮实际应用能力")

    kinds = sum(bool(x) for x in (bs, cs, backend))
    architecture = "tooling" if plugin_engineering else "hybrid" if kinds > 1 else "cs" if cs else "bs" if bs else "backend" if backend else "unknown"
    return {
        "schema_version": "1.0.0",
        "project_mode": mode,
        "architecture": architecture,
        "stage": stage,
        "selected": [{"skill": skill_display(s), "plugin": PLUGIN_DISPLAY[PLUGIN_FOR[s]], "reason": reason} for s, reason in selected],
        "load": [locate(s) for s, _ in selected],
        "max_loaded_skills": 2,
        "confidence": "high" if selected else "low",
        "project_evidence": signals["sources"],
        "receipt_required": bool(selected),
        "questions": [] if selected else ["当前请求未命中软件工程执行阶段；不自动加载原子Skill"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    print(json.dumps(route(Path(args.root).resolve(), args.request), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
