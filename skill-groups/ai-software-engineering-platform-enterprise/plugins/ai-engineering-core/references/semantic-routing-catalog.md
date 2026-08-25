# 原子 Skill 语义路由目录

本文件只提供候选元数据，不预读原子 `SKILL.md`。ChatGPT 按当前动作和有界证据最多选两个；脚本只校验。

## 核心与上下文

- `greenfield-project-planning`｜0→1需求融合与选型：空项目先融合需求、冲突、未知项、验收和技术候选。
- `architecture-decision-challenge`｜架构决策挑战与补全：反证用户提供的架构思路，找遗漏、失败模式和替代方案。
- `brownfield-requirement-reconciliation`｜存量源码需求对账：已有源码先建立能力基线，再对账新增、修改、替换或移除。
- `project-bootstrap`｜项目智能初始化：首次接管或技术栈变化时，从工程证据建立项目上下文。
- `bounded-context-memory`｜有界上下文记忆：超长单会话、多会话和多轮压缩时保持有界工作集。
- `context-recovery`｜上下文恢复：新会话或压缩后从正式状态和 Checkpoint 恢复。
- `interruptible-task-control`｜可中断任务控制：保存状态后暂停、调整、插入需求或恢复。
- `official-standards-resolver`｜官方规范解析：按已识别的语言、框架和版本解析官方规范。

## 浏览器端与服务端

- `web-ui-design`｜浏览器端界面与交互设计：设计 Web 设计系统、Token、组件契约和非默认状态。
- `web-component-implementation`｜浏览器端组件与页面实现：在已有 Web 技术栈中实现或修改页面组件。
- `web-quality-review`｜浏览器端质量审核：只读审核 Web 视觉、设计系统、组件复用和反模板质量。
- `backend-technology-router`｜服务端技术路由：先识别服务端语言、框架、运行时和版本。
- `api-event-contract-design`｜接口与事件契约设计：设计版本化 API、事件、错误模型和消费者兼容。
- `backend-component-implementation`｜服务端功能实现：在已有服务端架构中实现有边界功能。
- `database-migration-governance`｜数据库迁移治理：处理 Schema、迁移、兼容、回滚和串行门禁。
- `backend-quality-review`｜服务端质量审核：只读审核服务端、契约、数据和运行风险。

## 通用客户端与 Unity

- `cs-client-router`｜客户端技术路由：先识别真实 C/S 语言、框架、SDK、构建工具和版本。
- `cs-ui-design`｜客户端界面设计：设计 Qt、.NET、Electron/Tauri、Flutter、原生移动等客户端界面。
- `cs-component-implementation`｜客户端组件实现：在已有通用客户端框架中实现或修改功能。
- `cs-quality-review`｜客户端质量审核：只读审核客户端视觉、生命周期、平台和接口兼容。
- `unity-ui-design`｜游戏引擎界面设计：按真实 Unity 版本和 UI 体系设计页面。
- `unity-component-implementation`｜游戏引擎组件与页面实现：实现 Unity Prefab、Renderer 和页面组件。
- `unity-quality-review`｜游戏引擎质量审核：只读审核 Unity 资产、性能、分辨率和平台风险。

## 工作区、Git 与多会话

- `workspace-task-router`｜任务分流与会话规划：跨前端、客户端、服务端或仓库时拆分所有权和串并行边界。
- `multi-agent-project-governance`｜大型工程多智能体总控：长期管理大型工程、固定会话槽和自动终态回收。
- `project-state-manager`｜项目状态与上下文管理：维护项目事实、当前状态和多仓库隔离。
- `task-lifecycle-manager`｜工程任务生命周期：管理 Task ID、状态、负责人、分支、提交和证据。
- `long-chain-change-convergence`｜长链路变更收敛：压制范围膨胀、重复失败、新旧实现并存和旧证据沿用。
- `file-lock-manager`｜多智能体文件锁：保护 Unity 资产、Migration、API Contract 和核心 Service。
- `multi-project-portfolio-manager`｜多项目隔离管理：注册、切换和核验多个 Git 项目的独立上下文。
- `worktree-task-manager`｜多工作目录任务管理：安全创建、暂停和恢复受治理的并行 Worktree。
- `worktree-safe-convergence`｜工作目录安全收敛：接管、分类和收敛历史或堆积 Worktree。
- `change-ownership-merge`｜代码所有权与合并控制：在 merge 阶段审核分支、提交、冲突、锁和证据。
- `feature-acceptance-closure`｜功能验收闭环：用功能、测试、日志/截图、文档和状态关闭任务。
- `plugin-application-receipt`｜插件应用回执：仅当用户单独询问应用记录时显示真实加载回执。

## 质量、风险与发布

- `design-readiness-review`｜设计就绪独立复审：编码前只读复审设计系统、契约和实现就绪度。
- `interaction-conflict-governance`｜交互状态与冲突治理：检查隐藏表面、浮层、焦点、快捷键、乱序和重复提交。
- `full-change-risk-review`｜完整变更风险评估：只读审核完整变更集、公共能力、架构和发布影响。
- `knowledge-graph-maintenance`｜工程图谱维护：按需增量构建或查询文件级依赖与影响图谱。
- `regression-test-planner`｜回归测试范围规划：按真实变更风险和项目脚本生成最低充分回归。
- `release-readiness-review`｜发布就绪审核：在 release 阶段核对构建、测试、迁移、部署和回滚证据。

## 选择规则

1. 以当前动作定阶段，不把后续审核、测试、推送提前加载。
2. 分离正向、否定、示例、历史和未来；技术名不能单独成为候选证据。
3. 项目已有工程证据时以证据为准；证据不足写 `unknown`，不猜最新版或架构。
4. 识别事实≠需求对账，增长治理≠恢复，任务分流≠长期总控，项目状态≠Task生命周期。
5. 设计、实现、审核、测试、发布不跨阶段替代；第三项进入待执行队列。
6. 守门器被拒后由 ChatGPT 重选，脚本不得替换候选。
