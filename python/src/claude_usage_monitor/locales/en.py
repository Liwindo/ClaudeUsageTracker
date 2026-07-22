"""English — the authoritative catalog: every other language mirrors this key set."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — loading…",
    "tray.error": "Error: {message}",
    "tray.menu.show_hide": "Show / hide widget",
    "tray.menu.refresh": "Refresh now",
    "tray.menu.check_updates": "Check for updates",
    "tray.menu.view_log": "View log file",
    "tray.menu.open_appdata": "Open app data folder",
    "tray.menu.quit": "Quit",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Session (5h)",
    "bucket.weekly": "Weekly",
    "bucket.opus_weekly": "Opus Weekly",
    "bucket.sonnet_weekly": "Sonnet Weekly",
    "bucket.teams_weekly": "Teams Weekly",
    "bucket.oauth_weekly": "OAuth Apps Weekly",
    "bucket.opus_promo": "Opus Promo",
    "bucket.unknown": "Unknown ({key})",
    "countdown.hours_minutes": "{hours}h {minutes}m",
    "countdown.minutes": "{minutes}m",
    "tooltip.no_data": "No data",

    # Desktop notifications
    "notify.threshold.title": "Claude Usage — {label} at {percent}%",
    "notify.threshold.body": (
        "You've reached {threshold}% of your {label} limit.\n"
        "Consider wrapping up or waiting for the reset."
    ),
    "notify.reset.title": "Claude Usage — {label} reset",
    "notify.reset.body": "{label} limit has reset. Current usage: {percent}%.",

    # Widget
    "widget.metric.session": "Session",
    "widget.metric.weekly": "Weekly",
    "widget.status.connecting": "connecting…",
    "widget.status.active": "active",
    "widget.status.reset_in": "reset {countdown}",
    "widget.status.waiting_first_message": "Waiting for first message",
    "widget.menu.refresh": "Refresh",
    "widget.menu.quit": "Quit",
    "widget.peak_banner": "⚠ Peak hour ({start} – {end}) - reduced token limit",
    "widget.error.session_expired": "Session expired — open claude.ai in Firefox",
    "widget.error.cloudflare": "Blocked by Cloudflare — visit claude.ai in Firefox",
    "widget.error.login": "Log in to claude.ai in Firefox first",
    "widget.error.rate_limited": "Rate limited — waiting for next poll",
    "widget.error.network": "Network error — check connection",
    "widget.error.generic": "Error — hover here for details",
    "widget.tooltip.log": "Log: {path}",

    # Update dialog
    "update.window_title": "Update",
    "update.available": "Update available",
    "update.version_available": "Version {version} is available",
    "update.running_version": "You are running version {version}.",
    "update.cancel": "Cancel",
    "update.skip": "Skip version",
    "update.open_github": "Open GitHub",
    "update.up_to_date": "You are running the latest version ({version}).",
    "update.check_failed": "Could not check for updates. Please try again later.",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker is already running.\n"
        "Look for the coloured circle in the system tray."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Startup Error",
    "dialog.startup_error.body": "Failed to load configuration:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Fatal Error",
    "dialog.fatal.body": (
        "The application crashed and must close.\n\n"
        "{error}\n\n"
        "Full details in the log file:\n{log_file}"
    ),
}
