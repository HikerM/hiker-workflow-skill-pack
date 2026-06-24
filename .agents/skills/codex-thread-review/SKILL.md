---
name: codex-thread-review
description: Review pasted Codex App thread results for Hiker-style engineering governance. Use when the user pastes a Codex thread, execution summary, PR-like result, terminal output, or asks whether a Codex run really completed the task, stayed within boundaries, produced real evidence, and what message to send next.
---

# Codex Thread Review

version: 0.2.0
owner: Hiker

## Use When

Use when the user asks to复核 Codex 线程结果、执行摘要、测试输出、改动说明、阶段推进结论或下一条可复制线程消息。

## Do Not Use When

Do not use for direct implementation tasks where no thread/result is being reviewed. Do not use to praise work without checking evidence.

## Goal

Determine what was actually done, whether it stayed inside the requested boundary, whether the evidence is strong enough, what is missing, and what exact message the user should send back to Codex.

## Required Inputs

- Pasted Codex thread content or summary.
- User's original task if available.
- Any referenced file paths, commands, test logs, screenshots, commits, or PR links.

## Required Process

1. Extract the claimed work: files changed, commands run, tests run, decisions made.
2. Compare against the requested boundary: scope, forbidden actions, data access, install/write behavior, provider/DB/service side effects.
3. Classify evidence:
   - Strong: command output, test logs, smoke result, screenshots, diff, commit hash, API response, DB/query proof.
   - Medium: precise file list plus plausible command names but no output.
   - Weak: "已完成", narrative summary, unverified claims, screenshots without state context.
4. Identify missing proof, unresolved risks, or boundary violations.
5. Give a conclusion: pass, conditional pass, needs follow-up, or reject.
6. Produce a copyable Codex follow-up message.

## Evidence Rules

- Treat "I changed it" as a claim, not evidence.
- Do not accept tests unless the command, target, and result are visible.
- Separate smoke, contract, unit, integration, build, source audit, and manual visual evidence.
- If the thread references files that are not shown, state that verification is limited.

## Output Format

```text
结论：
做了什么：
边界检查：
证据等级：
缺口/风险：
下一步：

可复制给 Codex 的消息：
...
```

## Hard Rules

- Do not invent missing logs or test results.
- Do not let "编译通过" substitute for real integration evidence.
- Do not ignore unauthorized DB writes, service restarts, provider calls, push/merge, force push, or destructive git commands.
- Always include the copyable follow-up message unless the user explicitly does not need it.

## Failure Modes

- Summarizing the thread without judging whether it is done.
- Confusing changed files with validated behavior.
- Missing boundary drift such as extra refactors, real provider calls, or overwritten project rules.

## Example User Inputs

- "复核这段 Codex 线程结果，能不能算完成？"
- "这是 P2.7 的执行摘要，帮我判断下一步。"
- "给我一段可以继续发给 Codex 的话。"

## Example Final Output

```text
结论：条件通过。代码改动方向匹配任务，但证据还停在 build + happy path smoke，缺少异常输入和接口契约输出。
做了什么：线程声称修改了 quote/create/result 链路和前端字段映射。
边界检查：未看到 DB 写入、provider 真调用、push/merge 证据；边界暂未发现越界。
证据等级：中等。
缺口/风险：缺少 contract response、worker 队列结果、billing release 场景。
下一步：要求补一轮最小真实联调。

可复制给 Codex 的消息：
请不要继续扩范围。基于当前改动补充证据：1. git status 和 diff summary；2. quote -> create -> result smoke 命令及输出；3. 一个异常输入用例；4. result API 实际响应；5. 如果没有真 provider，请明确是接口形状 mock。
```
