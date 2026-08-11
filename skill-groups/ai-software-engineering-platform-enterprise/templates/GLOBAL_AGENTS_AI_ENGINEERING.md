<!-- ai-engineering-global-governance start -->

# AI 软件工程插件全局自动应用规则

- 遇到软件工程项目初始化、需求实现、修复、重构、审核、测试、合并或发布任务时，自动选择已安装的 `ai-engineering-core`、`ai-engineering-web`、`ai-engineering-unity`、`ai-engineering-workspace`、`ai-engineering-quality` 中最小必要 Skill 集，无需用户逐个点选。
- 三组仓库能力按意图选择一个主路由：工程复核/证据/契约守护使用 `hiker-workflow-router`；长期软件开发使用 `workspace-task-router`；已授权桌面软件等价重建使用 `desktop-app-reconstruction-zh`。不得因三组都已安装而同时加载三组。
- 大型、跨模块、长期、B/S、C/S、Unity、NodeTS、多仓库、多分支或多 Agent 任务，优先应用 `multi-agent-project-governance`；简单解释或纯问答不得强行初始化治理文件。
- B/S 项目必须同时识别浏览器前端与服务端；C/S 项目必须同时识别客户端与服务端；存在共享 API、数据库或协议时增加契约与数据通道。
- C/S 客户端先使用 `cs-client-router` 从统一项目状态识别语言、运行时、框架、SDK、构建工具及版本证据，再按设计/实现/审核阶段选择一个通用或Unity专项Skill。缺少精确版本必须显示缺口，不得写死技术或默认最新版。
- 性能预算：路由阶段不扫描全仓；一次只读取当前项目、技术族、阶段和风险直接需要的状态/参考/文件；不预加载未选Skill，不默认建立图谱、运行全量测试或创建多Agent/Worktree。
- 首次实质动作前展示“插件应用回执”：插件显示名、Skill 名、触发原因、项目 ID/仓库根、执行模式。只列本次实际应用项，不把“已安装”冒充“已应用”。
- 执行结束时再次汇总实际使用的插件/Skill、生成的状态或证据文件、未触发的相关插件及原因。
- 自动应用不扩大权限：不得因插件存在而自动 push、merge、部署、发布、写生产数据、强制删除 Worktree 或修改 main。按用户明确授权和各 Skill 门禁执行。
- 当用户暂停、调整、插入需求或恢复时，保留任务状态与工作现场，并生成 checkpoint；不得用删除目录或回退提交代替暂停。
- 长期、多会话、多Agent或上下文压缩任务，04号使用 `multi-agent-project-governance` 管理Task/会话/Worktree/交接，01号同时使用 `bounded-context-memory` 与 `context-recovery` 管理有界持久记忆；不得把完整聊天历史重复注入新会话。
- 压缩或交接前先将新增需求、关键决定、完成项、待办、风险和证据写入正式状态；当前工作集、会话注入、每节条目和checkpoint数量必须遵守 `.ai/governance/context-retention.json` 上限。
- 新会话恢复必须显示“有界记忆回执”：活动工作集字符数/上限、保留/已收敛checkpoint数、当前Task、事实源和恢复下一步；原始聊天只作线索。

回执格式：

```text
插件应用回执
- 插件：04 工作区与多会话协作
- Skill：multi-agent-project-governance, task-lifecycle-manager
- 原因：大型跨模块工程，需要任务状态与Git门禁
- 项目：PROJECT-A / D:\repos\project-a（未初始化时明确标注）
- 模式：自动治理；串行执行或用户已授权的多Agent并行
```

<!-- ai-engineering-global-governance end -->
