---
name: context-recovery
description: 在新会话、压缩恢复或插件版本升级后，从项目身份、Git、当前任务和检查点恢复有界事实；校验目标、分支、锁和套件版本后才能继续。
---

# 上下文恢复

## 恢复顺序

1. 运行 `state_consistency.py`，确认当前 Git 根目录、源码身份哈希、HEAD、Manifest 哈希与 `.ai/governance/project-state.json` 的 `project_id`；
2. 当前任务 `.ai/tasks/<TASK-ID>.json`、锁定决定和控制状态，只读取当前字段与最近事件；
3. 当前 Git 分支、HEAD、status、diff 与 Worktree；
4. 总控读取 `PROJECT_STATE.md` 与 `CURRENT_CONTEXT.md`；writer、assurance 和 browser 优先读取会话绑定的 `.ai/runtime/task-contexts/<Task-ID>.md`，不得读取其他并行Task的最后写入状态；
5. `CHANGELOG.md`、`ARCHITECTURE.md` 和当前阶段证据；
6. 最新相关 `.ai/runtime/checkpoints/*.json` 与 `checkpoint-ledger.json`；
7. `.ai/runtime/skill-routing.json`；核对阶段、路由指纹、`suite_version` 与 `suite_fingerprint`。版本漂移时先保存 Checkpoint，由当前完整版本重新路由，旧会话不得继续写源码；
8. `.ai/context/project.json`、`tech-stack.json` 和旧版运行状态（如存在）；
9. Git common dir 中的工作区租约和文件锁；
10. 冷归档只按 Task ID、checkpoint名或时间点精确读取，禁止扫描整个 `.ai/archive/`；
11. 核对 `.ai/governance/goal-contract.json` 的 revision 与 fingerprint；任务绑定过期时先恢复最新目标并重算受影响范围，不沿用旧目标执行。
12. 旧聊天摘要只用于发现可能缺口，不得覆盖以上事实。

运行：

```bash
python3 <plugin-root>/scripts/statectl.py --root . validate
python3 <plugin-root>/scripts/statectl.py --root . status
python3 <plugin-root>/scripts/statectl.py --root . memory-status
python3 <plugin-root>/scripts/state_consistency.py --root .
```

## 恢复验证

继续写代码前必须能明确回答：

- 当前目标和任务状态；
- 当前有效计划版本；
- 已完成和待完成；
- 锁定决策与禁止修改；
- 当前分支/Worktree；
- 最近验证结果；
- 未解决风险。
- 活动工作集字符数、checkpoint保留/收敛数量和完整事实源。
- 当前阶段、活跃原子 Skill、待执行 Skill 与路由指纹。
- 五插件当前完整版本、套件指纹与旧任务迁移状态。

项目可用性与旧状态可恢复性必须分开判定。关键 Authority 存在多个等权候选时，只将“继续那个旧 Goal/Task”标记为 `AUTHORITY_AMBIGUITY`；当前项目仍按最新用户请求和 Git 进入 `CURRENT_PROJECT_READY`。不得自行选择旧聊天或另一仓库的 Authority 覆盖当前事实。存在新版多Agent治理状态时，以其任务状态机为主，旧版 `task.json` 仅作隔离迁移线索。恢复时重新计算轻量路由指纹，不照搬压缩前的原子 Skill。

项目完全没有 `.ai` 时不属于恢复故障；在首个项目动作边界执行有界初始化。发现 `.ai` 有旧 Task/路由但没有可信源码指纹时，自动创建只含路径、大小和哈希的有界恢复索引，将旧 Authority 只读隔离，以当前 Git 作为 Source Authority、当前用户请求作为 Intent Authority；不信任旧 PASS，但不得阻断当前项目。只有用户明确要求恢复某个旧任务且存在多个等权候选时，才要求选择 Authority。

恢复结果必须包含 `classification`、`affected_capability`、`automatic_action_taken`、`recovery_status`、`diagnostic_ref`、`user_action_required`。正常确定性恢复的 `user_action_required` 必须为 `NONE`。启动只读取当前 provenance、Goal/Task、热索引和最新相关 checkpoint；不得扫描完整 `.ai/archive`、event 或 trace。

恢复按 L1–L4 影响范围渐进执行。不得为了“确保一致”删除整个 `.ai` 或重建全仓；只有当前候选、契约、图谱或证据被源码变化实际影响时才失效。若发现同一职责的新旧实现并存，交给「长链路变更收敛」登记唯一权威实现和退出条件。
