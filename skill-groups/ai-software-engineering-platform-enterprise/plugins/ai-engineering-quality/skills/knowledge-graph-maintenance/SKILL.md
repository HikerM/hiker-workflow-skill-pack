---
name: knowledge-graph-maintenance
description: 增量构建和校验大型工程的文件级关系图谱。
---


# 工程图谱维护

## 职责

- 将文件元数据和可验证关系写入 SQLite；
- 增量更新变更文件并删除已不存在节点；
- 保存当前 Git Commit 与更新时间；
- 按方向、深度和节点上限查询影响；
- 输出图谱健康报告。

## 约束

- 不存储源码全文；
- 不把所有关系强制解释为双向；
- 达到节点上限必须返回 `truncated: true`；
- 图谱 Commit 与当前仓库不一致时必须标记 `stale`。
