# Claude Usage Tracker

<p align="center">
  <img src="src/claude_usage_monitor/assets/logo.png" alt="Claude Usage Tracker" width="200">
</p>

A lightweight Windows system-tray tool that shows your [claude.ai](https://claude.ai) usage limits at a glance — without opening a browser tab.

## Why this exists

The Claude desktop app doesn't surface usage limits anywhere in the chat interface. To check how much of your session or weekly quota is left, you have to leave the conversation, open a menu, and navigate to the usage page — interrupting your workflow every time.

This tool puts the information where you can always see it: a colour-coded tray icon and an optional floating widget, updated automatically in the background.

> **Disclaimer:** This tool uses internal, undocumented claude.ai API endpoints that Anthropic has not publicly documented. It may break without notice. This project is not affiliated with or endorsed by Anthropic.

## Quick start

**Option A — Download the EXE (no Python required)**

1. Download `ClaudeUsageTracker.exe` from the [latest release](../../releases/latest)
2. Double-click it — it starts in the system tray

**Option B — Build from source**

1. Install [uv](https://docs.astral.sh/uv/) if you haven't already
2. Clone the repo and run:
   ```
   build_exe.bat
   ```
   The script handles everything (dependencies, PyInstaller, build). The EXE ends up in `dist\ClaudeUsageTracker.exe`.

## How it works

The tool reads your existing session cookies directly from Firefox's local cookie database — **no passwords, no manual exports, no stored credentials**. It then polls `claude.ai`'s internal `/usage` endpoint every 30 seconds (configurable) and updates the tray icon and floating widget accordingly. Firefox does not need to be open while the tool is running.

Cookie values are read directly from the database file using a read-only SQLite connection. Firefox's WAL journal mode allows concurrent reads without needing a file copy.

On each poll cycle the tool calls two endpoints: `/api/bootstrap/{org}/app_start` to determine the subscription tier (cached for one hour to halve the request volume) and `/api/organizations/{org}/usage` for the actual limits.

## Why Firefox only?

Chrome (and other Chromium-based browsers) introduced **App-Bound Encryption** in version 127 (July 2024). Cookie values are encrypted with a key that is cryptographically tied to the Chrome application itself — decryption requires Chrome's own elevation service and cannot be performed by any external process, regardless of permissions.

In practice, this means:
- When Chrome is **running**: the Cookies database file is locked exclusively — no other process can read or copy it.
- When Chrome is **closed**: the file can be read, but the cookie values are encrypted with a key only Chrome can access — they cannot be decrypted externally.

This is a deliberate security measure by Google to prevent cookie theft, and there is no user-space workaround. Firefox stores cookies unencrypted in its SQLite database and does not apply equivalent restrictions, making it the only reliably supported browser for this tool.

## Requirements

- Windows 10/11
- **Firefox** (Mozilla build), logged in to claude.ai. Firefox forks such as LibreWolf, Floorp, or Waterfox use different `AppData` paths and are not auto-detected — point `firefox_profile_path` at the fork's profile if you want to try them.
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) *(only if building from source)*

## Tray icon

The coloured circle reflects your current **session (5-hour)** limit:

| Colour | Session usage |
|--------|--------------|
| 🟢 Green  | Below 40%   |
| 🟡 Yellow | 40–59%      |
| 🟠 Orange | 60–84%      |
| 🔴 Red    | 85%+        |
| ⚫ Grey   | No data / error |

Left-click the icon to show or hide the widget. Right-click for **Show / hide widget**, **Refresh now**, **View log file**, **Open app data folder**, and **Quit**.

## Floating widget

An always-on-top mini-panel shows:

- **Session** — 5-hour usage % with progress bar
- **Weekly** — weekly usage % with progress bar
- **Reset countdown** — time until the session limit resets; the dot colour indicates how soon the limit refreshes:

  | Dot colour | Time until reset |
  |------------|-----------------|
  | 🟢 Green  | < 15 min        |
  | 🟡 Yellow | 15–30 min       |
  | 🟠 Orange | 30–90 min       |
  | 🔴 Red    | > 90 min        |

- Progress bars use the same four-colour scale as the tray icon (green → yellow → orange → red at 40 / 60 / 85 %)
- Hover to reveal **refresh (⟳)**, **minimise (−)**, and **quit (×)** buttons
- Drag anywhere to reposition; drag the bottom-right grip to resize
- Right-click for a context menu
- Position, size, and minimised state are remembered between sessions — if the widget was hidden when you last quit, it stays hidden in the tray on next launch

**Error display** — when a poll fails, the footer shows a short inline message (e.g. *"Session expired — open claude.ai in Firefox"*). For unexpected errors it shows *"Error — hover here for details"*; hovering over that text reveals a tooltip with the full error message and the path to the log file.

## Configuration

The config file is created automatically on first run at:

```
%APPDATA%\claude-usage-monitor\config.toml
```

Available settings:

```toml
# How often to poll claude.ai (seconds). Default: 30.
poll_interval_seconds = 30

# Percent thresholds that trigger a desktop notification.
notification_thresholds = [80, 95]

# Log level: DEBUG, INFO, WARNING, ERROR.
# Note: at DEBUG level the full claude.ai /usage response (including
# organisation UUID and bucket data) is written to app.log. Keep WARNING
# unless you're actively debugging, and review the log before sharing it.
log_level = "WARNING"

# Override the Firefox profile directory (leave empty for auto-detection).
firefox_profile_path = ""
```

### Custom Firefox profile path

If auto-detection picks the wrong profile, set the path manually:

```toml
firefox_profile_path = "C:\\Users\\YourName\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\abc123.default-release"
```

## Running from source

```bash
uv sync
start.bat
```

Or directly:

```bash
uv run python -m claude_usage_monitor
```

## Rebuilding the EXE

```bash
# Incremental rebuild (~10 s, uses cached build/):
build_exe.bat

# Clean rebuild from scratch (~30 s):
build_exe_clean.bat
```

## Troubleshooting

### Grey icon / "No claude.ai cookies found"

You must be logged in to claude.ai in Firefox. Open [claude.ai](https://claude.ai), log in, then right-click the tray icon → **Refresh now**.

### "Session expired" / grey icon after working for a while

Your Cloudflare clearance cookie has expired. Visit claude.ai in Firefox — navigating the page refreshes the cookie automatically. The next poll will succeed.

### Requests return 403

Cloudflare is blocking the request. The `cf_clearance` cookie is likely stale. Open claude.ai in Firefox, navigate around briefly, then right-click → **Refresh now**.

### "Firefox profiles.ini not found"

Firefox has not been launched yet or is not installed. Launch Firefox, log in to claude.ai, then restart this tool.

### The usage numbers seem wrong

The `/usage` endpoint uses Anthropic's internal bucket names (e.g. `seven_day_omelette`). The mapping to human-readable labels is best-effort and may be incorrect. Open an issue if you can confirm the correct mapping for your plan.

## Privacy

- No data leaves your machine except the HTTPS requests to `claude.ai` (which your browser already makes).
- Cookie values are read directly from the Firefox database without copying the file to disk.
- Firefox cookies are stored unencrypted in the SQLite database; they are read into memory for the duration of each poll only and are never written to any other file.
- No telemetry.

## Project structure

```
src/claude_usage_monitor/
├── __main__.py          Entry point
├── app.py               Orchestration (threads, callbacks)
├── config.py            TOML config, OS paths
├── firefox_cookies.py   Read cookies.sqlite from Firefox (read-only, no copy)
├── client.py            httpx calls to claude.ai (⚠ reverse-engineered)
├── models.py            UsageData / LimitInfo dataclasses
├── poller.py            Background polling thread
├── tray.py              pystray icon + colour logic
├── widget.py            Persistent always-on-top tkinter widget
├── notifications.py     Desktop notification throttling
└── assets/              Application icons (logo.png, logo.ico)
```

## License

MIT
