"""Русский."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — загрузка…",
    "tray.error": "Ошибка: {message}",
    "tray.menu.show_hide": "Показать / скрыть виджет",
    "tray.menu.refresh": "Обновить сейчас",
    "tray.menu.view_log": "Открыть файл журнала",
    "tray.menu.open_appdata": "Открыть папку данных приложения",
    "tray.menu.quit": "Выход",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Сессия (5 ч)",
    "bucket.weekly": "Неделя",
    "bucket.opus_weekly": "Opus (неделя)",
    "bucket.sonnet_weekly": "Sonnet (неделя)",
    "bucket.teams_weekly": "Teams (неделя)",
    "bucket.oauth_weekly": "OAuth-приложения (неделя)",
    "bucket.opus_promo": "Промо Opus",
    "bucket.unknown": "Неизвестно ({key})",
    "countdown.hours_minutes": "{hours} ч {minutes} мин",
    "countdown.minutes": "{minutes} мин",
    "tooltip.no_data": "Нет данных",

    # Desktop notifications
    "notify.threshold.title": "Использование Claude — {label}: {percent} %",
    "notify.threshold.body": (
        "Достигнуто {threshold} % лимита «{label}».\n"
        "Лучше завершить работу или дождаться сброса."
    ),
    "notify.reset.title": "Использование Claude — {label}: сброс",
    "notify.reset.body": (
        "Лимит «{label}» сброшен. Текущее использование: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Сессия",
    "widget.metric.weekly": "Неделя",
    "widget.status.connecting": "подключение…",
    "widget.status.active": "активно",
    "widget.status.reset_in": "сброс через {countdown}",
    "widget.status.waiting_first_message": "Ожидание первого сообщения",
    "widget.menu.refresh": "Обновить",
    "widget.menu.quit": "Выход",
    "widget.peak_banner": "⚠ Часы пик ({start} – {end}) – сниженный лимит токенов",
    "widget.error.session_expired": "Сессия истекла — откройте claude.ai в Firefox",
    "widget.error.cloudflare": "Заблокировано Cloudflare — зайдите на claude.ai в Firefox",
    "widget.error.login": "Сначала войдите на claude.ai в Firefox",
    "widget.error.rate_limited": "Превышен лимит запросов — ожидание следующего опроса",
    "widget.error.network": "Ошибка сети — проверьте подключение",
    "widget.error.generic": "Ошибка — наведите сюда для подробностей",
    "widget.tooltip.log": "Журнал: {path}",

    # Update dialog
    "update.window_title": "Обновление",
    "update.available": "Доступно обновление",
    "update.version_available": "Доступна версия {version}",
    "update.running_version": "Установлена версия {version}.",
    "update.cancel": "Отмена",
    "update.skip": "Пропустить версию",
    "update.open_github": "Открыть GitHub",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker уже запущен.\n"
        "Ищите цветной кружок в системном трее."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Ошибка запуска",
    "dialog.startup_error.body": "Не удалось загрузить конфигурацию:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Критическая ошибка",
    "dialog.fatal.body": (
        "Приложение аварийно завершилось.\n\n"
        "{error}\n\n"
        "Подробности в файле журнала:\n{log_file}"
    ),
}
