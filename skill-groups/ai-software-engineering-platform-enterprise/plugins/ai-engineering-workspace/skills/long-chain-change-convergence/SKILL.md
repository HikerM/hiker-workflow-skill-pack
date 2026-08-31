---
name: long-chain-change-convergence
description: 为跨模块、跨仓库或反复修复的复杂任务限制范围、唯一实现、证据层级、失败换策和版本漂移；状态变化时输出去重工程告警。
---

# 长链路变更收敛

只控制工程过程，不保存业务案例规则。禁止把项目名、对象名、模型名、固定坐标、固定资产数量或一次故障现象写成通用策略。

## 何时启用

出现任一高风险组合时启用：跨前后端或多仓库；修复、真实验证和部署连续执行；需要计费或不可逆外部操作；发生回滚；同一验收点重复失败；用户推翻既有结论；生产版本与远程主线不一致；同一职责出现多个实现入口；任务持续扩大到原变更契约之外。

普通局部修改不启用，不扫描全仓，不预加载历史会话。

## 开始任务

先确保项目和 Task 已由项目状态管理初始化，再用稳定验收 ID 建立收敛状态：

```powershell
py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 init `
  --criterion "AC-001|原有公开行为保持不变|integration" `
  --criterion "AC-002|用户可见目标在真实运行环境成立|user-visible" `
  --strategy "在批准范围内完成最小可证伪改动"
```

证据层级从低到高为 `static`、`integration`、`runtime`、`user-visible`、`production`。低层证据不能替代高层验收：编译或合同测试通过不能证明真实界面、外部执行或最终用户效果通过。

## 强制收敛规则

1. 每个业务职责登记唯一活动实现路径。迁移兼容路径必须使用 `MIGRATION` 并带退出条件；合并前必须退役。退役路径必须提供删除提交或调用图不可达证据。
   当能力分散在多个文件、入口或版本时，维护最小 `.ai/governance/implementation-registry.json`，并运行 `implementation_guard.py`。每个能力必须恰有一个权威活动实现，最多一个权威状态写入者；废弃实现禁止接收新需求或写权威状态。
   已验证的 Structural Change Decision 只作为当前 Task Contract 的结构动作输入；本能力复用其范围与退出条件，不另写第二份结构裁决。
2. 用户纠正、证据矛盾、范围扩大、方案失效或回滚发生时立即记录。旧 PASS 只对原验收修订、策略修订、代码指纹和环境有效。
3. 同一验收条件连续两次真实实验失败后进入 `PIVOT_REQUIRED`。停止继续加补丁，先说明旧方案失效依据并创建新的策略修订。
4. 真实、计费、生产或不可逆实验必须先登记假设、预期观察和停止条件；任何时刻只允许一个未结实验，禁止无依据重复执行。
5. 修复前先登记问题 ID、单一根因假设、本轮允许动作与禁止动作。相同问题连续两个根因假设被证据否定即进入 `DIAGNOSIS_REQUIRED`，禁止继续猜测式修改，必须回到首个可观测失真边界补调用链、状态转换或运行时证据，再建立新策略。
6. 源码 HEAD、远程主线和部署版本不一致时标记版本漂移。版本漂移未解释和收敛前，禁止再次生产执行或发布。
7. 合并前所有验收条件必须达到各自要求的证据层级，不得使用一个总 PASS 覆盖局部失败或未知项。

## 治理不得吞噬交付

把“治理进展”和“业务价值进展”分开记录。控制账本、校验器、测试夹具、会话恢复或门禁修复完成，只能算治理进展；只有业务源码、用户可见行为、真实契约或可运行能力发生有效变化，才能算业务价值进展。向用户汇报时必须同时说明 `业务源码是否已开始`、`当前治理周期数` 和 `下一项精确业务门禁`，不得把控制代码修改描述成业务功能已经进入实现。

连续两个治理周期没有业务价值增量时，停止继续增加投影、摘要、交叉摘要或全量矩阵。若变更契约已满足，下一动作必须进入首个安全业务切片；若未满足，只能报告一个具体真实阻断。治理周期上限禁止继续治理，不能反向成为禁止 Development 的门禁。

审批、任务、证据和 Gate 只保留一个机器可写事实源。README、状态表和对话摘要是派生视图，只保存稳定 ID 与指针；禁止把同一批准事实复制到多份 JSON，再用整文件 digest 相互锁死。必须服务外部合同的派生文件由事实源确定性生成，不得人工多点同步。

验证采用“证据指纹 + 影响范围”复用：相同门禁、源码/合同指纹和范围已有 PASS 时直接复用；发生变化只重跑受影响切片。测试夹具、汇总器或清理脚本失败只使该测试运行 `INVALID`，不能冒充产品失败，也不能自动让已经独立通过且未受影响的证据全部失效。全量重放只用于共享测试基础、公共合同或验证逻辑本身发生实质变化，不做无界笛卡尔积。

```powershell
py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 progress-record `
  --lane governance --summary "修复发布门禁自身缺陷" --next-business-gate "开始最小业务源码切片"

py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 verification-plan `
  --gate-id GATE-001 --fingerprint "<源码与合同指纹>" --scope "受影响验证表面"
```

## 路径与实验登记

```powershell
py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 route-set `
  --responsibility "订单状态推进" --route-id "统一状态服务" --status ACTIVE

py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 experiment-authorize `
  --criterion-id AC-002 --hypothesis "本次最小改动能恢复目标行为" `
  --expected "真实运行后状态与验收描述一致" --stop-condition "首次失败立即停止，不自动重试" `
  --environment production

py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 hypothesis-add `
  --issue-id ISSUE-001 --statement "<可证伪根因假设>" `
  --allowed-actions "<本轮允许动作>" --forbidden-actions "<禁止改动>"

py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 hypothesis-result `
  --hypothesis-id HYP-001 --result REJECTED --evidence "<否定该假设的证据>"
```

禁止为了通过门禁伪造职责登记、证据层级、部署哈希或实验结果。

实现登记不是全仓手工清单：只有出现新旧实现并存、多入口、多写入者、迁移或职责膨胀时才登记受影响能力。普通局部修改保持零配置；登记内容必须有源码或调用证据，迁移完成后保留最小历史指针，不复制源码事实。

## 用户可见工程健康告警

每个阶段切换、用户纠正、失败实验、回滚、部署变化和方案修订后运行：

```powershell
py -3 <plugin-root>\scripts\convergence_guard.py --root . --task-id KG-001 status --phase status
```

当 `should_notify=true` 时，在正常插件应用回执之后显示一次简短中文告警，必须包含：

- 出现了什么问题；
- 哪些结论或范围受到影响；
- 当前正在采取什么处置；
- 下一道可继续门禁是什么。

只在告警指纹变化时再次显示。展示后用 `ack --fingerprint <值>` 记录，禁止每轮重复、输出英文内部名、复制完整日志或把告警写成长篇过程汇报。

## 与现有门禁衔接

- 任务生命周期负责分支、角色、状态、Commit、Review 和 Test 流转。
- 架构守卫负责文件增长、公共表面、消费者、依赖方向和影响半径。
- 本能力负责结论失效、唯一实现路径、真实实验预算、分层验收和部署漂移。
- 本能力同时限制治理空转与重复验证；不会用全面性为由无限增加控制文件、会话或测试组合。
- 功能验收闭环在合并与发布前读取本状态；存在方案失效、证据矛盾、未结实验、迁移路径、版本漂移或未通过验收条件时必须阻断。
