<!-- document_status: DRAFT -->
# 项目代理协作规则

1. 开始工作前读取 `00_control/PROJECT.yaml`、`STATUS.yaml`、`DECISIONS.md` 和当前门禁文件。
2. 只从 `current_primary_action` 继续，不重复已完成工作。
3. 所有实现必须关联范围、库存、规格和测试 ID；禁止静态演示、假接口和固定成功值。
4. 修改前确认权威分支、提交和允许修改范围；多代理使用独立分支或 worktree。
5. 每轮更新 STATUS、CHANGELOG、TRACEABILITY_MATRIX 和测试结果。
6. 用户中断或改变方向时，先记录当前安全状态和受影响门禁，再按新指令继续。
7. 未通过 G5-T 不进行大规模正式编码；未通过全门禁不宣称发布完成。
