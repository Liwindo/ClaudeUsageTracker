<#
.SYNOPSIS
    Fail unless CHANGELOG.md has a non-empty section for the current version.

.DESCRIPTION
    Mirrors the release guard in .github/workflows/release.yml so a LOCAL build
    is held to the same standard: an EXE is never produced for a version that
    has no user-facing release notes. The version is read from
    src/claude_usage_monitor/__init__.py (the single source of truth that the
    built EXE reports) unless -Version is supplied. Prints the extracted notes
    on success; exits 1 on a missing/empty section.
#>
param(
    [string]$Version
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot   # repo root (scripts/..)

if (-not $Version) {
    $initPath = Join-Path $root 'src/claude_usage_monitor/__init__.py'
    $initText = Get-Content $initPath -Raw -Encoding UTF8
    $vm = [regex]::Match($initText, '__version__\s*=\s*"([^"]+)"')
    if (-not $vm.Success) {
        Write-Error "Could not parse __version__ from $initPath"
        exit 1
    }
    $Version = $vm.Groups[1].Value
}

$changelogPath = Join-Path $root 'CHANGELOG.md'
$content = Get-Content $changelogPath -Raw -Encoding UTF8
# Same pattern as the release workflow: the version heading up to the next
# '## ' heading (or end of file), with the captured body required non-empty.
$pattern = "(?ms)^## \[?$([regex]::Escape($Version))\]?[^\r\n]*\r?\n(.*?)(?=^## |\z)"
$m = [regex]::Match($content, $pattern)
if (-not $m.Success -or -not $m.Groups[1].Value.Trim()) {
    Write-Error ("CHANGELOG.md has no section for version $Version. " +
        "Add '## $Version - <date>' with user-facing notes before building.")
    exit 1
}

Write-Host "CHANGELOG.md notes for $Version :"
Write-Host ""
Write-Host ($m.Groups[1].Value.Trim())
exit 0
