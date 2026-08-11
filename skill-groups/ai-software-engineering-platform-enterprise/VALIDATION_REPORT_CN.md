# Enterprise 5.2 本地验证报告

生成版本：5.2.0

## 确定性验证

- 插件清单：5 个
- Skill 数量：由验证器从插件目录动态统计为30个
- 新增 `bounded-context-memory` 及本次修改的 `context-recovery`、`interruptible-task-control`、`project-state-manager`：官方 `quick_validate.py` 全部通过
- 5 个插件：官方 `validate_plugin.py` 全部通过
- 插件结构与图标：通过
- Manifest：已移除当前规范不接受的 `hooks` 字段；状态与事件脚本保留为显式调用工具
- Python 编译：通过
- Eval 基础样例：每个插件至少 10 条并包含负向样例
- 单元测试：通过
- 单元测试明细：Core 9、Quality 11、C/S与Unity 7、Web 6、Workspace 10，共43/43通过
- Python 3.10 兼容：`tomllib` 缺失时回退 `tomli`，无依赖时安全降级；`pyproject.toml` 探测测试通过
- UI 反模板静态信号：Bootstrap、重复卡片、硬编码间距、装饰效果与 Token 证据测试通过
- 集成 Smoke：通过
- 完整本地变更集：已验证暂存、未暂存、未跟踪同时存在
- Git Worktree：已验证受保护分支、正确基线、任务绑定、创建、暂停和安全移除
- 多Agent治理：已验证B/S前后端及Qt、.NET、Flutter、Tauri等C/S客户端/服务端/契约路由、PROJECT_STATE/CURRENT_CONTEXT、Task状态机、暂停/恢复/插入、Unity与migration锁冲突、功能闭环和合并门禁
- C/S技术版本：已验证WPF从TargetFramework、Qt从CMake、React Native从依赖清单获取版本；客户端收据同时输出技术、版本、证据与version_gaps，缺失版本不会被写死。
- 运行性能：三组均使用轻量入口；单次只选择一个主组、当前技术族和当前阶段，不默认重扫全仓、加载全部参考、建立图谱或运行全量测试。
- 有界上下文保护：已验证12000字符活动工作集、6500字符会话注入、每节条目上限、近期/里程碑checkpoint双限额、有界压缩账本、SHA-256连续哈希链和恢复回执；Task、正式决定、Git与验收证据不进入清理范围
- 长期性能：已验证已关闭任务摘要索引固定保留200项，额外摘要进入计数和哈希链，205个完整Task文件仍全部保留；日常PROJECT_STATE渲染不扫描全部历史Task。
- 图谱限流：已验证节点上限
- 测试命令发现：已验证读取项目真实 package scripts
- 本机重新安装：5个插件均通过个人Marketplace安装并显示为 `installed: true, enabled: true`，版本为 `5.2.0+codex.20260811063559`；01号包含5个Skill，03号显示名为“03 C/S客户端工程”。
- 三组本机安装：第一组9个用户级Skill已安装；第三组1个总路由与4个原子Skill已安装并通过安装后校验。
- 全局自动应用：已把带标记治理区块合并到 `C:\Users\Administrator\.codex\AGENTS.md`，要求任务开始/结束展示实际插件与Skill回执
- 分发安装器：已在隔离用户目录验证保留原AGENTS规则、默认写入自动应用/回执、重复安装不重复、退出参数生效、卸载只删除托管区块。
- 插件自动启用：已在隔离用户目录通过显式桌面Codex CLI验证5/5插件自动安装成功；无可执行CLI时输出 `manual-required` 和手动命令。

## UI 视觉与反模板验证

- `web-ui-design` 在编码前强制要求项目专属设计系统、语义色彩、间距尺度、组件复用契约、视觉焦点、疏密节奏、签名元素与适度微交互。
- `web-component-implementation` 在缺少上述设计契约或独立复审仍有 P0/P1 时阻断编码。
- `web-quality-review` 和 `design-readiness-review` 对普通后台骨架、Bootstrap 式默认视觉、重复卡片汤和无焦点的单调等权布局至少给出 HIGH/P1 并阻断新增或重做 UI。
- 视觉丰富度不能靠无语义渐变、阴影、发光、玻璃效果或动效伪造；必须服务识别、比较、定位、反馈或空间连续性。

## 验证器输出

```json
{
  "ok": true,
  "plugin_count": 5,
  "skill_count": 30,
  "errors": [],
  "warnings": []
}
```

## 设计收敛前向验证

审查者只获得 Skill、模拟项目目录和只读审核任务，没有收到预期问题、预期等级或预期结论。

- 简单 CRUD 管理系统：首次独立复审发现 P1=5，增量整改后仍自行发现 P1=1，再次定向整改后达到 P0=0、P1=0 并 `PASS`；验证轮数由问题是否清零决定。
- 复杂编辑/画布/实时/发布系统：动态识别高复杂度表面，独立复审得到 P0=4、P1=7、P2=1 并 `BLOCKED`，主动发现数据丢失、服务端授权、内部标识泄露、发布/回滚边界和计数型自检盲区。
- 新增批量导入要求的增量风险场景：识别旧设计 `PASS` 已失效，只重开导入链及共享消费者，得到 P0=2、P1=6、P2=2，并发现只更新 UI、未同步数据/API/权限/测试的表面整改。

前向验证同时确认：简单项目可在一轮或少量定向整改后结束；复杂项目持续到 P0/P1 清零或明确阻塞；自检不能替代独立复审；新增要求不会默认使无关设计全量失效。

## 集成测试输出

```json
{
  "ok": true,
  "checks": [
    {
      "name": "bootstrap",
      "ok": true
    },
    {
      "name": "precompact",
      "ok": true
    },
    {
      "name": "recovery",
      "ok": true
    },
    {
      "name": "bounded-memory",
      "ok": true
    },
    {
      "name": "governed-worktree",
      "ok": true
    },
    {
      "name": "complete-change-set",
      "ok": true
    },
    {
      "name": "risk-tags",
      "ok": true
    },
    {
      "name": "graph-limit",
      "ok": true
    },
    {
      "name": "real-commands",
      "ok": true
    },
    {
      "name": "personal-install",
      "ok": true
    },
    {
      "name": "global-auto-application",
      "ok": true
    },
    {
      "name": "global-rules-idempotent",
      "ok": true
    },
    {
      "name": "global-rules-safe-uninstall",
      "ok": true
    },
    {
      "name": "global-rules-opt-out",
      "ok": true
    },
    {
      "name": "repo-install",
      "ok": true
    }
  ],
  "failed": []
}
```

## 未替代的真实环境验证

本地测试和本机插件列表不能替代：其他账号或客户端版本中的实际安装、真实 Unity Editor 构建和具体项目 CI。详见 `LIMITATIONS_CN.md`。
