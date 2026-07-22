"""Português."""

STRINGS: dict[str, str] = {
    # Tray icon
    "tray.loading": "Claude Usage Tracker — carregando…",
    "tray.error": "Erro: {message}",
    "tray.menu.show_hide": "Mostrar / ocultar widget",
    "tray.menu.refresh": "Atualizar agora",
    "tray.menu.check_updates": "Procurar atualizações",
    "tray.menu.view_log": "Ver arquivo de log",
    "tray.menu.open_appdata": "Abrir pasta de dados",
    "tray.menu.quit": "Sair",

    # Usage buckets (tray tooltip + notifications)
    "bucket.session": "Sessão (5 h)",
    "bucket.weekly": "Semanal",
    "bucket.opus_weekly": "Opus (semanal)",
    "bucket.sonnet_weekly": "Sonnet (semanal)",
    "bucket.teams_weekly": "Teams (semanal)",
    "bucket.oauth_weekly": "Apps OAuth (semanal)",
    "bucket.opus_promo": "Promoção Opus",
    "bucket.unknown": "Desconhecido ({key})",
    "countdown.hours_minutes": "{hours} h {minutes} min",
    "countdown.minutes": "{minutes} min",
    "tooltip.no_data": "Sem dados",

    # Desktop notifications
    "notify.threshold.title": "Uso do Claude — {label} em {percent} %",
    "notify.threshold.body": (
        "Você atingiu {threshold} % do limite «{label}».\n"
        "Considere encerrar em breve ou aguardar o reinício."
    ),
    "notify.reset.title": "Uso do Claude — {label} reiniciado",
    "notify.reset.body": (
        "O limite «{label}» foi reiniciado. Uso atual: {percent} %."
    ),

    # Widget
    "widget.metric.session": "Sessão",
    "widget.metric.weekly": "Semanal",
    "widget.status.connecting": "conectando…",
    "widget.status.active": "ativo",
    "widget.status.reset_in": "reinício em {countdown}",
    "widget.status.waiting_first_message": "Aguardando a primeira mensagem",
    "widget.menu.refresh": "Atualizar",
    "widget.menu.quit": "Sair",
    "widget.peak_banner": "⚠ Horário de pico ({start} – {end}) – limite de tokens reduzido",
    "widget.error.session_expired": "Sessão expirada — abra o claude.ai no Firefox",
    "widget.error.cloudflare": "Bloqueado pela Cloudflare — visite o claude.ai no Firefox",
    "widget.error.login": "Primeiro faça login no claude.ai no Firefox",
    "widget.error.rate_limited": "Limite de requisições — aguardando a próxima consulta",
    "widget.error.network": "Erro de rede — verifique a conexão",
    "widget.error.generic": "Erro — passe o cursor aqui para detalhes",
    "widget.tooltip.log": "Log: {path}",

    # Update dialog
    "update.window_title": "Atualização",
    "update.available": "Atualização disponível",
    "update.version_available": "A versão {version} está disponível",
    "update.running_version": "Você está usando a versão {version}.",
    "update.cancel": "Cancelar",
    "update.skip": "Ignorar versão",
    "update.open_github": "Abrir GitHub",
    "update.up_to_date": "Você está usando a versão mais recente ({version}).",
    "update.check_failed": "Não foi possível procurar atualizações. Tente novamente mais tarde.",

    # Startup dialogs
    "dialog.already_running.title": "Claude Usage Tracker",
    "dialog.already_running.body": (
        "O Claude Usage Tracker já está em execução.\n"
        "Procure o círculo colorido na bandeja do sistema."
    ),
    "dialog.startup_error.title": "Claude Usage Tracker — Erro de inicialização",
    "dialog.startup_error.body": "Falha ao carregar a configuração:\n\n{error}",
    "dialog.fatal.title": "Claude Usage Tracker — Erro fatal",
    "dialog.fatal.body": (
        "O aplicativo travou e precisa fechar.\n\n"
        "{error}\n\n"
        "Detalhes completos no arquivo de log:\n{log_file}"
    ),
}
