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

# Check the pattern EXISTS (not "did the text change") so re-running the bump
# when already at $Version is a harmless no-op instead of a false "not found"
# throw — that lets a half-finished release be re-run cleanly.
$init = Get-Content $initPath -Raw -Encoding UTF8
if ($init -notmatch '__version__ = "\d+(?:\.\d+)*"') { throw "No __version__ line found in $initPath" }
$newInit = $init -replace '__version__ = "\d+(?:\.\d+)*"', ('__version__ = "' + $Version + '"')
[IO.File]::WriteAllText($initPath, $newInit)

$csproj = Get-Content $csprojPath -Raw -Encoding UTF8
if ($csproj -notmatch '<Version>\d+(?:\.\d+)*</Version>') { throw "No <Version> element found in $csprojPath" }
$newCsproj = $csproj -replace '<Version>\d+(?:\.\d+)*</Version>', "<Version>$Version</Version>"
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
