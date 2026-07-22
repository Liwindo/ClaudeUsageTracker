# One-time setup of the OFFLINE update-signing key.
#
# Creates an ECDSA P-256 keypair. The PRIVATE key is written AES-256-encrypted
# to a DEDICATED FOLDER OUTSIDE THE REPOSITORY so it can never be accidentally
# git-added. It must stay offline (password manager / offline store) - it is the
# one secret a compromised GitHub or CI must never obtain. The PUBLIC key is
# printed for you to paste into csharp/ClaudeUsageTracker/UpdateKeys.json
# ({"keys": ["<base64>"]}), which is the trust anchor the shipped app carries.
#
# Two independent safeguards keep the private key off GitHub:
#   1. It defaults to (and this script REFUSES any path inside) the repo tree -
#      it lives in a separate folder under your user profile.
#   2. .gitignore ignores *.pem / *.key / update-signing-key* as a backstop.
#
# Usage (Windows PowerShell 5.1 is fine - the crypto runs in the .NET tool):
#   $env:CUT_UPDATE_KEY_PASS = '<a strong passphrase>'
#   ./scripts/generate_update_key.ps1                 # -> %USERPROFILE%\.cut-signing\...
#   ./scripts/generate_update_key.ps1 -OutFile D:\keys\cut-key.pem   # custom, still outside the repo

param(
    # Default: a dedicated folder OUTSIDE the repository, under the user profile.
    [string]$OutFile = (Join-Path $env:USERPROFILE ".cut-signing\update-signing-key.pem")
)

$ErrorActionPreference = "Stop"

if (-not $env:CUT_UPDATE_KEY_PASS) {
    throw "Set `$env:CUT_UPDATE_KEY_PASS to the passphrase that will encrypt the private key first."
}

$repoRoot = Split-Path -Parent $PSScriptRoot

# HARD GUARD: never allow the private key anywhere inside the repo tree, so it
# can never be staged/committed by accident. Compare normalised full paths.
$fullOut = [System.IO.Path]::GetFullPath($OutFile)
$fullRepo = [System.IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
if ($fullOut.StartsWith($fullRepo, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw ("Refusing to write the private key inside the repository ($fullOut). " +
        "Choose a path OUTSIDE the repo, e.g. under your user profile.")
}

$outDir = Split-Path -Parent $fullOut
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force $outDir | Out-Null }

if (Test-Path $fullOut) {
    throw "$fullOut already exists - refusing to overwrite an existing signing key."
}

$tool = Join-Path $repoRoot "csharp\UpdateTool"
# Prefer the user-local SDK if present (matches build-release.ps1).
$dotnet = Join-Path $env:LOCALAPPDATA "Microsoft\dotnet\dotnet.exe"
if (-not (Test-Path $dotnet)) { $dotnet = "dotnet" }

& $dotnet run --project $tool -c Release -- keygen --out $fullOut
if ($LASTEXITCODE -ne 0) { throw "keygen failed" }

Write-Host ""
Write-Host "Private key stored OUTSIDE the repo at: $fullOut" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Paste the public key above into csharp/ClaudeUsageTracker/UpdateKeys.json"
Write-Host "     as {""keys"": [""<that base64>""]} and commit ONLY that file."
Write-Host "  2. Keep $fullOut offline (back it up in your password manager). Never commit it."
Write-Host "  3. For releases, set:  `$env:CUT_UPDATE_KEY = '$fullOut'  and  `$env:CUT_UPDATE_KEY_PASS = '<passphrase>'"
Write-Host "     then run  ./scripts/publish_release.ps1 -Tag vX.Y.Z"
