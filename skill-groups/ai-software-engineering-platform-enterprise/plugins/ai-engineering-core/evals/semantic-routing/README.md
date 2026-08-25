# 宿主语义路由评估协议

本目录评估 ChatGPT Desktop / Codex 的语义选择，不实现文本到 Skill 的本地路由器。

- `cases.json`：交给宿主的语料，只含 ID、请求和有界项目事实，不含答案或用例分类。
- `gold.json`：独立评分答案和阈值，不得放进宿主选择载荷。
- `host-baseline.json`：当前宿主基于紧凑语义目录给出的结构化选择。
- `tools/evaluate_semantic_routing.py`：只比较结构化 ID、调用现有守门器并计算指标；不按请求文字推导 Skill。

执行新一轮评估时，先固定 `cases.json` 和语义目录，再只把 cases 交给当前 ChatGPT/Codex。宿主最多返回两个当前候选，第三项进入 `deferred`。完成选择后才由评分步骤读取 `gold.json`。禁止把答案键、关键词映射或候选提示拼入选择载荷。

基准文件只含合成工程请求，不保存真实 Prompt、聊天、源码或凭据。评估不会调用外部模型 API，也不会启动后台 Runtime。

仓库内 `host-baseline.json` 是载荷隔离的当前宿主校准结果。若答案键与预测产物在同一开发会话中形成，必须标记 `payload-separated-same-development-session`，不能冒充跨会话独立盲测；后续可在新的当前宿主会话里只提供 `cases.json`，生成预测后再评分。
