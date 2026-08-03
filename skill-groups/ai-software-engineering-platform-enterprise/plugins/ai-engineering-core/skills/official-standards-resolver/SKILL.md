---
name: official-standards-resolver
description: 在项目智能初始化后，根据 .ai/context/tech-stack.json 中的真实版本，查阅对应语言、框架和平台的官方文档，形成项目专属编码规范。不得使用无版本依据的通用模板冒充官方规范。
---

# 官方规范解析

## 前置条件

必须已有 `.ai/context/tech-stack.json`。缺失时调用“项目智能初始化”，不要自行重复全仓库扫描。

## 在线模式

1. 读取 `references/official-docs-registry.json` 生成检索目标。
2. 只优先使用语言、框架、包管理器和平台的官方文档或正式标准。
3. 对版本敏感规则记录：技术、检测版本、文档版本、来源、访问日期和适用范围。
4. 将结论写入：
   - `.ai/context/standards.json`；
   - `docs/engineering/PROJECT_CODING_STANDARD.md`。
5. 项目既有 ADR 和锁定决策优先于一般最佳实践。

## 离线模式

运行 [resolve_standards.py](../../scripts/resolve_standards.py) 生成待核验清单。不得声称已经查阅在线手册。

## 禁止

- 把 B/S 写死为 Vue/React；
- 把 C/S 写死为 Unity；
- 忽略实际主版本；
- 直接复制大段受版权保护的文档；
- 因“最佳实践”擅自改架构。
