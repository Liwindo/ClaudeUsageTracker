# Set the same version in BOTH variants (lockstep releases, see CHANGELOG.md):
#   scripts\bump_version.ps1 2.1.0
# Writes __version__ (python) and <Version> (csharp csproj), then refreshes
# uv.lock so `uv lock --check` in CI stays green. Windows PowerShell 5.1.

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$initPath = Join-Path $repoRoot "python\src\claude_usage_monitor\__init__.py"
$csprojPath = Join-Path $repoRoot "csharp\ClaudeUsageTracker\ClaudeUsageTracker.csproj"

$init = Get-Content $initPath -Raw -Encoding UTF8
$newInit = $init -replace '__version__ = "\d+(?:\.\d+)*"', ('__version__ = "' + $Version + '"')
if ($newInit -eq $init) { throw "No __version__ line found in $initPath" }
[IO.File]::WriteAllText($initPath, $newInit)

$csproj = Get-Content $csprojPath -Raw -Encoding UTF8
$newCsproj = $csproj -replace '<Version>\d+(?:\.\d+)*</Version>', "<Version>$Version</Version>"
if ($newCsproj -eq $csproj) { throw "No <Version> element found in $csprojPath" }
[IO.File]::WriteAllText($csprojPath, $newCsproj)

Push-Location (Join-Path $repoRoot "python")
try {
    uv lock
    if ($LASTEXITCODE -ne 0) { throw "uv lock failed" }
}
finally {
    Pop-Location
}

Write-Host "Both variants now at $Version (python __init__.py, csharp csproj, uv.lock)."
