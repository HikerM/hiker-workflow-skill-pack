---
name: brownfield-requirement-reconciliation
description: 存量源码融合新需求时建立证据化能力基线，将需求对账为新增、修改、替换或移除；禁止重套脚手架或擅换技术栈。
---

# 存量工程需求对账

## 输入

- 已完成 `project-bootstrap` 的 `.ai/context/tech-stack.json`；
- 现有源码、配置、API、Schema、Migration、测试和运行证据；
- 带验收条件的新需求或变更请求。

## 执行

1. 运行 [brownfield_reconcile.py](../../scripts/brownfield_reconcile.py) `init`，建立存量项目需求空间。不得删除或重建现有工程。
2. 从代码和测试证据登记 `CAP-001` 等现有能力。每项必须附仓库内证据路径；无法证明的行为记入未知项。
3. 为新需求分配稳定 `REQ-001`，并分类为：
   - `add`：新增能力；
   - `modify`：保持能力身份并改变行为；
   - `replace`：替换旧实现或契约；
   - `remove`：移除能力及其消费者。
4. 运行 `reconcile`，生成需求到模块、API、数据、权限、测试和迁移的影响矩阵。
5. 先解决阻塞冲突，再进入任务拆解。涉及架构、公共API、数据库兼容、安全边界或迁移时自动生成决策 Checkpoint，记录影响、证据、兼容策略、风险和回退后非阻塞继续，不弹出审批；真正不可逆的高影响操作仍在执行前进入对应安全门禁。
6. 用户提供目标架构、模块重组或功能拆分思路时，在能力基线和影响矩阵建立后使用「架构决策挑战与补全」反证；不得把现有源码当成合理架构，也不得绕过现有能力、消费者和迁移约束重画理想系统。
7. 聊天只读取 `REQUIREMENT_DELTA.md`；完整基线、哈希、需求历史和对账结果留在 `.ai/requirements/`。

## 输出

```text
.ai/requirements/source-baseline.json
.ai/requirements/ledger.json
.ai/requirements/reconciliation.json
.ai/context/requirement-reconciliation.json
REQUIREMENT_DELTA.md
```

## 权限与禁止

- 允许读取工程证据，写需求、影响分析和状态文件。
- 对账通过前不得批量修改业务源码、重做项目结构或生成破坏性迁移。
- 不得因代码存在就推断它仍是有效业务需求；代码事实与产品目标必须分开记录。
- 不得自动升级框架、删除兼容层、修改 main、push、merge或发布。

## 命令

```powershell
py -3 <plugin-root>\scripts\brownfield_reconcile.py init --root . --project-id APP --goal "继续开发现有系统"
py -3 <plugin-root>\scripts\brownfield_reconcile.py baseline --root . --input existing-capabilities.json
py -3 <plugin-root>\scripts\brownfield_reconcile.py reconcile --root . --input requirement-changes.json
py -3 <plugin-root>\scripts\brownfield_reconcile.py validate --root .
```

## 完成门禁

- 现有能力均有仓库内证据或明确标记未知；
- 每个非新增需求指向有效 `CAP-*`；
- 新需求具备验收条件和影响范围；
- 架构、API、数据、安全与迁移风险已进入自动决策 Checkpoint 或任务计划，且不存在人工审批暂停点；
- 未用重写工程掩盖存量兼容问题。
