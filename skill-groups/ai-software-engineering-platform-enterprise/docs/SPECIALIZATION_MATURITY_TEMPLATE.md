# 专项工程能力成熟度模板

专项不是新的 Skill，也不是常驻 Prompt。它是在现有 Skill 已按语义选中、项目证据确认技术族后，显式运行的确定性检查剖面。

## 必需构成

每个专项必须同时提供：

1. `rules`：与现有 Skill 职责一致的冷加载规则引用；
2. `identity`：从锁文件、Manifest、工程文件或运行时文件提取真实技术与版本，证据不足时返回 `unknown` 或 `BLOCKED`；
3. `dimensions`：至少六个与该技术真实失败模式对应的检查维度；
4. `evidence_command`：按需运行、默认只输出 stdout、不写 `.ai` 的本地脚本；
5. `positive_case`：能够以真实项目结构证明全部必需维度；
6. `negative_case`：至少证明身份缺失、边界违规或关键失败模式会被阻断；
7. `regression_test`：进入插件测试发现路径；
8. `boundedness`：明确最大深度、最大文件数、跳过目录和截断策略。

## 统一输出

输出至少包含：`schema_version`、`profile`、`result`、`identity`、`dimensions`、`source_fingerprint`、`bounded_scan`、`storage_policy`。

维度状态只使用：

- `PASS`：存在足够工程证据且未发现该维度问题；
- `GAP`：未观察到足够证据，不能推断为通过；
- `FAIL`：发现确定性高风险反例；
- `BLOCKED`：缺少身份、关键工程文件或扫描完整性，禁止猜测。

总结果按 `BLOCKED → FAIL → PASS_WITH_GAPS → PASS` 收敛。检查器只保存相对路径、版本、状态、计数和哈希，不保存完整源码、Prompt 或聊天。

## 性能与路由边界

- 不挂载 Hook，不进入 FAST/PROJECT 默认路径，不写默认 Prompt。
- 不扫描未选择的技术族；普通项目不得加载全部专项规则。
- 检查脚本不得选择 Skill、推断用户意图或调用模型 API。
- 新专项先登记 `specialization-maturity-profiles.json`，通过成熟度审计后才能作为正式证据能力声明。
