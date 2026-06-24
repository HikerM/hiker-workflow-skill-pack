# NodeTs Execution Pipeline Example

## User Prompt

```text
请用 nodets-execution-pipeline-guardrails 检查 quote -> create -> result 是否走统一链路。重点看 canonical intent、provider adapter、resource_transfer、result normalization、billing、worker queue、preview_url。
```

## Expected Shape

```text
链路结论：先 Hold，等证据补齐。
保护信息：需要 branch、HEAD、git status、diff summary。
统一链路检查：quote/create/result 需要同一 canonical intent 和 execution id。
契约/DTO：OpenAPI、DTO、前端字段、provider payload、result response 必须对齐。
DB/Seed：检查 execution、resource_transfer、asset/storage、status enum parity。
Worker/Queue：检查 poll/callback、retry、timeout、duplicate callback。
Billing：检查 reservation、settlement、release。
Provider/Mock 边界：明确真 provider 或接口形状 mock。
证据：smoke 命令、DB parity、queue trace、billing state、result API response。
```
