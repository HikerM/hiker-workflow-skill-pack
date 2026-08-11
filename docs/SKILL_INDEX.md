# Skill 索引

仓库包含三组，共 44 个 Skill。每组都有轻量入口，单次只选择当前意图、技术栈和阶段所需的原子能力。

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

## 第二组：AI 软件工程平台 Enterprise（38 个）

### `ai-engineering-core`

| Skill | 作用 |
|---|---|
| `project-bootstrap` | 识别真实技术栈和子项目，建立 `.ai/` 状态 |
| `official-standards-resolver` | 按真实版本生成官方依据的项目规范 |
| `interruptible-task-control` | 管理长期任务启动、暂停、继续和检查点 |
| `context-recovery` | 从 `.ai/` 状态恢复目标、决策、分支和下一步 |
| `bounded-context-memory` | 用固定大小工作集、分级检查点和哈希账本支持多会话恢复，避免上下文持续增重 |
| `ai-engineering-router` | 唯一轻量自动入口，按项目模式、架构和阶段最多加载两个原子 Skill |
| `greenfield-project-planning` | 从零项目先融合稳定需求、冲突、未知项、验收条件和技术 Checkpoint |
| `brownfield-requirement-reconciliation` | 为部分源码建立能力基线并对账新增、修改、替换或移除需求 |

### `ai-engineering-web`

| Skill | 作用 |
|---|---|
| `web-ui-design` | 动态设计非模板化 Web UI，建立设计系统、间距、色彩、组件复用、视觉焦点与节奏，并补齐真实数据/API 和验收契约 |
| `web-component-implementation` | 复用语义 Token 与组件实现有辨识度的页面，保留视觉层级和微交互 |
| `web-quality-review` | 只读审核设计系统、视觉丰富度、反模板、组件复用、样式和响应式 |
| `backend-technology-router` | 从工程清单识别服务端语言、框架、运行时、包管理器和版本证据 |
| `api-event-contract-design` | 设计版本化 API、事件、错误、幂等和消费者兼容契约 |
| `backend-component-implementation` | 在真实服务端技术栈中实现有界功能并保留公共行为 |
| `database-migration-governance` | 治理迁移顺序、兼容窗口、数据回填、回滚和多实例发布 |
| `backend-quality-review` | 独立审核服务端契约、迁移、并发、安全、性能和回归证据 |

### `ai-engineering-unity`

| Skill | 作用 |
|---|---|
| `cs-client-router` | 从统一项目状态识别C/S技术族和版本证据，只选择当前阶段能力 |
| `cs-ui-design` | 为多技术栈客户端建立设计系统、组件、生命周期、离线和API契约 |
| `cs-component-implementation` | 在现有客户端框架中实现并验证，不擅自迁移技术栈 |
| `cs-quality-review` | 独立只读审核客户端视觉、线程、生命周期、API、平台和发布质量 |
| `unity-ui-design` | 按真实 Unity/UI 技术栈设计页面和 Prefab 层级 |
| `unity-component-implementation` | 实现 Prefab、VisualElement、Renderer 或页面组件 |
| `unity-quality-review` | 只读审核 Scene、Prefab、GUID、资源、GC 和平台兼容 |

### `ai-engineering-workspace`

| Skill | 作用 |
|---|---|
| `multi-agent-project-governance` | 七角色大型工程控制平面与总控入口 |
| `project-state-manager` | 维护项目状态、上下文快照和四个根文档 |
| `task-lifecycle-manager` | 管理 Task ID、Created→Released 和人工控制 |
| `workspace-task-router` | 按B/S与C/S前后端、契约、审核、测试和发布拆分任务 |
| `worktree-task-manager` | 按分支治理安全创建、管理和清理 Worktree |
| `file-lock-manager` | 保护Unity资产和NodeTS共享核心文件 |
| `feature-acceptance-closure` | 验证需求、代码、测试、证据、文档和状态闭环 |
| `change-ownership-merge` | 检查流向、提交、所有权、冲突、锁和门禁 |
| `multi-project-portfolio-manager` | 隔离多个Git仓库的项目身份与上下文 |
| `plugin-application-receipt` | 用一行中文展示本次实际应用的插件和 Skill |

### `ai-engineering-quality`

| Skill | 作用 |
|---|---|
| `design-readiness-review` | 独立只读审核需求、设计系统、视觉质量到证据的语义追踪链，仅在 P0/P1 清零时允许进入编码 |
| `full-change-risk-review` | 审核完整变更集，并判断设计变化的增量影响、跨层同步和重新复审范围 |
| `knowledge-graph-maintenance` | 增量维护文件级关系图谱和限深影响分析 |
| `regression-test-planner` | 根据风险和真实脚本生成最低必要回归范围 |
| `release-readiness-review` | 综合风险、构建、测试、迁移和回滚审核发布状态 |

源码：`../skill-groups/ai-software-engineering-platform-enterprise/`

## 第三组：桌面软件等价重建（5 个）

| Skill | 作用 |
|---|---|
| `desktop-app-reconstruction-zh` | 轻量识别当前门禁并只路由一个阶段原子Skill |
| `desktop-reconstruction-discovery` | G0–G4授权、证据、界面、功能、数据和追踪规格 |
| `desktop-reconstruction-technical-design` | G5-T候选技术、POC、官方版本核验和精确锁定 |
| `desktop-reconstruction-implementation` | G6按规格、任务和测试编号实现真实软件 |
| `desktop-reconstruction-verification-release` | G7–G9独立差分、性能、交付和发布门禁 |

源码：`../skill-groups/desktop-app-reconstruction-zh/`

完整中文说明见 [`THREE_SKILL_GROUPS_ZH.md`](THREE_SKILL_GROUPS_ZH.md)。
