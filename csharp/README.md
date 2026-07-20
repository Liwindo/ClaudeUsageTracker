# Claude Usage Tracker — C# variant

![.NET](https://img.shields.io/badge/.NET-10-512BD4?logo=dotnet&logoColor=white)

C#/.NET 10 port of the tracker: a Windows tray tool that monitors your claude.ai usage limits via your Firefox session cookies and claude.ai's internal (reverse-engineered) endpoints. Not affiliated with Anthropic.

Not sure which variant you want? See ["Which version is for me?"](../README.md#which-version-is-for-me) in the repository README.

## What it adds over the Python variant

- **Settings dialog** (tray/widget → "Settings…"): edits every config.toml option without touching the file. Poll interval, thresholds, autostart, and log level apply immediately; language changes apply on the next start.
- **Clickable notifications** — clicking one opens claude.ai; missed notifications land in the Action Center.
- **Instant re-poll on standby resume and network return**; while offline it does not poll at all (no error flicker).
- **EcoQoS/efficiency mode**, **ReadyToRun** (faster start), **per-monitor V2 DPI awareness**, edge snapping while dragging the widget, animated bars.
- Smaller memory footprint: ~4 MB working set / ~52 MB private bytes when idle (Release build).

Configuration lives in `%APPDATA%\claude-usage-tracker-cs\config.toml` — same TOML schema as the Python variant, in its own folder so both variants can run side by side.

## Project structure

```
ClaudeUsageTracker/        WPF app (net10.0-windows, UI entirely in code — no XAML)
├─ Program.cs              Entry point: mutex, config, i18n, logging, autostart, EcoQoS
├─ AppOrchestrator.cs      Wires poller, widget, tray, notifications, update check, triggers
├─ WidgetWindow.cs         Always-on-top widget
├─ SettingsWindow.cs       Settings dialog (an editor over config.toml)
├─ TrayIcon.cs             WinForms NotifyIcon (colour circle, menu, clickable toasts)
├─ Poller.cs               Background thread, 30 s interval, 429 backoff, offline skip
├─ ClaudeClient.cs         HTTP client (WinHttpHandler — see below), tier cache
├─ FirefoxCookies.cs       profiles.ini + cookies.sqlite (read-only)
├─ Config.cs               TOML via Tomlyn, auto-migration of missing keys
├─ I18n.cs + Locales/*.json  9 languages (exported from python/, see scripts/)
├─ NotificationManager.cs  Thresholds + hysteresis + reset detection, live updates
├─ UpdateCheck.cs          GitHub release check (once per start)
├─ Autostart.cs            HKCU Run key "ClaudeUsageTrackerCS"
├─ SystemTriggers.cs       Instant poll on resume/network return
├─ EfficiencyMode.cs       EcoQoS (E-cores/throttling while idle)
├─ WorkingSetTrimmer.cs    RAM trimming for idle operation
└─ app.manifest            Per-monitor V2 DPI
ClaudeUsageTracker.Tests/  xunit test suite
installer/                 Inno Setup 6 script (per-user installer)
```

## Build & test

Requires a .NET 10 SDK.

```powershell
dotnet test ClaudeUsageTracker.slnx        # run the test suite
dotnet run --project ClaudeUsageTracker    # run from source
```

## Release artifacts (installer + portable)

One script builds everything into `dist\` (tests run as a gate first). It needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`) for the installer; without it, only the portable EXE is produced.

```powershell
.\build-release.ps1
```

| Artifact | Size | For whom |
|----------|------|----------|
| `ClaudeUsageTracker-Setup-<ver>.exe` | ~4 MB | The normal case: per-user install (no UAC), Start-menu entry, optional autostart checkbox, uninstaller. Detects a missing .NET 10 Desktop Runtime and offers to download it from the official Microsoft link. |
| `ClaudeUsageTracker-Portable-<ver>.exe` | ~80 MB | Everything in one EXE (runtime included), no installation, no dependencies. Slightly higher RAM use than the installed variant (single-file bundle). |

Installer details (`installer/ClaudeUsageTracker.iss`): the setup dialog speaks the same 9 languages as the app. Everywhere a user reads the name (installer, Start menu, Programs list, Task Manager display name) the app is plainly **"Claude Usage Tracker"**. Only the EXE/process name stays `ClaudeUsageTrackerCS.exe` — a deliberate technical identity kept distinct from the Python variant's `ClaudeUsageTracker.exe`, so the uninstaller's taskkill, the autostart registry value, and the process list can never hit the other variant.

The installer's runtime detection checks the **filesystem** (`%ProgramFiles%\dotnet\shared\Microsoft.WindowsDesktop.App\10.*` and `DOTNET_ROOT`), not the registry — the often-quoted `HKLM\SOFTWARE\dotnet\Setup\InstalledVersions` key was missing on a machine with a provably installed runtime.

## Notes for contributors

- **WinHttpHandler is mandatory.** Cloudflare fingerprints the TLS ClientHello: .NET's `SocketsHttpHandler` gets a 403 "Just a moment" challenge on *every* claude.ai request (regardless of headers or HTTP version); the native WinHTTP stack passes. Verified empirically 2026-07. Do not switch back without re-testing.
- **Own data locations:** `%APPDATA%\claude-usage-tracker-cs\` (config.toml, app.log, widget_pos.json), its own single-instance mutex, its own autostart registry value, and its own EXE name — this is what makes side-by-side operation with the Python variant safe.
- **Translations are not edited here.** `Locales/*.json` carries every string the Python variant also has, exported via `scripts/export_locales.py` (repo root); CI fails on drift. Only C#-only strings (settings dialog, toast hint) are maintained directly in the JSONs — add them to `en.json` first, then to the other eight catalogs (a test enforces key and placeholder parity).
- Notifications use clickable NotifyIcon balloon tips (click → claude.ai). Real toast buttons were deliberately left out: they require an AppUserModelID/shortcut identity that can fail silently, while the clickable notification delivers the core benefit reliably.
- RAM optimisations: software rendering (no D3D for a 256-px widget), `System.GC.ConserveMemory=6`, periodic working-set trimming, EcoQoS.
- The version is maintained centrally in the csproj (`<Version>`), set by `scripts/bump_version.ps1` together with the Python variant; the update check reads it from the assembly metadata.

## License

MIT
