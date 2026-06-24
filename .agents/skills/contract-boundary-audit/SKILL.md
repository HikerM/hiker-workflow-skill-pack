---
name: contract-boundary-audit
description: Audit API contracts and implementation boundaries for Hiker systems. Use when the user mentions OpenAPI, DTO, request/response schema, provider adapter, frontend/backend boundary, seed data, DB parity, provider payload, result response, resource_transfer, or whether a UI bypasses the unified execution chain.
---

# Contract Boundary Audit

version: 0.2.0
owner: Hiker

## Use When

Use for API/DTO/OpenAPI/provider/front-end boundary checks, especially when contract drift may break quote/create/result or UI workflows.

## Do Not Use When

Do not use for broad architecture pricing or timeline questions; use `agent-architecture-consultant`.

## Goal

Verify that contracts, DTOs, adapters, seed data, DB fields, provider payloads, and frontend dependencies agree at the boundary.

## Required Inputs

- OpenAPI or route definitions.
- DTO/request/response types.
- Frontend call sites and consumed fields.
- Provider adapter payload mapping.
- Seed data, DB schema, migrations, and example responses when available.

## Required Process

1. Identify the canonical contract artifact: OpenAPI, route schema, DTO, or generated client.
2. Compare request fields from UI -> API -> service -> provider adapter.
3. Compare response fields from provider/result normalization -> API -> frontend.
4. Check seed and DB parity: enum values, IDs, status lifecycle, resource references, storage URLs.
5. Check boundary rules: frontend must not bypass unified chain, provider-specific fields must not leak unless explicitly part of contract.
6. Produce a field-level mismatch table and recommended fix owner.

## Evidence Rules

- Strong evidence is a specific file/line, schema excerpt, generated type, API response, or test output.
- Weak evidence is a naming assumption or natural-language summary.
- Contract acceptance requires at least one executable or inspectable artifact, not just agreement by wording.

## Output Format

```text
契约结论：
权威契约：
字段对齐：
边界问题：
证据：
修复建议：
可复制给 Codex 的消息：
...
```

## Hard Rules

- Do not let frontend call provider-specific endpoints when unified execution is required.
- Do not add fields to one side only.
- Do not rename statuses/enums without migration and compatibility plan.
- Do not treat seed data as production truth.

## Failure Modes

- OpenAPI says one shape while DTO returns another.
- Provider adapter accepts fields that UI never sends.
- `preview_url`, asset, billing, or resource fields exist in DB but not result API.
- Mock response hides missing normalization.

## Example User Inputs

- "检查 DTO/OpenAPI 和前端字段有没有对齐。"
- "provider adapter 的 payload 会不会漏字段？"
- "result API 能不能支撑前端预览？"

## Example Final Output

```text
契约结论：Hold，result response 缺少前端预览依赖字段。
权威契约：OpenAPI `POST /execution/result`。
字段对齐：`asset.preview_url` 在前端需要，但 DTO 未声明；DB 有 storage key，normalizer 未映射。
边界问题：前端不应直接拼 storage URL，应由 result API 返回。
修复建议：更新 DTO/OpenAPI、normalizer、contract smoke，并补 seed parity。
```
