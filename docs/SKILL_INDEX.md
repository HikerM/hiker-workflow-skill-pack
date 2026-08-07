# Skill 索引

仓库包含三组，共 28 个 Skill。

## 第一组：Hiker 工作流守护组（9 个）

| Skill | 作用 |
|---|---|
| `hiker-workflow-router` | 把复杂任务路由到最短匹配工作流 |
| `codex-thread-review` | 复核 Codex 结果的范围、证据、缺口和下一步 |
| `project-phase-review` | 判断阶段或里程碑能否进入下一阶段 |
| `evidence-first-testing` | 设计真证据、Smoke、Contract、异常、并发和性能测试 |
| `contract-boundary-audit` | 审计 OpenAPI、DTO、数据库、Provider 和前后端边界 |
| `nodets-execution-pipeline-guardrails` | 守护 NodeTs 统一执行、结果和计费链路 |
| `unity-codex-guardrails` | 保护 Unity Scene、Prefab、资源、`.meta` 和 GUID |
| `design-output-discipline` | 约束 PPT、图片、SVG、PDF、Excel 等真实文件交付 |
| `agent-architecture-consultant` | 输出架构、范围、工期、报价、风险和双方案 |

源码：`../.agents/skills/`

## 第二组：AI 软件工程平台 Enterprise（18 个）

### `ai-engineering-core`

| Skill | 作用 |
|---|---|
| `project-bootstrap` | 识别真实技术栈和子项目，建立 `.ai/` 状态 |
| `official-standards-resolver` | 按真实版本生成官方依据的项目规范 |
| `interruptible-task-control` | 管理长期任务启动、暂停、继续和检查点 |
| `context-recovery` | 从 `.ai/` 状态恢复目标、决策、分支和下一步 |

### `ai-engineering-web`

| Skill | 作用 |
|---|---|
| `web-ui-design` | 动态设计非模板化 Web UI，建立设计系统、间距、色彩、组件复用、视觉焦点与节奏，并补齐真实数据/API 和验收契约 |
| `web-component-implementation` | 复用语义 Token 与组件实现有辨识度的页面，保留视觉层级和微交互 |
| `web-quality-review` | 只读审核设计系统、视觉丰富度、反模板、组件复用、样式和响应式 |

### `ai-engineering-unity`

| Skill | 作用 |
|---|---|
| `unity-ui-design` | 按真实 Unity/UI 技术栈设计页面和 Prefab 层级 |
| `unity-component-implementation` | 实现 Prefab、VisualElement、Renderer 或页面组件 |
| `unity-quality-review` | 只读审核 Scene、Prefab、GUID、资源、GC 和平台兼容 |

### `ai-engineering-workspace`

| Skill | 作用 |
|---|---|
| `workspace-task-router` | 把大型需求拆到主会话、Subagent 或 Worktree |
| `worktree-task-manager` | 安全创建、管理和清理 Worktree 与独立分支 |
| `change-ownership-merge` | 检查所有权、冲突和证据，生成安全合并计划 |

### `ai-engineering-quality`

| Skill | 作用 |
|---|---|
| `design-readiness-review` | 独立只读审核需求、设计系统、视觉质量到证据的语义追踪链，仅在 P0/P1 清零时允许进入编码 |
| `full-change-risk-review` | 审核完整变更集，并判断设计变化的增量影响、跨层同步和重新复审范围 |
| `knowledge-graph-maintenance` | 增量维护文件级关系图谱和限深影响分析 |
| `regression-test-planner` | 根据风险和真实脚本生成最低必要回归范围 |
| `release-readiness-review` | 综合风险、构建、测试、迁移和回滚审核发布状态 |

源码：`../skill-groups/ai-software-engineering-platform-enterprise/`

## 第三组：桌面软件等价重建（1 个）

| Skill | 作用 |
|---|---|
| `desktop-app-reconstruction-zh` | 已授权桌面软件的证据盘点、技术指纹、完整库存、技术选型、实现、差分测试、性能、打包和交付门禁 |

源码：`../skill-groups/desktop-app-reconstruction-zh/`

完整中文说明见 [`THREE_SKILL_GROUPS_ZH.md`](THREE_SKILL_GROUPS_ZH.md)。
