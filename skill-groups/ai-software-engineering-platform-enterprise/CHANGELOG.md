# CHANGELOG

## 5.6.0

- 新增源码身份门禁：Git 仓库只使用当前 Worktree 的已跟踪 Manifest 识别技术栈，排除兄弟及嵌套 Worktree；检测到规范仓库内部嵌套工作目录时停止源码实现路由。
- 新增轻量 Worktree 库存器，快速模式只解析一次 `git worktree list --porcelain`；标准和深度模式只在创建、恢复、合并、发布或安全收敛时按需执行。
- 新增「工作目录安全收敛」原子 Skill，支持历史 Worktree 只读接管、证据分类、清理计划、安全 Token 和执行前重新验证；禁止批量强制删除及自动删除分支。
- 创建 Worktree 前强制检查项目初始化、真实活动预算和嵌套工作目录；租约增加活动、到期和复核时间，暂停到期只提醒复核、不自动删除。
- 任务状态增加 `MergedPendingCleanup`；合并完成但任务 Worktree 尚未关闭时不能进入 Merged，避免已完成任务长期留下源码副本。
- 对账器增加开发、创建、合并和发布阶段严重度：普通开发允许清点历史债务，创建与发布阻断未纳管工作目录，嵌套 Worktree 始终阻断。
- 实测 30 次本地冷进程路由 P95 为 97.32ms；现有前端 23 个、后端 33 个 Worktree 的快速库存约 210ms/237ms，均不读取源码内容。

## 5.5.0

- 2026-08-11 修订：修复 ASP.NET Core、WPF、React Native、纯 React 与 Fastify 的技术栈误判；混合前后端任务先拆分工作通道，插件性能诊断不再误入客户端工程。
- 2026-08-11 修订：修复 Windows 中文 Git 历史解码崩溃与 ZIP 二进制文件增长假阻断；增加开放任务总预算、已关闭任务 Worktree 对账和可恢复的插件缓存保留策略。
- 2026-08-11 修订：Unity GUID 与 .NET 项目引用改为增量语义索引；发布包使用固定时间戳和权限生成可复现 ZIP；新增冷进程路由 P95 性能门禁。
- 将服务端能力拆为技术路由、接口与事件契约、功能实现、数据库迁移、质量审核五个原子 Skill，供 B/S、C/S 与混合项目共享；真实清单缺失时返回 unknown，不猜最新版本。
- 修复插件增强、桌面端重装、审核和推送请求误入 C/S 客户端审核的问题；路由结果继续严格限制为最多两个直接相关能力。
- 增加项目并行预算与 Task/Branch/Worktree/文件锁对账器，默认最多两个活动写任务和两个待收敛任务，阻止大型工程持续制造孤儿分支与合并债务。
- 工程图谱增加 Unity GUID 资源引用、.NET ProjectReference、Protobuf import 与更多资源/契约文件类型，提升修改公共资源和跨项目依赖时的影响识别。
- 应用回执收敛为一行实际使用的中文插件与中文 Skill 名称，不再显示组织分组、内部英文ID、未使用插件或重复结束回执。
- 安装器增加源目录、安装目录、版本缓存、启用配置与全局规则一致性核验，生成桌面端安装快照；新任务即可刷新能力快照，只有仍命中旧注册时才需重启。
- 测试覆盖扩展到路由误判、跨技术栈服务端、并行预算、任务对账、Unity资源与.NET项目依赖。

## 5.4.0

- 新增大型工程架构守卫：任务变更契约、范围漂移、公共表面/消费者、特征回归、依赖方向、图谱影响半径、受保护模块和文件增长预算形成机器门禁。
- 架构守卫证据绑定 Git HEAD 与工作区指纹，并接入 Development→Review、功能闭环、合并审核和完整风险评估；代码变化后旧证据自动失效。
- 采用“零配置可运行、约定优先、渐进增强”：模块表、依赖规则、公共表面和运行拓扑为空时不阻塞普通改动，只对高风险边界要求显式登记。
- C/S技术族增加Qt、.NET桌面、跨平台客户端、原生移动/Java桌面和嵌入式HMI五组懒加载原子参考；后端增加Node/TypeScript、.NET、JVM、Python和其他技术族参考。
- 修复嵌套Monorepo误判空项目、纯后端不路由、角色伪造审核、发布无任务仍通过、Unity嵌套ProjectSettings和Prefab/meta同任务锁误判等问题。
- 风险等级现在受最高发现严重度约束；公共/核心文件和超大文件的小改动不再被误判为低风险；Bootstrap与重复卡片汤组合直接阻断。
- 所有插件与33个Skill的用户可见名称统一为中文；路由和应用回执只展示中文名，英文ID仅保留在机器内部。
- 新增可执行路由Eval，74条正向与31条负向场景全部通过；仍保持唯一隐式入口和每轮最多两个原子能力。
- 有界恢复优先读取工作区 `CURRENT_CONTEXT.md`，检查点同时保存活动Task、四个根状态文档及关键架构登记，避免两套状态脱节。
- 多智能体总控改为按治理域懒加载：作为审核辅助时读取零份参考，普通任务读取零到一份，真正跨域时最多两份，禁止启动阶段预读全部治理文档。
- 个人安装器默认面向 ChatGPT/Codex 桌面端：在本地插件和Marketplace就绪后，安全、幂等地写入五个插件启用配置并保留原配置备份；CLI仅作为显式旧版兼容选项。
- 安装器同时原子生成版本化个人Marketplace缓存；不再依赖桌面端何时自行刷新，本机源码、插件目录与新缓存可以逐文件校验一致。

## 5.3.0

- 新增唯一隐式入口 `ai-engineering-router`，路由阶段只检查有限工程标记并返回最多两个需要读取的原子Skill。
- 新增 `greenfield-project-planning` 与 `requirements_fusion.py`：稳定 Requirement ID、revision history、冲突、未知项、验收活动切片和技术决策Checkpoint。
- 新增 `brownfield-requirement-reconciliation` 与 `brownfield_reconcile.py`：从真实源码建立 `CAP-*` 能力基线，将新增自定义需求对账为新增、修改、替换或移除，阻止无依据重新脚手架。
- 其余32个原子Skill全部关闭隐式调用但保留手动可见；验证器强制该性能策略，防止版本回退。
- 全局AGENTS模板改为短路由契约，不再预列举全部原子Skill。
- 将核心插件默认提示收敛到客户端支持的三条，并增加本地Cachebuster，避免更新后继续命中旧缓存。
- Enterprise Skill数量由30个增至33个。

## 5.2.0

- 新增 `bounded-context-memory`，明确01号负责有界持久记忆，04号负责多会话Task/Agent/Worktree/合并交接。
- 新增项目级 `context-retention.json`，限制活动上下文、会话注入、每节条目、近期checkpoint、里程碑checkpoint和压缩账本大小。
- 新增 `checkpoint-ledger.json`：旧冗余checkpoint在移除前记录有界索引、SHA-256和连续哈希链；Task、正式决定、Git和验收证据不被清理。
- `CURRENT_CONTEXT.md`、`active-context.md` 与 `PROJECT_STATE.md` 改为有界工作集，并指向完整机器事实源，避免多轮压缩和多年任务持续增重。
- 新增有界 `task-index.json`，日常状态刷新不再扫描全部历史Task；默认只保留最近200个已关闭摘要，完整Task文件不删除。
- Enterprise Skill数量由29个增至30个。

## 5.1.0

- 将03号从Unity专项扩展为通用C/S客户端工程：新增轻量技术栈路由、通用UI设计、组件实现和独立质量审核，原Unity三项能力完整保留。
- 从统一项目状态识别Qt、.NET桌面、Electron/Tauri、Flutter、Android、Apple原生、React Native、Java桌面和LVGL，并输出语言、运行时、框架、SDK、构建工具的版本证据和缺口。
- C/S工作区固定拆分客户端、服务端与版本化契约/数据通道，不把客户端插件冒充后端实现。
- 增加单技术族、单阶段、按需参考和不重复扫仓的性能预算；全局规则只选择一个主路由。
- Enterprise Skill数量由25个增至29个。

## 5.0.1

- 个人安装器默认安全合并 `~/.codex/AGENTS.md` 中的全局自动应用与插件回执区块，并在修改前备份。
- 安装器自动发现Codex CLI并安装启用五个插件；CLI不可用时输出明确的 `manual_commands`，不冒充已启用。
- 重复安装只更新同一标记区块；新增 `--no-merge-global-agents`、`--no-activate-plugins` 和 `--codex-cli`。
- 卸载器默认只移除自己管理的全局区块并保留其他指令，可用 `--keep-global-agents` 保留。

## 5.0.0

- 将 Workspace 插件从三个工具型 Skill 升级为十个 Skill 的大型工程多Agent控制平面。
- 新增 Master、Planning、Developer、Review、Test、Merge、Document 七角色输入、输出、权限和禁止操作契约。
- 新增 PROJECT_STATE、CURRENT_CONTEXT、Task ID状态机、checkpoint、多项目隔离与Git common-dir文件锁。
- 建立B/S浏览器前端+服务端、C/S客户端+服务端及共享契约/数据通道，覆盖Unity与NodeTS并行冲突保护。
- 实施main/release/develop及feature/bugfix/hotfix/release分支治理、Conventional Commit和合并门禁。
- 新增需求→实现→审核→测试→截图/日志→文档→状态的Feature Closed Loop。
- 新增全局自动应用规则模板和插件应用回执，明确展示实际启用的插件、Skill、原因和项目。

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
