---
name: worktree-task-manager
description: 为并行写代码任务创建、查看、暂停和安全清理Git Worktree及独立分支；用于Codex桌面端多会话并行，禁止在非Git项目或脏状态下强制删除。
---

# Worktree任务管理

## 创建

```bash
python3 <plugin-root>/scripts/git_workspace.py --root . create \
  --task-id web-resource --base main --branch feature/web-resource
```

脚本使用同一 Git 公共目录，并把运行时租约存入 Git common dir 的 `ai-engineering/workspace.json`，避免不同分支各自维护一份冲突状态。

## 安全规则

- 一个写任务一个 Worktree/分支；
- 默认不创建第二个 Git 仓库；
- 删除前检查脏文件、未推送/未合并提交和租约；
- 默认不自动 merge、不自动删分支；
- Detached HEAD Worktree 在写代码前创建明确分支；
- 用户中断时保留 Worktree 和未提交文件，状态标记 PAUSED。

## 桌面端

ChatGPT/Codex 桌面端原生 Worktree 会话可直接使用；本脚本主要用于可审计的 CLI、自动化或自定义路径管理。
