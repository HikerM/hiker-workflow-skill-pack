# 智能软件工程平台 5.17 验证报告

生成版本：`5.17.0+codex.20260825194113`

## 已执行结果

- 五插件全量单元回归：237项全部通过（核心70、质量36、客户端15、浏览器端与服务端19、工作区97），源码测试指纹为 `ee5dfbea525763e8919a`。
- 真实语义路由评测：39项宿主选择用例全部通过；Top1准确率、Top2召回、拒绝/unknown质量均为1.0，错误插件率、过度加载率和不必要Skill率均为0，外部模型调用为0。
- 路由冷进程性能：20次增量P95为114.63毫秒、原始P95为143.69毫秒，分别低于200/500毫秒发布门限；范围不包含网络与模型服务端延迟。
- 发布级Skill一致性审核：5个插件、42个Skill全部通过；结构、路由、职责、权限、可用性和性能均为0错误、0警告。
- 桌面稳定性门禁：全局性能内核3673字节；42个Skill前置描述合计9602字节；Skill正文合计132755字节；无生命周期Hook。
- 五插件版本栅栏：完整版本一致，套件指纹可写入项目路由状态；旧指纹普通开发被阻断，上下文恢复迁移通过。
- 安装验证：隔离临时HOME中的个人Marketplace、五插件源码、5.17缓存、桌面启用配置和全局规则哈希一致；未修改当前Codex 5.15安装。
- 总控推进多维评估：小型真实开发、大型动态并行、长期总控纪元和目标中途调整4个场景全部通过。
- Crash Recovery E2E：原子提交、Trace补偿、PREPARED/DOMAIN_COMMITTED中断、dead PID、PID复用和损坏锁8项通过；Desktop Turn生命周期12项通过。
- Goal Change E2E：AFFECTED/UNAFFECTED/SUPERSEDED/REQUIRES_REVIEW、消费者证据失效、撤销和中断恢复16项通过。
- Event Pressure E2E：10,001事件、冷热Rotation、显式恢复、STREAM聚合、RED/DRAINING、损坏segment和热查询有界12项通过。
- Multi Session E2E：会话租约、固定writer/assurance槽、最多两个运行通道、重复派发阻断、Worktree和资源释放相关Workspace回归57项通过。
- 长会话门禁：75%软阈值只推荐自然边界Checkpoint；硬阈值要求Checkpoint与唯一新总控纪元接管。
- 有界输出：12001字符完整输出写证据文件，会话摘要为525字符。
- Architecture Self Guard：105个生产Python文件通过；`hikerctl.py` 196行、`governance_state.py` 648行，Task状态保持单一权威writer。
- 公开内容审计：扫描633个受控及发布包文本条目，0项敏感信息发现。
- 桌面软件等价重建1.3.0独立验证：PASS，0错误、0警告。
- 发布包：5个5.17.0 ZIP已生成并通过源码文件级完整性检查；旧5.16.0 ZIP已移出发布目录。

## 5.17 发布门禁

- `self_governance.py`：按Architecture → Privacy → Version Facts → Tests → Performance → Package Facts → Release Gate顺序失败关闭。
- `control_kernel.py`：operation journal统一Task状态提交语义，Domain提交后Trace失败只进入补偿，不诱导业务重放。
- `desktop_turn_lifecycle.py` 与 `runtime_release_probe.py`：以Turn租约和运行时身份阻断重复发送，并验证进程释放。
- `event_store.py`、`event_budget.py` 与 `desktop_pressure.py`：保持热索引有界，压力升高时收敛新dispatch。
- `goal_change_transaction.py`：结构化影响分类在一个可恢复修订事务内更新多Task绑定与证据有效性。
- `evaluate_semantic_routing.py`：评分宿主给出的结构化选择，不读取gold作为选择输入，不按关键词推导Skill。
- `audit_release_facts.py` 与 `release-versions.json`：统一README、Manifest、安装文档、ZIP和checksums的当前版本事实。
- `package_release.py`：先在临时候选目录验证完整五包，再原子发布，任何源码或包事实漂移均不更新 `dist`。

## 发布包摘要

| 插件 | 文件 | SHA-256 |
|---|---|---|
| 智能工程核心 | `dist/ai-engineering-core-5.17.0.zip` | `752426cc7e496e5eb58926f1b4a4f88597f5bf1c220eeaef3b7f8fee5d278027` |
| 质量、风险与发布 | `dist/ai-engineering-quality-5.17.0.zip` | `7668a58e1e667639afc99ff4f22222e324eb25dbc5f0c25c0e6fe5bcc30f4698` |
| 客户端工程 | `dist/ai-engineering-unity-5.17.0.zip` | `2f72f0a71abead4f62cd8c9906810ef7e85ab9b7403bf81a13f507986a473be8` |
| 浏览器端与服务端工程 | `dist/ai-engineering-web-5.17.0.zip` | `d46e316709148a426cbe91a733d41564162577dbfcd1621061070b9e432daf32` |
| 工作区与多会话协作 | `dist/ai-engineering-workspace-5.17.0.zip` | `1670f642d24297a8b2a8d37ef9c2fc74492004e25257aba6ff154b409eca2fbf` |

本报告不包含本机安装路径、用户信息、公司信息、真实项目信息或会话标识。
