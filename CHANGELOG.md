# Changelog

## 0.2.0

- Reworked the pack into a project-level Hiker Workflow Skill Pack.
- Renamed the router skill to `hiker-workflow-router`.
- Added `nodets-execution-pipeline-guardrails`.
- Standardized every `SKILL.md` with required sections and `owner: Hiker`.
- Added project-safe `INSTALL.ps1`, `UNINSTALL.ps1`, `VALIDATE.ps1`, and dependency-free `scripts/validate_skills.py`.
- Added docs and examples for installation, usage, skill routing, safety rules, thread review, phase review, and NodeTs execution pipeline checks.
- Added dry-run-first install behavior, backup support, merge-only `AGENTS.md` handling, install marker, validation, and rollback flow.
