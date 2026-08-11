---
name: desktop-reconstruction-discovery
description: 用于已授权桌面软件等价重建的G0至G4阶段，完成授权范围、环境证据、原软件技术指纹、入口窗口页面控件、交互状态机、功能数据权限异常与覆盖追踪；只做发现和规格，不生成正式实现或声称已完成软件。
---

# 桌面重建发现与规格

共享资源位于同一 skills 根下的 `desktop-app-reconstruction-zh` 包。按当前门禁只读对应参考：G0读01，G1读03，G1-T读13，G2/G3读04，G4读05与15；字段不明确时才读18。

依次建立授权与范围、环境和证据索引、带置信度的源技术指纹、入口/窗口/页面/控件/快捷键库存、交互状态机、功能/数据/角色/异常清单及端到端追踪。P0/P1必须有至少两个独立发现渠道或正式豁免，连续两轮无新增核心项后才可关闭发现。

只运行当前门禁需要的 `init_project.py`、`index_evidence.py`、`detect_project_stack.py`、`validate_discovery.py`、`calculate_coverage.py`、`validate_traceability.py` 或 `detect_orphan_items.py`。输出证据等级、产物、门禁结果、未知项和下一唯一动作。
