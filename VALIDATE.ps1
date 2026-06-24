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
if ($Python.Name -eq "py.exe" -or $Python.Name -eq "py") {
    & $Python.Source -3 $Validator --root $ResolvedRoot
} else {
    & $Python.Source $Validator --root $ResolvedRoot
}
exit $LASTEXITCODE
