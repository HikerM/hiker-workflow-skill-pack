---
name: greenfield-project-planning
description: 从空目录或零代码开始开发自定义B/S、C/S或混合软件时，建立可增量合并的需求账本、冲突与未知项、验收条件、架构候选和人工决策检查点；根据真实约束选择技术及版本，不套固定脚手架，不在关键决策锁定前开始大规模编码。
---

# 0→1 项目需求融合与技术决策

## 输入

- 用户目标、用户角色、核心工作流和成功指标；
- 目标平台、部署、联网/离线、数据、安全合规、集成、性能、预算、期限和维护约束；
- 新增或变更需求及来源。

## 产出

- `.ai/requirements/ledger.json`：完整需求事实源，使用稳定 Requirement ID；
- `.ai/context/greenfield.json`：当前项目模式、决策阶段和已锁定选择；
- `REQUIREMENTS.md`：有界活动切片、冲突、未知项与验收条件；
- 技术候选比较与一个人工 Checkpoint；批准后才锁定架构和精确版本。

## 工作流

1. 运行 `bootstrap_project.py --root <repo>` 建立兼容的 `.ai` 基础状态。空项目检测为 `unknown` 是有效事实。
2. 运行 [requirements_fusion.py](../../scripts/requirements_fusion.py) `init`。不要先创建业务脚手架。
3. 把需求拆成稳定 ID，例如 `REQ-001`；每项记录陈述、优先级、类型、来源、验收、依赖、冲突和状态。
4. 新消息用 `merge` 增量合并：同 ID 更新必须保留 revision history；新需求不得静默改写旧需求。
5. 对冲突和未知项分级。只有会改变平台、架构、部署、数据、安全边界或核心技术栈的选择才请求用户 Checkpoint；普通细节继续处理。
6. 用户已经给出架构或功能拆分思路时，先使用「架构决策挑战与补全」把它作为候选进行反证，主动发现用户未覆盖的失败、数据、契约、安全、部署、运维和演进问题；不得因用户描述详细就跳过独立分析。
7. 根据约束生成最多三个候选，比较兼容性、交付风险、长期维护、生态、性能、部署成本和团队接手成本。不得按流行度直接决定，也不得为显得强大而默认最复杂方案。
8. 技术方向确认后查对应官方文档核验受支持版本，将证据和精确版本写入决策记录；随后再初始化脚手架并转入标准任务生命周期。
9. 聊天只加载 `REQUIREMENTS.md` 活动切片和当前决策，不加载整个 revision history。

## 权限

- 允许写需求、架构候选、项目状态和 Checkpoint。
- 未锁定关键选择前只允许做小型验证性 POC；禁止批量生成正式业务代码、数据库迁移或发布配置。
- 不得替用户虚构合规、部署、预算或验收标准。

## 命令

```powershell
py -3 <plugin-root>\scripts\requirements_fusion.py init --root . --project-id APP --goal "项目目标"
py -3 <plugin-root>\scripts\requirements_fusion.py merge --root . --input requirements.json
py -3 <plugin-root>\scripts\requirements_fusion.py validate --root .
py -3 <plugin-root>\scripts\requirements_fusion.py slice --root . --limit 30
```

## 完成门禁

- 核心工作流与验收条件可追踪到 Requirement ID；
- 冲突和未知项未被伪装成已决定；
- 技术选择有需求约束和官方版本证据；
- 关键 Checkpoint 已记录，新增需求以增量方式融合；
- 当前会话输入保持有界。

