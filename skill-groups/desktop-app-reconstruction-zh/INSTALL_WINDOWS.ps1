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
    $PythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCommand = "python3"
} else {
    throw "未找到 Python 3。请先安装 Python 3，再重新运行本脚本。"
}

$Arguments = @($Installer, "--scope", $Scope)
if ($RepoRoot) { $Arguments += @("--repo-root", $RepoRoot) }
if ($Destination) { $Arguments += @("--destination", $Destination) }
if ($NoBackup) { $Arguments += "--no-backup" }
if ($DryRun) { $Arguments += "--dry-run" }

& $PythonCommand @PythonPrefix @Arguments
exit $LASTEXITCODE
