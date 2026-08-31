---
name: workspace-task-router
description: 校验 ChatGPT 基于当前 Project Facts 提出的有界写范围、共享权威和执行责任，在大型或确需隔离的任务中生成安全通道；不从架构标签或关键词推导固定 Agent、前后端拓扑或完整生命周期。
---

# 工作区任务路由

## 轻量入口原则

- ChatGPT 负责理解需求，并根据当前 Project Fact Plane、变更范围、依赖和任务提出实际 `implementation_lanes`；脚本只验证边界与冲突。
- `architecture` 仅是粗分类，不创建 frontend、backend、client 或 contract 通道；未知架构也可使用真实 Surface。
- `client_families` 是工程证据元数据，不等于执行拓扑，不得因此创建 Agent、Session 或 Worktree。
- 简单低风险任务允许当前会话完成理解、修改和最小验证，不强制额外 Agent、Worktree 或完整生命周期。
- 提案缺失、非法、事实指纹过期或范围冲突时返回 `REJECTED`；脚本不得根据请求关键词猜测替代提案。
- 单次只加载当前阶段最多两个相关 Skill，不预载完整能力链。

需要绑定事实时，将已有 Project Fact Plane 作为有界输入：

```bash
python <plugin-root>/scripts/task_router.py --root . --request "需求文本" --project-facts-file <fact-plane.json> --proposal-json '{"architecture":"unknown","client_families":[],"project_fact_fingerprint":"<sha256>","implementation_lanes":[{"id":"orders","surface":"order-service","write_scope":["src/orders"],"authority_ids":["API:ORDERS"]}]}'
```

未提供 `--project-facts-file` 时只读取现有 `.ai/context/tech-stack.json` 兼容证据，不扫描源码或 Git 历史。

## 路由规则

- 每个实现通道声明稳定 ID、实际 Surface、仓库键和 1–32 个有界写范围；可选 `authority_ids` 标识共享 API、Schema、Contract 或其他单写权威。
- 写范围重叠产生 `BLOCK_SCOPE_CONFLICT`；不同文件共享权威产生 `BLOCK_AUTHORITY_CONFLICT`。阻断理由来自真实所有权，而不是固定 frontend/backend 流程。
- 两个真实独立范围可由模型提议并行，Runtime 验证后最多激活两个写绑定；不能证明独立时串行。
- `contract_change=true` 才生成契约责任；`false` 或未声明不得创建虚假契约通道。
- Assurance 是否独立由风险事实或模型提案决定。结构、高共享或发布风险不得降低独立性；普通任务不机械创建独立 ASSURE 执行实体。
- `Responsibility != Agent != Provider Session != Worktree != Task`。历史角色名只作为兼容职责标签。
- 自动路由不扩大创建桌面任务、Worktree、合并、发布或其他外部写入权限。

输出 `.ai/workspace/task-map.json`，只保存有界事实回执、责任、冲突和绑定策略，不保存完整 Prompt、聊天或源码。
