---
name: file-lock-manager
description: 为多Worktree写任务提供Git公共目录级文件锁，保护Unity Scene、Prefab、ProjectSettings、meta，以及多技术栈服务端核心Service、数据库迁移和API Contract。用于并行开发前的锁定、冲突检查、心跳和释放，不把某一种服务端语言写成唯一规则。
---

# 文件锁管理

锁存储在 Git common dir，所有 Worktree 共享。Unity 资产与 `.meta` 视为同一资源；`ProjectSettings`、数据库迁移和 API Contract 采用全局互斥。服务端核心 Service 根据真实文件类型识别，TypeScript、C#、Java/Kotlin和Python等现有技术至少采用文件级互斥。

```bash
python <plugin-root>/scripts/file_lock.py --root . acquire --task-id KG-001 --agent-role "Developer Agent" --owner agent-a --paths Assets/Main.unity Assets/Main.unity.meta
python <plugin-root>/scripts/file_lock.py --root . check --task-id KG-001 --files Assets/Main.unity
python <plugin-root>/scripts/file_lock.py --root . release --task-id KG-001
```

只允许 Development、Review、Testing 中的任务持锁。锁冲突时禁止写入；不得删除他人锁、伪造任务 ID 或让暂停任务继续写。异常接管必须由 Master Agent核对 checkpoint、任务状态和持有者后处理。
