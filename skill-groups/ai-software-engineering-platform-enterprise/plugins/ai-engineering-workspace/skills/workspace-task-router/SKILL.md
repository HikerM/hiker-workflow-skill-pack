---
name: workspace-task-router
description: 将大型需求按B/S浏览器前端与服务端、C/S客户端与服务端、契约数据、审核、测试、文档、合并和发布控制拆成可追踪通道，并选择主任务、Subagent或Git Worktree。用于大型需求分流和多Agent执行规划。
---

# 工作区任务路由

## 轻量入口原则

- 先从用户请求和 `.ai/context/tech-stack.json` 路由，不为路由重复扫描全仓。
- 单次只启用当前阶段、当前技术族和当前风险所需的最小 Skill 集；不同时预加载设计、实现、审核、测试、合并和发布全部能力。
- B/S只加载Web当前阶段能力；C/S先调用 `cs-client-router`，再只加载命中的客户端技术族能力；后端与契约保持独立通道。
- 纯后端请求先调用「服务端技术路由」识别真实语言、框架、运行时、包管理器和版本，再按阶段只加载「接口与事件契约设计」「服务端功能实现」「数据库迁移治理」或「服务端质量审核」之一；工作区路由不得自行承担服务端实现。
- 简单、单文件、低风险任务可由当前会话顺序完成，不强制创建多Agent、Worktree、图谱或完整项目治理。
- 输出实际启用、未启用及原因，防止把“已安装”误报为“已应用”。

先读取 `PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、`CHANGELOG.md`、`ARCHITECTURE.md` 和 Git 状态，再运行：

```bash
python <plugin-root>/scripts/task_router.py --root . --request "需求文本"
```

## 路由规则

- B/S 必须同时存在 `bs-frontend`、共享 `backend-service` 与 `contract-data`，不能把后台页面误当成完整系统。
- C/S 必须同时存在 `cs-client`、共享 `backend-service` 与 `contract-data`，Unity/桌面客户端不能吞掉服务端工作。
- 混合项目同时保留浏览器前端与客户端，但只建立一个共享后端通道，防止两个 Agent 重复修改同一服务；共享契约必须串行定版。
- 后端实现先执行变更契约和公共接口影响检查；Service、数据库迁移、API/事件契约、鉴权和队列消费者不得由多个写通道并行修改。`backend-service` 通道必须记录实际加载的服务端原子能力。
- 写入通道一任务一分支；修改同一文件或高风险资产时串行并获取文件锁。
- `review`、`testing` 必须由独立角色执行；`merge` 必须等待验收闭环通过。

输出 `.ai/workspace/task-map.json`。只有用户明确要求多 Agent 并行时才实际调度；否则生成可执行路由，由当前任务按依赖顺序推进。
