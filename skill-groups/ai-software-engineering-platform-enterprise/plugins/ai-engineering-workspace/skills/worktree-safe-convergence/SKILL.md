---
name: worktree-safe-convergence
description: 只读清点、接管、分类并安全关闭长期堆积、孤儿、嵌套、已合并或登记失效的 Git Worktree。用于整理历史工作目录、合并后收敛、发布前治理和源码身份冲突；任何关闭都必须先生成计划并由用户确认，禁止批量强制删除。
---

# 工作目录安全收敛

## 性能分级

- 普通工程路由只运行 `source_identity.py`，不得加载本 Skill 或逐目录执行 `git status`。
- 发现异常或用户要求清点时运行快速库存：

  ```bash
  python <plugin-root>/scripts/worktree_inventory.py --root . --mode quick
  ```

- 准备分类或关闭一个工作目录时才运行 `--mode deep`；不得默认计算目录大小、读取源码或执行 `git fetch`。

## 安全流程

1. 用 `inventory` 读取真实 Git Worktree，不修改项目。
2. 用 `adopt` 登记历史工作目录；登记不移动、不提交、不合并、不关闭。
3. 只对一个精确路径运行 `plan-close`，核对脏文件、独有提交和目标分支合并关系。
4. 向用户展示计划和阻断原因。只有用户明确确认后，才把计划 Token 传给 `close`。
5. `close` 必须重新计算安全指纹；分支、HEAD、状态或库存变化时终止，并要求重新规划。
6. 关闭只执行 `git worktree remove`，默认保留分支；不得递归删除目录、自动删分支或使用强制参数。

```bash
python <plugin-root>/scripts/git_workspace.py --root . inventory --mode quick
python <plugin-root>/scripts/git_workspace.py --root . adopt --worktree-id WT-001 --path <path>
python <plugin-root>/scripts/git_workspace.py --root . plan-close --path <path> --target develop
python <plugin-root>/scripts/git_workspace.py --root . close --token <approved-token>
```

涉及阻断分类、两阶段确认和发布门禁时读取 [安全收敛规则](references/safe-convergence.md)。
