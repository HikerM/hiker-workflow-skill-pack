# 三组 Skill 使用示例

## 第一组：Hiker 工作流守护

### 自动路由

```text
请先按 hiker-workflow-router 判断该用哪个 Hiker Skill，再执行任务。不要默认写生产 DB、重启服务、真实 Provider 调用、push/merge 或覆盖 AGENTS.md。
```

### 线程结果复核

```text
请用 codex-thread-review 复核下面的 Codex 线程结果，输出结论、证据、问题、下一步，以及可复制给 Codex 的消息。
```

### 阶段验收

```text
请用 project-phase-review 判断这个阶段是否能进入下一阶段。必须区分源码存在、build、smoke、contract、commit、push 和 merge。
```

### 真证据测试

```text
请用 evidence-first-testing 设计最小真证据测试，明确真实数据、fixture、接口形状 mock 和 happy-path stub 的边界。
```

### 契约审计

```text
请用 contract-boundary-audit 检查 OpenAPI、DTO、DB Seed、Provider Payload、Result Response 和前端字段是否对齐。
```

### NodeTs 链路

```text
请用 nodets-execution-pipeline-guardrails 检查 quote → create → worker/provider → resource_transfer → result normalization → asset/storage/preview_url → billing 是否走统一链路。
```

### Unity 修改

```text
请用 unity-codex-guardrails。先检查 Unity 项目根目录、Git 状态、Editor、Console 和 Scene Hierarchy，再修改 Scene、Prefab、Script 或 Asset。
```

### 设计文件交付

```text
请用 design-output-discipline。保留原内容、顺序和比例，生成真实文件，并报告路径和视觉抽查证据。
```

## 第二组：AI 软件工程平台 Enterprise

### 项目初始化

```text
使用 project-bootstrap 读取当前仓库，识别真实语言、框架、精确版本、包管理器和子项目，建立 .ai 状态，不修改业务源码。
```

### 长任务恢复

```text
使用 context-recovery 从 .ai 状态和最新检查点恢复当前目标、已锁定决策、分支和唯一下一步，然后继续执行。
```

### Web 页面设计与实现

```text
先使用 web-ui-design 沿用当前项目的组件库和 Design Token 形成页面规格，再使用 web-component-implementation 实现并验证。
```

### Unity 页面设计与实现

```text
先读取 .ai 中的 Unity 版本、UI 技术栈和目标平台，使用 unity-ui-design 设计页面，再使用 unity-component-implementation 实现 Prefab 或 VisualElement。
```

### 完整变更风险与回归

```text
使用 full-change-risk-review 审核暂存、未暂存、未跟踪和提交范围的完整变更集，再用 regression-test-planner 生成最低必要回归范围。
```

### Worktree 并行任务

```text
使用 workspace-task-router 拆分任务并定义文件所有权，再使用 worktree-task-manager 为确实需要并行写代码的任务创建独立 Worktree。
```

### 发布门禁

```text
使用 release-readiness-review 根据风险、构建、测试、迁移、回滚和发布证据判断当前版本是否可以发布。
```

## 第三组：桌面软件等价重建

### 开始新项目

```text
使用 desktop-app-reconstruction-zh 开始新项目。先冻结授权、目标软件版本、目标平台、P0/P1 范围、允许差异和禁止项，然后初始化项目目录。
```

### 盘点材料

```text
盘点现有截图、录屏、可执行程序、样例文件、接口资料和源码；建立证据索引、环境基线、缺口和未知风险，不把推断写成已验证事实。
```

### 识别技术指纹

```text
区分原软件技术指纹和目标实现技术栈。有源码时读取项目文件、锁文件、CI 和构建脚本；只有二进制时只输出带证据和置信度的候选结论。
```

### 检查遗漏

```text
检查范围、入口、页面、控件、交互、功能、数据、角色、异常、性能、规格、实施任务和测试之间是否存在断链或孤立项。
```

### 进入正式实现

```text
只有 G0 到 G5-T 门禁通过后才能进入正式实现。实现时关联规格、任务和测试编号，不得用静态页面、假接口或固定成功值冒充完成。
```

### 全门禁验收

```text
执行全门禁，验证视觉、功能、数据、性能、长稳、安装、升级、卸载、迁移和交付物完整性；明确所有 UNVERIFIED、BLOCKED、豁免和残余未知风险。
```

## 组合使用

### 第二组执行、第一组复核

```text
先用第二组完成项目初始化、实现和质量检查；然后用第一组 codex-thread-review 和 project-phase-review 独立判断证据是否足以进入下一阶段。
```

### 第三组主导、第一组独立验收

```text
桌面软件重建由 desktop-app-reconstruction-zh 主导；每个关键门禁结束后，可用 evidence-first-testing 或 project-phase-review 做独立复核。
```
