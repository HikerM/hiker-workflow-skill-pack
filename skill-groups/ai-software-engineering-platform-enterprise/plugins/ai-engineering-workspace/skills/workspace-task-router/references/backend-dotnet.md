# .NET 后端

只在技术栈证据命中 ASP.NET Core、Minimal API、MVC、gRPC、EF Core 或 .NET 服务时读取。

- 锁定 SDK、TargetFramework、C#、ASP.NET Core、EF Core 和包版本；保持现有 Host、DI、Middleware 与配置方式。
- 维护 API/Application/Domain/Infrastructure 边界；Controller 或 Endpoint 不直接承载领域流程和持久化细节。
- 公共 Contract、DTO、gRPC proto、认证策略和 EF Migration 采用串行所有权，检查所有调用方与兼容版本。
- 异步链路必须传播取消、超时和错误；不得用同步阻塞破坏线程池或请求生命周期。
- 数据变更验证事务、并发标记、索引、回填、滚动发布和回滚；禁止把迁移成功等同于业务兼容。
- 执行解决方案真实的 build、test、格式/分析器、集成、契约与迁移验证，并保存日志。
