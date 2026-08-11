# Node.js 与 TypeScript 后端

只在技术栈证据命中 Node.js、TypeScript、NestJS、Express、Fastify、Koa 或相关服务框架时读取。

- 锁定 Node.js、TypeScript、框架、包管理器和 ORM/数据库驱动的真实版本；不把声明范围当已安装版本。
- 保持现有模块、Controller/Route、Application Service、Domain、Repository、Provider 和队列边界，不在 Controller 堆业务逻辑。
- API/事件变更先登记请求、响应、错误、鉴权、幂等、顺序、重试、版本和消费者；DTO、OpenAPI 与契约测试同步。
- 核心 `*Service.ts`、数据库迁移、API Contract、认证授权和队列消费者使用文件锁；同一公共服务只能有一个写任务。
- 数据修改必须说明事务、并发、唯一性、索引、回填、向前/向后兼容和回滚；迁移与应用发布顺序可验证。
- 验证只使用项目真实脚本，覆盖类型检查、lint、单元、集成、契约、迁移、并发/幂等和关键日志证据。
- 文件接近增长预算时先拆责任边界；禁止继续向大型 Service、Controller 或 Provider 追加无关职责。
