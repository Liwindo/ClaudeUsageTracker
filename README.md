# Claude Usage Tracker

[![CI (Python)](https://github.com/Liwindo/ClaudeUsageTracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Liwindo/ClaudeUsageTracker/actions/workflows/ci.yml)
[![CI (C#)](https://github.com/Liwindo/ClaudeUsageTracker/actions/workflows/ci-csharp.yml/badge.svg)](https://github.com/Liwindo/ClaudeUsageTracker/actions/workflows/ci-csharp.yml)
[![Latest release](https://img.shields.io/github/v/release/Liwindo/ClaudeUsageTracker?logo=github)](../../releases/latest)
[![License: MIT](https://img.shields.io/github/license/Liwindo/ClaudeUsageTracker)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Languages](https://img.shields.io/badge/🌐_languages-9-2ea44f)

<p align="center">
  <img src="docs/screenshot.png" alt="Floating widget" width="300">
</p>

A lightweight Windows system-tray app that tracks your [claude.ai](https://claude.ai) **usage limits** — your **session (5-hour)** and **weekly** rate limits, for Claude Free, Pro, and Max plans — at a glance. A colour-coded tray icon and an optional floating widget update automatically in the background, so you never have to open the usage page or interrupt a conversation to see how much of your limit is left. The interface is available in 9 languages and follows your Windows display language automatically.

> **Disclaimer:** This tool uses internal, undocumented claude.ai API endpoints. It may break without notice. This project is not affiliated with or endorsed by Anthropic.

## Which version is for me?

The tracker ships in two variants that monitor the same claude.ai limits and read the same Firefox cookies. Every [release](../../releases/latest) contains all three downloads plus a `SHA256SUMS.txt` with their checksums:

| I want to… | Download |
|------------|----------|
| just install it and go | **`ClaudeUsageTracker-Setup-X.Y.Z.exe`** (C#, ~4 MB) — **recommended**. Per-user install (no admin rights), Start-menu entry, optional autostart, uninstaller. Downloads the .NET runtime automatically if it is missing. |
| nothing installed, a single EXE | `ClaudeUsageTracker-Portable-X.Y.Z.exe` (C#, ~80 MB) — no installation, no dependencies; runs from anywhere, USB stick included. |
| keep using the classic Python build | `ClaudeUsageTracker.exe` (Python, ~12 MB) — the proven original, portable as always. |

The **C# variant** (new) additionally offers a settings dialog (no more hand-editing the config file), clickable notifications, an instant re-poll after standby/network changes, and a smaller memory footprint. The **Python variant** is the battle-tested base the project started with — it keeps working exactly as before.

Both variants use separate config folders, so they can run side by side while you compare (that doubles the requests to claude.ai — harmless, but pick one for daily use). Settings use the same TOML format in both; to migrate, copy your values over once — or just set them again in the C# settings dialog.

- **C# variant:** sources, build, and details in [`csharp/`](csharp/README.md)
- **Python variant:** sources, build, and details in [`python/`](python/README.md)

## How it works (both variants)

The tool reads your existing claude.ai session cookies directly from Firefox's cookie database — read-only, no file copy, **no passwords, no manual exports, no stored credentials** — and polls claude.ai's internal `/usage` endpoint every 30 seconds (configurable). Firefox does not need to be open while the tool is running. Once per start it asks the GitHub API whether a newer release exists (disable with `update_check = false`).

**Why Firefox only?** Since Chrome 127, Chromium browsers encrypt cookies with App-Bound Encryption — only the browser itself can decrypt them, and there is no user-space workaround. Firefox stores cookies unencrypted in SQLite, making it the only reliably supported browser.

## Privacy

- Outbound traffic is limited to HTTPS requests to `claude.ai` (the same ones your browser already makes) and, unless disabled, a single anonymous version lookup to `api.github.com` per app start. No cookies or usage data ever leave your machine; no telemetry.
- Cookies are read read-only from the Firefox database into memory for each poll and are never written to any other file.

## Repository layout

```
python/    the Python variant (source, tests, PyInstaller build)
csharp/    the C# variant (source, tests, installer, release build)
scripts/   shared tooling: locale export/check, lockstep version bump,
           changelog guard, dependency validation
docs/      screenshots
```

One version number covers both variants: releases are tagged `vX.Y.Z` and built by CI from the matching [CHANGELOG.md](CHANGELOG.md) section. Translations have a single source — the Python locale catalogs — and CI fails if the C# catalogs drift (`scripts/export_locales.py --check`).

The behaviour both variants must share — including the invisible invariants that
aren't obvious from the UI — is written down in [REQUIREMENTS.md](REQUIREMENTS.md).
Any behavioural change updates it in the same PR (see its "Keeping this file
complete" section and the pull-request checklist).

## License

MIT
