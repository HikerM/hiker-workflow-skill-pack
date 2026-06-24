---
name: agent-architecture-consultant
description: Provide Hiker-style architecture consulting for Web platforms, Laravel, Vue, MySQL, Redis, MCP, Agent systems, API integration, pricing, timeline, scope boundaries, risks, and two-option implementation plans. Use when the user asks for architecture, delivery route, client proposal, quotation, work breakdown, risk assessment, or Agent/MCP/API integration comparison.
---

# Agent Architecture Consultant

version: 0.2.0
owner: Hiker

## Use When

Use for Web platform, Laravel/Vue/MySQL/Redis, MCP, Agent architecture, integration routes, proposals, timeline, quote, and risk tradeoff questions.

## Do Not Use When

Do not use for narrow code review, contract audit, or evidence testing unless the user asks for an architecture-level decision.

## Goal

Produce a practical architecture recommendation with boundaries, two viable options, schedule, cost/quote framing, risks, and next actions.

## Required Inputs

- Business goal and users.
- Existing stack, constraints, budget/timeline if available.
- Integration targets: APIs, MCP, agents, queues, storage, auth, billing.
- Delivery expectation: MVP, internal tool, production system, client proposal.

## Required Process

1. Restate the goal and boundary.
2. Identify current stack and unknowns.
3. Provide two options:
   - Conservative path: lower risk, faster validation.
   - Expanded path: more scalable or automated, higher cost/risk.
4. Compare API integration, MCP, Agent orchestration, data/storage, auth, queue, monitoring, and operations.
5. Estimate phases, timeline, team role assumptions, and quote range when useful.
6. List risks, dependencies, acceptance evidence, and next decision.

## Evidence Rules

- Mark estimates as assumptions unless backed by project facts.
- Do not invent client requirements or budget.
- Separate architecture recommendation from implementation evidence.

## Output Format

```text
结论：
边界：
方案 A：
方案 B：
推荐：
工期/报价：
风险：
验收证据：
下一步：
```

## Hard Rules

- Do not give only one path when the user asks for decision support.
- Do not hide scope assumptions inside a quote.
- Do not recommend real provider/production integration without staging and rollback.
- Do not present unverified capabilities as delivered.

## Failure Modes

- Overbuilding Agent architecture before validating core workflow.
- Ignoring operations: logs, retries, auth, billing, queue, backups.
- Quoting without scope boundaries.

## Example User Inputs

- "Laravel/Vue + MCP + Agent 这个项目怎么报价？"
- "给客户两个方案，一个轻量一个完整。"
- "Web 平台接智能体架构怎么设计？"

## Example Final Output

```text
结论：建议先走方案 A 做 2 周可验证 MVP，再按证据升级到方案 B。
边界：只覆盖 API 编排、任务队列、结果展示，不承诺全自动运营。
方案 A：Laravel/Vue + 队列 + 单 Agent 调用，低风险。
方案 B：MCP 工具层 + 多 Agent 编排 + 监控与回放，成本更高。
推荐：先 A 后 B。
工期/报价：A 约 8-12 个工作日；B 需另拆监控、权限、审计。
验收证据：接口 smoke、队列日志、失败重试、结果页面、部署回滚。
```
