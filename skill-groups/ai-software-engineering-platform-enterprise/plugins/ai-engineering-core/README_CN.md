# 01 AI工程核心

本插件是其他插件的前置底座。首次接管项目时运行“项目智能初始化”，后续领域 Skill 只读取 `.ai/context/`，不重复扫描整个仓库。

状态与事件脚本（由 Skill 或外部编排显式调用，当前 manifest 不自动注册 Hook）：

- SessionStart：恢复当前任务、活动上下文和锁定决策；
- UserPromptSubmit：识别暂停、继续、调整、状态和回滚请求；
- PreCompact 协议：调用时保存检查点；
- Stop：记录本轮结果，不强制继续；
- SessionEnd：归档会话结束事件。
