# 端到端示例：KG-001 统一账户登录

本例的结构化计划明确声明planning、development、review、testing、documentation、merge和release均适用；它不是普通Task的固定流程模板。

1. CONTROL读取项目状态并创建`KG-001`，目标为“Web 与 Unity 客户端使用同一后端登录”。
2. CONTROL按真实所有权拆出Web、Unity、合同与后端WRITE范围，定义401、锁定、刷新令牌和离线场景。
3. 仅因这些WRITE范围已证明独立，CONTROL按预算建立必要Worktree；职责标签不产生额外Agent。
4. API Contract串行定版并锁定；Unity WRITE通道锁定相关Prefab与meta，NodeTS WRITE通道锁定AuthService与migration。
5. 每个适用WRITE通道完成实现和单测，提交`feat(auth): implement KG-001 login`，记录Commit ID并释放锁。
6. 独立ASSURE检查权限、协议兼容、Unity生命周期与重复实现，输出PASS或退回WRITE修复。
7. ASSURE运行后端/API、Web E2E、Unity PlayMode/设备验证，保存范围化日志和截图。
8. CONTROL更新CHANGELOG；架构变化则更新ARCHITECTURE，否则保留确定性NOT_APPLICABLE。
9. 适用Gate闭合后，获授权的CONTROL按依赖顺序合并到develop并复验冲突面。
10. release Gate适用且迁移、回滚和冒烟证据通过后，CONTROL推进到Released。
