# 其他后端技术族

用于 Go、Rust、PHP、Ruby 或项目已存在但未单列的服务端技术；只应用与实际证据匹配的部分。

- Go：保持 module/package、context 取消、goroutine 所有权、接口边界和数据库事务；执行真实 `go test`、静态检查和竞态验证。
- Rust：保持 crate/module、所有权与并发模型、错误类型、Feature 和迁移边界；执行真实 fmt、clippy、test 与集成验证。
- PHP：保持 Composer、框架容器、Controller/Service/Domain/Repository 和队列边界；验证请求生命周期、事务、权限与迁移。
- Ruby：保持 Bundler、Rails/现有框架约定、模型与服务职责、Job、事务和迁移兼容；执行真实测试与静态门禁。
- 未识别框架时不得套用以上任一方法；先补齐版本和项目结构证据，再建立变更契约。
- 所有技术族共同执行公共 API/事件、数据迁移、认证授权、可回滚性、消费者回归和文件增长检查。
