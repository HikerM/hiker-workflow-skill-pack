# 智能软件工程平台 5.14 验证报告

生成版本：`5.14.0+codex.20260818144314`

## 已执行结果

- 五插件全量单元回归：108项全部通过。
- 路由行为评测：95项正向与42项负向全部通过。
- 发布级Skill一致性审核：5个插件、42个Skill全部通过；结构、路由、职责、权限、可用性和性能均无错误、无警告。
- 发布包：5个当前版本ZIP已生成；旧版本ZIP已从发布目录移除。
- 插件作者与开发者标识：统一为 Hiker。
- 公开内容审计：扫描566个受版本控制或待提交文本条目及发布包内部文本，0项敏感信息发现。
- 仓库结构与公开文档事实验证：通过；仓库只包含两套能力包。
- 桌面软件等价重建1.3.0原生包验证：通过，0错误、0警告。
- PowerShell质量门禁：Windows PowerShell 5.1与PowerShell 7静态检查均为0发现；两种运行时的LF和CRLF四组合执行全部通过。
- 路由冷进程性能：20次，P95为244.85毫秒，低于500毫秒门限。

## 5.14 新增门禁

- `context_budget.py`：按小型、标准和大型项目限制当前工作集，不扫描全部任务、归档、历史或Skill正文。
- `state_consistency.py`：使用源码身份和Manifest哈希进行L1–L4分级恢复，不删除需求、Task、决定和证据原件。
- `implementation_guard.py`：同一能力只允许一个权威活动实现和一个权威状态写入者，迁移必须有退出条件。
- `delivery_hygiene.py`：阻断正式运行路径中的默认Demo、Mock、Fixture、占位身份和用户可见内部诊断。
- `audit_public_content.py`：审核源码、文档和ZIP内部文本中的个人、公司、真实项目、会话、凭据和本机路径。

## 发布包摘要

| 插件 | 文件 | SHA-256 |
|---|---|---|
| 智能工程核心 | `dist/ai-engineering-core-5.14.0.zip` | `aa5944c7b733a27068bf289a9120fe946515163b46d706440340db77ba2627d5` |
| 质量、风险与发布 | `dist/ai-engineering-quality-5.14.0.zip` | `1493daaba289ae871d9b4bca3a1acdb07a590b244376b2dc01ff2f6f921d678b` |
| 客户端工程 | `dist/ai-engineering-unity-5.14.0.zip` | `99ed37142392de2eecec088bc942a29d9e4035ccda0b22c4015ce1546685dda3` |
| 浏览器端与服务端工程 | `dist/ai-engineering-web-5.14.0.zip` | `52cb17f6a1d11226959abfebebaf30f9a075f786a2e0de0495fb55d411cbe902` |
| 工作区与多会话协作 | `dist/ai-engineering-workspace-5.14.0.zip` | `715855feda4ebb23ec1ed707edd973bab7b66fe32a5c017e56b4042484f5eb97` |

本报告不包含本机安装路径、用户信息、公司信息、真实项目信息或会话标识。
