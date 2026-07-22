# Finish a release: sign the update manifest with the OFFLINE key, attach it,
# and flip the CI-built draft to published - in one command.
#
# WHY THIS EXISTS. release.yml builds every tagged release as a DRAFT. The
# in-app updater trusts only a manifest signed by the offline key, which CI does
# not hold. This script signs locally, PROVES the signature verifies against the
# public key the app ships (UpdateKeys.json), uploads update.json(+.sig) and only
# THEN publishes. Because the update check follows releases/latest (drafts are
# invisible to it) and this is the only step that publishes, a forgotten or
# failed signature can never ship an unsigned update - the release just stays a
# draft. This is the "signing can never be forgotten" guarantee, automated.
#
# Prerequisites:
#   - gh CLI authenticated (repo scope).
#   - $env:CUT_UPDATE_KEY  = path to the encrypted private key (generate_update_key.ps1)
#   - $env:CUT_UPDATE_KEY_PASS = its passphrase
#   - UpdateKeys.json already carries the matching public key.
#
# Usage:
#   ./scripts/publish_release.ps1 -Tag v2.2.0

param(
    [Parameter(Mandatory = $true)][string]$Tag
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $repoRoot "csharp\UpdateTool"
$keysJson = Join-Path $repoRoot "csharp\ClaudeUsageTracker\UpdateKeys.json"

$dotnet = Join-Path $env:LOCALAPPDATA "Microsoft\dotnet\dotnet.exe"
if (-not (Test-Path $dotnet)) { $dotnet = "dotnet" }

if (-not $env:CUT_UPDATE_KEY -or -not (Test-Path $env:CUT_UPDATE_KEY)) {
    throw "Set `$env:CUT_UPDATE_KEY to the encrypted private-key file (see generate_update_key.ps1)."
}
if (-not $env:CUT_UPDATE_KEY_PASS) { throw "Set `$env:CUT_UPDATE_KEY_PASS to the key passphrase." }

# Refuse early if no public key is embedded - the app would reject every update
# and the self-verify below would fail anyway.
$keys = (Get-Content $keysJson -Raw | ConvertFrom-Json).keys
if (-not $keys -or $keys.Count -eq 0) {
    throw "UpdateKeys.json has no public key. Run generate_update_key.ps1 and paste the public key first."
}

$version = $Tag -replace '^v', ''
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("cut-publish-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $work | Out-Null

try {
    Write-Host "[1/5] Downloading built C# assets from draft release $Tag" -ForegroundColor Cyan
    gh release download $Tag --dir $work --pattern "ClaudeUsageTracker-Setup-*.exe" --pattern "ClaudeUsageTracker-Portable-*.exe"
    if ($LASTEXITCODE -ne 0) { throw "gh release download failed (is $Tag a draft with the C# assets?)" }

    $assetArgs = @()
    $verifyAssetArgs = @()
    foreach ($f in Get-ChildItem $work -Filter "ClaudeUsageTracker-*.exe") {
        $assetArgs += @("--asset", $f.FullName)
        $verifyAssetArgs += @("--asset", ("{0}={1}" -f $f.Name, $f.FullName))
    }
    if ($assetArgs.Count -eq 0) { throw "no C# .exe assets found in the release" }

    Write-Host "[2/5] Signing manifest with the offline key" -ForegroundColor Cyan
    & $dotnet run --project $tool -c Release -- sign --key $env:CUT_UPDATE_KEY --version $version `
        --out-dir $work --keys $keysJson @assetArgs
    if ($LASTEXITCODE -ne 0) { throw "signing failed" }

    Write-Host "[3/5] Verifying the signature the app will enforce" -ForegroundColor Cyan
    & $dotnet run --project $tool -c Release -- verify --keys $keysJson `
        --manifest (Join-Path $work "update.json") --sig (Join-Path $work "update.json.sig") `
        --current "0.0.0" @verifyAssetArgs
    if ($LASTEXITCODE -ne 0) { throw "self-verify failed - NOT publishing" }

    Write-Host "[4/5] Uploading update.json + update.json.sig" -ForegroundColor Cyan
    gh release upload $Tag (Join-Path $work "update.json") (Join-Path $work "update.json.sig") --clobber
    if ($LASTEXITCODE -ne 0) { throw "gh release upload failed" }

    Write-Host "[5/5] Publishing (draft -> live)" -ForegroundColor Cyan
    gh release edit $Tag --draft=false
    if ($LASTEXITCODE -ne 0) { throw "gh release edit failed" }

    Write-Host "`nPublished $Tag with a verified signed manifest." -ForegroundColor Green
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
