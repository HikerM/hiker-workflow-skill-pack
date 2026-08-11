---
name: hiker-workflow-router
description: 作为Hiker工作流守护组的轻量入口，把工程复核、阶段验收、证据测试、契约、NodeTs链路、Unity安全、设计交付或架构咨询请求路由到最短匹配的一个原子Skill。用于不确定应选哪个Hiker Skill时；简单任务不启用重流程，也不预加载其他Skill内容。
---

# Hiker Workflow Router

version: 0.3.0
owner: Hiker

## Use When

Use this first when a task matches Hiker's engineering governance workflows but the correct specialized skill is not obvious.

## Do Not Use When

Do not route tiny factual questions, simple shell commands, or ordinary code edits that do not need Hiker review rules. Answer or implement directly.

## Goal

Pick the smallest sufficient workflow skill, state the routing decision briefly, then execute that workflow without adding unnecessary ceremony.

## Required Inputs

- User request and any pasted thread, diff, log, artifact, or project context.
- Current repository context when the task involves code or project files.

## Required Process

1. Classify the task by trigger:
   - Codex thread/result review -> `codex-thread-review`
   - P2.x or stage gate review -> `project-phase-review`
   - Real evidence, smoke, chaos, abnormal input, concurrency, performance -> `evidence-first-testing`
   - API contract, DTO, OpenAPI, seed, provider adapter, boundary -> `contract-boundary-audit`
   - NodeTs quote/create/result unified execution pipeline -> `nodets-execution-pipeline-guardrails`
   - Unity, Codex App, MCP, scene, prefab, script, asset -> `unity-codex-guardrails`
   - PPT, image, poster, SVG, PDF, Excel, batch export -> `design-output-discipline`
   - Laravel, Vue, MySQL, Redis, MCP, Agent architecture, quote, timeline -> `agent-architecture-consultant`
2. If more than one skill applies, choose the narrowest one first and mention any secondary checks.
3. For ambiguous complex work, ask one concise clarification only if the missing fact changes safety or scope.

## Performance Budget

- Classify from the user request and directly supplied artifacts first; do not scan the repository merely to choose a skill.
- Activate one primary atomic skill. Add a secondary skill only when a concrete unresolved gate requires it.
- Do not load the instructions, references, logs, or source scope of unselected skills.
- Prefer changed files and direct evidence over full-history or full-repository analysis unless the selected gate requires broader evidence.
- Routing itself must not run builds, tests, service calls, database actions, push, merge, or deployment.

## Evidence Rules

Routing evidence is the user's words plus available artifacts. Do not invent project facts. Say when the decision is based only on current context.

## Output Format

```text
路由：
使用 skill：
原因：
未启用：
接下来执行：
```

For simple work, collapse this into one sentence.

## Hard Rules

- Do not force every request into a heavy review flow.
- Do not run risky commands, database writes, service restarts, provider calls, push/merge, force push, or `git reset --hard` by default.
- Do not overwrite a user's `AGENTS.md` or existing skills without explicit install parameters.
- Keep final answers in Chinese unless the user asks otherwise.

## Failure Modes

- Over-routing a small request into a slow governance workflow.
- Choosing a broad architecture skill when a contract or test skill is enough.
- Treating missing evidence as proof of completion.

## Example User Inputs

- "帮我复核这段 Codex 线程结果。"
- "P2.8 能不能进入下一阶段？"
- "检查 quote -> create -> result 有没有绕过统一链路。"
- "Unity 场景改动前先确认安全边界。"

## Example Final Output

```text
路由：这是 P2.x 阶段验收，不是普通总结。
使用 skill：project-phase-review，必要时补充 evidence-first-testing。
接下来我会先核对阶段目标、边界、证据和缺口，再给出能否进入下一阶段的结论。
```
