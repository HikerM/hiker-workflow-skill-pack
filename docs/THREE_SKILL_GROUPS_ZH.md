# 三组 Skill 中文详解

本文档解释仓库中的三组 Skill 如何分工、各自包含什么、适合什么任务、如何触发，以及它们之间如何协作。

## 一、分组原则

三组 Skill 按“治理复核、工程执行、专项重建”分开：

- **第一组：Hiker 工作流守护组**——重点是判断任务有没有越界、证据够不够、阶段能不能通过。
- **第二组：AI 软件工程平台 Enterprise**——重点是长期工程的初始化、状态维护、代码实现、质量门禁和并行协作。
- **第三组：桌面软件等价重建**——重点是一个高度专业化的桌面软件迁移与等价重建全流程。

三组不是相互替代关系。第一组可以作为第二组的外部复核层；第三组在桌面重建项目中担任主工作流，必要时也可以调用第一组做独立验收。

全局自动策略只有一个入口：第二组 `ai-engineering-router`。第一组和第三组必须由用户通过 `@`/`$` 明确点名或在插件列表手动选择，普通消息不得自动触发它们。

---

## 二、第一组：Hiker 工作流守护 Skill Pack

### 2.1 设计目标

这一组把 Hiker 常用的工程判断标准固化成可复用 Skill。它关注的是：

- 当前目录、分支、HEAD 和变更集是否正确；
- 用户给出的范围和禁止事项是否被遵守；
- “完成”是否有可复现的 build、smoke、contract、集成、日志、截图或数据证据；
- 接口、数据库、队列、Provider、资产和计费边界是否闭环；
- 阶段是否真正满足进入下一阶段的门禁；
- 是否能生成一段清晰、可直接复制给 Codex 的下一步消息。

这组 Skill 不会因为“代码写完”“编译通过”或“提交了一个 commit”就自动认定任务完成。

### 2.2 组内 9 个 Skill

#### `hiker-workflow-router`

总路由器。面对复杂工程请求时，先识别任务属于线程复核、阶段验收、证据测试、契约边界、NodeTs 链路、Unity、设计交付还是架构咨询，然后选择最短匹配 Skill。简单任务不会被强行套入重流程。

典型触发：

```text
请先用 hiker-workflow-router 判断应该调用哪个 Skill，再执行这个任务。
```

#### `codex-thread-review`

复核一段 Codex 执行结果、终端输出或任务总结。检查目标是否完成、是否超出授权、证据是否真实、是否漏掉验证，以及下一轮应该如何要求 Codex 补齐。

标准输出包括：结论、证据、问题、下一步和可复制消息。

#### `project-phase-review`

用于 P2.x、里程碑、Sprint 阶段或任意 Stage Gate 验收。它会区分“代码存在”“构建成功”“smoke 通过”“契约通过”“已提交”“已推送”“已合并”等不同状态，不把它们混为一谈。

适合回答：当前阶段能否进入下一阶段、有哪些硬缺口、需要哪些最小补证。

#### `evidence-first-testing`

设计和审核真证据测试。覆盖源代码审计、build/typecheck、smoke、contract、集成测试、异常输入、混乱数据、并发、性能和稳定性；同时明确真实数据、fixture、接口形状 mock 和 happy-path stub 的边界。

适合需要证明“真的可用”，而不是只想增加测试数量的任务。

#### `contract-boundary-audit`

审计 OpenAPI、DTO、路由、请求/响应、数据库 Schema/Seed、Provider Adapter、结果归一化和前端消费字段。它特别关注前端是否绕过统一业务链路，或后端不同层之间是否出现字段漂移。

#### `nodets-execution-pipeline-guardrails`

针对 NodeTs AI 漫剧/内容生成平台的专项守护。统一链路为：

```text
quote → create → worker/provider → resource_transfer → result normalization
      → asset/storage/preview_url → billing
```

它检查 Provider Payload、异步队列、轮询/回调、结果归一化、资产落库以及计费 reservation/settlement/release 是否一致，防止前端或新 Provider 绕过统一执行链路。

#### `unity-codex-guardrails`

针对通过 Codex App、Unity MCP 或脚本修改 Unity 项目的安全规则。修改前先确认项目根、Git 状态、Editor/Console、Scene Hierarchy；修改时保护 `.meta`、GUID、Prefab 引用和序列化字段；完成后报告 Play Mode、测试、Console 和 Hierarchy 证据。

#### `design-output-discipline`

用于 PPT、图片、海报、扑克牌、SVG、PDF、Excel、文件转换和批量导出。要求保留原内容、顺序、比例和命名规则，必须生成真实文件，并用渲染或抽查证据证明输出可用。

#### `agent-architecture-consultant`

用于 Laravel、Vue、MySQL、Redis、MCP、Agent、API 集成和平台架构咨询。输出可落地的架构路线、工作拆分、时间线、风险、范围边界、报价框架，以及保守/进取两套方案。

### 2.3 适用与不适用

适用：

- 复核 Codex 任务、PR 类结果或阶段成果；
- 复杂 API/DB/Queue/Provider/Billing 链路；
- Unity 工程修改和设计文件交付；
- 需要真实证据、风险判断和下一步消息的工程任务。

不适用：

- 只需回答一个简单知识问题；
- 需要直接替代某个框架官方开发文档；
- 未经授权执行生产 DB、计费、部署、强制推送或服务重启。

### 2.4 安装范围

第一组默认安装到具体项目的 `.agents/skills/`，并可把 Hiker 规则区块安全合并到项目 `AGENTS.md`。它强调项目级治理，不默认做全局覆盖。

---

## 三、第二组：AI Software Engineering Platform Enterprise 5.5

### 3.1 设计目标

这一组是一套插件化软件工程平台。它解决长期任务中最常见的六类问题：

1. 项目技术栈和规范不明确；
2. 会话中断或上下文压缩后事实丢失；
3. Web 与 Unity 实现没有沿用真实项目架构；
4. 编码前的设计只有引用和计数，没有足以实现、验收的语义深度；
5. 只看已提交文件，漏掉暂存、未暂存或未跟踪变更；
6. 多任务、多会话和 Worktree 缺乏所有权与合并治理。

核心原则是“核心插件只探测一次，其他插件消费统一 `.ai/` 上下文”。这样 Web、Unity、质量和工作区模块不会重复猜测技术栈。

### 3.2 五个插件和 38 个 Skill

#### 插件一：`ai-engineering-core`（8 个 Skill）

- `project-bootstrap`：首次接管仓库时识别语言、框架、精确版本、包管理器、Unity 版本和子项目，并建立 `.ai/` 状态。
- `official-standards-resolver`：根据真实版本查阅对应官方文档，生成项目专属规范；禁止用无版本依据的通用模板冒充官方标准。
- `interruptible-task-control`：管理长期任务的启动、暂停、继续、调整和检查点；用户插入指令时保留已经完成的工作。
- `context-recovery`：从 `.ai/` 状态和最新检查点恢复目标、决策、分支和下一步，不把旧聊天摘要当作唯一事实来源。
- `bounded-context-memory`：把关键需求、决定、任务、证据和Git事实持久化，只向会话注入固定大小工作集；近期与里程碑checkpoint分别限额，旧冗余副本收敛到有界索引和哈希链，避免长期使用越来越重。
- `ai-engineering-router`：唯一轻量自动入口，只检查有限工程标记，并按项目模式、架构和阶段选择最多两个原子 Skill。
- `greenfield-project-planning`：从零开发先融合带稳定 ID 的需求、冲突、未知项、验收条件和技术决策 Checkpoint。
- `brownfield-requirement-reconciliation`：为部分源码建立 `CAP-*` 能力基线，并把 `REQ-*` 对账为新增、修改、替换或移除。

`ai-engineering-core` 提供保存和恢复工程状态的脚本。当前 Codex 插件 manifest 不注册已不受支持的 `hooks` 字段，相关脚本由 Skill 或外部编排显式调用。

#### 插件二：`ai-engineering-web`（8 个 Skill）

- `web-ui-design`：从需求、工作流、品牌语境、路由和技术栈动态识别页面；先定义项目专属设计系统、语义色彩、间距尺度、组件复用、视觉焦点、疏密节奏和签名元素，再补齐复杂页面的数据、命令、状态、降级、并发、发布和验收。明确禁止普通后台模板、Bootstrap 式默认视觉、重复卡片汤和单调等权布局。
- `web-component-implementation`：只实现独立复审通过的设计；复用语义 Token 与现有组件，保留视觉层级、节奏和服务任务的微交互，缺少设计系统契约时阻断编码。
- `web-quality-review`：只读审核设计系统、组件复用、依赖边界、TypeScript、响应式、视觉状态、反模板质量和视觉丰富度，不通过“边改边审”制造假通过。
- `backend-technology-router`：从项目清单识别 Node/TypeScript、Python、.NET、JVM、Go、Rust、PHP、Ruby 的服务端框架、运行时、包管理器和版本证据。
- `api-event-contract-design`：设计版本化 API、事件、错误模型、幂等和消费者兼容契约。
- `backend-component-implementation`：在现有服务端技术与版本中实现有界功能，避免破坏公共行为。
- `database-migration-governance`：治理迁移顺序、兼容窗口、回填、回滚和多实例发布。
- `backend-quality-review`：独立审核契约、迁移、事务、并发、安全、性能和真实回归证据。

#### 插件三：`ai-engineering-unity`（显示为“03 C/S客户端工程”，7 个 Skill）

- `cs-client-router`：从统一项目状态轻量识别 Unity、Qt、.NET桌面、Electron/Tauri、Flutter、Android、Apple原生、React Native、Java桌面和嵌入式HMI；同时报告语言、运行时、框架、SDK、构建工具的版本证据和缺口。
- `cs-ui-design`：为非Unity客户端建立设计系统、色彩、间距、组件复用、窗口/设备生命周期、离线和API契约。
- `cs-component-implementation`：在当前项目真实框架和版本中实现，不写死技术路线或擅自迁移。
- `cs-quality-review`：独立只读审核客户端视觉、组件、线程、生命周期、资源、API、平台、性能、安装和更新证据。

- `unity-ui-design`：根据 Unity 版本、UGUI/UI Toolkit 和现有导航设计 UI、Prefab 层级、Anchor、页面生命周期和交互状态。
- `unity-component-implementation`：实现 Prefab、VisualElement、Renderer 或页面组件，遵守资源生命周期和现有数据层。
- `unity-quality-review`：只读审核代码、Prefab、Scene、`.meta`/GUID、多分辨率、GC、资源和平台兼容性。

#### 插件四：`ai-engineering-workspace`（10 个 Skill）

- `multi-agent-project-governance`：Master总控入口，协调Planning、Developer、Review、Test、Merge和Document角色。
- `project-state-manager`：维护PROJECT_STATE、CURRENT_CONTEXT、CHANGELOG、ARCHITECTURE及机器状态。
- `task-lifecycle-manager`：管理Task ID、Created到Released状态机和暂停/调整/恢复。
- `workspace-task-router`：B/S拆分浏览器前端与服务端，C/S拆分客户端与服务端，并建立契约数据通道。
- `worktree-task-manager`：按main/release/develop和feature/bugfix/hotfix规则管理Worktree。
- `file-lock-manager`：保护Unity Scene/Prefab/ProjectSettings/meta与NodeTS Service/migration/API Contract。
- `feature-acceptance-closure`：检查需求、代码、审核、测试、截图/日志、文档和状态闭环。
- `change-ownership-merge`：检查分支流向、Conventional Commit、所有权、冲突、文件锁和合并门禁。
- `multi-project-portfolio-manager`：隔离多个Git仓库的项目身份、状态、任务与分支。
- `plugin-application-receipt`：只用一行中文显示本次实际应用的插件和 Skill。

该插件提供多会话和工作区状态管理脚本，但不通过 manifest 自动注册 Hook。完整架构、角色契约、状态模型与端到端示例见 [`MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md`](MULTI_AGENT_ENGINEERING_SYSTEM_ZH.md)。

#### 插件五：`ai-engineering-quality`（5 个 Skill）

- `design-readiness-review`：独立、只读构建“需求→工作流→页面→设计系统/Token→组件→数据→API/事件→权限→测试→证据”追踪链；缺少间距、色彩、组件复用或视觉丰富度契约，以及明显模板化、卡片化、单调化的新增 UI 均按 P1 阻断，只有 P0/P1 清零才允许进入编码。
- `full-change-risk-review`：覆盖完整变更集；当需求、架构、数据、API、UI 或测试设计变化时执行增量影响分析，检查跨层同步并判断是否必须重新进行设计就绪复审。
- `knowledge-graph-maintenance`：增量维护文件级关系图谱，用限深影响分析控制大型仓库扫描成本。
- `regression-test-planner`：根据变更风险和项目真实脚本生成最低必要回归范围。
- `release-readiness-review`：结合风险、构建、测试、迁移、回滚和发布证据审核版本是否可发布。

### 3.3 推荐工作流

```text
project-bootstrap（识别真实技术与版本）
  → official-standards-resolver
  → Web 或 C/S轻量路由
  → 当前技术族的设计
  → design-readiness-review
  → 定向整改与相关回归（若有 P0/P1）
  → Web 或 Unity 实现
  → full-change-risk-review
  → regression-test-planner
  → release-readiness-review
```

大型并行任务可在实现前加入：

```text
multi-agent-project-governance → project-state-manager → task-lifecycle-manager
  → workspace-task-router → worktree-task-manager/file-lock-manager
  → Review → Test → feature-acceptance-closure → change-ownership-merge
```

会话中断或上下文压缩后使用：

```text
context-recovery → interruptible-task-control
```

### 3.4 适用与不适用

适用：长期工程、跨模块需求、Web及各类C/S客户端实现、多个Codex会话、Worktree并行、完整变更风险和发布门禁。

不适用：只修改一行文本、非 Git 临时目录、未确认仓库根目录的批量写入，或希望插件自动强制合并/部署的场景。

### 3.5 安装范围

第二组必须保持插件包结构完整。运行 `install_personal.py` 会复制并注册 5 个插件、写入桌面端启用配置、生成版本缓存、合并全局路由规则，并核验源码、安装目录和缓存哈希一致性。

---

## 四、第三组：Desktop App Reconstruction ZH 1.2

### 4.1 设计目标

这一组包含一个轻量总路由和四个阶段原子 Skill。总路由只判断当前门禁，不再把完整发现、选型、实现和发布指令一次装入会话：

- `desktop-app-reconstruction-zh`：轻量总路由与授权边界；
- `desktop-reconstruction-discovery`：G0–G4证据、库存、规格和覆盖追踪；
- `desktop-reconstruction-technical-design`：G5-T候选技术、POC、官方版本与精确锁定；
- `desktop-reconstruction-implementation`：G6独立实现；
- `desktop-reconstruction-verification-release`：G7–G9差分、性能、交付和发布门禁。

共享参考、脚本、证据协议和模板仍属于第三组，安装时不会混入前两组。单次任务只启用当前门禁的一个原子 Skill。

它支持四种模式：

1. **资料分析**：只有截图、录屏、文档、样例文件或用户描述；输出规格、缺口和实施任务，不声称已经完成软件。
2. **代码实施**：存在可读写项目；可探测技术栈、修改源码、运行测试和构建。
3. **自动观测**：具备 Computer Use、桌面自动化或 MCP；可在授权范围内操作源软件、截图和采样性能。
4. **混合模式**：资料、源码和自动观测同时存在；优先用直接观测验证推断。

### 4.2 证据等级

所有结论使用以下等级，避免把猜测写成事实：

- `OBSERVED`：直接观察并记录；
- `MEASURED`：按可重复方法测量；
- `INFERRED`：根据证据推断；
- `UNVERIFIED`：有说法但没有验证；
- `BLOCKED`：因权限、账号、环境、数据或工具受阻；
- `NOT_APPLICABLE`：不适用。

### 4.3 阶段门禁

- **G0**：授权与范围冻结。
- **G1**：环境和证据基线。
- **G1-T**：原软件技术指纹与未知边界。
- **G2**：入口、窗口、页面、控件和视觉库存。
- **G3**：交互与状态机。
- **G4-C**：功能、数据、权限、异常和覆盖完整性。
- **G5-T**：目标技术选型、精确版本锁定和代表性 POC。
- **G6**：独立实现。
- **G7**：视觉、功能和数据差分验证。
- **G8**：性能与稳定性。
- **G9-D**：打包、交付物完整性和发布门禁。

### 4.4 核心输出

- 授权、范围、环境和证据索引；
- 原软件技术指纹与目标技术栈决策；
- 窗口、页面、控件、快捷键、功能、角色、数据、异常和性能库存；
- UI、交互、功能、数据、权限、性能和错误恢复规格；
- 实施任务、源码、依赖锁、构建脚本和安装器；
- 测试用例、覆盖矩阵、端到端追踪矩阵、缺陷和豁免；
- 视觉/数据/性能差分证据；
- 安装、升级、卸载、迁移、回滚和发布报告；
- 残余未知风险报告。

### 4.5 适用与禁止用途

适用：已获授权的软件迁移、国产化替代、跨平台重写、UI/行为还原、功能复现、性能对标和遗漏审计。

禁止：绕过许可证、登录或 DRM；提取源码、密钥或凭据；隐蔽监控；复制未授权资产；冒充原厂；把纯黑盒推断写成已证明的内部实现。

### 4.6 完成标准

只有范围和版本冻结、关键门禁通过、P0/P1 追踪和测试 100% 通过、视觉/数据/性能/安装链路验证完成，并且所有未知、受阻和豁免已被接受时，才能写“达到约定范围内等价”或“验收通过”。

---

## 五、三组协作示例

### 场景一：长期 Web 项目

第二组负责初始化、规范、设计、实现和发布门禁；第一组在阶段结束时独立复核证据：

```text
第二组：project-bootstrap → web-ui-design → design-readiness-review → web-component-implementation
第二组：full-change-risk-review → regression-test-planner
第一组：codex-thread-review → project-phase-review
```

### 场景二：Unity 多会话开发

第二组负责路由和 Worktree，第一组提供 Unity 修改守护和阶段验收：

```text
第二组：workspace-task-router → worktree-task-manager
第二组：unity-ui-design → unity-component-implementation → unity-quality-review
第一组：unity-codex-guardrails → evidence-first-testing
```

### 场景三：桌面软件重建

第三组担任主工作流；第一组只在需要独立复核时介入：

```text
第三组：G0 → G1 → G1-T → G2 → G3 → G4-C → G5-T → G6 → G7 → G8 → G9-D
第一组：project-phase-review / evidence-first-testing（可选独立验收）
```

## 六、选择原则

- 任务重点是“检查是否真的完成”——选第一组。
- 任务重点是“长期工程怎么持续执行”——选第二组。
- 任务重点是“完整重建一个已授权桌面软件”——选第三组。
- 同时需要执行和独立验收——第二组执行，第一组复核。
- 不要把第二组38个Skill拆散安装成普通平铺Skill；第三组的五个可发现Skill可以按阶段选择，但共享参考、脚本和模板不能从主资源包剥离。
