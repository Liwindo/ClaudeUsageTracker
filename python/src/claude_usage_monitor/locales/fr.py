"""Français."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — chargement…",
    "tray.error": "Erreur : {message}",
    "tray.menu.show_hide": "Afficher / masquer le widget",
    "tray.menu.refresh": "Actualiser maintenant",
    "tray.menu.view_log": "Afficher le fichier journal",
    "tray.menu.open_appdata": "Ouvrir le dossier de données",
    "tray.menu.quit": "Quitter",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Session (5 h)",
    "bucket.weekly": "Hebdomadaire",
    "bucket.opus_weekly": "Opus (hebdo)",
    "bucket.sonnet_weekly": "Sonnet (hebdo)",
    "bucket.teams_weekly": "Teams (hebdo)",
    "bucket.oauth_weekly": "Applis OAuth (hebdo)",
    "bucket.opus_promo": "Promo Opus",
    "bucket.unknown": "Inconnu ({key})",
    "countdown.hours_minutes": "{hours} h {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Aucune donnée",

    # Desktop notifications
    "notify.threshold.title": "Utilisation Claude — {label} à {percent} %",
    "notify.threshold.body": (
        "Vous avez atteint {threshold} % de votre limite « {label} ».\n"
        "Pensez à conclure ou attendez la réinitialisation."
    ),
    "notify.reset.title": "Utilisation Claude — {label} réinitialisée",
    "notify.reset.body": (
        "La limite « {label} » a été réinitialisée. Utilisation actuelle : {percent} %."
    ),

    # Widget
    "widget.metric.session": "Session",
    "widget.metric.weekly": "Hebdo",
    "widget.status.connecting": "connexion…",
    "widget.status.active": "actif",
    "widget.status.reset_in": "réinit. dans {countdown}",
    "widget.status.waiting_first_message": "En attente du premier message",
    "widget.menu.refresh": "Actualiser",
    "widget.menu.quit": "Quitter",
    "widget.peak_banner": "⚠ Heure de pointe ({start} – {end}) – limite de jetons réduite",
    "widget.error.session_expired": "Session expirée — ouvrez claude.ai dans Firefox",
    "widget.error.cloudflare": "Bloqué par Cloudflare — visitez claude.ai dans Firefox",
    "widget.error.login": "Connectez-vous d'abord à claude.ai dans Firefox",
    "widget.error.rate_limited": "Débit limité — en attente du prochain sondage",
    "widget.error.network": "Erreur réseau — vérifiez la connexion",
    "widget.error.generic": "Erreur — survolez ici pour les détails",
    "widget.tooltip.log": "Journal : {path}",

    # Update dialog
    "update.window_title": "Mise à jour",
    "update.available": "Mise à jour disponible",
    "update.version_available": "La version {version} est disponible",
    "update.running_version": "Vous utilisez la version {version}.",
    "update.cancel": "Annuler",
    "update.skip": "Ignorer cette version",
    "update.open_github": "Ouvrir GitHub",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker est déjà en cours d'exécution.\n"
        "Cherchez le cercle coloré dans la zone de notification."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Erreur de démarrage",
    "dialog.startup_error.body": "Échec du chargement de la configuration :\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Erreur fatale",
    "dialog.fatal.body": (
        "L'application a planté et doit se fermer.\n\n"
        "{error}\n\n"
        "Détails complets dans le fichier journal :\n{log_file}"
    ),
}
