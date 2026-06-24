# Codex Thread Review Example

## User Prompt

```text
请用 codex-thread-review 复核下面的 Codex 线程结果。判断是否完成、证据是否真实、有没有越界，并给我一段可复制给 Codex 的下一步消息。

线程结果：
- 修改了 execution.ts 和 result.ts
- 运行 npm run build 通过
- 说 quote/create/result 已完成
```

## Expected Shape

```text
结论：条件不通过或 Hold。
做了什么：只看到代码修改和 build。
边界检查：未看到 provider/DB/billing/push 越界证据，但也未看到完整状态。
证据等级：弱到中等。
缺口/风险：缺少 quote/create/result smoke、result API response、DB parity、worker queue、billing release。
下一步：补最小真实联调。

可复制给 Codex 的消息：
请不要扩范围。补充 branch、HEAD、git status、diff summary、quote/create/result smoke 输出、result API 响应、DB parity、worker queue、billing reservation/settlement/release，并明确 provider 是真实调用还是接口形状 mock。
```
