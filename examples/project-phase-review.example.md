# Project Phase Review Example

## User Prompt

```text
请用 project-phase-review 判断 P2.8 能不能进入 P2.9。

当前证据：
- build passed
- source audit 完成
- happy path smoke 通过
- 未跑异常输入、并发、billing release
```

## Expected Shape

```text
阶段结论：Hold。
阶段目标：P2.8 应证明统一链路真实可用，而不是只证明代码能编译。
已完成：build、source audit、happy path smoke。
证据：中等。
缺口：异常输入、并发、billing release、queue retry、result API 真实响应。
是否进入下一阶段：不建议。
进入条件：补齐最小真实联调和失败路径证据。
```
