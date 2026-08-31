# 会话与运行时生命周期

本契约只由当前 CONTROL 执行。旧版 Master/Developer/Review/Test 标签只用于兼容映射，不是必须存在的 Agent；WRITE 与 ASSURE 不得自行创建桌面任务、Worktree 或替代会话。

## 按需运行时绑定

默认不创建任何新槽位。只有结构化 Gate 已证明职责适用且当前会话不能安全复用时，才按 `project_id + repository + execution_class` 建立绑定：

- `write/<ownership-lane>`：WRITE按稳定所有权通道复用；通道由真实模块和变更契约动态产生。默认复用当前会话，只有写冲突或隔离环境要求时才创建，活动上限为两个。
- `assure`：ASSURE默认复用当前会话；独立性Gate要求时才建立一个只读验证绑定，不创建审核 Worktree。
- `control`：CONTROL绑定当前控制器，不为Planning/Merge/Document旧标签分别建会话。
- 浏览器、设备和E2E是绑定资源，不是第四类权威职责；按任务资源租约复用和释放。

Task ID、Candidate ID、base SHA 和 Gate 指纹记录在槽位内，用于证据隔离，但不改变槽位身份。writer身份额外包含 `ownership_lane`，不得用Task ID冒充新通道；同一通道正忙则排队，不同且已证明独立的通道可在预算内并行。

## 自动分派协议

```powershell
python <plugin-root>/scripts/dispatch_guard.py --root . observe --project-id PROJECT-A --task-id KG-001 --role "WRITE" --repository . --base-sha <sha> --api-result EMPTY
python <plugin-root>/scripts/dispatch_guard.py --root . bind --project-id PROJECT-A --task-id KG-001 --role "WRITE" --repository . --base-sha <sha> --thread-id <id> --runtime-state RUNNING --worktree <path>
python <plugin-root>/scripts/dispatch_guard.py --root . turn-guard --task-id KG-001 --thread-id <id> --host-status notLoaded --turn-status completed --turn-id <turn-id> --dispatch-id <dispatch-id> --operation-id <operation-id> --message-digest <sha256> --reserve
python <plugin-root>/scripts/dispatch_guard.py --root . turn-ack --thread-id <id> --operation-id <operation-id> --accepted
python <plugin-root>/scripts/dispatch_guard.py --root . pressure-observe --task-id KG-001 --backend-status ALIVE --observation-id <local-observation-id>
python <plugin-root>/scripts/dispatch_guard.py --root . stream-observe --thread-key <thread-key> --task-id KG-001 --event-count <count> --byte-count <bytes> --observation-id <local-observation-id>
```

总控只执行返回的动作：

- `CONTINUE_EXISTING` / `REUSE_THREAD`：继续或复用，禁止新建。
- `QUEUE` / `WAIT_PENDING`：入队等待，禁止新建。
- `BLOCK_QUERY`：禁止新建；无需独立运行时的工作在当前有界线程继续。
- `BLOCK_SCOPE_CONFLICT` / `BLOCK_RELEASE_PENDING`：等待重叠写通道或回收状态解除。
- `CREATE_THREAD`：唯一允许创建的状态，创建后必须立即绑定。
- `DISPATCH_RESERVED`：唯一允许向已有任务发送消息的状态；相同 operation 只返回已有预留，不能重复发送。
- `WAIT_ACTIVE` / `BLOCK_OUTSTANDING_DISPATCH`：目标已有活动 Turn 或未确认分派，只等待，不重发。
- `WAIT_ONCE` / `CHECKPOINT_AND_PAUSE`：宿主外层状态与最新 Turn 不一致；只复查一次，仍不一致就停止本轮总控。
- `QUEUE_ACTIVE_TURN_BUDGET`：项目已有两个活动 Turn；等待终态，不增加流式并发。
- `DRAIN_DESKTOP_PRESSURE` / `BLOCK_DESKTOP_PRESSURE`：宿主负载已进入熔断，只允许 Checkpoint、终态对账、归档和资源释放。
- `RECOVERY_PROBE_REQUIRED`：旧Turn处于 `INTERRUPTED_UNKNOWN` 或证据不足；禁止自动重发。

默认新增槽位数为零；硬上限仍为 `max_resident_slots=6`、`max_writer_slots=2`、`max_pending_creates=1`、`max_active_turns=2`。上限不是预建数量，也不能成为固定多Agent拓扑。CONTROL不得通过改Task ID、旧角色别名、所有权通道别名或base SHA绕开预算。

查询失败或超时只禁止创建替代桌面任务；已有会话或不要求隔离运行时的工作使用 `CURRENT_THREAD_BOUNDED` 降级继续。每个目标任务同一时刻最多一个未确认分派；普通工具失败在当前 Task 内记录并收敛，不得通过重复 `send_message`、循环 `wait/read` 或创建替代任务升级成桌面事件风暴。每个分派携带Task上下文路径和目标契约指纹，禁止所有角色共用最后写入的根上下文。

总控采用有界纪元而不是永久长会话：达到会话健康阈值后先Checkpoint，归档旧总控并验证运行时释放，再建立唯一新总控纪元。Task变化不触发总控轮换。

## 桌面压力熔断与后端中断恢复

只有长期总控、多会话调度、宿主重启或明显卡顿时才显式运行压力观察；普通单任务不执行该探针。压力只使用 Hiker 可验证的本地事实：当前 Task 热事件数与文件体积、当前 Turn 生命周期计数、活动 Lease、Stream 数值聚合、Trace 热索引和进程身份结果。旧 CLI 传入的宿主任务数、加载项目数、增量事件数或任务文件体积仅作兼容输入并被忽略，不能成为压力权威。

`GREEN` 允许最多两个受治理活动 Turn；`YELLOW` 把新并发收敛到一个；`RED` 拒绝新 Turn；`DRAINING` 只允许 checkpoint、verify、archive、release、recovery 和 complete。达到硬阈值、后端消失或后端刚重启时进入 `RED/DRAINING`；只有新的本地观测证明后端存活且活动 Turn、Stream 都已清零才解除，不能由模型自述清除。

State/Control 事实保持在 Task、Turn 和 Session 的权威状态文件中；Trace 使用有界热 segment，完整性校验后进入冷归档，日常状态只读索引。Stream 只记录计数、字节数与哈希链，不接收内容；Turn 终态写入有界摘要后删除热 Stream 聚合。摘要只含 Turn/Task ID、起止时间、状态、Operation、变更面、证据/Checkpoint 引用和哈希，不保存 Prompt、助手输出、源码或 delta。

后端退出前处于 `RESERVED / STARTED / ACTIVE / COMPLETING` 的Turn统一进入 `INTERRUPTED_UNKNOWN`。用原 operation ID 调用 `turn-recovery-probe`，脚本核对operation journal、Domain指纹、Checkpoint、Task和lease身份，只能得到 `RECOVERED`、`RETRYABLE` 或 `REVIEW_REQUIRED`；仅 `RETRYABLE` 允许用新dispatch identity建立新Turn，但不自动重发。不得把应用重启等价为Task失败、Task完成或允许盲目替代Turn。

插件只能约束自己创建和复用的桌面任务，不能直接修复 Electron 页面路由、布局循环或宿主后端内部退出。宿主任务归档与状态读取必须由 ChatGPT Desktop / Codex 提供的任务工具完成；本地脚本只验证登记的进程与 Worktree，不伪造宿主终态。

## 自动终态回收

普通任务完成：

1. 生成 Checkpoint，记录候选和证据 ID。
2. 自动释放文件锁、浏览器租约、端口、容器句柄等任务资源。
3. writer Worktree 必须为 `CLEAN` 或 `CLOSED`；未提交修改只能进入 `PAUSED_DIRTY`。
4. 调用 `complete`，项目仍继续时进入 `IDLE_REUSABLE`。

项目终态、用户停止或槽位不再需要：

1. 调用 `complete --project-terminal` 进入 `RELEASE_PENDING`。
2. 总控用桌面任务工具读取绑定的 `thread_id`，确认任务终态后执行归档，再读取一次获得去重的桌面观测 ID；不得用模型自述代替工具结果。
3. 对槽位登记的运行时 PID 和实际 Git Worktree 执行 `runtime_release_probe.py`。探针必须真实确认进程已退出、Worktree 已关闭或保持干净，并绑定当前槽位和桌面观测 ID；没有可观察 PID 时明确 `BLOCKED`，不得填写布尔值冒充验证。
4. 使用探针返回的 `probe_id` 调用 `release-ack --probe-id <id>`；只有桌面归档、进程释放和 Worktree 处置同时成立才进入 `RELEASED`。
5. 仅归档成功时保持 `ARCHIVED_RUNTIME_UNVERIFIED`。最多进行一次延迟重查；仍不可观测则保留阻断和证据，不请求用户确认、不创建替代会话，也不进入反复治理。

自动回收不授权强杀进程、强制删除 Worktree、删除分支或丢弃脏改动。遇到这些情况只保存证据并进入安全收敛流程。
