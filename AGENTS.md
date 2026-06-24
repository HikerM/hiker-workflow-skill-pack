# Hiker Workflow Skill Pack

<!-- hiker-workflow-pack start -->

## Default Workflow

- 默认先读取 `hiker-workflow-router`，再按任务选择最短匹配 skill。
- 默认中文回答；代码、命令、文件路径、API 名称、包名、框架名保持原文。
- 对工程任务先看仓库状态、边界、证据，再判断完成。
- 对复核任务先给结论，再给证据、问题、下一步、可复制线程消息。

## Skill Routing

- Codex 线程结果复核：`codex-thread-review`
- P2.x / 阶段验收 / 是否进入下一阶段：`project-phase-review`
- 真证据 / smoke / contract / 混乱数据 / 异常输入 / 并发性能：`evidence-first-testing`
- 接口契约 / DTO / OpenAPI / provider adapter / 前后端边界：`contract-boundary-audit`
- NodeTs / AI 漫剧平台 / quote -> create -> result 统一链路：`nodets-execution-pipeline-guardrails`
- Unity / Codex App / Unity MCP / scene / prefab / asset：`unity-codex-guardrails`
- PPT / 图片 / 海报 / SVG / 扑克牌 / PDF / Excel / 批量导出：`design-output-discipline`
- Laravel / Vue / MySQL / Redis / MCP / Agent 架构 / 报价：`agent-architecture-consultant`

## Before Code Changes

- 先检查当前目录是否为目标项目根目录。
- 先检查 `git status`、分支、HEAD、已有未提交改动。
- 先确认用户边界和禁止事项。
- 涉及接口时先找 OpenAPI、DTO、route、request/response、前端调用点。
- 涉及异步链路时先找 queue、worker、callback、poll、retry、result normalization。

## Evidence Standard

- 真证据必须有可复现命令、输出、文件路径、响应、截图、日志、DB/queue/provider/billing 状态之一。
- `写完了`、`应该可以`、`编译通过`、`看起来没问题` 都不是完成证据。
- smoke、contract、unit、integration、source audit、build 必须分开说。
- mock 必须标明边界：真实数据、fixture seed、接口形状 mock、happy path stub。

## Testing Standard

- 最小验收至少包含 source audit、build/typecheck、目标 smoke。
- 涉及 API/DB/queue/provider/billing 时，需要 contract 或真实联调证据。
- 涉及稳定性时，需要异常输入、混乱数据、并发或性能证据。
- 涉及 UI/设计产物时，需要生成文件和视觉抽查证据。

## Output Format

默认输出：

```text
结论：
证据：
问题：
下一步：
可复制给 Codex 的消息：
```

阶段验收输出：

```text
阶段结论：
已完成：
证据：
缺口：
是否进入下一阶段：
```

## Prohibited Defaults

- 不要默认执行 DB 写入、生产数据变更、真实 provider 调用、计费动作或服务重启。
- 不要默认 push、merge、force push、rebase 公共分支、删除分支或发布部署。
- 不要使用 `git reset --hard`、`git checkout --`、递归删除或覆盖用户文件，除非用户明确要求并确认目标。
- 不要把单次 commit 当作完成标准。
- 不要覆盖用户已有 `AGENTS.md`；安装时只能追加或带备份合并。

## Unity Rules

- 先确认 Unity project root：`Assets`、`Packages/manifest.json`、`ProjectSettings`。
- 先检查 git 状态、Unity Editor 状态、console、scene hierarchy。
- 不要未验证就改 scene、prefab、script、asset、`.meta`。
- 保留 GUID、`.meta`、prefab reference、serialized field。
- 完成后报告 console/test/play mode/hierarchy 或明确说明无法验证。

## NodeTs Rules

- 统一链路以 quote -> create -> worker/provider -> resource_transfer -> result normalization -> asset/storage/preview_url -> billing 为准。
- 前端不得绕过统一链路直接调用 provider 或拼接 provider/storage 私有字段。
- OpenAPI、DTO、seed、DB schema、provider payload、result response、前端字段必须对齐。
- billing 必须区分 reservation、settlement、release；失败路径必须释放或回滚。

## Design/PPT Rules

- 先保留原内容、顺序、比例、页数/卡数。
- 不要误改中文文字、尺寸、比例、文件名规则。
- 完成必须产出真实文件或压缩包，并报告绝对路径。
- 不要伪造下载链接或声称未生成的文件存在。

<!-- hiker-workflow-pack end -->
