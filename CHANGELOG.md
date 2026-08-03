# Changelog

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
