---
name: plugin-application-receipt
description: 在Codex或ChatGPT桌面任务中展示本次自动应用的插件、Skill、触发原因、项目身份和治理状态，形成用户可见的应用回执。用于全局插件透明度、排查未触发或避免多个工程插件混用。
---

# 插件应用回执

使用任何个人工程插件时，在首次实质动作前用简短中文显示：

```text
插件应用回执
- 插件：04 工作区与多会话协作
- Skill：multi-agent-project-governance, task-lifecycle-manager
- 原因：大型软件需求，需要任务状态与Git门禁
- 项目：PROJECT-A / D:\repos\project-a
- 模式：自动治理；未启用并行Agent
```

任务结束时列出实际使用的插件/Skill、生成的状态或证据文件、未触发的相关插件及原因。不得声称使用未加载的 Skill，也不得把“已安装”写成“本次已应用”。若项目身份未知，明确显示 `未初始化`，不要猜测。
