[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,

    [switch]$DryRun,
    [switch]$Apply,
    [switch]$Backup,
    [string]$Skills = "core",
    [switch]$MergeAgents,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Apply -and $DryRun) {
    throw "Use either -Apply or -DryRun, not both."
}

$IsDryRun = -not $Apply
$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackSkillsRoot = Join-Path $PackRoot ".agents\skills"
$Version = (Get-Content -Raw (Join-Path $PackRoot "VERSION")).Trim()

$CoreSkills = @(
    "hiker-workflow-router",
    "codex-thread-review",
    "project-phase-review",
    "evidence-first-testing",
    "contract-boundary-audit",
    "nodets-execution-pipeline-guardrails",
    "unity-codex-guardrails"
)

function Resolve-SkillSelection {
    param([string]$Selection)
    $all = Get-ChildItem -LiteralPath $PackSkillsRoot -Directory | ForEach-Object { $_.Name } | Sort-Object
    if ($Selection -eq "all") { return $all }
    if ($Selection -eq "core") { return $CoreSkills }
    return ($Selection -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-ProjectRoot {
    param([string]$Root)
    $markers = @(
        ".git",
        "AGENTS.md",
        ".agents",
        "package.json",
        "pyproject.toml",
        "composer.json",
        "Assets",
        "Packages\manifest.json",
        "ProjectSettings"
    )
    foreach ($marker in $markers) {
        if (Test-Path -LiteralPath (Join-Path $Root $marker)) {
            return $true
        }
    }
    return $false
}

function Write-Plan {
    param([string[]]$Lines)
    $Lines | ForEach-Object { Write-Host $_ }
}

if (-not (Test-Path -LiteralPath $TargetRoot)) {
    throw "TargetRoot does not exist: $TargetRoot"
}

$TargetRoot = (Resolve-Path -LiteralPath $TargetRoot).Path
if (-not (Test-ProjectRoot -Root $TargetRoot) -and -not $Force) {
    throw "TargetRoot does not look like a project root. Re-run with -Force if this is intentional: $TargetRoot"
}

$SelectedSkills = @(Resolve-SkillSelection -Selection $Skills)
$KnownSkills = @(Get-ChildItem -LiteralPath $PackSkillsRoot -Directory | ForEach-Object { $_.Name })
$MissingSkills = @($SelectedSkills | Where-Object { $_ -notin $KnownSkills })
if ($MissingSkills.Count -gt 0) {
    throw "Unknown skill(s): $($MissingSkills -join ', ')"
}

$TargetAgentsRoot = Join-Path $TargetRoot ".agents"
$TargetSkillsRoot = Join-Path $TargetAgentsRoot "skills"
$TargetAgentsFile = Join-Path $TargetRoot "AGENTS.md"
$SourceAgentsFile = Join-Path $PackRoot "AGENTS.md"
$MarkerFile = Join-Path $TargetAgentsRoot "hiker-workflow-pack.installed.json"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path $TargetRoot ".backups\hiker-workflow-pack\$Timestamp"

$Plan = New-Object System.Collections.Generic.List[string]
$Plan.Add("Mode: $(if ($IsDryRun) { 'DryRun' } else { 'Apply' })")
$Plan.Add("TargetRoot: $TargetRoot")
$Plan.Add("Version: $Version")
$Plan.Add("Skills: $($SelectedSkills -join ', ')")
$Plan.Add("MergeAgents: $($MergeAgents.IsPresent)")
$Plan.Add("Force: $($Force.IsPresent)")
$Plan.Add("BackupRoot: $BackupRoot")

foreach ($skill in $SelectedSkills) {
    $targetSkill = Join-Path $TargetSkillsRoot $skill
    if (Test-Path -LiteralPath $targetSkill) {
        if ($Force) {
            $Plan.Add("OVERWRITE skill: $skill")
        } else {
            $Plan.Add("SKIP existing skill: $skill")
        }
    } else {
        $Plan.Add("COPY skill: $skill")
    }
}

if ($MergeAgents) {
    $Plan.Add("MERGE AGENTS.md Hiker block")
} elseif (Test-Path -LiteralPath $TargetAgentsFile) {
    if ($Force) {
        $Plan.Add("OVERWRITE AGENTS.md")
    } else {
        $Plan.Add("SKIP existing AGENTS.md")
    }
} else {
    $Plan.Add("COPY AGENTS.md")
}

if ($IsDryRun) {
    Write-Plan -Lines $Plan
    Write-Host "DryRun only. Re-run with -Apply to write changes."
    exit 0
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
if (Test-Path -LiteralPath $TargetAgentsFile) {
    Copy-Item -LiteralPath $TargetAgentsFile -Destination (Join-Path $BackupRoot "AGENTS.md") -Force
}
if (Test-Path -LiteralPath $TargetSkillsRoot) {
    Copy-Item -LiteralPath $TargetSkillsRoot -Destination (Join-Path $BackupRoot "skills") -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $TargetSkillsRoot | Out-Null
$Installed = New-Object System.Collections.Generic.List[string]

foreach ($skill in $SelectedSkills) {
    $sourceSkill = Join-Path $PackSkillsRoot $skill
    $targetSkill = Join-Path $TargetSkillsRoot $skill
    if (Test-Path -LiteralPath $targetSkill) {
        if (-not $Force) {
            Write-Host "Skipped existing skill: $skill"
            continue
        }
        Remove-Item -LiteralPath $targetSkill -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceSkill -Destination $targetSkill -Recurse -Force
    $Installed.Add($skill)
}

$AgentsBlock = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceAgentsFile
if ($MergeAgents) {
    $Start = "<!-- hiker-workflow-pack start -->"
    $End = "<!-- hiker-workflow-pack end -->"
    $BlockOnly = [regex]::Match($AgentsBlock, "(?s)<!-- hiker-workflow-pack start -->.*?<!-- hiker-workflow-pack end -->").Value
    if (-not $BlockOnly) { throw "Could not find Hiker AGENTS block in source AGENTS.md" }
    if (Test-Path -LiteralPath $TargetAgentsFile) {
        $ExistingAgents = Get-Content -Raw -Encoding UTF8 -LiteralPath $TargetAgentsFile
        if ($ExistingAgents.Contains($Start) -and $ExistingAgents.Contains($End)) {
            $UpdatedAgents = [regex]::Replace($ExistingAgents, "(?s)<!-- hiker-workflow-pack start -->.*?<!-- hiker-workflow-pack end -->", $BlockOnly)
        } else {
            $UpdatedAgents = $ExistingAgents.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $BlockOnly + [Environment]::NewLine
        }
        Set-Content -LiteralPath $TargetAgentsFile -Value $UpdatedAgents -Encoding UTF8
    } else {
        Set-Content -LiteralPath $TargetAgentsFile -Value $AgentsBlock -Encoding UTF8
    }
} else {
    if ((Test-Path -LiteralPath $TargetAgentsFile) -and -not $Force) {
        Write-Host "Skipped existing AGENTS.md"
    } else {
        Copy-Item -LiteralPath $SourceAgentsFile -Destination $TargetAgentsFile -Force
    }
}

New-Item -ItemType Directory -Force -Path $TargetAgentsRoot | Out-Null
$Marker = [pscustomobject]@{
    package = "hiker-workflow-pack"
    version = $Version
    installedAt = (Get-Date).ToString("o")
    backupId = $Timestamp
    backupRoot = $BackupRoot
    skills = @($Installed)
    mergeAgents = $MergeAgents.IsPresent
    force = $Force.IsPresent
}
$Marker | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $MarkerFile -Encoding UTF8

Write-Plan -Lines $Plan
Write-Host "Installed skills: $($Installed -join ', ')"
Write-Host "Backup created: $BackupRoot"

$Validate = Join-Path $PackRoot "VALIDATE.ps1"
& $Validate -Root $TargetRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
