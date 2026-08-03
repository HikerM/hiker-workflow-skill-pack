[CmdletBinding()]
param(
    [string]$Root = "."
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Validator = Join-Path $PackRoot "scripts\validate_skills.py"

if (-not (Test-Path -LiteralPath $Validator)) {
    throw "Validator not found: $Validator"
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "Python is required to run validation."
}

$ResolvedRoot = (Resolve-Path -LiteralPath $Root).Path
$ResolvedPackRoot = (Resolve-Path -LiteralPath $PackRoot).Path
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"

function Invoke-PythonValidator {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$ScriptArgs = @()
    )

    if ($Python.Name -eq "py.exe" -or $Python.Name -eq "py") {
        & $Python.Source -3 -B $ScriptPath @ScriptArgs
    } else {
        & $Python.Source -B $ScriptPath @ScriptArgs
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Validation failed: $ScriptPath"
    }
}

Write-Host "[Group 1/3] Validating Hiker workflow skills..."
Invoke-PythonValidator -ScriptPath $Validator -ScriptArgs @("--root", $ResolvedRoot)

if ($ResolvedRoot -eq $ResolvedPackRoot) {
    $EnterpriseRoot = Join-Path $PackRoot "skill-groups\ai-software-engineering-platform-enterprise"
    $EnterpriseValidator = Join-Path $EnterpriseRoot "tools\validate_bundle.py"
    $DesktopRoot = Join-Path $PackRoot "skill-groups\desktop-app-reconstruction-zh"
    $DesktopValidator = Join-Path $DesktopRoot "scripts\validate_skill_package.py"

    if (-not (Test-Path -LiteralPath $EnterpriseValidator)) {
        throw "Enterprise validator not found: $EnterpriseValidator"
    }
    if (-not (Test-Path -LiteralPath $DesktopValidator)) {
        throw "Desktop reconstruction validator not found: $DesktopValidator"
    }

    Write-Host "[Group 2/3] Validating AI Software Engineering Platform Enterprise..."
    Invoke-PythonValidator -ScriptPath $EnterpriseValidator

    Write-Host "[Group 3/3] Validating Desktop App Reconstruction ZH..."
    Invoke-PythonValidator -ScriptPath $DesktopValidator -ScriptArgs @($DesktopRoot)

    Write-Host "ALL THREE SKILL GROUPS VALIDATED"
}

exit 0
