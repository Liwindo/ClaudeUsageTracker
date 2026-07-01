"""Español."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — cargando…",
    "tray.error": "Error: {message}",
    "tray.menu.show_hide": "Mostrar / ocultar widget",
    "tray.menu.refresh": "Actualizar ahora",
    "tray.menu.view_log": "Ver archivo de registro",
    "tray.menu.open_appdata": "Abrir carpeta de datos",
    "tray.menu.quit": "Salir",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Sesión (5 h)",
    "bucket.weekly": "Semanal",
    "bucket.opus_weekly": "Opus (semanal)",
    "bucket.sonnet_weekly": "Sonnet (semanal)",
    "bucket.teams_weekly": "Teams (semanal)",
    "bucket.oauth_weekly": "Apps OAuth (semanal)",
    "bucket.opus_promo": "Promo Opus",
    "bucket.unknown": "Desconocido ({key})",
    "countdown.resetting": "reiniciando…",
    "countdown.hours_minutes": "{hours} h {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Sin datos",

    # Desktop notifications
    "notify.threshold.title": "Uso de Claude — {label} al {percent} %",
    "notify.threshold.body": (
        "Has alcanzado el {threshold} % de tu límite «{label}».\n"
        "Considera terminar pronto o esperar el reinicio."
    ),
    "notify.reset.title": "Uso de Claude — {label} reiniciado",
    "notify.reset.body": (
        "El límite «{label}» se ha reiniciado. Uso actual: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Sesión",
    "widget.metric.weekly": "Semanal",
    "widget.status.connecting": "conectando…",
    "widget.status.active": "activo",
    "widget.status.reset_in": "reinicio en {countdown}",
    "widget.menu.refresh": "Actualizar",
    "widget.menu.quit": "Salir",
    "widget.peak_banner": "⚠ Hora punta ({start} – {end}) – límite de tokens reducido",
    "widget.error.session_expired": "Sesión caducada — abre claude.ai en Firefox",
    "widget.error.cloudflare": "Bloqueado por Cloudflare — visita claude.ai en Firefox",
    "widget.error.login": "Inicia sesión primero en claude.ai en Firefox",
    "widget.error.rate_limited": "Límite de peticiones — esperando el próximo sondeo",
    "widget.error.network": "Error de red — comprueba la conexión",
    "widget.error.generic": "Error — pasa el cursor aquí para ver detalles",
    "widget.tooltip.log": "Registro: {path}",

    # Update dialog
    "update.window_title": "Actualización",
    "update.available": "Actualización disponible",
    "update.version_available": "La versión {version} está disponible",
    "update.running_version": "Estás usando la versión {version}.",
    "update.cancel": "Cancelar",
    "update.skip": "Omitir versión",
    "update.open_github": "Abrir GitHub",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker ya se está ejecutando.\n"
        "Busca el círculo de color en la bandeja del sistema."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Error de inicio",
    "dialog.startup_error.body": "No se pudo cargar la configuración:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Error fatal",
    "dialog.fatal.body": (
        "La aplicación ha fallado y debe cerrarse.\n\n"
        "{error}\n\n"
        "Detalles completos en el archivo de registro:\n{log_file}"
    ),
}
