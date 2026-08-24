# 智能软件工程平台 5.15 验证报告

生成版本：`5.15.0+codex.20260824035802`

## 已执行结果

- 五插件全量单元回归：134项全部通过（核心39、质量26、客户端7、浏览器端与服务端14、工作区48）。
- 总控推进多维评估：4个临时真实Git/状态场景全部通过，覆盖小型真实开发、大型动态并行、长期总控纪元和目标中途调整。
- 小型真实开发门禁：治理预算退出到Development；真实业务Commit前禁止进入Review；局部且契约未变化时跳过contract-data。
- 大型动态并行门禁：两个独立writer允许并行，第三个writer排队，父子写范围返回`BLOCK_SCOPE_CONFLICT`。
- 长期总控门禁：有效轮次、工具调用、输出字符和压缩次数均能触发Checkpoint轮换；12001字符完整输出落证据文件，会话摘要为525字符。
- 目标调整门禁：项目目标修订后旧Task被阻断，重绑定修订2后恢复Planning。
- 路由行为评测：95项正向与42项负向全部通过。
- 发布级Skill一致性审核：5个插件、42个Skill全部通过；结构、路由、职责、权限、可用性和性能均为0错误、0警告。
- 路由冷进程性能：20次，发布包门禁P95为77.34毫秒，低于500毫秒门限。
- 桌面稳定性门禁：5个插件均无生命周期Hook，`defaultPrompt`均不超过3项，42个Skill与测试报告体积均在限制内。
- Windows运行时释放探针：真实子进程存活/退出回归通过；存活检测改为只读进程句柄查询，不再使用可能干扰进程的Windows `os.kill(pid, 0)`。
- 发布包：5个当前版本ZIP已生成；旧5.14版本ZIP已从发布目录移除。
- 插件作者与开发者标识：统一为Hiker。
- 公开内容审计：扫描574个受版本控制、待提交或发布包内部文本条目，0项敏感信息发现。
- 仓库根级总验证：repository、public-content、engineering、desktop-reconstruction四项全部PASS；仓库只包含两套能力包。
- 桌面软件等价重建1.3.0验证：PASS，4个阶段原子Skill、0错误、0警告。

## 5.15 新增门禁

- `.ai` 三态执行策略：无状态项目直接轻量推进；一致状态才允许复用；无可信来源或身份冲突的旧状态自动隔离，并由测试证明不能自动补写 provenance 重新获得执行权。
- `goal_contract.py`：以稳定目标ID、修订号、验收条件和指纹绑定Task；目标变化后旧Task必须重绑定。
- `session_epoch.py`：按有效轮次、工具调用、工具输出和压缩次数管理唯一总控纪元，Checkpoint后才允许替代接管。
- `bounded_run.py`：完整脱敏stdout/stderr落到证据文件，对话只接收有界摘要、退出码、路径和SHA-256。
- `task_router.py`：支持最多8个动态规划通道；保留名称、越界写范围和循环依赖会被拒绝。
- `session_pool.py`：writer槽增加稳定所有权通道，最多两个活动writer，并兼容5.14旧状态键。
- `dispatch_guard.py`：父子写范围冲突强制串行；查询失败只禁止新建，不需要隔离运行时的当前工作继续。
- `governance_state.py`：治理无业务增量达到预算后进入Development；根上下文与Task上下文分离，Task历史压缩归档。
- `evaluate_master_progression.py`：把小型、大型、长期总控和目标调整纳入每次发布的可执行场景门禁。

## 发布包摘要

| 插件 | 文件 | SHA-256 |
|---|---|---|
| 智能工程核心 | `dist/ai-engineering-core-5.15.0.zip` | `a5d1e4eab55ec629258477123862e2ea80eac3e3dd639f29bc9d9631b38bbff7` |
| 质量、风险与发布 | `dist/ai-engineering-quality-5.15.0.zip` | `fbefb83050d9230c75edc439b20a4ba076560b181e2c550c689b69bb7e3ef262` |
| 客户端工程 | `dist/ai-engineering-unity-5.15.0.zip` | `150ae73b75ff946a5fcc21acab9fc0047dad04baa70b4affa519fda49af36cdb` |
| 浏览器端与服务端工程 | `dist/ai-engineering-web-5.15.0.zip` | `ecd9bf78aedafc2e400b1734142256a160843e44ffbd8fed52fe3167b44ba90f` |
| 工作区与多会话协作 | `dist/ai-engineering-workspace-5.15.0.zip` | `bdf2f710b087ec8c8484faf897996164ba86bc60f582a43d11c96f3c1bb14a09` |

本报告不包含本机安装路径、用户信息、公司信息、真实项目信息或会话标识。
