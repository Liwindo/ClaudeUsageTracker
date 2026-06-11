# Changelog

User-facing changes per release. The release workflow publishes the matching
section as the GitHub release notes — **a release without an entry here fails**.

## Unreleased

- Workflow hardening: minimal token permissions, supply-chain-pinned actions
  (CodeQL: zero findings), Dependabot now also updates the pinned actions
- Release notes are now sourced from this changelog instead of being
  auto-generated from (non-existent) pull requests

## 1.4.0 — 2026-06-11

### ✨ New features

- **Skip a release you don't want.** The update dialog now has a third button, **Skip version** — that release will never be offered again, while anything newer still triggers the dialog. (Undo by clearing `skip_update_version` in the config.)
- **Start with Windows.** Set `autostart = true` in the config and the app registers itself to launch at login (current user, packaged EXE only). The entry is kept in sync on every start, so a moved EXE re-registers itself automatically.
- **Only one instance at a time.** Launching the EXE while it's already running now just shows a short hint instead of starting a second tray icon that doubles every request to claude.ai.
- **The config file maintains itself.** `config.toml` always contains every available option. When an update introduces a new option, it is appended to your existing file with its default value on the next start — you only ever change values, never add keys.

### 🔧 Under the hood

- Releases are now built, tested, and published automatically on clean GitHub runners
- A test suite (33 tests) guards the config migration, usage-response parsing, notification thresholds, and the update check; CI runs it on every change
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
