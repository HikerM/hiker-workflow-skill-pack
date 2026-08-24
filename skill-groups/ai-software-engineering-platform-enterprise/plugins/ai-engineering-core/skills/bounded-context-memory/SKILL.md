---
name: bounded-context-memory
description: 为长期、多会话或频繁压缩的软件工程保留有界事实、检查点和接管状态；限制热上下文与历史注入，并阻止旧插件版本继续写入。简单短任务不启用。
---

# 有界上下文记忆

## 使用场景

用于跨会话继续、大型任务交接、Agent接管、上下文即将压缩或多次压缩后的恢复。简单问答、一次性小修改且没有长期状态时不启用。

## 记忆分层

1. 永久事实：`PROJECT_STATE.md`、`.ai/tasks/*.json`、锁定决定、`CHANGELOG.md`、`ARCHITECTURE.md`、测试证据和Git历史；
2. 当前工作集：`CURRENT_CONTEXT.md` 只保存总控摘要，`.ai/runtime/task-contexts/<Task-ID>.md` 保存绑定Task与所有权通道的上下文；`.ai/runtime/active-context.md` 兼容未启用工作区治理的任务；
3. 恢复点：`.ai/runtime/checkpoints/`，分近期快照与里程碑快照；
4. 压缩账本：`.ai/runtime/checkpoint-ledger.json`，记录被收敛快照的数量、时间、摘要索引和哈希链。
5. Skill 路由态：`.ai/runtime/skill-routing.json`，只保存当前阶段、最多两个活跃原子 Skill、待执行名称和路由指纹，不保存 Skill 正文。
6. 冷归档：`.ai/archive/` 保存压缩后的历史恢复包和只追加索引；日常启动、路由和状态渲染不得扫描冷归档。
7. 源码溯源：`.ai/governance/source-provenance.json` 只保存仓库身份哈希、HEAD、分支、工作区状态和工程清单哈希，不保存远程地址或本机绝对路径。

聊天内容不是永久事实。任何会影响实现的新增需求、决定、完成项和风险，必须先写入第一层，之后才允许压缩或交接。

## 执行规则

- 初始化时创建 `.ai/governance/context-retention.json`；默认活动上下文不超过8000字符、会话自动注入不超过4000字符、每节最多8项；
- 默认最多保留8个近期检查点和6个里程碑检查点；更旧快照写入有界账本与连续哈希后移出热区，不复制源代码；
- 超出热区保留数的检查点先压缩到 `.ai/archive/checkpoints/`，记录归档路径与哈希后再从热目录移除；历史内容可按检查点恢复，但不会参与日常扫描；
- 04号日常状态渲染只读取有界任务摘要索引，默认保留最近120个已关闭任务摘要；更旧摘要进入计数与哈希链，完整Task JSON不删除；
- `.ai/tasks/` 很大时，日常状态、创建任务和checkpoint不得枚举全部Task文件，只从 `task-index.json` 读取活动任务ID；全量一致性审计必须由用户明确触发；
- 压缩前先刷新任务、决定、Git事实和当前工作集，再创建 `PreCompact` checkpoint；保存失败时阻止压缩；
- 新会话按“项目身份 → Task/决定 → Git → 正式文档 → 最新checkpoint → 聊天摘要”恢复；
- 只加载当前任务、当前技术栈和当前阶段需要的文件。不得预载所有历史、所有Skill、所有任务或完整知识图谱；
- 每个阶段最多保留两个活跃原子 Skill；轻量路由不计入额度，待执行 Skill 只保存名称并在门禁通过后重新路由。
- 长期总控每个纪元运行 `session_epoch.py status/record`。达到75%软阈值时只在下一个自然阶段边界保存Checkpoint，不立即治理或轮换；达到20个实质轮次、40次工具调用、60000字符工具输出或1次压缩硬阈值后，才禁止实质执行并由唯一新总控纪元接管。
- 预计产生大输出的构建、测试和审计使用 `bounded_run.py`：完整脱敏输出写入 `.ai/evidence/tool-output/`，会话只接收退出码、首尾摘要、路径和指纹。字符预算必须由执行包装器约束，不能只写在路由建议中。
- 插件只能限制启动注入和持久状态，不能删除已经进入桌面任务的聊天历史；因此会话纪元轮换是桌面稳定性硬门禁，不得依赖同一任务第二次自动压缩，也不得用继续压缩冒充轮换。已开始出现工具调用结果丢失、持久化序号不一致或恢复失败的桌面任务不能靠Skill修复历史，必须从最新Checkpoint开新纪元接管。
- 桌面端已创建任务不能可靠原地替换其系统指令和已加载 Skill。检测到套件版本指纹变化时，旧任务只允许保存 Checkpoint；新任务必须核对五插件同一完整版本后接管。禁止为了“热更新”同时保留新旧 Skill 继续修改项目。
- 插件不得通过 `SessionStart`、`UserPromptSubmit`、`PreCompact`、`Stop`、`SessionEnd`或子Agent生命周期Hook自动运行脚本。这些高频Hook会增加中途工具输出丢失、重入写入和桌面任务无法收尾的风险；状态恢复、Checkpoint和轮换脚本只能由当前Skill在明确阶段边界内显式调用。
- 每次路由先运行 `context_budget.py`。小型项目最多读取12个源码文件，标准项目40个，大型项目80个；达到上限必须按模块或风险分片，不能自动扩大成全仓扫描。
- 每次接管和压缩恢复先运行 `state_consistency.py`。L1只重建受影响热索引，L2重建受影响模块和契约基线，L3使候选、图谱与审核测试证据失效，L4隔离旧 `.ai` 派生状态并重新建立项目身份。修复只归档旧溯源，不删除需求、任务、决定或证据原件。
- `.ai` 与源码不一致时，Git、Manifest、锁文件、测试和当前源码优先；`.ai` 是有来源约束的工程记忆，不是不可质疑的第二套源码。
- 用户可查看：

```bash
python3 <plugin-root>/scripts/statectl.py --root . memory-status
python3 <plugin-root>/scripts/context_budget.py --root . --stage development
python3 <plugin-root>/scripts/state_consistency.py --root .
python3 <plugin-root>/scripts/session_epoch.py --root . status
python3 <plugin-root>/scripts/bounded_run.py --root . --evidence-id TEST-001 -- <测试命令>
```

## 与04插件协作

`04 工作区与多会话协作`负责Task ID、Agent分工、Worktree、锁、合并和交接；本Skill负责01插件中的有界记忆与恢复。长期多会话工程必须同时满足两层，不能只创建新聊天，也不能只累计聊天摘要。

## 权限与禁止操作

允许写入`.ai/`治理状态和受控Markdown投影；允许清理超过保留上限的自动生成checkpoint副本。禁止删除源码、Git提交、任务事实、正式决定、验收证据或用户文档；禁止用“上下文太长”为由丢弃未落盘需求；禁止声称能逐字永久保留所有聊天。

## 输出

返回有界记忆回执：项目ID/根目录、活动任务、工作集字符数/上限、保留与收敛checkpoint数量、事实源、恢复下一步和任何冲突。
