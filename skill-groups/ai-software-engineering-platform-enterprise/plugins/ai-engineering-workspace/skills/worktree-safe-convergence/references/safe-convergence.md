# 安全收敛规则

## 分类

- `PRIMARY`：规范工作区，禁止关闭。
- `UNMANAGED`：未纳入任务治理，先接管或人工确认。
- `NESTED_BLOCKED`：嵌套在规范仓库内，阻断源码修改路由和新建 Worktree。
- `BLOCKED_DIRTY`：存在未提交修改，禁止关闭。
- `PRUNABLE_METADATA`：目录缺失，仅可在单独确认后清理 Git 登记。
- `CAN_CLOSE`：工作区干净、目标分支已包含该分支且没有独有提交。

## 两阶段确认

关闭计划必须记录路径、分支、HEAD、目标分支、脏文件数量、合并关系、独有提交数、库存摘要和安全 Token。执行关闭时重新读取上述事实；Token 不匹配立即停止。

## 债务门禁

- 快速库存只解析一次 `git worktree list --porcelain`。
- 嵌套 Worktree 始终是阻断项。
- 普通开发允许只读清点历史债务；创建新 Worktree 和发布阶段把未纳管 Worktree 升级为阻断。
- 每个仓库默认最多两个活动写 Worktree；已合并任务必须进入待清理状态，关闭后才能完成。
- 租约到期只要求复核，不自动删除。

## 禁止

- 禁止 `cleanup-all`、`force-remove-all` 或按时间批量删除。
- 禁止把未提交修改自动 stash、commit 或覆盖。
- 禁止用文件管理器删除已登记 Worktree。
- 禁止关闭规范仓库、删除分支或修改目标分支。
