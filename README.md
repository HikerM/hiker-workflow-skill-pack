# Hiker 中文工程能力仓库

<!-- repository-facts: repo=0.13.0; engineering=5.18.0; plugins=5; engineering-skills=42; desktop=1.3.0; desktop-skills=5; total-skills=47 -->

这是面向 ChatGPT/Codex 桌面应用的软件工程能力仓库。仓库已经收敛，只保留两套用途明确、安装边界独立的能力包。

> 仓库版本：`0.13.0`
>
> 当前规模：`2` 套能力包、共 `47` 个 Skill
>
> 自动应用边界：只有“智能工程轻量路由”允许自动进入；桌面软件等价重建必须由用户明确选择。

## 能力包总览

| 能力包 | 版本 | 规模 | 适用范围 | 使用方式 |
|---|---:|---:|---|---|
| 智能软件工程平台 | 5.18.0 | 5 个插件、42 个原子 Skill | 从零开发、存量接管、B/S、C/S、Service/Data、产品级UI与错误体验、大型工程、多会话、Git、测试、质量与发布 | ChatGPT 语义选择，规则守门，按阶段懒加载 |
| 桌面软件等价重建 | 1.3.0 | 5 个 Skill | 已授权桌面软件的发现、规格、技术方案、实现、差分验证与发布 | 用户手动选择，阶段路由每次只加载一个原子 Skill |

两套能力不会在同一消息中自动全部加载。详细说明见 [能力包中文详解](docs/CAPABILITY_PACKS_ZH.md)，完整名称见 [Skill 索引](docs/SKILL_INDEX.md)。

## 智能软件工程平台 5.18.0

平台由一个轻量入口和42个原子 Skill 组成。ChatGPT 根据用户当前目标、否定项、阶段和有界工程证据选择最多两个原子 Skill；确定性脚本只校验候选存在性、阶段、架构证据、权限、源码身份和数量，不按关键词代替模型决策。

### 五个中文插件

| 插件名称 | Skill 数 | 核心职责 |
|---|---:|---|
| 智能工程核心 | 9 | 项目初始化、真实技术与版本、0→1需求融合、存量对账、架构反证、有界上下文和压缩恢复 |
| 浏览器端与服务端工程 | 8 | 非模板化界面设计系统、组件实现、服务端识别、API/事件契约、数据库迁移和质量审核 |
| 客户端工程 | 7 | Unity、Qt、.NET桌面、Electron/Tauri、Flutter、Android、Apple原生、React Native、Java桌面和嵌入式HMI |
| 工作区与多会话协作 | 12 | 项目状态、任务生命周期、多智能体、文件锁、Worktree、实现收敛、合并和验收闭环 |
| 质量、风险与发布 | 6 | 独立设计复审、完整变更风险、交互冲突、工程图谱、回归范围和发布审核 |

### 5.18.0 的增强重点

- **B/S 与 C/S 工程深化**：顶层按 Engineering Control Core、B/S、C/S、共享 Service & Data、Assurance 分层；Vue、React、Laravel、Unity、Qt 等仍只是按项目事实选择的 Technology Adapter。
- **语义 UI Design IR**：用业务任务、信息层级、阅读路径、状态、交互与验收表达设计，不把页面锁成 sidebar/cards/columns 模板；视觉输入严格区分 `OBSERVED`、`INFERRED` 与 `UNKNOWN`。
- **Decision Authority 与增量变更**：系统不变量、用户锁定决策、项目事实、架构约束、批准基线、适应策略和模型提案具有明确权威级别；用户修改只通过 Goal Change 使受影响的 Design、Screen、Component 与 Evidence 变为 `STALE`。
- **Component Registry 2.0 与 Design-to-Code**：绑定 Design ↔ Code、变体、状态、Token、可访问性、平台和真实源码指纹；适配器只观察显式或 Git 变更范围，不默认扫描组件库。
- **真实 Runtime 与 Fidelity Evidence**：把设计、源码、候选、目标修订、屏幕状态、架构、技术和视口绑定到运行证据；机器检查 overflow/clipping/overlap/state/token，感知质量保持独立审核，不使用虚假总分。
- **Presentation / Content / Interaction Copy**：阻断数据库内部 ID、raw enum、SQL、堆栈和本机路径直出，同时允许有业务含义的工单号、合同号等；内容压力依赖真实运行测量，不用固定字符数或列数替代语义。
- **协议中立 Error Contract**：兼容 REST、Problem Details、GraphQL、gRPC、C/S Local 与项目协议，分离用户消息和开发诊断，强制 Error ID 可反查并检测 catch-and-hide。
- **有界产品保障**：旧项目没有 UI IR 时保持零写兼容；活动门禁只读小型热索引，截图与冷证据显式按需读取，不增加默认 Prompt、Skill 或模型调用。
- **风险自适应稀疏治理**：10维风险画像和Verification Budget控制Validator、Runtime、Evidence与Review范围；控制不可接受结果，不规定模型推理或实现步骤。
- **增量Runtime与Evidence**：浏览器/客户端身份、Design IR、Component Registry和Evidence均绑定指纹与Affected Scope；完整截图和日志默认不进入主上下文。
- **交付效率可测量**：Governance Tax、Development Velocity和Time-to-Accepted-Change进入发布性能门禁；默认路由上下文和Prompt相对5.17不增长。

### 保持不变的 5.17 可靠性基线

- **可靠Control Kernel**：Task状态只有一个权威写协调入口；operation journal区分Domain提交与Trace补偿，重复请求不会重放已提交业务动作。
- **可恢复Desktop生命周期**：Turn租约、Checkpoint、终态、归档和释放形成闭环；app-server中断后进入受控恢复，不盲目重复派发。
- **有界Event与压力治理**：STATE/CONTROL低频持久化，TRACE有界分段，STREAM在Turn结束后聚合移除；压力升高时收敛并发并进入DRAINING。
- **局部Goal Change**：结构化影响分类只失效受影响Task、消费者和证据，未受影响的完成成果、测试与Checkpoint继续有效。
- **可证明发布**：Self Governance在打包前后强制Architecture、Privacy、Version、Tests、Performance、Package和Release Gate。
- **专项能力证据化**：Laravel、NodeTS、Unity和Qt按需读取真实版本、构建、边界、测试与平台证据，不进入普通项目默认路径。

5.16建立的性能内核、三档路径和版本栅栏继续保留：

- **常驻上下文减重**：全局自动应用模板从约7.1KB压缩到约3KB；42个Skill前置描述从约13.3KB压缩到10KB以内，并由桌面稳定性门禁阻止回涨。
- **三条性能路径**：简单解释与状态查询直接回答；普通项目在证据充分时一次准入；只有多会话、合并、发布和长链路任务进入完整治理。
- **路由准入可复用**：指纹绑定目标修订、仓库身份、HEAD、脏状态、Manifest、阶段、动作和候选；命中后不重复读取目录、Skill正文或回执。
- **长任务软硬阈值分离**：75%软阈值只在自然阶段边界保存Checkpoint，不触发治理空转；达到硬阈值才轮换唯一总控纪元。
- **新旧插件禁止混用**：五个插件必须具有同一完整版本。旧任务检测到版本漂移后只允许Checkpoint与迁移，由使用当前版本的新任务接管后才能继续写源码。
- **验证按插件分片**：日常修改只运行受影响插件测试并把完整输出写入证据；五插件全量审核只用于套件发布收尾。

- **并行不再依赖用户口令**：总控从变更契约、依赖和写范围自动提出安全通道。B/S、C/S、纯后端、多仓库都可动态拆分，规划态最多8个、运行态最多2个；父子目录或共享写表面重叠会被派发守门器强制串行。
- **治理有硬预算**：准备条件满足后，连续两个只有文档、矩阵或门禁变化而没有业务源码增量的治理周期会自动转入首个可执行开发切片，不能把“继续治理”当永久阻断。
- **总控长会话可控轮换**：按有效轮次、工具调用、输出字符和压缩次数管理会话纪元；超阈值先 Checkpoint，再用唯一替代总控接管并归档旧运行时，不按每个 Task 新建会话。
- **目标与执行不会静默漂移**：项目目标有修订号与指纹；旧 Task 在目标变化后必须重绑定。每个并行 Task 使用独立上下文包，根 `CURRENT_CONTEXT.md` 只保留总控摘要。
- **大输出不再灌入聊天**：完整脱敏日志写入证据文件，会话只返回有界首尾摘要、路径和哈希；Task 历史自动压缩归档，日常状态只读活动索引。
- **查询故障不中断已有工作**：桌面任务查询失败只禁止盲目创建替代会话；不需要新隔离运行时的步骤在当前有界线程继续，确实需要隔离的步骤才排队。

- **按规模分配上下文**：小型项目最多读取12个源码文件，标准项目40个，大型或长寿命项目80个；超限后按模块和风险分片，不自动扫描全仓、全部任务、全部检查点或全部 Skill 正文。
- **`.ai` 不再凌驾于源码**：源码身份、HEAD、分支和 Manifest 使用哈希溯源。L1只刷新热索引，L2重建受影响基线，L3使候选、图谱和审核测试证据失效，L4隔离跨项目污染；不会粗暴删除整个 `.ai`。
- **同一能力保持唯一**：只有一个权威活动实现和一个权威状态写入者。旧版、兼容层和临时实现必须有目标、退出条件和删除 Gate，废弃实现不得接收新增需求。
- **交付内容保持干净**：变更审核和发布审核自动检查正式运行路径，阻断默认 Demo/Mock/Fixture、占位或样例身份，以及用户可见的本机路径、堆栈和数据库内部错误。
- **长时间迭代仍有界**：需求、决定、Task、证据和 Checkpoint 落盘；对话只加载当前工作集。相同 Gate、源码/合同指纹和范围的 PASS 直接复用，测试工具失败只影响对应测试运行。
- **防止改一点坏一片**：每个 Task 先声明允许范围、原有行为不变量、公共表面、消费者和最低回归；Review、Testing、Merge 绑定不可变候选，源码变化后旧结论自动失效。
- **防止会话与 Worktree 爆炸**：只有总控管理固定 writer 与 assurance 会话槽；Task 变化不新建会话，普通任务终态自动释放锁和资源并复用槽位。
- **设计不是机械照抄**：用户方案视为候选，AI 主动检查遗漏、冲突、隐性耦合、失败模式和替代方案；深度由风险和决策成本控制。
- **B/S 与 C/S 都从证据识别**：读取真实工程文件、锁文件、SDK和版本；证据不足标记 unknown，不默认最新版，不把 Unity 当成全部客户端技术。
- **公开资产不携带敏感信息**：插件模板、Eval、发布包和文档禁止写入个人、公司、真实项目、会话、凭据和本机路径；唯一作者标识为 Hiker。

### 自动应用与性能

ChatGPT 软件工程会话先显示“已应用：01 智能工程核心｜智能工程轻量路由”。完成语义选择、守门校验和 Skill 读取后，再显示实际应用的中文插件名称与中文 Skill 名称。轻量路由不占两个原子 Skill 上限；第三个及之后的未来能力只进入有界待执行队列，阶段变化后重新选择。

路由只读取紧凑语义目录、浅层 Manifest、有界 `.ai` 热状态和源码身份摘要，不预加载42个 Skill。普通局部任务不自动建全量图谱、不跑全量测试、不创建多会话或 Worktree。

### 安装到 ChatGPT/Codex 桌面端

```powershell
Set-Location .\skill-groups\ai-software-engineering-platform-enterprise
py -3 -B .\install_personal.py
py -3 -B .\tools\verify_desktop_install.py
```

安装器复制并注册五个插件、更新个人 Marketplace、写入桌面端启用配置、生成唯一活动版本缓存并合并全局性能内核。已打开任务保存的是启动时能力快照，不能可靠原地热换：旧任务先Checkpoint并停止写入，再由新任务验证五插件版本指纹后接管；若新任务仍指向旧缓存，必须重启桌面端。

### 5.17发布验证

当前正式候选为 `5.17.0+codex.20260825194113`。发布流水线已完成以下验证：

- 五插件237项测试全部通过，源码测试指纹为 `ee5dfbea525763e8919a`；
- 42个Skill发布一致性审核通过；
- 39项宿主语义路由Eval通过，未调用外部模型API；
- Long Task、Crash Recovery、Multi Session、Goal Change和Event Pressure E2E通过；
- Architecture、Privacy、Version Facts、Performance和Package Facts全部通过；
- 五个5.17 ZIP与源码逐文件一致，并通过隔离HOME安装验证。

发行包位于 `skill-groups/ai-software-engineering-platform-enterprise/dist/`，SHA-256以同目录的 `SHA256SUMS.txt` 为准。完整证据见 [5.17验证报告](skill-groups/ai-software-engineering-platform-enterprise/VALIDATION_REPORT_CN.md)。任一发布Gate失败时，打包器不会更新正式发行目录。

## 桌面软件等价重建 1.3.0

用于已获授权的 Windows、macOS 或 Linux 桌面软件等价重建。总路由根据当前门禁只加载一个阶段 Skill：发现与规格、技术方案、实现、验证与发布。它不会自动加入普通软件工程消息，也不会绕过许可证、登录、DRM或授权边界。

本版本同样要求唯一当前候选、迁移退出条件和交付洁净度：旧原型与失败方案不得继续接收新需求，正式包不得包含默认演示数据、占位内容或内部诊断泄漏。

```powershell
Set-Location .\skill-groups\desktop-app-reconstruction-zh
.\INSTALL_WINDOWS.ps1 -Scope user
```

## 验证

```powershell
.\VALIDATE.ps1
```

总验证覆盖：仓库只能存在两套能力包、公开文档版本与实际 Manifest 一致、五插件42个 Skill 一致性、桌面重建5个 Skill 完整性、敏感信息、发布包、脚本测试、动态并行/长期总控/目标调整场景、路由性能和版本唯一性。评估维度见 [总控推进多维评估清单](skill-groups/ai-software-engineering-platform-enterprise/docs/MASTER_PROGRESSION_EVALUATION_CN.md)。任何一项失败都不得发布。

## 目录结构

```text
.
├─ README.md
├─ VERSION
├─ VALIDATE.ps1
├─ docs/
├─ scripts/
└─ skill-groups/
   ├─ ai-software-engineering-platform-enterprise/
   └─ desktop-app-reconstruction-zh/
```

仓库根目录不再提供旧守护 Skill、旧项目安装器或旧示例。
