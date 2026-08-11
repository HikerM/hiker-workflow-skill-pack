# JVM 后端

只在技术栈证据命中 Java、Kotlin、Spring Boot、Quarkus、Micronaut 或 JVM 服务时读取。

- 锁定 JDK、语言、构建工具、框架和插件版本；保持现有 Gradle/Maven 多模块边界。
- Controller、Application Service、Domain、Repository、消息与外部集成职责分离；事务边界位于明确的应用用例。
- API、事件 Schema、鉴权规则、Flyway/Liquibase 迁移和共享领域模型采用单写所有权并分析消费者。
- 验证线程模型、协程/异步、连接池、事务传播、重试、幂等、序列化和配置兼容。
- 使用真实构建任务执行单元、切片、集成、契约、迁移和启动验证；记录 JDK 与运行环境。
