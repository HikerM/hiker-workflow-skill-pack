---
name: nodets-execution-pipeline-guardrails
description: Guard Hiker NodeTs AI comic/drama execution pipeline changes. Use when working on quote -> create -> result unified chain, canonical intent, provider adapters, resource_transfer, result normalization, billing reservation/settlement/release, worker queues, polling/callbacks, assets/storage/preview_url, seed/DB parity, or preventing frontend bypass of the unified execution chain.
---

# NodeTs Execution Pipeline Guardrails

version: 0.2.0
owner: Hiker

## Use When

Use for NodeTs / AI 漫剧平台 / 统一画布执行接口 work involving quote, create, result, provider adapters, resource transfer, billing, workers, assets, or result preview.

## Do Not Use When

Do not use for unrelated frontend styling, generic Laravel/Vue architecture, or design artifact tasks.

## Goal

Keep the unified execution chain contract-safe, evidence-backed, and free of frontend or provider-specific bypasses.

## Required Inputs

- Current branch, HEAD, and `git status`.
- Target workflow: quote, create, result, callback, poll, worker, asset preview, billing.
- Relevant OpenAPI/DTO, DB schema/seed, provider adapter, queue/worker, and frontend call sites.
- Allowed test environment and provider/DB/billing permissions.

## Required Process

1. Protect scope first: report branch, HEAD, status, and diff summary.
2. Identify canonical intent and execution lifecycle: quote -> create -> worker/provider -> resource_transfer -> result normalization -> asset/storage/preview_url -> billing settlement/release.
3. Verify contract artifacts: OpenAPI, DTO, request/response examples, frontend consumed fields.
4. Verify backend boundaries: provider adapter payload, result normalizer, DB/seed parity, status enum lifecycle, idempotency.
5. Verify async behavior: worker queue, poll/callback, retry, timeout, duplicate callback, failed provider.
6. Verify billing: reservation, settlement, release, and failure rollback.
7. Run safe smoke/contract/source audit commands; use real provider only with explicit authorization.
8. Report evidence and a copyable next Codex message.

## Evidence Rules

- Strong evidence includes branch/HEAD/status, diff, smoke command output, DB parity check, worker queue trace, billing state, provider payload sample, and result API response.
- Interface-shape mock proves only shape, not provider behavior.
- Frontend screenshots do not prove backend chain execution.

## Output Format

```text
链路结论：
保护信息：
统一链路检查：
契约/DTO：
DB/Seed：
Worker/Queue：
Billing：
Provider/Mock 边界：
证据：
缺口：
可复制给 Codex 的消息：
...
```

## Hard Rules

- Frontend must not bypass quote -> create -> result.
- Do not let provider-specific payload leak into canonical DTO unless explicitly modeled.
- Do not settle billing without verified execution success; release reservation on failure.
- Do not mutate DB, run real provider calls, restart services, push/merge, or rewrite history without permission.

## Failure Modes

- Result API returns success before worker/provider completion.
- `resource_transfer` is created but not attached to result normalization.
- `preview_url` works only in mock and not storage-backed result.
- Billing reservation remains locked after failure.
- Seed data diverges from DB enum/status lifecycle.

## Example User Inputs

- "检查 quote -> create -> result 是否统一。"
- "P2.8 统一画布执行接口真实联调。"
- "不要让前端绕过 provider adapter。"

## Example Final Output

```text
链路结论：Hold，统一链路实现存在，但 result 证据不足。
保护信息：需要先补 branch、HEAD、git status、diff summary。
统一链路检查：quote/create 有入口，worker/result normalization 未见输出证据。
Billing：reservation 有声明，settlement/release 未验证。
Provider/Mock 边界：当前只能证明接口形状 mock。

可复制给 Codex 的消息：
请在不扩范围的前提下补证据：branch、HEAD、git status、diff summary、quote/create/result smoke 输出、DB parity、worker queue trace、billing reservation/settlement/release、provider payload 或明确 mock 边界、result API response。
```
