"""Deutsch."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — lädt…",
    "tray.error": "Fehler: {message}",
    "tray.menu.show_hide": "Widget ein-/ausblenden",
    "tray.menu.refresh": "Jetzt aktualisieren",
    "tray.menu.check_updates": "Nach Updates suchen",
    "tray.menu.release_notes": "Versionshinweise",
    "tray.menu.view_log": "Logdatei anzeigen",
    "tray.menu.open_appdata": "App-Datenordner öffnen",
    "tray.menu.quit": "Beenden",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Sitzung (5 h)",
    "bucket.weekly": "Woche",
    "bucket.opus_weekly": "Opus (Woche)",
    "bucket.sonnet_weekly": "Sonnet (Woche)",
    "bucket.teams_weekly": "Teams (Woche)",
    "bucket.oauth_weekly": "OAuth-Apps (Woche)",
    "bucket.opus_promo": "Opus-Aktion",
    "bucket.unknown": "Unbekannt ({key})",
    "countdown.hours_minutes": "{hours} h {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Keine Daten",

    # Desktop notifications
    "notify.threshold.title": "Claude-Nutzung — {label} bei {percent} %",
    "notify.threshold.body": (
        "{threshold} % des Limits „{label}“ sind erreicht.\n"
        "Besser bald abschließen oder auf den Reset warten."
    ),
    "notify.reset.title": "Claude-Nutzung — {label} zurückgesetzt",
    "notify.reset.body": (
        "Das Limit „{label}“ wurde zurückgesetzt. Aktuelle Nutzung: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Sitzung",
    "widget.metric.weekly": "Woche",
    "widget.forecast.lasts": "reicht bis Reset",
    "widget.forecast.runs_out": "Limit in {countdown}",
    "widget.status.connecting": "verbinde…",
    "widget.status.active": "aktiv",
    "widget.status.reset_in": "Reset in {countdown}",
    "widget.status.waiting_first_message": "Warte auf erste Nachricht",
    "widget.menu.refresh": "Aktualisieren",
    "widget.menu.quit": "Beenden",
    "widget.peak_banner": "⚠ Stoßzeit ({start} – {end}) – reduziertes Token-Limit",
    "widget.error.session_expired": "Sitzung abgelaufen — claude.ai in Firefox öffnen",
    "widget.error.cloudflare": "Von Cloudflare blockiert — claude.ai in Firefox besuchen",
    "widget.error.login": "Zuerst in Firefox bei claude.ai anmelden",
    "widget.error.rate_limited": "Rate-Limit — warte auf nächsten Abruf",
    "widget.error.network": "Netzwerkfehler — Verbindung prüfen",
    "widget.error.generic": "Fehler — für Details hierher zeigen",
    "widget.tooltip.log": "Log: {path}",

    # Update dialog
    "update.window_title": "Update",
    "update.available": "Update verfügbar",
    "update.cancel": "Abbrechen",
    "update.skip": "Version überspringen",
    "update.open_github": "GitHub öffnen",
    "update.up_to_date": "Sie verwenden die neueste Version ({version}).",
    "update.check_failed": "Suche nach Updates fehlgeschlagen. Bitte später erneut versuchen.",
    "update.notes_version": "Version {version}",
    "update.notes_unavailable": "Die Versionshinweise konnten nicht geladen werden. Sie finden sie auf der GitHub-Release-Seite.",
    "update.notes_more": "Ältere Änderungen finden Sie auf GitHub.",
    "update.versions": "Versionen",
    "update.latest": "neueste",
    "update.installed": "installiert",
    "update.notes_title": "Versionshinweise",
    "update.close": "Schließen",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker läuft bereits.\n"
        "Suche den farbigen Kreis im Infobereich der Taskleiste."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Startfehler",
    "dialog.startup_error.body": "Konfiguration konnte nicht geladen werden:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Schwerer Fehler",
    "dialog.fatal.body": (
        "Die Anwendung ist abgestürzt und muss beendet werden.\n\n"
        "{error}\n\n"
        "Alle Details in der Logdatei:\n{log_file}"
    ),
}
