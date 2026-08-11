# CHANGELOG

## 5.3.0

- 新增唯一隐式入口 `ai-engineering-router`，路由阶段只检查有限工程标记并返回最多两个需要读取的原子Skill。
- 新增 `greenfield-project-planning` 与 `requirements_fusion.py`：稳定 Requirement ID、revision history、冲突、未知项、验收活动切片和技术决策Checkpoint。
- 其余31个原子Skill全部关闭隐式调用但保留手动可见；验证器强制该性能策略，防止版本回退。
- 全局AGENTS模板改为短路由契约，不再预列举全部原子Skill。
- Enterprise Skill数量由30个增至32个。

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
- 增加单技术族、单阶段、按需参考和不重复扫仓的性能预算；全局规则在三组能力之间只选择一个主路由。
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
