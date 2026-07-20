# Builds all release artifacts into dist\:
#   ClaudeUsageTracker-Setup-<ver>.exe     Installer (framework-dependent payload,
#                                          downloads the .NET runtime if missing)
#   ClaudeUsageTracker-Portable-<ver>.exe  Self-contained single EXE, no dependencies
#
# Requires a .NET 10 SDK and Inno Setup 6 (winget install JRSoftware.InnoSetup).
# Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$csproj = Join-Path $root "ClaudeUsageTracker\ClaudeUsageTracker.csproj"

# Prefer the user-local SDK if present (machine-wide SDKs may be older).
$dotnet = Join-Path $env:LOCALAPPDATA "Microsoft\dotnet\dotnet.exe"
if (-not (Test-Path $dotnet)) { $dotnet = "dotnet" }

$iscc = $null
foreach ($candidate in @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
  if ($candidate -and (Test-Path $candidate)) { $iscc = $candidate; break }
}

$version = ([xml](Get-Content $csproj -Raw)).Project.PropertyGroup.Version |
  Where-Object { $_ } | Select-Object -First 1
if (-not $version) { throw "No <Version> found in $csproj" }
Write-Host "Building Claude Usage Tracker (C#) $version" -ForegroundColor Cyan

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null

Write-Host "`n[1/4] Tests" -ForegroundColor Cyan
& $dotnet test (Join-Path $root "ClaudeUsageTracker.slnx") --nologo -v q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Host "`n[2/4] Publish framework-dependent (installer payload)" -ForegroundColor Cyan
& $dotnet publish $csproj -c Release -r win-x64 --self-contained false `
  /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
  /p:DebugType=none -o (Join-Path $root "publish\fdd")
if ($LASTEXITCODE -ne 0) { throw "fdd publish failed" }

Write-Host "`n[3/4] Publish portable (self-contained single EXE)" -ForegroundColor Cyan
& $dotnet publish $csproj -c Release -r win-x64 --self-contained true `
  /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
  /p:EnableCompressionInSingleFile=true /p:DebugType=none `
  -o (Join-Path $root "publish\portable")
if ($LASTEXITCODE -ne 0) { throw "portable publish failed" }
Copy-Item (Join-Path $root "publish\portable\ClaudeUsageTrackerCS.exe") `
  (Join-Path $dist "ClaudeUsageTracker-Portable-$version.exe") -Force

Write-Host "`n[4/4] Installer (Inno Setup)" -ForegroundColor Cyan
if ($iscc) {
  & $iscc "/DMyAppVersion=$version" /Qp (Join-Path $root "installer\ClaudeUsageTracker.iss")
  if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
} else {
  Write-Warning "Inno Setup 6 not found - skipping the installer. Install with: winget install JRSoftware.InnoSetup"
}

Write-Host "`nArtifacts in dist\:" -ForegroundColor Cyan
Get-ChildItem $dist -Filter "*-$version.exe" | ForEach-Object {
  $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  "{0,-46} {1,8:n1} MB  SHA256 {2}" -f $_.Name, ($_.Length / 1MB), $hash
}
