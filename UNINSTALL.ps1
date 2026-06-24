[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,

    [switch]$DryRun,
    [switch]$Apply,
    [string]$RestoreBackup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Apply -and $DryRun) {
    throw "Use either -Apply or -DryRun, not both."
}

$IsDryRun = -not $Apply
if (-not (Test-Path -LiteralPath $TargetRoot)) {
    throw "TargetRoot does not exist: $TargetRoot"
}

$TargetRoot = (Resolve-Path -LiteralPath $TargetRoot).Path
$TargetAgentsRoot = Join-Path $TargetRoot ".agents"
$TargetSkillsRoot = Join-Path $TargetAgentsRoot "skills"
$TargetAgentsFile = Join-Path $TargetRoot "AGENTS.md"
$MarkerFile = Join-Path $TargetAgentsRoot "hiker-workflow-pack.installed.json"
$BackupBase = Join-Path $TargetRoot ".backups\hiker-workflow-pack"

$SkillsToRemove = @()
if (Test-Path -LiteralPath $MarkerFile) {
    $Marker = Get-Content -Raw -LiteralPath $MarkerFile | ConvertFrom-Json
    $SkillsToRemove = @($Marker.skills)
} else {
    Write-Host "No install marker found. Skill removal is disabled to protect user-owned skills."
}

$Plan = New-Object System.Collections.Generic.List[string]
$Plan.Add("Mode: $(if ($IsDryRun) { 'DryRun' } else { 'Apply' })")
$Plan.Add("TargetRoot: $TargetRoot")
foreach ($skill in $SkillsToRemove) {
    $skillPath = Join-Path $TargetSkillsRoot $skill
    if (Test-Path -LiteralPath $skillPath) {
        $Plan.Add("REMOVE installed skill: $skill")
    }
}
$Plan.Add("REMOVE install marker: $MarkerFile")

if ($RestoreBackup) {
    $BackupRoot = Join-Path $BackupBase $RestoreBackup
    $Plan.Add("RESTORE backup: $BackupRoot")
}

$Plan | ForEach-Object { Write-Host $_ }
if ($IsDryRun) {
    Write-Host "DryRun only. Re-run with -Apply to write changes."
    exit 0
}

foreach ($skill in $SkillsToRemove) {
    $skillPath = Join-Path $TargetSkillsRoot $skill
    if (Test-Path -LiteralPath $skillPath) {
        Remove-Item -LiteralPath $skillPath -Recurse -Force
    }
}

if ($RestoreBackup) {
    $BackupRoot = Join-Path $BackupBase $RestoreBackup
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        throw "Backup not found: $BackupRoot"
    }
    $BackupAgents = Join-Path $BackupRoot "AGENTS.md"
    $BackupSkills = Join-Path $BackupRoot "skills"
    if (Test-Path -LiteralPath $BackupAgents) {
        Copy-Item -LiteralPath $BackupAgents -Destination $TargetAgentsFile -Force
    }
    if (Test-Path -LiteralPath $BackupSkills) {
        if (Test-Path -LiteralPath $TargetSkillsRoot) {
            Remove-Item -LiteralPath $TargetSkillsRoot -Recurse -Force
        }
        Copy-Item -LiteralPath $BackupSkills -Destination $TargetSkillsRoot -Recurse -Force
    }
}

if (Test-Path -LiteralPath $MarkerFile) {
    Remove-Item -LiteralPath $MarkerFile -Force
}

Write-Host "Uninstall completed."
