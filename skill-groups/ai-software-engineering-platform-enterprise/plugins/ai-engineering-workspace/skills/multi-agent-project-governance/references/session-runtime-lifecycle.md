# 会话与运行时生命周期

本契约只由 Master Agent 执行。Developer、Review、Test 等角色不得自行创建桌面任务、Worktree 或替代会话。

## 固定槽位

槽位键是 `project_id + repository + role_family`：

- `writer/<ownership-lane>`：Developer、Fix、Repair按稳定所有权通道复用；通道由真实模块和变更契约动态产生，不限于frontend/backend。规划态可登记最多8个，默认最多两个活动writer通道，同一通道共用一个写会话和返工Worktree链。
- `assurance`：Review、Test、Reverify，共用一个只读验证会话；默认读取冻结候选，不创建审核 Worktree。
- `control`：Planning、Merge、Document；只有确有隔离运行时需要时才创建。
- `browser`：浏览器/E2E；复用同一受控浏览器槽。
- `master`：只保留决策、队列、状态与回收，不承载大日志。

Task ID、Candidate ID、base SHA 和 Gate 指纹记录在槽位内，用于证据隔离，但不改变槽位身份。writer身份额外包含 `ownership_lane`，不得用Task ID冒充新通道；同一通道正忙则排队，不同且已证明独立的通道可在预算内并行。

## 自动分派协议

```powershell
python <plugin-root>/scripts/dispatch_guard.py --root . observe --project-id PROJECT-A --task-id KG-001 --role "Developer Agent" --repository . --base-sha <sha> --api-result EMPTY
python <plugin-root>/scripts/dispatch_guard.py --root . bind --project-id PROJECT-A --task-id KG-001 --role "Developer Agent" --repository . --base-sha <sha> --thread-id <id> --runtime-state RUNNING --worktree <path>
```

总控只执行返回的动作：

- `CONTINUE_EXISTING` / `REUSE_THREAD`：继续或复用，禁止新建。
- `QUEUE` / `WAIT_PENDING`：入队等待，禁止新建。
- `BLOCK_QUERY`：禁止新建；无需独立运行时的工作在当前有界线程继续。
- `BLOCK_SCOPE_CONFLICT` / `BLOCK_RELEASE_PENDING`：等待重叠写通道或回收状态解除。
- `CREATE_THREAD`：唯一允许创建的状态，创建后必须立即绑定。

默认 `max_resident_slots=6`、`max_writer_slots=2`、`max_pending_creates=1`。总控不得通过改 Task ID、角色别名、所有权通道别名或 base SHA 绕开预算。

查询失败或超时只禁止创建替代桌面任务；已有会话或不要求隔离运行时的工作使用 `CURRENT_THREAD_BOUNDED` 降级继续。每个分派携带Task上下文路径和目标契约指纹，禁止所有角色共用最后写入的根上下文。

总控采用有界纪元而不是永久长会话：达到会话健康阈值后先Checkpoint，归档旧总控并验证运行时释放，再建立唯一新总控纪元。Task变化不触发总控轮换。

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
