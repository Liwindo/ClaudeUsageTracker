"""Italiano."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — caricamento…",
    "tray.error": "Errore: {message}",
    "tray.menu.show_hide": "Mostra / nascondi widget",
    "tray.menu.refresh": "Aggiorna ora",
    "tray.menu.view_log": "Visualizza file di log",
    "tray.menu.open_appdata": "Apri cartella dati",
    "tray.menu.quit": "Esci",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Sessione (5 h)",
    "bucket.weekly": "Settimanale",
    "bucket.opus_weekly": "Opus (settimanale)",
    "bucket.sonnet_weekly": "Sonnet (settimanale)",
    "bucket.teams_weekly": "Teams (settimanale)",
    "bucket.oauth_weekly": "App OAuth (settimanale)",
    "bucket.opus_promo": "Promo Opus",
    "bucket.unknown": "Sconosciuto ({key})",
    "countdown.hours_minutes": "{hours} h {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Nessun dato",

    # Desktop notifications
    "notify.threshold.title": "Utilizzo Claude — {label} al {percent} %",
    "notify.threshold.body": (
        "Hai raggiunto il {threshold} % del limite «{label}».\n"
        "Meglio concludere presto o attendere il ripristino."
    ),
    "notify.reset.title": "Utilizzo Claude — {label} ripristinato",
    "notify.reset.body": (
        "Il limite «{label}» è stato ripristinato. Utilizzo attuale: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Sessione",
    "widget.metric.weekly": "Settimana",
    "widget.status.connecting": "connessione…",
    "widget.status.active": "attivo",
    "widget.status.reset_in": "ripristino tra {countdown}",
    "widget.status.waiting_first_message": "In attesa del primo messaggio",
    "widget.menu.refresh": "Aggiorna",
    "widget.menu.quit": "Esci",
    "widget.peak_banner": "⚠ Ora di punta ({start} – {end}) – limite di token ridotto",
    "widget.error.session_expired": "Sessione scaduta — apri claude.ai in Firefox",
    "widget.error.cloudflare": "Bloccato da Cloudflare — visita claude.ai in Firefox",
    "widget.error.login": "Accedi prima a claude.ai in Firefox",
    "widget.error.rate_limited": "Richieste limitate — in attesa del prossimo aggiornamento",
    "widget.error.network": "Errore di rete — controlla la connessione",
    "widget.error.generic": "Errore — passa qui sopra per i dettagli",
    "widget.tooltip.log": "Log: {path}",

    # Update dialog
    "update.window_title": "Aggiornamento",
    "update.available": "Aggiornamento disponibile",
    "update.version_available": "È disponibile la versione {version}",
    "update.running_version": "Stai usando la versione {version}.",
    "update.cancel": "Annulla",
    "update.skip": "Ignora versione",
    "update.open_github": "Apri GitHub",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker è già in esecuzione.\n"
        "Cerca il cerchio colorato nell'area di notifica."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Errore di avvio",
    "dialog.startup_error.body": "Impossibile caricare la configurazione:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Errore fatale",
    "dialog.fatal.body": (
        "L'applicazione si è arrestata e deve chiudersi.\n\n"
        "{error}\n\n"
        "Dettagli completi nel file di log:\n{log_file}"
    ),
}
