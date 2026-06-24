---
name: project-phase-review
description: Review Hiker P2.x or staged project progress and decide whether a phase is complete enough to move forward. Use when the user mentions P2.6, P2.7, P2.8, P2.9, phase acceptance, stage gate, milestone review, whether written work equals done, or whether smoke/evidence/commit/push/merge is sufficient.
---

# Project Phase Review

version: 0.2.0
owner: Hiker

## Use When

Use for staged project推进, especially P2.x phase acceptance, when the user needs a go/no-go decision.

## Do Not Use When

Do not use for a single pasted thread unless the question is specifically about phase acceptance. Use `codex-thread-review` first for thread-only reviews.

## Goal

Judge whether the phase objective is actually complete, what proof exists, what remains, and whether the project can safely enter the next phase.

## Required Inputs

- Phase name and stated objective.
- Scope boundary and known non-goals.
- Evidence: diffs, build/test logs, smoke results, contract artifacts, screenshots, commit/PR state.

## Required Process

1. Restate the phase objective in testable terms.
2. Separate implementation, smoke, evidence, commit, push, PR, and merge states.
3. Check boundary: no unrelated refactor, no hidden provider/DB/service side effects, no skipped contract.
4. Check coverage: happy path, abnormal input, chaotic data, concurrency/performance if relevant, backward compatibility.
5. Determine status:
   - Pass: objective met with strong evidence and no blocking boundary issue.
   - Conditional pass: core works, evidence gap is small and bounded.
   - Hold: key proof or behavior missing.
   - Reject: objective not met or boundary violated.
6. Provide next-phase entry conditions and a copyable Codex message.

## Evidence Rules

- "写完" is not done.
- Build success is not phase completion.
- A commit hash proves a snapshot, not behavior.
- Push/merge state must be reported separately from implementation state.
- Use real integration evidence when the phase touches API, DB, queue, provider, billing, or UI workflow.

## Output Format

```text
阶段结论：
阶段目标：
已完成：
证据：
缺口：
是否进入下一阶段：
进入条件：
可复制给 Codex 的消息：
...
```

## Hard Rules

- Do not approve next phase without explicit evidence.
- Do not collapse smoke, contract, build, and source audit into one vague "测试通过".
- Do not accept real-provider, DB mutation, push, merge, or deployment unless authorized.

## Failure Modes

- Treating a long change list as phase completion.
- Ignoring missing rollback, billing release, queue failure, or contract response evidence.
- Letting a phase expand into new scope without naming it.

## Example User Inputs

- "P2.8 这个线程能不能进 P2.9？"
- "帮我验收这一阶段，不要只看他说完成。"
- "这轮只有 build 和 smoke，够不够？"

## Example Final Output

```text
阶段结论：Hold。
阶段目标：P2.8 要证明统一执行链路可真实跑通，而不只是完成代码改动。
已完成：实现和基础 build 已有证据。
证据：build 输出存在；缺少 quote/create/result 端到端响应、DB parity、worker 队列、billing reservation/release。
是否进入下一阶段：暂不建议。
进入条件：补齐最小真实联调和异常输入 smoke。

可复制给 Codex 的消息：
请停在当前范围，不要进入 P2.9。补充 P2.8 验收证据：git status、diff summary、quote/create/result 端到端命令和响应、DB parity、worker 队列状态、billing reservation/settlement/release 三态结果。
```
