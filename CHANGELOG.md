# Changelog

## 0.6.0

- Expanded plugin 03 from Unity-only coverage to a general C/S client layer for Unity, Qt, .NET desktop, Electron/Tauri, Flutter, Android, Apple native, React Native, Java desktop, and embedded HMI.
- Added evidence-based C/S language, runtime, framework, SDK, build-tool, and version detection; missing exact versions remain explicit gaps instead of hard-coded defaults.
- Added four C/S atomic Skills and preserved all three Unity-specific Skills, increasing Enterprise to 29 Skills.
- Applied lightweight routing and lazy phase loading across all three repository groups; the desktop reconstruction group now has one router plus four atomic phase Skills.
- Added cross-group routing receipts and performance budgets so installed capabilities are not all loaded into one conversation.

## 0.5.1

- Made the Enterprise personal installer automatically merge the managed global Codex governance block while preserving and backing up existing `~/.codex/AGENTS.md` content.
- Added automatic five-plugin activation through a discovered or explicitly supplied Codex CLI, with honest manual-command fallback when no runnable CLI is available.
- Added idempotent reinstall, opt-out flags, and safe uninstall of only the installer-owned global instruction block.
- Extended integration coverage for automatic routing rules, visible plugin receipts, reinstall idempotency, opt-out behavior, and safe uninstall.

## 0.5.0

- Upgraded AI Software Engineering Platform Enterprise to 5.0.0 with 5 plugins and 25 Skills while preserving all three independent groups.
- Rebuilt workspace collaboration as a seven-role multi-Agent engineering control plane with project/task state, context snapshots, file locks, Git governance, multi-project isolation, acceptance closure, and visible plugin receipts.
- Added global Codex/ChatGPT Desktop auto-application instructions without expanding push, merge, deploy, or production-write authority.

## 0.4.0

- Upgraded AI Software Engineering Platform Enterprise to 4.2.0 while preserving the repository's three independent Skill groups.
- Added enforceable anti-template UI rules: no generic admin-dashboard skeletons, Bootstrap-style default visuals, or repetitive card soup.
- Required project-specific design systems, semantic color tokens, spacing scales, component reuse contracts, visual focus, rhythm, signature elements, and purposeful micro-interactions before implementation.
- Extended independent design readiness and read-only Web quality review to block monotonous or template-driven UI, and enhanced `web_audit.py` with Bootstrap, repeated-card, hardcoded-spacing, decorative-effect, and Token-evidence signals.
- Fixed Python 3.10 TOML detection compatibility and made root `VALIDATE.ps1` resolve the repository root correctly when invoked from another directory.

## 0.3.1

- Upgraded AI Software Engineering Platform Enterprise to 4.1.0 with 5 plugins and 18 Skills.
- Enhanced `web-ui-design` for requirement-driven page discovery, dynamic complexity assessment, deep contracts for complex surfaces, identifier isolation, and lifecycle consistency.
- Added the independent, read-only `design-readiness-review` gate with semantic traceability, P0/P1 blocking, confidence, unknowns, and next-stage decisions.
- Enhanced `full-change-risk-review` with incremental design impact analysis, re-review triggers, and cross-layer remediation checks.
- Added simple CRUD and complex editor/publishing forward-validation scenarios and refreshed repository indexes, documentation, validation evidence, and plugin archives.

## 0.3.0

- Expanded the repository from one pack into three clearly separated Skill groups.
- Preserved the original Hiker workflow group at `.agents/skills/` with 9 Skills and backward-compatible project installers.
- Added AI Software Engineering Platform Enterprise 4.0 as an independent group with 5 plugins and 17 Skills.
- Added Desktop App Reconstruction ZH 1.1 as an independent, validated desktop reconstruction Skill.
- Added detailed Chinese documentation, a 27-Skill index, separate installation procedures, usage examples, and group-selection guidance.
- Extended repository validation to run the native validators for all three groups.

## 0.2.0

- Reworked the pack into a project-level Hiker Workflow Skill Pack.
- Renamed the router skill to `hiker-workflow-router`.
- Added `nodets-execution-pipeline-guardrails`.
- Standardized every `SKILL.md` with required sections and `owner: Hiker`.
- Added project-safe `INSTALL.ps1`, `UNINSTALL.ps1`, `VALIDATE.ps1`, and dependency-free `scripts/validate_skills.py`.
- Added docs and examples for installation, usage, skill routing, safety rules, thread review, phase review, and NodeTs execution pipeline checks.
- Added dry-run-first install behavior, backup support, merge-only `AGENTS.md` handling, install marker, validation, and rollback flow.
