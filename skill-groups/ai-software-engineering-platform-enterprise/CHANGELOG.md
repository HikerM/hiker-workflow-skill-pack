# CHANGELOG

## 4.2.0

- 为 `web-ui-design` 增加项目专属设计系统、语义色彩、间距尺度、组件复用、视觉焦点、疏密节奏、签名元素和适度微交互契约。
- 明确阻断普通后台模板、Bootstrap 式默认视觉、重复卡片汤和无焦点的单调等权布局；同时防止用无语义渐变、阴影、发光或动效替代设计。
- 强化 `web-component-implementation`、`web-quality-review` 和 `design-readiness-review`，使缺少视觉系统或视觉丰富度证据的新增/重做 UI 不能进入编码或通过审核。
- `web_audit.py` 新增 Bootstrap、重复卡片、硬编码间距、装饰效果和 Token 证据信号，并补充自动化测试与 Eval 场景。
- 修复核心项目探测器在 Python 3.10 缺少标准库 `tomllib` 时无法导入的问题；优先回退到 `tomli`，依赖不存在时安全降级。

## 4.1.0

- 增强 `web-ui-design`：从项目事实动态识别页面，按编辑器、画布、实时、自动保存、并发、发布等特征评估复杂度，并对复杂页面要求深层数据、API/事件、状态、失败、降级、并发、发布和验收设计。
- 新增 `design-readiness-review`：独立只读检查需求到证据的追踪链和语义深度，输出 P0/P1/P2、置信度、未知项和允许进入的下一阶段。
- 增强 `full-change-risk-review`：对需求及设计变化做增量影响分析，检查整改是否同步数据、API 和测试契约，并决定是否重新执行设计就绪复审。
- 设计收敛改为问题驱动的多轮流程，不写死轮数、页面数、需求数、测试数或任何项目专用常量。
- 使用简单 CRUD 与复杂编辑/画布/实时/发布系统完成盲测式前向验证。

## 4.0.0

- 将历史零散模块收敛为 5 个插件。
- 新增统一 `.ai` 状态协议和原子写入。
- 新增 SessionStart、PreCompact、Stop、SessionEnd、UserPromptSubmit Hook。
- 新增真实多语言/多框架/Monorepo 检测。
- 新增安全 Git Worktree 和分支租约。
- 修复风险分析遗漏 staged changes 的致命问题。
- 新增 SQLite 增量图谱，避免全量 JSON 图谱内存膨胀。
- 新增安装器、结构验证、单元和端到端测试。
