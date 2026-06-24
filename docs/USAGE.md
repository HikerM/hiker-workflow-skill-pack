# Usage

## Default Prompt

Use this at the start of complex Codex threads:

```text
请先按 hiker-workflow-router 判断该用哪个 Hiker skill，再执行任务。不要默认写 DB、重启服务、真 provider 调用、push/merge 或覆盖 AGENTS.md。
```

## Thread Review

```text
请用 codex-thread-review 复核下面的 Codex 线程结果，输出结论、证据、问题、下一步，以及可复制给 Codex 的消息。
```

## Phase Review

```text
请用 project-phase-review 判断这个 P2.x 阶段是否能进入下一阶段。不要把写完代码当作完成，必须区分 smoke、contract、build、commit、push、merge。
```

## Evidence Testing

```text
请用 evidence-first-testing 设计最小真证据测试。区分真实数据、fixture、接口形状 mock、happy path stub。
```

## Contract Audit

```text
请用 contract-boundary-audit 检查 OpenAPI、DTO、DB seed、provider payload、result response 和前端字段是否对齐。
```

## NodeTs Pipeline

```text
请用 nodets-execution-pipeline-guardrails 检查 quote -> create -> result 是否走统一链路，补 branch、HEAD、git status、diff、smoke、DB parity、worker queue、billing、provider payload、result API 证据。
```

## Unity Work

```text
请用 unity-codex-guardrails。先检查 Unity 项目根目录、git status、Editor 状态、console、scene hierarchy，再修改 scene/prefab/script/asset。
```

## Design Output

```text
请用 design-output-discipline。保留原内容和比例，生成单独文件或 zip，完成时报告真实文件路径和抽查证据。
```
