---
name: workspace-task-router
description: 将 ChatGPT 已完成的项目架构语义判断校验并展开为B/S浏览器前端与服务端、C/S客户端与服务端、契约数据、审核、测试、文档、合并和发布控制通道。用于大型需求分流和多Agent执行规划，不按关键词替代 ChatGPT 选择。
---

# 工作区任务路由

## 轻量入口原则

- ChatGPT 先理解完整需求、否定约束和当前工程证据，提出 `architecture` 与 `client_families`；脚本只校验合法值并展开执行通道，不按请求关键词替代模型选择。
- `.ai/context/tech-stack.json` 只作为轻量证据快照，不为路由重复扫描全仓，也不能覆盖用户本轮明确目标。
- 单次只启用当前阶段、当前技术族和当前风险所需的最小 Skill 集；不同时预加载设计、实现、审核、测试、合并和发布全部能力。
- B/S只加载Web当前阶段能力；C/S先调用 `cs-client-router`，再只加载命中的客户端技术族能力；后端与契约保持独立通道。
- 纯后端请求先调用「服务端技术路由」识别真实语言、框架、运行时、包管理器和版本，再按阶段只加载「接口与事件契约设计」「服务端功能实现」「数据库迁移治理」或「服务端质量审核」之一；工作区路由不得自行承担服务端实现。
- 简单、单文件、低风险任务可由当前会话顺序完成，不强制创建多Agent、Worktree、图谱或完整项目治理；提案用 `risk_class=local` 且确认 `contract_change=false` 时跳过契约通道，并把文档、合并、发布通道标为按需。
- 提案缺失、非法或自相矛盾时返回 `REJECTED`，由 ChatGPT 根据诊断重新选择；脚本不得自动猜测或替换。
- 输出实际启用、未启用及原因，防止把“已安装”误报为“已应用”。

先读取 `PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、`CHANGELOG.md`、`ARCHITECTURE.md` 和 Git 状态，再运行：

```bash
python <plugin-root>/scripts/task_router.py --root . --request "需求文本" --proposal-json '{"architecture":"hybrid","client_families":["unity"]}'
```

## 路由规则

- 合法架构为 `bs`、`cs`、`backend`、`hybrid`、`unknown`；客户端技术族必须来自当前支持目录。`cs`/`hybrid` 未能确认技术族时写 `unspecified`，不得猜成 Unity。

- B/S 必须同时存在 `bs-frontend`、共享 `backend-service` 与 `contract-data`，不能把后台页面误当成完整系统。
- C/S 必须同时存在 `cs-client`、共享 `backend-service` 与 `contract-data`，Unity/桌面客户端不能吞掉服务端工作。
- 混合项目同时保留浏览器前端与客户端，但只建立一个共享后端通道，防止两个 Agent 重复修改同一服务；共享契约必须串行定版。
- 后端实现先执行变更契约和公共接口影响检查；Service、数据库迁移、API/事件契约、鉴权和队列消费者不得由多个写通道并行修改。`backend-service` 通道必须记录实际加载的服务端原子能力。
- 写入通道一任务一分支；修改同一文件或高风险资产时串行并获取文件锁。
- 默认 `parallel_mode=auto-safe`。ChatGPT 根据文件/模块所有权、共享契约、Migration、核心Service、Unity受保护资产、测试环境和当前预算自动选择最多两个独立写通道；用户无需重复输入“并行”。任一共享写表面未知或冲突时串行。
- 大型纯后端、多仓库或同一技术表面存在独立模块时，ChatGPT 可提出最多8个 `implementation_lanes`；每个通道必须声明稳定ID、技术表面、仓库键和1至32个真实写范围。脚本验证父子路径重叠并生成 `serial_with`，不会按固定技术栈名称替代模型拆分。
- `dispatch_guard.py` 只激活最多两个无重叠通道；与活动 writer 的写范围冲突时返回 `BLOCK_SCOPE_CONFLICT`，不能用剩余并行额度绕开串行门禁。
- `review`、`testing` 必须由独立角色执行；`merge` 必须等待验收闭环通过。

输出 `.ai/workspace/task-map.json`。安全独立通道可自动调度；不能证明独立时保持串行。自动并行不扩大创建新桌面任务、Worktree、合并或发布权限。
