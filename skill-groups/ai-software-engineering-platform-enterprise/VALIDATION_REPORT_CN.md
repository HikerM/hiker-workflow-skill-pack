# 智能软件工程平台 5.12 桌面端验证报告

生成版本：`5.12.0+codex.20260814102226`

验证日期：2026-08-14

## 结论

- 发布包、源码结构、行为回归、路由 Eval 与五插件全量 Skill 一致性审核全部通过。
- 本机五个插件的仓库源码、个人安装目录、5.12 版本缓存三层哈希全部一致，五插件启用配置和全局规则一致。
- 文件、缓存和配置已部署生效；已经运行的旧任务仍可能保留创建时的 Skill 快照，不能把文件一致冒充为旧任务已经热刷新。新任务会读取新的非阻塞决策规则，旧任务需在上下文恢复时重新读取全局规则。

## 发布级审核

- 插件：5/5。
- 原子 Skill：42/42。
- 唯一隐式入口：智能工程轻量路由；其余41个能力按需读取或手动选择。
- 一致性检查：结构、路由、归属、权限、可用性、性能均为0错误、0警告。
- 路由行为 Eval：正向95/95，负向38/38。
- 单元回归：核心37、质量22、客户端7、浏览器端与服务端10、工作区31，共107/107通过。
- 集成冒烟：Skill一致性、状态恢复、有界记忆、长链路收敛、Worktree治理、完整变更、安装、缓存保留和全局规则等19项全部通过。
- 三套仓库总验证：全部通过；另外两套 Skill 内容未被修改。
- 本地冷进程路由性能：中位数93.88ms，P95 117.44ms，低于500ms门限。

## 5.12 新增门禁

- 平台、架构、部署、数据、安全、核心技术栈和公共契约变化自动生成决策 Checkpoint，记录候选、证据、风险、回退与选择后非阻塞继续，不弹出审批。
- 从零项目状态使用 `decision_mode=automatic_non_blocking` 与 `checkpoint_status=AUTO_RECORD_REQUIRED`；存量对账命中关键影响后自动落为 `AUTO_RECORDED`，不产生 `PENDING/REQUIRED` 审批态。
- 发布级审核会扫描全局规则、从零规划、存量对账和架构挑战，发现旧式阻塞审批措辞即失败。
- 只有 Master Agent 可以创建、复用和回收桌面任务与 Worktree，执行角色不得自行制造替代任务。
- 会话槽以 `project_id + repository + role_family` 为稳定身份；Task、Candidate 和 base SHA 是槽内工作项，不再触发新任务。
- Developer、Fix、Repair 复用 writer；Review、Test、Reverify 复用 assurance。
- 默认每项目最多4个常驻角色槽、同一时刻最多1个 pending create；槽忙时排队。
- 普通任务终态自动 Checkpoint、释放锁和任务资源并进入 `IDLE_REUSABLE`，无需用户确认。
- 项目终态自动归档并验证本地运行时释放；仅归档成功时保持 `ARCHIVED_RUNTIME_UNVERIFIED` 并自动重查。
- API错误、查询超时、`SETUP_PENDING`、脏 Worktree 或回收未完成时禁止创建替代任务。
- 自动回收不授权强杀进程、强删 Worktree、删除分支或丢弃未提交改动。

## 安装核验

- 安装目录：`C:\Users\Administrator\.codex\plugins\<插件>`。
- 5.12 缓存：`C:\Users\Administrator\.codex\plugins\cache\personal-ai-engineering-marketplace\<插件>\5.12.0+codex.20260814102226`。
- 五插件启用：5/5，方式为 `desktop-config`。
- 三层哈希：5/5一致，`mismatches=[]`。
- 全局自动路由与总控固定槽规则：一致。
- 最终安装备份：`C:\Users\Administrator\.codex\plugins-backup\20260814T102417Z`。
- 首次安装已把阻塞式决策审批替换为自动、非阻塞 Checkpoint；最终复装状态为 `unchanged`，证明全局规则幂等一致。

## 运行中任务刷新

- 已打开任务不会被安装器强制替换创建时的 Skill 快照；上下文恢复时应重新读取 `C:\Users\Administrator\.codex\AGENTS.md` 和实际 Skill 缓存路径。
- 不允许为了刷新插件新建 Worktree。若旧任务无法重新载入 Skill，只完成当前最小原子步骤并落盘，再由现有固定角色槽或新任务接管。
- 新任务是验证运行时加载的安全边界。只有新任务仍指向旧缓存时才需要重启桌面应用。

## 发布包

- 已生成五个 `5.12.0` ZIP，并移除发布目录中的五个 `5.11.0` ZIP。
- `SHA256SUMS.txt` 已更新。
- 生成发布包前后均执行五插件全部 Skill 一致性审核；失败会阻断发布。

## 能力边界

本报告证明插件结构、路由、脚本、发布包、安装文件与配置正确，不证明任意业务项目已经通过真实端到端验收。对具体项目仍须建立 Task、变更契约、候选版本与对应层级的运行证据。
