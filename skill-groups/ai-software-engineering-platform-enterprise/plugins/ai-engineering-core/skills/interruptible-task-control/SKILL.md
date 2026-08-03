---
name: interruptible-task-control
description: 用于启动、暂停、继续、调整、检查点和恢复长期工程任务。AI应连续执行，不在每个普通步骤停下来询问；用户中途插入控制指令时必须保留已完成工作并修订当前计划。
---

# 可中断任务控制

## 运行模式

默认是“连续协作模式”：计划确定后连续处理，只有破坏性操作、越权修改或事实缺失会阻断。普通阶段完成只自动保存检查点，不询问用户。

## 启动任务

使用 [statectl.py](../../scripts/statectl.py)：

```bash
python3 <plugin-root>/scripts/statectl.py --root . task-start \
  --id REQ-001 --goal "目标" --scope "允许修改范围"
```

## 用户中断

当用户说“暂停、继续、调整方向、查看状态、回滚到某检查点”时：

1. 先读取 `.ai/runtime/control.json` 与 `task.json`；
2. 不把中断当作失败；
3. 保存当前有效状态；
4. 对调整指令做影响分析，仅废弃受影响方案；
5. 更新计划版本和 `active-context.md`；
6. 在无破坏性风险时继续，不重复询问已知信息。

## 回滚

默认只生成回滚计划并标记目标检查点。代码恢复必须基于 Git/Worktree 且由用户明确要求，禁止静默 `git reset --hard`。

## 完成门禁

任务完成前更新：状态、实际修改、验证证据、遗留风险和下一步。
