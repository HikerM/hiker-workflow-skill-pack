[CmdletBinding()]
param(
    [ValidateSet("user", "repo")]
    [string]$Scope = "user",
    [string]$RepoRoot = "",
    [string]$Destination = "",
    [switch]$NoBackup,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $Root "scripts\install_skill.py"

$PythonCommand = $null
$PythonPrefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
    $PythonPrefix = @("-3", "-B")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
    $PythonPrefix = @("-B")
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCommand = "python3"
    $PythonPrefix = @("-B")
} else {
    throw "Python 3 was not found. Install Python 3 and run this installer again."
}

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"

$Arguments = @($Installer, "--scope", $Scope)
if ($RepoRoot) { $Arguments += @("--repo-root", $RepoRoot) }
if ($Destination) { $Arguments += @("--destination", $Destination) }
if ($NoBackup) { $Arguments += "--no-backup" }
if ($DryRun) { $Arguments += "--dry-run" }

& $PythonCommand @PythonPrefix @Arguments
exit $LASTEXITCODE
