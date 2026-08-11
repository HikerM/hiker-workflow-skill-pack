# B/S 与 C/S 分层模型

## B/S

`Browser UI → API Contract → Server/Application → Data/External Systems`

- 浏览器前端负责页面、交互、状态、响应式与视觉验收。
- 服务端负责业务规则、权限、API、持久化、任务和集成。
- API Contract 与数据库迁移是共享串行面，不归任一前端独占。

## C/S

`Desktop/Unity Client → API/Protocol Contract → Server/Application → Data/External Systems`

- 客户端负责本地UI、场景/Prefab、设备能力、缓存与生命周期。
- 服务端负责权威业务状态、权限、同步、存储和运维接口。
- 离线单机也要显式标记“嵌入式后端/本地数据层”，不能把数据和业务服务遗漏。

## 混合系统

B/S Web 与 C/S Client 可以共享后端和契约，但各自拥有独立验收矩阵。任何接口变化先由 contract-data 通道定版，再并行实现消费者和提供者。
