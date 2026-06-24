# Hiker Workflow Skill Pack v0.2

This pack turns Hiker's recurring Codex workflows into installable, project-level skills.

It is built for engineering governance work: Codex thread review, staged phase acceptance, evidence-first testing, contract audits, NodeTs execution pipeline checks, Unity/Codex guardrails, design output delivery, and architecture consulting.

## Suitable Projects

- Codex App projects that need repeatable review and acceptance rules.
- Web/API systems with contract, DTO, DB, queue, provider, and billing boundaries.
- Unity projects worked through Codex App or Unity MCP.
- PPT/image/SVG/PDF/Excel delivery tasks where files and visual QA matter.

## Not Suitable For

- Global installation without project-level review.
- Fully automatic production DB/provider/billing operations.
- Replacing a project's existing `AGENTS.md` or local rules without a merge decision.

## Quick Install

Dry run first:

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
```

Install core skills with backup and merged `AGENTS.md` block:

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills core -MergeAgents
```

Install all skills:

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills all -MergeAgents
```

Validate the pack or a target project:

```powershell
.\VALIDATE.ps1 -Root .
.\VALIDATE.ps1 -Root C:\path\to\project
```

Uninstall dry run:

```powershell
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
```

Restore a backup:

```powershell
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -Apply -RestoreBackup 20260624-210000
```

## Safety Defaults

- Default install and uninstall mode is DryRun.
- `-Apply` is required before any write.
- Existing skills are skipped unless `-Force` is provided.
- Existing `AGENTS.md` is not overwritten by default.
- `-MergeAgents` appends or replaces only the Hiker marked block.
- Apply mode creates a backup under `.backups/hiker-workflow-pack/<timestamp>/`.

## How To Use In Codex

Ask Codex to read `hiker-workflow-router` first when the task is complex or governance-related. The router chooses the narrowest workflow skill and avoids heavy process for simple requests.

For example:

```text
请先按 hiker-workflow-router 判断该用哪个 skill，再复核这段 Codex 线程结果。
```

## FAQ

**Will this overwrite my project rules?**  
No by default. Use `-MergeAgents` to append/update the marked Hiker block, or `-Force` only when you explicitly want replacement behavior.

**Can I install only the review skills?**  
Yes. Use `-Skills codex-thread-review,project-phase-review,evidence-first-testing`.

**Does uninstall remove my original skills?**  
No. It removes only skills recorded in the install marker created by this pack.
