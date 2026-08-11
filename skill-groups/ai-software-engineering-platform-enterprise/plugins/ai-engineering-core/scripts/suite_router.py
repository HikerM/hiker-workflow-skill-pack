from __future__ import annotations

import argparse
import json
from pathlib import Path


PLUGIN_FOR = {
    "greenfield-project-planning": "ai-engineering-core",
    "brownfield-requirement-reconciliation": "ai-engineering-core",
    "project-bootstrap": "ai-engineering-core",
    "bounded-context-memory": "ai-engineering-core",
    "interruptible-task-control": "ai-engineering-core",
    "context-recovery": "ai-engineering-core",
    "web-ui-design": "ai-engineering-web",
    "web-component-implementation": "ai-engineering-web",
    "web-quality-review": "ai-engineering-web",
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
}

PROJECT_MARKERS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "CMakeLists.txt", "Packages/manifest.json")


def has_project_evidence(root: Path) -> bool:
    return any((root / marker).exists() for marker in PROJECT_MARKERS) or any(root.glob("*.sln")) or any(root.glob("*.csproj"))


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


def route(root: Path, request: str) -> dict:
    text = request.lower()
    existing = has_project_evidence(root)
    explicit_greenfield = any(x in text for x in ("从0", "从零", "空项目", "新项目", "greenfield", "从头开发", "初始化一个项目"))
    create_intent = any(x in text for x in ("开发一个", "创建一个", "新建一个", "搭建一个", "做一个系统", "做一套"))
    greenfield = (explicit_greenfield or create_intent) and not existing
    brownfield_intent = existing and any(x in text for x in (
        "已有一部分", "部分源码", "已有源码", "现有源码", "半成品", "遗留系统",
        "二次开发", "接着开发", "继续开发", "基于现有", "接手项目", "存量项目",
        "在现有工程", "增量需求",
    ))
    bs = any(x in text for x in ("b/s", "bs架构", "web", "网页", "前端", "浏览器", "后台", "saas", "网站"))
    unity = "unity" in text
    cs = unity or any(x in text for x in ("c/s", "cs架构", "桌面", "客户端", "wpf", "winui", "qt", "electron", "tauri", "flutter", "android", "ios", "react native", "嵌入式hmi"))
    design = any(x in text for x in ("设计", "ui", "视觉", "交互", "原型"))
    review = any(x in text for x in ("审核", "审查", "review", "风险"))
    test = any(x in text for x in ("测试", "回归", "验证"))
    release = any(x in text for x in ("发布", "上线", "release"))
    merge = any(x in text for x in ("合并", "merge", "冲突", "pull request", " pr"))
    long_context = any(x in text for x in ("多会话", "长会话", "上下文压缩", "不会丢", "越来越重", "恢复任务"))
    pause = any(x in text for x in ("暂停", "继续执行", "恢复执行", "调整方向", "插入需求"))
    multi = any(x in text for x in ("多agent", "多 agent", "worktree", "多仓库", "大型项目", "任务拆解"))
    selected: list[tuple[str, str]] = []

    def add(skill: str, reason: str) -> None:
        if len(selected) < 2 and skill not in {x[0] for x in selected}:
            selected.append((skill, reason))

    if greenfield:
        add("greenfield-project-planning", "空项目需要先融合自定义需求并锁定关键技术决策")
        mode, stage = "greenfield", "planning"
    elif brownfield_intent:
        mode, stage = "brownfield", "planning"
        add("project-bootstrap", "先从现有工程证据识别真实技术、版本和项目边界")
        add("brownfield-requirement-reconciliation", "建立现有能力基线，并把自定义需求对账为新增、修改、替换或移除")
    else:
        mode = "existing" if existing else "unknown"
        stage = "release" if release else "testing" if test else "review" if review else "design" if design else "development"
        if not existing and any(x in text for x in ("接管", "识别技术", "技术栈", "版本")):
            add("project-bootstrap", "需要从工程证据识别真实技术与版本")
        elif release:
            add("release-readiness-review", "发布前需要独立门禁证据")
        elif merge:
            add("change-ownership-merge", "合并前需要所有权、冲突与证据检查")
        elif test:
            add("regression-test-planner", "按变更风险生成最低必要回归范围")
        elif review:
            add("unity-quality-review" if unity else "cs-quality-review" if cs else "web-quality-review" if bs else "full-change-risk-review", "当前请求是只读质量审核")
        elif cs:
            add("cs-client-router", "先识别C/S客户端语言、框架、SDK和版本证据")
            add("unity-ui-design" if unity and design else "unity-component-implementation" if unity else "cs-ui-design" if design else "cs-component-implementation", "按已识别客户端技术处理当前阶段")
        elif bs:
            add("web-ui-design" if design else "web-component-implementation", "按现有Web技术和设计系统处理当前阶段")
        elif multi:
            add("workspace-task-router", "任务跨模块或需要工作区编排")
    if long_context:
        add("bounded-context-memory", "长期多会话只注入有界工作集")
    elif pause:
        add("interruptible-task-control", "控制指令必须先保存检查点")
    if multi and len(selected) < 2:
        add("multi-agent-project-governance", "大型工程需要任务、Git与Agent治理")

    architecture = "hybrid" if bs and cs else "cs" if cs else "bs" if bs else "unknown"
    return {
        "schema_version": "1.0.0",
        "project_mode": mode,
        "architecture": architecture,
        "stage": stage,
        "selected": [{"skill": s, "plugin": PLUGIN_FOR[s], "reason": reason} for s, reason in selected],
        "load": [locate(s) for s, _ in selected],
        "max_loaded_skills": 2,
        "confidence": "high" if selected else "low",
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
