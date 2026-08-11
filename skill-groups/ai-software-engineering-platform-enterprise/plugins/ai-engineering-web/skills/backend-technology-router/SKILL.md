---
name: backend-technology-router
description: 为B/S、C/S或纯服务端任务从真实清单轻量识别Node.js/TypeScript、.NET、JVM、Python、Go、Rust、PHP或Ruby服务端的框架、运行时、包管理器和版本证据，并只路由当前阶段所需的一个服务端原子Skill。不得猜测最新版或扫描依赖缓存。
---

# 服务端技术路由

运行 `python <plugin-root>/scripts/backend_guard.py --root . detect`。证据不足时输出 `unknown`，不得默认框架或版本。

- API或事件定义进入「接口与事件契约设计」。
- 普通功能进入「服务端功能实现」。
- Schema或迁移进入「数据库迁移治理」。
- 只读审核进入「服务端质量审核」。

单次只加载当前技术族、当前阶段需要的参考；不得同时加载全部服务端资料。
