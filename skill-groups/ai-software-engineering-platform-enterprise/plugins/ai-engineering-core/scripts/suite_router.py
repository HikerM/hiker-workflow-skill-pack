from __future__ import annotations

import argparse
import json
import os
import re
from collections import deque
from functools import lru_cache
from pathlib import Path

from source_identity import context_fresh, identify


PLUGIN_FOR = {
    "greenfield-project-planning": "ai-engineering-core",
    "architecture-decision-challenge": "ai-engineering-core",
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
    "interaction-conflict-governance": "ai-engineering-quality",
    "feature-acceptance-closure": "ai-engineering-workspace",
    "file-lock-manager": "ai-engineering-workspace",
    "multi-project-portfolio-manager": "ai-engineering-workspace",
    "plugin-application-receipt": "ai-engineering-workspace",
    "project-state-manager": "ai-engineering-workspace",
    "task-lifecycle-manager": "ai-engineering-workspace",
    "long-chain-change-convergence": "ai-engineering-workspace",
    "worktree-task-manager": "ai-engineering-workspace",
    "worktree-safe-convergence": "ai-engineering-workspace",
}

PROJECT_MARKERS = ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "Gemfile", "CMakeLists.txt", "Packages/manifest.json")
IGNORED_DIRS = {".git", ".ai", "node_modules", "Library", "Temp", "obj", "bin", "dist", "build", ".venv", "venv", "Pods", "DerivedData"}
FRONTEND_TOKENS = ("vue", "react", "next.js", "next", "nuxt", "angular", "svelte", "vite", "web-node")
BACKEND_TOKENS = ("nestjs", "express", "fastify", "koa", "@hapi/hapi", "fastapi", "django", "flask", "litestar", "sanic", "spring boot", "spring-boot", "quarkus", "micronaut", "asp.net", "microsoft.net.sdk.web", "laravel", "rails", "backend", "server")
CLIENT_TOKENS = ("unity", "wpf", "winui", "winforms", "avalonia", "maui", "qt", "qml", "electron", "tauri", "flutter", "android", "swiftui", "uikit", "appkit", "react native", "react-native", "javafx", "swing", "lvgl")
PLUGIN_DISPLAY = {
    "ai-engineering-core": "01 智能工程核心",
    "ai-engineering-web": "02 浏览器端与服务端工程",
    "ai-engineering-unity": "03 客户端工程",
    "ai-engineering-workspace": "04 工作区与多会话协作",
    "ai-engineering-quality": "05 质量、风险与发布",
}


def bounded_marker_paths(root: Path, max_depth: int = 3, max_dirs: int = 160) -> list[Path]:
    """Find only shallow project manifests; never turn routing into a repository scan."""
    identity = identify(root)
    if identity["is_git"]:
        return [Path(path) for path in identity["trusted_markers"]]
    root = root.resolve(); found: list[Path] = []; queue = deque([(root, 0)]); visited = 0
    while queue and visited < max_dirs:
        current, depth = queue.popleft(); visited += 1
        for marker in PROJECT_MARKERS:
            path = current / marker
            if path.is_file(): found.append(path)
        found.extend(sorted(current.glob("*.sln"))[:4]); found.extend(sorted(current.glob("*.csproj"))[:8])
        if depth >= max_depth: continue
        try: children = [p for p in current.iterdir() if p.is_dir() and p.name not in IGNORED_DIRS and not (p / ".git").exists()]
        except OSError: children = []
        queue.extend((child, depth + 1) for child in sorted(children)[:64])
    return list(dict.fromkeys(found))


def project_signals(root: Path) -> dict:
    identity = identify(root)
    context = root / ".ai" / "context" / "tech-stack.json"; sources: list[str] = []; evidence_parts: list[str] = []
    context_ready = context_fresh(context, identity.get("branch") or "", identity.get("head") or "") if identity["is_git"] else context.is_file()
    if context_ready:
        try: evidence_parts.append(json.dumps(json.loads(context.read_text(encoding="utf-8")), ensure_ascii=False).lower()); sources.append(str(context))
        except (OSError, json.JSONDecodeError): pass
    markers = bounded_marker_paths(root)
    package_dependencies: set[str] = set()
    backend = False; cs = False; unity = False
    for marker in markers:
        sources.append(str(marker))
        try: content = marker.read_text(encoding="utf-8", errors="ignore")[:120_000].lower()
        except OSError: content = ""
        evidence_parts.extend((marker.as_posix().lower(), content))
        if marker.name == "package.json":
            try:
                package = json.loads(content)
                package_dependencies.update(str(x).lower() for section in ("dependencies", "devDependencies", "peerDependencies") for x in (package.get(section) or {}))
            except (TypeError, json.JSONDecodeError): pass
        if marker.suffix.lower() == ".csproj":
            backend = backend or any(token in content for token in ("microsoft.net.sdk.web", "microsoft.aspnetcore", "include=\"aspnetcore\""))
            cs = cs or any(token in content for token in ("<usewpf>true", "<usewindowsforms>true", "microsoft.windowsappsdk", "avalonia", "maui", "xamarin"))
        if marker.name.lower() in {"pyproject.toml", "requirements.txt", "go.mod", "cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "gemfile"}:
            backend = backend or marker.name.lower() in {"go.mod", "cargo.toml", "composer.json", "gemfile"} or any(token in content for token in BACKEND_TOKENS)
        unity = unity or marker.as_posix().lower().endswith("packages/manifest.json") or "com.unity" in content
    evidence = " ".join(evidence_parts)
    react_native = "react-native" in package_dependencies or "react-native" in evidence or "react native" in evidence
    web_packages = {"vue", "next", "nuxt", "@angular/core", "svelte", "vite"}
    web_from_packages = bool(package_dependencies & web_packages) or ("react" in package_dependencies and not react_native)
    backend = backend or any(dep == token or dep.startswith(token) for dep in package_dependencies for token in ("@nestjs/", "express", "fastify", "koa", "@hapi/", "hapi", "fastapi", "django", "flask", "spring-boot", "laravel", "rails"))
    return {
        "existing": bool(markers or context_ready),
        "bs": web_from_packages or any(token in evidence for token in FRONTEND_TOKENS if token != "react") and not react_native,
        "backend": backend or any(token in evidence for token in BACKEND_TOKENS),
        "cs": cs or react_native or any(token in evidence for token in CLIENT_TOKENS),
        "unity": unity or "unity" in evidence,
        "context_ready": context_ready,
        "sources": sources[:12],
        "identity": identity,
        "source_conflicts": bool(identity.get("nested_worktrees")),
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
    plugin_engineering = any(x in text for x in ("插件", "skill", "marketplace", "codex扩展", "chatgpt桌面", "桌面端插件")) and any(
        x in text for x in ("增强", "升级", "更新", "开发", "修改", "修复", "审核", "验证", "安装", "重新安装", "推送", "发布", "检查", "诊断", "性能", "变慢", "慢", "走偏", "遗漏", "卡")
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
    explicit_cs = not plugin_engineering and (explicit_unity or any(x in text for x in ("c/s", "cs架构", "桌面", "客户端", "wpf", "winui", "winforms", "avalonia", "maui", "qt", "qml", "electron", "tauri", "flutter", "android", "ios", "macos", "swiftui", "react native", "react-native", "javafx", "swing", "lvgl", "嵌入式hmi")))
    explicit_backend = any(x in text for x in ("后端", "服务端", "服务器", "nodets", "node.ts", "nestjs", "express", "fastify", "koa", "hapi", "fastapi", "django", "flask", "spring", "asp.net", "laravel", "rails", "数据库", "migration", "service.ts", "api接口", "接口契约"))
    explicit_architecture = explicit_bs or explicit_cs or explicit_backend
    bs = explicit_bs or (not explicit_architecture and signals["bs"])
    cs = explicit_cs or (not explicit_architecture and signals["cs"])
    backend = explicit_backend or (not explicit_architecture and signals["backend"])
    unity = explicit_unity or (cs and signals["unity"])
    unsafe_shortcut = any(x in text for x in ("假装", "不看证据直接", "直接宣布", "强制合并并删除", "升级到最新大版本", "迁移成", "迁移到", "解释什么是", "解释一下", "架构概念"))
    implementation = any(x in text for x in ("实现", "增加", "新增", "修改", "复用已有", "按现有", "按已通过", "继续")) and not unsafe_shortcut
    design = any(x in text for x in ("设计", "ui", "视觉", "交互", "原型")) and not implementation
    architecture_decision = any(x in text for x in (
        "功能架构", "系统架构", "技术架构", "业务架构", "数据架构", "部署架构",
        "架构设计", "架构方案", "模块架构", "模块拆分", "服务拆分",
    )) or ("架构" in text and any(x in text for x in ("思路", "方案", "设计", "评估", "补全", "遗漏", "问题", "合理", "怎么拆")))
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
    worktree = any(x in text for x in ("worktree", "工作树", "多工作目录", "工作目录"))
    worktree_cleanup = worktree and any(x in text for x in ("堆积", "孤儿", "历史", "清理", "关闭", "收敛", "整理", "接管", "过期"))
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
    interaction_conflict = any(x in text for x in (
        "交互冲突", "状态冲突", "隐藏交互", "隐藏状态", "交互状态机", "浮层冲突",
        "下拉冲突", "下拉框冲突", "弹窗冲突", "抽屉冲突", "快捷键冲突",
        "请求乱序", "重复提交", "焦点冲突", "菜单冲突",
    ))
    long_chain = not unsafe_shortcut and (
        any(x in text for x in (
            "复杂链路", "长链路", "反复修复", "多次修改", "多轮修复", "多次失败",
            "越来越大", "越来越乱", "内部膨胀", "新旧代码", "多份实现", "旧口子",
            "真实执行", "付费执行", "计费执行", "真实计费", "生产回滚", "回滚后", "主线不一致",
            "部署版本不一致", "结论作废", "验收被推翻", "方向走偏", "一直不行",
        ))
        or (implementation and test and (release or merge))
        or (multi and implementation and test)
    )
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
        add("full-change-risk-review", "插件增强结束前需要审核完整变更，并核对五个插件全部Skill的一致性")
        if merge:
            add("change-ownership-merge", "推送前需要核对分支、提交范围与质量证据")
    elif greenfield:
        add("greenfield-project-planning", "空项目需要先融合自定义需求并锁定关键技术决策")
        if architecture_decision:
            add("architecture-decision-challenge", "用户架构思路需要独立反证、补全遗漏并比较真正不同的方案")
        mode, stage = "greenfield", "planning"
    elif brownfield_intent:
        mode, stage = "brownfield", "planning"
        add("project-bootstrap", "先从现有工程证据识别真实技术、版本和项目边界")
        add("brownfield-requirement-reconciliation", "建立现有能力基线，并把自定义需求对账为新增、修改、替换或移除")
    else:
        mode = "existing" if existing else "unknown"
        stage = "release" if release else "review" if review else "testing" if test else "design" if design else "development"
        if signals["source_conflicts"]:
            stage = "governance"
            add("worktree-task-manager", "检测到嵌套工作目录，必须先确认唯一源码身份")
        elif bootstrap:
            add("project-bootstrap", "需要从工程证据识别真实技术与版本")
        elif standards:
            add("official-standards-resolver", "需要按已识别的真实版本解析官方规范")
        elif recovery:
            add("context-recovery", "新会话或压缩后必须从正式状态恢复并核对锁定决定")
        elif long_context:
            add("bounded-context-memory", "长期多会话只注入有界工作集")
        elif pause and not worktree:
            add("interruptible-task-control", "控制指令必须先保存检查点")
        elif architecture_decision:
            if existing and not signals["context_ready"]:
                add("project-bootstrap", "先从当前仓库证据确认真实技术、版本和系统边界")
            add("architecture-decision-challenge", "把用户思路视为待验证假设，主动发现遗漏、反例和替代方案")
        elif portfolio:
            add("multi-project-portfolio-manager", "多个仓库必须保持项目身份与上下文隔离")
        elif worktree_cleanup:
            add("worktree-safe-convergence", "历史或堆积工作目录需要只读接管、证据分类和两阶段安全收敛")
        elif worktree:
            add("worktree-task-manager", "并行写任务需要受治理的独立工作目录")
        elif file_lock:
            add("file-lock-manager", "高冲突文件需要显式互斥和锁验证")
        elif long_chain:
            add("long-chain-change-convergence", "复杂任务需要压制范围膨胀、重复失败、实现路径分叉和旧结论沿用")
            if sum(bool(x) for x in (bs, cs, backend)) > 1 or multi:
                add("workspace-task-router", "跨模块或跨仓库链路需要先拆分所有权、依赖和串并行边界")
            elif release:
                add("release-readiness-review", "真实发布前需要核对当前证据、部署版本与回滚状态")
            elif test:
                add("regression-test-planner", "按当前策略和验收修订计算最小但充分的回归范围")
            elif backend:
                add("backend-component-implementation", "在真实服务端技术栈中执行当前最小改动")
            elif cs:
                add("cs-component-implementation", "在真实客户端技术栈中执行当前最小改动")
            elif bs:
                add("web-component-implementation", "在真实浏览器端技术栈中执行当前最小改动")
        elif task_state:
            add("project-state-manager", "需要维护有界项目状态与当前上下文")
        elif lifecycle:
            add("task-lifecycle-manager", "需要验证任务状态、角色和证据流转")
        elif closure:
            add("feature-acceptance-closure", "需要执行功能、测试、证据、文档和状态闭环")
        elif graph:
            add("knowledge-graph-maintenance", "大型工程需要增量关系图谱与影响查询")
        elif interaction_conflict:
            add("interaction-conflict-governance", "当前任务需要按模块检查隐藏状态、浮层、焦点、并发和交互冲突")
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
        elif review and sum(bool(x) for x in (bs, cs, backend)) > 1:
            add("workspace-task-router", "跨前后端审核必须先拆分边界、证据和独立质量通道")
        elif review:
            if unity_review or unity: add("unity-quality-review", "当前请求是游戏引擎专项只读质量审核")
            elif cs_review or cs: add("cs-quality-review", "当前请求是客户端专项只读质量审核")
            elif bs and not backend: add("web-quality-review", "当前请求是浏览器端只读质量审核")
            elif backend: add("backend-quality-review", "当前请求是服务端、契约与数据变更的独立审核")
            elif not unsafe_shortcut: add("full-change-risk-review", "当前请求是只读质量审核")
        elif sum(bool(x) for x in (bs, cs, backend)) > 1 and not unsafe_shortcut:
            add("workspace-task-router", "跨前后端变更必须先拆分所有权、依赖和可合并执行通道")
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
    if multi and not interaction_conflict and len(selected) < 2:
        add("multi-agent-project-governance", "大型工程需要任务、Git与Agent治理")
    if receipt and not selected:
        add("plugin-application-receipt", "用户只要求展示本轮实际应用能力")

    kinds = sum(bool(x) for x in (bs, cs, backend))
    architecture = "tooling" if plugin_engineering else "hybrid" if kinds > 1 else "cs" if cs else "bs" if bs else "backend" if backend else "unknown"
    ambiguous_hybrid = kinds > 1 and not explicit_architecture
    confidence = "low" if not selected else "medium" if ambiguous_hybrid or (kinds > 1 and not plugin_engineering) else "high"
    questions = []
    if not selected: questions.append("当前请求未命中软件工程执行阶段；不自动加载原子Skill")
    elif signals["source_conflicts"]: questions.append("当前仓库包含嵌套工作目录；清点并移出规范仓库后再执行源码修改")
    elif ambiguous_hybrid: questions.append("工程包含多个技术通道；执行前需在任务契约中确认本次前端、客户端和服务端范围")
    return {
        "schema_version": "1.0.0",
        "project_mode": mode,
        "architecture": architecture,
        "stage": stage,
        "selected": [{"skill": skill_display(s), "plugin": PLUGIN_DISPLAY[PLUGIN_FOR[s]], "reason": reason} for s, reason in selected],
        "load": [locate(s) for s, _ in selected],
        "max_loaded_skills": 2,
        "confidence": confidence,
        "project_evidence": signals["sources"],
        "source_identity": {
            "repo_root": signals["identity"].get("repo_root"),
            "worktree_root": signals["identity"].get("worktree_root"),
            "branch": signals["identity"].get("branch"),
            "head": signals["identity"].get("head"),
            "trusted_manifest_count": len(signals["identity"].get("trusted_markers", [])),
            "nested_worktree_count": len(signals["identity"].get("nested_worktrees", [])),
        },
        "receipt_required": bool(selected),
        "questions": questions,
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
