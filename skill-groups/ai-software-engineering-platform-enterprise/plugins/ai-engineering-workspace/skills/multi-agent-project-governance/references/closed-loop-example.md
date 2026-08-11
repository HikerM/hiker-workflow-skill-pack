# 端到端示例：KG-001 学生登录

1. Master Agent读取项目状态，创建 `KG-001`，目标为“Web 与 Unity 客户端使用同一后端登录”。
2. Planning Agent拆出 `bs-frontend`、`cs-client`、`contract-data`、`bs/cs-backend`，定义 401、锁定、刷新令牌和离线场景。
3. Merge Agent/项目维护者确保 develop 存在；Developer Agent分别创建 `feature/KG-001-web-login`、`feature/KG-001-unity-login`、`feature/KG-001-auth-api` Worktree。
4. API Contract 串行定版并锁定；Unity Agent锁定相关 Prefab 与 meta；NodeTS Agent锁定 AuthService 与 migration。
5. 每个 Developer 完成实现和单测，提交 `feat(auth): implement KG-001 login`，记录 Commit ID，释放锁。
6. Review Agent独立检查权限、协议兼容、Unity生命周期与重复实现，输出 PASS 或退回 Development。
7. Test Agent运行后端/API、Web E2E、Unity PlayMode/设备验证，保存日志和截图。
8. Document Agent更新 CHANGELOG；架构变化则更新 ARCHITECTURE，否则记录带理由的 NOT_APPLICABLE。
9. 闭环门禁通过后，Merge Agent按依赖顺序合并到 develop，解决冲突时保留双方意图并复测。
10. Master Agent更新 PROJECT_STATE，在发布候选通过迁移、回滚和冒烟验证后推进 Merged → Released。
