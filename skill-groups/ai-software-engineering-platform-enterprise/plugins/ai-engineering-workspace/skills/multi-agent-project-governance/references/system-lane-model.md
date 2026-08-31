# 系统表面与动态执行拓扑

## 权威边界

Architecture Label 只是描述性、粗粒度工程证据，不是执行拓扑权威。`bs`、`cs`、`backend`、`hybrid` 不得自动创建 frontend、backend、client、data 或 contract lane。

真实执行面只从以下当前事实生成：

- Project Fact Plane；
- 当前 changed scope 与依赖；
- 共享 `authority_ids`；
- ChatGPT 对当前任务提出的有界 model proposal。

Runtime 只验证范围、依赖、共享权威、预算与冲突，不按架构标签补出模型没有提出的通道。`Example != Architecture Constant`。

## 可观察组合

B/S、C/S 与 Hybrid 仅可用于描述已观察到的组合。真实项目可以是 browser only、static site、serverless、external SaaS、local database、embedded runtime、desktop local-only、client + external API、Unity + SaaS、multi-service、multi-repository，或项目事实证明的其他组合。

某个项目存在 Browser、Client、Server、Data 或 External System，并不证明本次任务需要修改对应表面。只有当前 changed scope 与依赖命中时，model proposal 才声明相应 implementation lane；没有真实写工作时保持不存在。

## 共享权威与并行

Shared Contract、Schema、API、事件、鉴权或共享 DTO 是否形成串行面，由当前 Project Facts、changed scope 与 `authority_ids` 决定。架构标签本身不得创建 `contract-data` lane。

模型提出的每个 lane 必须带稳定 ID、实际 surface、有界写范围与仓库键；需要时声明 `authority_ids`。父子路径重叠或共享 authority 会产生串行约束；范围、共享权威、受保护资产和测试环境均可证明独立时才允许并行。规划态最多 8 个，运行态最多 2 个。
