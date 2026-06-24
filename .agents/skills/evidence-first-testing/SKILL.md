---
name: evidence-first-testing
description: Plan and review evidence-first testing for Hiker workflows, including real integration tests, smoke tests, chaotic data, abnormal inputs, concurrency, performance, source audits, and distinguishing real data from mocks or weak claims. Use when the user asks for true evidence, smoke, contract, chaos testing, slow query, stability, semantic recognition, or test sufficiency.
---

# Evidence First Testing

version: 0.2.0
owner: Hiker

## Use When

Use when the user asks for真证据,真实联调, smoke, contract, chaotic data, abnormal input, concurrency, performance, stability, semantic recognition, or whether test evidence is strong.

## Do Not Use When

Do not use for ordinary unit-test authoring unless evidence classification or integration boundary matters.

## Goal

Design or evaluate tests by evidence strength, prioritizing reproducible proof over narrative claims.

## Required Inputs

- Feature or workflow under test.
- Allowed environment: local, test DB, mock provider, real provider, queue/worker availability.
- Safety limits: DB writes, billing, service restart, external calls, concurrency load.

## Required Process

1. Map the behavior to observable checkpoints: API response, DB row, queue job, provider payload, UI state, log, billing state.
2. Classify test type:
   - Source audit: code path exists.
   - Build/typecheck: compiles.
   - Unit: isolated logic.
   - Smoke: minimal runnable path.
   - Contract: request/response shape and DTO alignment.
   - Real integration: API + DB/queue/provider/storage behavior.
   - Chaos/abnormal: bad input, missing fields, partial provider failure, duplicated callbacks.
   - Concurrency/performance: race, idempotency, slow query, queue backlog.
3. Identify mock level: real data, fixture seed, interface-shape mock, happy-path stub, fabricated output.
4. Run or request the smallest safe evidence set.
5. Report commands, outputs, environment, and remaining gaps.

## Evidence Rules

- Strong evidence includes command, target, output, and observable state.
- A mock can prove contract shape but not provider behavior.
- Happy path smoke cannot prove stability.
- Performance claims need timing, volume, and environment.
- DB, queue, billing, and real provider actions require authorization or an isolated test environment.

## Output Format

```text
测试结论：
证据等级：
已验证：
未验证：
真实数据/Mock 边界：
建议补测：
可复制给 Codex 的消息：
...
```

## Hard Rules

- Do not call real providers, mutate production DB, restart services, or create billing side effects without explicit permission.
- Do not call generated logs "real" unless they came from an executed command or observable system.
- Always separate smoke from integration and contract evidence.

## Failure Modes

- Using only happy path seed data.
- Ignoring malformed input, duplicate request, timeout, callback replay, queue retry, or billing release.
- Reporting "稳定" without concurrency/performance evidence.

## Example User Inputs

- "给我混乱数据测试方案。"
- "这个 smoke 够不够算真证据？"
- "检查慢查询、并发和稳定性。"

## Example Final Output

```text
测试结论：当前证据只能证明 happy path smoke，不能证明真实联调。
证据等级：中等偏弱。
已验证：接口能返回成功结构。
未验证：DB parity、worker queue、provider payload、billing release、异常输入。
真实数据/Mock 边界：provider 是接口形状 mock，不代表真实供应商。
建议补测：增加缺字段、重复提交、provider timeout、queue retry、billing release 四组用例。
```
