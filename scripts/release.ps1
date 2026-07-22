# One-command release. Does the WHOLE release from a single call so you never
# run bump_version / publish_release by hand:
#
#   ./scripts/release.ps1 2.2.0
#
# Steps: bump both variants -> stamp CHANGELOG -> commit -> tag -> push -> WAIT
# for CI to build the draft release -> sign the update manifest with your OFFLINE
# key -> self-verify -> publish. The private key never leaves this machine; the
# only cost of that guarantee is that this command blocks a few minutes while CI
# builds. If anything fails after the tag is pushed, re-run just the signing step
# with:  ./scripts/publish_release.ps1 -Tag vX.Y.Z
#
# Prerequisites (checked up-front, before anything is committed):
#   - clean git tree on master, gh CLI authenticated
#   - $env:CUT_UPDATE_KEY / $env:CUT_UPDATE_KEY_PASS set (offline signing key)
#   - UpdateKeys.json carries the matching public key

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$tag = "v$Version"
$changelog = Join-Path $repoRoot "CHANGELOG.md"
$keysJson = Join-Path $repoRoot "csharp\ClaudeUsageTracker\UpdateKeys.json"

function Fail($msg) { Write-Error $msg; exit 1 }

# -- Pre-flight: fail BEFORE touching git if anything is missing --------------
Push-Location $repoRoot
try {
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "master") { Fail "Not on master (on '$branch'). Release from master." }
    if (git status --porcelain) { Fail "Working tree is not clean. Commit or stash first." }

    if (-not $env:CUT_UPDATE_KEY -or -not (Test-Path $env:CUT_UPDATE_KEY)) {
        Fail "Set `$env:CUT_UPDATE_KEY to the encrypted offline private key (generate_update_key.ps1)."
    }
    if (-not $env:CUT_UPDATE_KEY_PASS) { Fail "Set `$env:CUT_UPDATE_KEY_PASS to the key passphrase." }
    $keys = (Get-Content $keysJson -Raw | ConvertFrom-Json).keys
    if (-not $keys -or $keys.Count -eq 0) {
        Fail "UpdateKeys.json has no public key. Run generate_update_key.ps1 first."
    }
    gh auth status *> $null
    if ($LASTEXITCODE -ne 0) { Fail "gh CLI is not authenticated (run: gh auth login)." }

    if (git tag --list $tag) { Fail "Tag $tag already exists." }

    # -- 1. Bump both variants ------------------------------------------------
    Write-Host "[1/6] Bumping both variants to $Version" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "bump_version.ps1") $Version
    if ($LASTEXITCODE -ne 0) { Fail "bump_version failed" }

    # -- 2. CHANGELOG: reuse an existing '## X.Y.Z' section, else stamp the
    #      '## Unreleased' block with today's date (the release workflow requires
    #      a section for this version). ---------------------------------------
    Write-Host "[2/6] Preparing CHANGELOG.md section for $Version" -ForegroundColor Cyan
    $text = Get-Content $changelog -Raw
    $hasVersion = [regex]::IsMatch($text, "(?m)^## \[?$([regex]::Escape($Version))\]?\b")
    if (-not $hasVersion) {
        $dash = [char]0x2014  # em dash, matching the existing CHANGELOG style
        $date = Get-Date -Format 'yyyy-MM-dd'
        # Lookahead (not $) so the match ends BEFORE the line terminator: this
        # matches a CRLF '## Unreleased\r\n' line (where $ can't anchor before the
        # \r) and leaves the \r\n intact so the file's CRLF endings are preserved.
        $stamped = [regex]::Replace($text, "(?m)^## Unreleased[^\r\n]*(?=\r?\n|$)", "## $Version $dash $date", 1)
        if ($stamped -eq $text) {
            Fail "CHANGELOG.md has neither a '## $Version' section nor a '## Unreleased' block to stamp."
        }
        [IO.File]::WriteAllText($changelog, $stamped)
        Write-Host "      Stamped '## Unreleased' as '## $Version $dash $date'."
    } else {
        Write-Host "      Using the existing '## $Version' section."
    }

    # -- 3. Commit + tag + push -----------------------------------------------
    Write-Host "[3/6] Commit, tag $tag, push" -ForegroundColor Cyan
    git add -A
    git commit -m "Release $tag"
    if ($LASTEXITCODE -ne 0) { Fail "git commit failed" }
    git tag $tag
    git push origin master $tag
    if ($LASTEXITCODE -ne 0) { Fail "git push failed" }

    # -- 4. Wait for the Release workflow to build the draft ------------------
    Write-Host "[4/6] Waiting for the Release workflow to build the draft (this is the slow part)" -ForegroundColor Cyan
    $runId = $null
    for ($i = 0; $i -lt 24 -and -not $runId; $i++) {  # up to ~2 min for the run to appear
        Start-Sleep -Seconds 5
        # Select the object first, THEN read databaseId only if one was found:
        # piping an empty result straight into '-ExpandProperty databaseId'
        # throws "property cannot be found" on the polls before the run appears.
        $run = gh run list --workflow release.yml --event push -L 20 `
            --json databaseId,headBranch,createdAt |
            ConvertFrom-Json | Where-Object { $_.headBranch -eq $tag } |
            Sort-Object createdAt -Descending | Select-Object -First 1
        if ($run) { $runId = $run.databaseId }
    }
    if (-not $runId) { Fail "Could not find the Release workflow run for $tag. Check GitHub Actions, then run publish_release.ps1 -Tag $tag." }
    gh run watch $runId --exit-status
    if ($LASTEXITCODE -ne 0) { Fail "The Release workflow failed. Fix it, then run publish_release.ps1 -Tag $tag once the draft exists." }

    # -- 5 + 6. Sign the manifest with the offline key and publish ------------
    Write-Host "[5/6] Signing + publishing (offline key, self-verified)" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "publish_release.ps1") -Tag $tag
    if ($LASTEXITCODE -ne 0) { Fail "Signing/publishing failed. The draft is built; re-run: publish_release.ps1 -Tag $tag" }

    Write-Host "[6/6] Done." -ForegroundColor Green
    Write-Host "Released $tag with a verified signed update manifest. Key never left this machine." -ForegroundColor Green
}
finally {
    Pop-Location
}
