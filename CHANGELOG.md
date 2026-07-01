# Changelog

User-facing changes per release. The release workflow publishes the matching
section as the GitHub release notes — **a release without an entry here fails**.

## Unreleased

### 🐛 Bug fixes

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
