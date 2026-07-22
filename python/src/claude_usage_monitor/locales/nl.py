"""Nederlands."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — laden…",
    "tray.error": "Fout: {message}",
    "tray.menu.show_hide": "Widget tonen / verbergen",
    "tray.menu.refresh": "Nu vernieuwen",
    "tray.menu.check_updates": "Op updates controleren",
    "tray.menu.view_log": "Logbestand bekijken",
    "tray.menu.open_appdata": "App-gegevensmap openen",
    "tray.menu.quit": "Afsluiten",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Sessie (5 u)",
    "bucket.weekly": "Wekelijks",
    "bucket.opus_weekly": "Opus (wekelijks)",
    "bucket.sonnet_weekly": "Sonnet (wekelijks)",
    "bucket.teams_weekly": "Teams (wekelijks)",
    "bucket.oauth_weekly": "OAuth-apps (wekelijks)",
    "bucket.opus_promo": "Opus-promo",
    "bucket.unknown": "Onbekend ({key})",
    "countdown.hours_minutes": "{hours} u {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Geen gegevens",

    # Desktop notifications
    "notify.threshold.title": "Claude-gebruik — {label} op {percent} %",
    "notify.threshold.body": (
        "Je hebt {threshold} % van je limiet '{label}' bereikt.\n"
        "Rond het werk af of wacht op de reset."
    ),
    "notify.reset.title": "Claude-gebruik — {label} gereset",
    "notify.reset.body": (
        "De limiet '{label}' is gereset. Huidig gebruik: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Sessie",
    "widget.metric.weekly": "Week",
    "widget.status.connecting": "verbinden…",
    "widget.status.active": "actief",
    "widget.status.reset_in": "reset over {countdown}",
    "widget.status.waiting_first_message": "Wachten op het eerste bericht",
    "widget.menu.refresh": "Vernieuwen",
    "widget.menu.quit": "Afsluiten",
    "widget.peak_banner": "⚠ Piekuren ({start} – {end}) – verlaagde tokenlimiet",
    "widget.error.session_expired": "Sessie verlopen — open claude.ai in Firefox",
    "widget.error.cloudflare": "Geblokkeerd door Cloudflare — bezoek claude.ai in Firefox",
    "widget.error.login": "Log eerst in op claude.ai in Firefox",
    "widget.error.rate_limited": "Rate-limit — wachten op volgende poll",
    "widget.error.network": "Netwerkfout — controleer de verbinding",
    "widget.error.generic": "Fout — beweeg hierheen voor details",
    "widget.tooltip.log": "Log: {path}",

    # Update dialog
    "update.window_title": "Update",
    "update.available": "Update beschikbaar",
    "update.version_available": "Versie {version} is beschikbaar",
    "update.running_version": "Je gebruikt versie {version}.",
    "update.cancel": "Annuleren",
    "update.skip": "Versie overslaan",
    "update.open_github": "GitHub openen",
    "update.up_to_date": "Je gebruikt de nieuwste versie ({version}).",
    "update.check_failed": "Kan niet op updates controleren. Probeer het later opnieuw.",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker is al actief.\n"
        "Zoek de gekleurde cirkel in het systeemvak."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Opstartfout",
    "dialog.startup_error.body": "Kan de configuratie niet laden:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Fatale fout",
    "dialog.fatal.body": (
        "De applicatie is gecrasht en moet afsluiten.\n\n"
        "{error}\n\n"
        "Volledige details in het logbestand:\n{log_file}"
    ),
}
