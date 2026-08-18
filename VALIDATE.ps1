[CmdletBinding()]
param(
    [string]$Root = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PythonRuntime {
    $Command = Get-Command py -ErrorAction SilentlyContinue
    if ($Command) {
        return [pscustomobject]@{ Path = $Command.Source; Prefix = @("-3", "-B") }
    }
    $Command = Get-Command python -ErrorAction SilentlyContinue
    if ($Command) {
        return [pscustomobject]@{ Path = $Command.Source; Prefix = @("-B") }
    }
    throw "Python 3 is required."
}

function Invoke-PythonCheck {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Runtime,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$ScriptArgs = @()
    )
    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        return [pscustomobject]@{ Name = $Name; Status = "ERROR"; ExitCode = 2; Output = @("Missing: $ScriptPath") }
    }
    $Output = @(& $Runtime.Path @($Runtime.Prefix) $ScriptPath @ScriptArgs 2>&1 | ForEach-Object { $_.ToString() })
    $ExitCode = $LASTEXITCODE
    $Status = if ($ExitCode -eq 0) { "PASS" } else { "FAIL" }
    return [pscustomobject]@{ Name = $Name; Status = $Status; ExitCode = $ExitCode; Output = $Output }
}

$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = $PackRoot
}
$ResolvedRoot = (Resolve-Path -LiteralPath $Root).Path
$ResolvedPackRoot = (Resolve-Path -LiteralPath $PackRoot).Path
$Runtime = Get-PythonRuntime
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"

$Checks = @()
$Checks += Invoke-PythonCheck -Runtime $Runtime -Name "repository" -ScriptPath (Join-Path $PackRoot "scripts\validate_skills.py") -ScriptArgs @("--root", $ResolvedRoot)
if ($ResolvedRoot -eq $ResolvedPackRoot) {
    $EngineeringRoot = Join-Path $PackRoot "skill-groups\ai-software-engineering-platform-enterprise"
    $DesktopRoot = Join-Path $PackRoot "skill-groups\desktop-app-reconstruction-zh"
    $Checks += Invoke-PythonCheck -Runtime $Runtime -Name "public-content" -ScriptPath (Join-Path $PackRoot "scripts\audit_public_content.py") -ScriptArgs @("--root", $ResolvedRoot)
    $Checks += Invoke-PythonCheck -Runtime $Runtime -Name "engineering" -ScriptPath (Join-Path $EngineeringRoot "tools\validate_bundle.py")
    $Checks += Invoke-PythonCheck -Runtime $Runtime -Name "desktop-reconstruction" -ScriptPath (Join-Path $DesktopRoot "scripts\validate_skill_package.py") -ScriptArgs @($DesktopRoot)
}

$Failed = @($Checks | Where-Object { $_.Status -ne "PASS" })
$Result = [pscustomobject]@{
    SchemaVersion = "1.0.0"
    Status = if ($Failed.Count -eq 0) { "PASS" } else { "FAIL" }
    Root = $ResolvedRoot
    Checks = $Checks
}
$Result | ConvertTo-Json -Depth 6
if ($Failed.Count -eq 0) { exit 0 }
exit 1
