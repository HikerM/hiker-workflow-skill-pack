<!-- ai-engineering-global-governance start -->

# AI 工程三组轻量自动路由

- 软件工程开发、设计、测试、Git、多会话或发布任务只自动进入 `ai-engineering-router`；工程专项复核进入 `hiker-workflow-router`；已授权桌面软件等价重建进入 `desktop-app-reconstruction-zh`。一次只选一个主路由，原子 Skill 由主路由按需读取。
- 路由阶段不扫描全仓、不预加载原子 Skill、不默认建图、跑全量测试或创建 Worktree/Agent；每轮最多加载两个直接相关原子 Skill。
- 从零开发必须先融合带稳定 ID 的需求、冲突、未知项和验收条件，再比较最多三个技术候选；平台、架构、部署、数据、安全或核心技术栈变化需人工 Checkpoint，锁定前不得批量生成正式代码。
- 现有 B/S 与 C/S 项目按工程证据识别真实前后端技术和版本；缺失证据标记 unknown，不默认最新版本，不把 Unity 当成所有 C/S。
- 首次实质动作前显示“插件应用回执”：主路由、实际加载 Skill、原因、项目/仓库、模式；结束时只汇总实际应用项。
- 多会话只注入当前有界工作集；完整需求、任务、决定和证据写入 `.ai`，压缩或交接先落盘并生成 Checkpoint，不重复注入完整聊天历史。
- 自动应用不扩大权限：未经明确授权不得 push、merge、部署、发布、写生产数据、强制清理 Worktree 或直接修改 main。
- 用户暂停、调整、插入需求或恢复时先保存状态，再修订当前计划；不得用回退提交代替暂停。

<!-- ai-engineering-global-governance end -->
