# Git Governance Layer

## 长期分支

- `main`：已发布、可回滚基线；禁止 Agent 直接写。
- `release`：发布候选集成分支，仅具备授权的 CONTROL 管理。
- `develop`：日常集成分支，功能和缺陷分支的目标。

## 短期分支

- `feature/<task-id>-<slug>`：基于 develop。
- `bugfix/<task-id>-<slug>`：基于 develop。
- `hotfix/<task-id>-<slug>`：基于 main。
- `release/<version>`：基于 develop，仅具备授权的 CONTROL。

提交采用 Conventional Commit：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`，允许 scope 与破坏性变更标记。一个提交保持一个可解释目的，并把 Commit ID 写回任务。

只有merge Gate适用时才执行：WRITE提交候选 → 适用的ASSURE证据 → 闭环预检 → 获授权的CONTROL处理冲突并非强制合并 → 状态更新。不得因存在repository change自动推导merge；禁止WRITE直接合并main或跳过失败门禁。

## Worktree 生命周期

路由前只做当前源码身份与快速库存检查；创建前核对真实 Worktree 数量、嵌套目录、任务与租约。默认最多两个活动写 Worktree，达到预算后只允许审核、测试、合并和收敛。

历史 Worktree 先只读接管并分类。任务合并后进入 `MergedPendingCleanup`；只有两阶段安全关闭完成、分支保留决定明确、文件锁释放后才进入完成状态。禁止批量强制删除、自动删分支或在规范仓库内部创建嵌套 Worktree。
