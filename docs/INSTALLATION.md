# Installation

## Recommended Mode

Install per project, not globally. Keep the package outside the target project and install into the project's `.agents/skills` folder.

## Parameters

- `-TargetRoot <path>`: required project root.
- `-DryRun`: plan only. This is the default when `-Apply` is not provided.
- `-Apply`: write changes.
- `-Backup`: accepted for explicitness; apply mode creates a backup before writes.
- `-Skills core|all|comma-list`: install core skills, all skills, or selected skills.
- `-MergeAgents`: append/update only the marked Hiker block in `AGENTS.md`.
- `-Force`: overwrite existing skill folders or `AGENTS.md` where applicable.

## Dry Run

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
```

## Install Core

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills core -MergeAgents
```

## Install All

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills all -MergeAgents
```

## Install Selected Skills

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills codex-thread-review,project-phase-review -MergeAgents
```

## Backup Location

Apply mode writes backups to:

```text
<TargetRoot>\.backups\hiker-workflow-pack\<timestamp>\
```

## Validation

The installer automatically runs:

```powershell
.\VALIDATE.ps1 -Root <TargetRoot>
```

## Uninstall

```powershell
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -Apply
```

## Restore Backup

```powershell
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -Apply -RestoreBackup 20260624-210000
```
