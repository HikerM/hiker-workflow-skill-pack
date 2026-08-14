# 会话与运行时生命周期

本契约只由 Master Agent 执行。Developer、Review、Test 等角色不得自行创建桌面任务、Worktree 或替代会话。

## 固定槽位

槽位键是 `project_id + repository + role_family`：

- `writer`：Developer、Fix、Repair，共用一个写会话和同一条返工 Worktree 链。
- `assurance`：Review、Test、Reverify，共用一个只读验证会话；默认读取冻结候选，不创建审核 Worktree。
- `control`：Planning、Merge、Document；只有确有隔离运行时需要时才创建。
- `browser`：浏览器/E2E；复用同一受控浏览器槽。
- `master`：只保留决策、队列、状态与回收，不承载大日志。

Task ID、Candidate ID、base SHA 和 Gate 指纹记录在槽位内，用于证据隔离，但不改变槽位身份。新任务到来时优先复用 `IDLE_REUSABLE`；槽位正忙则排队，不创建第二个同族会话。

## 自动分派协议

```powershell
python <plugin-root>/scripts/dispatch_guard.py --root . observe --project-id PROJECT-A --task-id KG-001 --role "Developer Agent" --repository . --base-sha <sha> --api-result EMPTY
python <plugin-root>/scripts/dispatch_guard.py --root . bind --project-id PROJECT-A --task-id KG-001 --role "Developer Agent" --repository . --base-sha <sha> --thread-id <id> --runtime-state RUNNING --worktree <path>
```

总控只执行返回的动作：

- `CONTINUE_EXISTING` / `REUSE_THREAD`：继续或复用，禁止新建。
- `QUEUE` / `WAIT_PENDING`：入队等待，禁止新建。
- `BLOCK_QUERY` / `BLOCK_RELEASE_PENDING`：先修复查询或回收状态。
- `CREATE_THREAD`：唯一允许创建的状态，创建后必须立即绑定。

默认 `max_resident_slots=4`、`max_pending_creates=1`。总控不得通过改 Task ID、角色别名或 base SHA 绕开预算。

## 自动终态回收

普通任务完成：

1. 生成 Checkpoint，记录候选和证据 ID。
2. 自动释放文件锁、浏览器租约、端口、容器句柄等任务资源。
3. writer Worktree 必须为 `CLEAN` 或 `CLOSED`；未提交修改只能进入 `PAUSED_DIRTY`。
4. 调用 `complete`，项目仍继续时进入 `IDLE_REUSABLE`。

项目终态、用户停止或槽位不再需要：

1. 调用 `complete --project-terminal` 进入 `RELEASE_PENDING`。
2. 总控自动归档对应桌面任务并检查其本地工具运行时是否真正退出。
3. 调用 `release-ack` 记录归档与运行时证据；只有两者成立才进入 `RELEASED`。
4. 仅归档成功时保持 `ARCHIVED_RUNTIME_UNVERIFIED`，总控自动重查，不请求用户确认，也不得继续制造替代会话。

自动回收不授权强杀进程、强制删除 Worktree、删除分支或丢弃脏改动。遇到这些情况只保存证据并进入安全收敛流程。
