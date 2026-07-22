"""Polski."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — ładowanie…",
    "tray.error": "Błąd: {message}",
    "tray.menu.show_hide": "Pokaż / ukryj widżet",
    "tray.menu.refresh": "Odśwież teraz",
    "tray.menu.check_updates": "Sprawdź aktualizacje",
    "tray.menu.view_log": "Pokaż plik dziennika",
    "tray.menu.open_appdata": "Otwórz folder danych aplikacji",
    "tray.menu.quit": "Zakończ",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Sesja (5 h)",
    "bucket.weekly": "Tydzień",
    "bucket.opus_weekly": "Opus (tydzień)",
    "bucket.sonnet_weekly": "Sonnet (tydzień)",
    "bucket.teams_weekly": "Teams (tydzień)",
    "bucket.oauth_weekly": "Aplikacje OAuth (tydzień)",
    "bucket.opus_promo": "Promocja Opus",
    "bucket.unknown": "Nieznany ({key})",
    "countdown.hours_minutes": "{hours} godz. {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Brak danych",

    # Desktop notifications
    "notify.threshold.title": "Użycie Claude — {label}: {percent} %",
    "notify.threshold.body": (
        "Osiągnięto {threshold} % limitu „{label}”.\n"
        "Warto wkrótce skończyć lub poczekać na reset."
    ),
    "notify.reset.title": "Użycie Claude — {label}: reset",
    "notify.reset.body": (
        "Limit „{label}” został zresetowany. Bieżące użycie: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Sesja",
    "widget.metric.weekly": "Tydzień",
    "widget.status.connecting": "łączenie…",
    "widget.status.active": "aktywny",
    "widget.status.reset_in": "reset za {countdown}",
    "widget.status.waiting_first_message": "Oczekiwanie na pierwszą wiadomość",
    "widget.menu.refresh": "Odśwież",
    "widget.menu.quit": "Zakończ",
    "widget.peak_banner": "⚠ Godziny szczytu ({start} – {end}) – obniżony limit tokenów",
    "widget.error.session_expired": "Sesja wygasła — otwórz claude.ai w Firefoksie",
    "widget.error.cloudflare": "Zablokowane przez Cloudflare — odwiedź claude.ai w Firefoksie",
    "widget.error.login": "Najpierw zaloguj się na claude.ai w Firefoksie",
    "widget.error.rate_limited": "Limit zapytań — oczekiwanie na kolejne odpytanie",
    "widget.error.network": "Błąd sieci — sprawdź połączenie",
    "widget.error.generic": "Błąd — najedź tutaj, aby zobaczyć szczegóły",
    "widget.tooltip.log": "Dziennik: {path}",

    # Update dialog
    "update.window_title": "Aktualizacja",
    "update.available": "Dostępna aktualizacja",
    "update.version_available": "Dostępna jest wersja {version}",
    "update.running_version": "Używasz wersji {version}.",
    "update.cancel": "Anuluj",
    "update.skip": "Pomiń wersję",
    "update.open_github": "Otwórz GitHub",
    "update.up_to_date": "Używasz najnowszej wersji ({version}).",
    "update.check_failed": "Nie udało się sprawdzić aktualizacji. Spróbuj ponownie później.",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "Claude Usage Tracker już działa.\n"
        "Poszukaj kolorowego kółka w zasobniku systemowym."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Błąd uruchamiania",
    "dialog.startup_error.body": "Nie udało się wczytać konfiguracji:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Błąd krytyczny",
    "dialog.fatal.body": (
        "Aplikacja uległa awarii i musi zostać zamknięta.\n\n"
        "{error}\n\n"
        "Pełne szczegóły w pliku dziennika:\n{log_file}"
    ),
}
