<!-- ai-engineering-global-governance start -->

# AI 软件工程插件全局自动应用规则

- 遇到软件工程项目初始化、需求实现、修复、重构、审核、测试、合并或发布任务时，自动选择已安装的 `ai-engineering-core`、`ai-engineering-web`、`ai-engineering-unity`、`ai-engineering-workspace`、`ai-engineering-quality` 中最小必要 Skill 集，无需用户逐个点选。
- 大型、跨模块、长期、B/S、C/S、Unity、NodeTS、多仓库、多分支或多 Agent 任务，优先应用 `multi-agent-project-governance`；简单解释或纯问答不得强行初始化治理文件。
- B/S 项目必须同时识别浏览器前端与服务端；C/S 项目必须同时识别客户端与服务端；存在共享 API、数据库或协议时增加契约与数据通道。
- 首次实质动作前展示“插件应用回执”：插件显示名、Skill 名、触发原因、项目 ID/仓库根、执行模式。只列本次实际应用项，不把“已安装”冒充“已应用”。
- 执行结束时再次汇总实际使用的插件/Skill、生成的状态或证据文件、未触发的相关插件及原因。
- 自动应用不扩大权限：不得因插件存在而自动 push、merge、部署、发布、写生产数据、强制删除 Worktree 或修改 main。按用户明确授权和各 Skill 门禁执行。
- 当用户暂停、调整、插入需求或恢复时，保留任务状态与工作现场，并生成 checkpoint；不得用删除目录或回退提交代替暂停。

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
