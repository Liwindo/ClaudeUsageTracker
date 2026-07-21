# Changelog

User-facing changes per release. The release workflow publishes the matching
section as the GitHub release notes — **a release without an entry here fails**.

## Unreleased

### 🐛 Bug fixes

- **C# variant: the widget no longer jumps when Anthropic's peak-hour banner appears or disappears.** Its bottom edge is now anchored, so the extra banner height grows the window upward and the resting position stays put across every peak/non-peak transition — matching the Python variant (which fixed the same issue in 1.4.1). The saved position is stored as a height-invariant bottom anchor, so restarting during peak hours can no longer drift the widget.

## 2.1.1 — 2026-07-21

### 🐛 Bug fixes

- **The tray tooltip no longer shows a bogus third "Unknown (spend)" entry behind the session and weekly values.** claude.ai's usage response recently gained a `spend` object (credit-balance metadata, not a usage limit); both variants mistook every non-`extra_usage` object for a usage bucket and rendered it with the generic "Unknown (…)" label. A response object is now only treated as a bucket when it carries a real utilization value, so genuinely new limit buckets still appear while metadata like `spend` is ignored.

## 2.1.0 — 2026-07-20

The tracker now ships in **two variants** in every release — pick one on the ["Which version is for me?"](https://github.com/Liwindo/ClaudeUsageTracker#which-version-is-for-me) table. Both monitor the same claude.ai limits and read the same Firefox cookies; they share one version number from now on (which is why the Python variant jumps from 1.5.2 straight to 2.1.0).

### ✨ C# variant (new)

- First release of the C#/.NET 10 port, available two ways:
  - `ClaudeUsageTracker-Setup-2.1.0.exe` — per-user installer (no admin rights): Start-menu entry, optional autostart, uninstaller. Detects a missing .NET 10 Desktop Runtime and offers to download it from the official Microsoft link.
  - `ClaudeUsageTracker-Portable-2.1.0.exe` — everything in a single EXE, no installation, no dependencies.
- What it adds over the Python variant: a **settings dialog** (no more hand-editing config.toml), **clickable notifications** (click → claude.ai, missed ones land in the Action Center), an **instant re-poll** after standby resume or network return (offline it doesn't poll at all), efficiency mode (EcoQoS), per-monitor DPI sharpness, edge snapping, animated bars — and a smaller memory footprint.
- Runs side by side with the Python variant: own config folder (`%APPDATA%\claude-usage-tracker-cs`), own autostart entry, own process name.

### 🐍 Python variant

- No functional changes — `ClaudeUsageTracker.exe` keeps working exactly as in 1.5.2; the version only moves in lockstep with the new C# variant.

### 📦 Both

- Releases now include a `SHA256SUMS.txt` with checksums of all three EXEs.

## 1.5.2 — 2026-07-02

### 🐛 Bug fixes

- When the 5-hour session window has ended and the next one hasn't started yet, the widget footer now says "Waiting for first message" (translated into all 9 languages) instead of the garbled "reset resetting…". A new session only begins with your first message, so there is no countdown to show in that state.

## 1.5.1 — 2026-07-01

### 🐛 Bug fixes

- **The released EXE could no longer reach claude.ai (constant 403 "Session expired" even with a fresh Firefox login).** The GitHub build runner compiled the 1.5.0 EXE with its preinstalled Python 3.12, whose bundled OpenSSL produces a TLS fingerprint Cloudflare currently blocks. The build Python is now pinned to 3.14.4 (`.python-version`) — the same runtime the EXE was always built with locally, which Cloudflare accepts. Cookie reading itself was never affected.
- The widget's footer status line (e.g. "Session expired — open claude.ai in Firefox") no longer gets cut off at the right edge. Like the peak-hour banner, it now wraps to as many lines as needed for the current widget width — translations made these texts longer than the widget — and the window grows to keep every line visible, shrinking back once a shorter status arrives.

## 1.5.0 — 2026-07-01

### ✨ New features

- **The app is now multilingual.** All visible texts — widget, tray menu, desktop notifications, update dialog, and error messages — are available in English, German, French, Spanish, Italian, Portuguese, Dutch, Polish, and Russian. The language follows the Windows display language automatically; a new `language` option in `config.toml` (default `"auto"`) can pin it to a specific language. Log file entries stay English so logs remain shareable for support.

## 1.4.3 — 2026-06-24

### 💄 UI

- The "update available" dialog shown at startup is now clearly branded as Claude Usage Tracker: it leads with the app logo and name plus an "Update available" header, so it's immediately obvious which app is reporting the update rather than relying on the title bar alone. The window title was shortened so it is no longer clipped in the compact dialog.

### 🔧 Build / developer

- The local build scripts (`build_exe.bat` / `build_exe_clean.bat`) now enforce the same quality gates as the GitHub release workflow: a CHANGELOG check for the current version, byte-compilation, the full test suite, and an abort if the existing EXE is locked — so a local build can no longer silently produce a stale or untested EXE.
- Batch files are pinned to CRLF line endings (via `.gitattributes`) so `cmd.exe` parses them correctly regardless of editor or `core.autocrlf`.
- The clean build now calls `build_exe.bat` by absolute path, avoiding a transient failure when the working directory was being synced.

## 1.4.2 — 2026-06-23

### ✨ New features

- The version number in the title row now appears only on hover, just like the refresh / minimise / quit buttons — the resting widget stays clean.

### 🐛 Bug fixes

- The peak-hour warning is now fully readable at any widget size. Its text wraps to as many lines as needed and the widget grows taller to fit, instead of being clipped on the right when the widget is made narrow.

## 1.4.1 — 2026-06-20

### 🐛 Bug fixes

- The widget no longer creeps slightly downward on each restart or peak/non-peak transition. The peak-hour banner's grow/shrink now derives from an authoritative, banner-free window frame and re-asserts its position after Windows settles the resize — so a reverted move can no longer drift the bottom edge (or the saved position) down by the banner height.

## 1.4.0 — 2026-06-11

### ✨ New features

- **The running version is visible in the app** — in the widget's title row and as a header line in the tray menu.
- **Skip a release you don't want.** The update dialog now has a third button, **Skip version** — that release will never be offered again, while anything newer still triggers the dialog. (Undo by clearing `skip_update_version` in the config.)
- **Start with Windows.** Set `autostart = true` in the config and the app registers itself to launch at login (current user, packaged EXE only). The entry is kept in sync on every start, so a moved EXE re-registers itself automatically.
- **Only one instance at a time.** Launching the EXE while it's already running now just shows a short hint instead of starting a second tray icon that doubles every request to claude.ai.
- **The config file maintains itself.** `config.toml` always contains every available option. When an update introduces a new option, it is appended to your existing file with its default value on the next start — you only ever change values, never add keys.

### 🔧 Under the hood

- Releases are now built, tested, and published automatically on clean GitHub runners, with release notes sourced from this changelog
- A test suite (33 tests) guards the config migration, usage-response parsing, notification thresholds, and the update check; CI runs it on every change
- Workflow hardening: minimal token permissions, supply-chain-pinned actions (CodeQL: zero findings); Dependabot keeps the pinned actions updated
- The version number now lives in a single place (`__init__.py`)

### 📝 Docs

- README: widget screenshot, CI badge, and a 40 % trim with the same information

## 1.3.0 — 2026-06-10

### ✨ New features

- **Update check on startup** (once per start): if a newer release exists on GitHub, a dialog offers to open the release page. Disable with `update_check = false`.
- **User-Agent override** (`user_agent` in config.toml) — fix Cloudflare blocks after a Firefox update without waiting for a new build.

### 🐛 Bug fixes

- First poll result is shown immediately instead of up to 30 s of "connecting…"
- Reset notifications fire once per limit instead of once per threshold; slowly declining usage no longer triggers a false "limit has reset" toast
- Desktop notifications work in the packaged EXE (they silently failed before)
- Long tray tooltips no longer break the data display
- Lowercase `log_level` values no longer crash the app at startup
- Exponential backoff on rate limiting (HTTP 429)
- Firefox profile auto-detection honours the default profile; Firefox container cookies can no longer shadow the regular login
- The widget can no longer get stuck off-screen after a monitor change

## 1.2.0 — 2026-06-09

- Peak-hour banner with automatic conversion to your local time zone

## 1.1.0

- Premium glass widget redesign

## 1.0.0

- Initial public release
