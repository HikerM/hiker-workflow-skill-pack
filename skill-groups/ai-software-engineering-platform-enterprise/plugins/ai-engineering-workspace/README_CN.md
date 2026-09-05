# 工作区与多会话协作

<!-- engineering-current-facts: version=5.19.0; plugins=5; skills=42; tests=487 -->

本插件属于 Hiker Engineering Capability System（Hiker 工程能力系统），为大型软件工程提供按需协作约束，共 12 个 Skill；它不是独立 Agent Runtime。桌面任务、Agent Runtime 与工具调用由 ChatGPT Desktop / Codex 宿主提供，本插件只提供任务、Git、Worktree、锁、证据与发布状态的能力和确定性门禁。

## 控制平面

- **大型工程总控**：总入口，按实际工作协调 CONTROL、WRITE、ASSURE 责任、状态、Git、锁、验收和发布；责任本身不创建 Agent。
- **项目状态管理**：维护有界 PROJECT_STATE、CURRENT_CONTEXT、CHANGELOG、ARCHITECTURE 与机器状态；与01号有界记忆协作，避免多会话持续增重。
- **任务生命周期管理**：管理 Task ID 和 Created → Released 状态机及最小变更契约。
- **多项目组合管理**：隔离多个 Git 仓库的项目身份和上下文。
- **插件应用回执**：仅用一行中文名称展示本次实际启用的插件和 Skill。

## 执行与门禁

- **任务分流与会话规划**：按真实需求拆分浏览器端、客户端、共享后端服务、契约/数据、审核、测试、文档和合并通道。
- **多工作目录任务管理**：执行受保护分支和 Worktree 规则。
- **多智能体文件锁**：保护 Unity Scene/Prefab/ProjectSettings/meta、核心服务、migration 和 API Contract。
- **功能验收闭环**：需求、实现、测试、截图/日志、文档和状态闭环。
- **代码所有权与合并控制**：检查分支流向、Conventional Commit、冲突、锁、架构守卫和合并证据。

按需会话池由 CONTROL 独占规划：默认新建 Agent 数为 0，实现/修复优先复用当前会话或稳定 writer，确需独立保证时复用 assurance。项目终态时，CONTROL 请求宿主归档并在宿主动作完成后调用本地探针验证运行时释放。API 错误、超时、待启动、脏 Worktree 或回收未完成都不能触发替代会话。

普通局部任务只写最小范围、不变量和测试，不要求维护全量架构配置；公共表面、受保护模块或影响半径高的变更才渐进启用消费者登记、模块规则和工程图谱。

Master、Planning、Developer、Review、Test、Merge、Document 仅是旧 API 的兼容职责标签，并分别折叠到 CONTROL、WRITE、ASSURE；它们不是执行实体、会话槽或创建额外 Agent 的理由。只有真实独立性、写冲突、资源隔离、保证独立性或运行时要求才允许增加执行实体。

全局自动应用模板位于 `templates/GLOBAL_AGENTS_AI_ENGINEERING.md`。它要求会话开头显示轻量路由，并在真实加载、阶段切换或上下文恢复时显示一次去重中文应用回执；不会扩大 push、merge、部署或生产写入权限。

桌面任务归档与本地工具运行时释放由 ChatGPT Desktop / Codex 宿主显式执行；本地脚本只验证并记录结果。进程探针、Worktree 状态或本地会话池不能替代宿主动作，也不得伪造桌面任务已归档。
