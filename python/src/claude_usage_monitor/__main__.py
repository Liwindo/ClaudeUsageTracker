"""Entry point: python -m claude_usage_monitor"""

from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import i18n
from .config import Config, log_file_path
from .i18n import tr


def _show_error_dialog(title: str, message: str) -> None:
    """Show a modal Windows error dialog. Works even if tkinter failed to start."""
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def _show_info_dialog(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)  # MB_ICONINFORMATION
    except Exception:
        pass


# Keep a module-level reference so the mutex handle lives for the whole
# process lifetime — Windows releases it automatically on exit.
_instance_mutex = None


def _another_instance_running() -> bool:
    """Create the app's named mutex; True if another instance already owns it.

    Never raises — if the mutex cannot be created for any reason, startup
    proceeds (running twice is annoying, refusing to start is worse).
    """
    global _instance_mutex
    _ERROR_ALREADY_EXISTS = 183
    try:
        _instance_mutex = ctypes.windll.kernel32.CreateMutexW(
            None, False, "claude-usage-monitor-single-instance"
        )
        return ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    except Exception:
        return False


def _setup_logging(config: Config) -> Path:
    log_file = log_file_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_file, maxBytes=500_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    # getattr(logging, "warning") would return the *function* logging.warning,
    # which setLevel() rejects with TypeError — normalise and type-check.
    level = getattr(logging, config.log_level.upper(), None)
    if not isinstance(level, int):
        level = logging.WARNING
    root.setLevel(level)
    root.addHandler(handler)

    return log_file


def main() -> None:
    # Detected language for the dialogs shown before the config is available;
    # re-initialised below once the configured language is known.
    i18n.init("auto")

    if _another_instance_running():
        _show_info_dialog(
            tr("dialog.already_running.title"),
            tr("dialog.already_running.body"),
        )
        sys.exit(0)

    try:
        config = Config.load()
    except Exception as exc:
        _show_error_dialog(
            tr("dialog.startup_error.title"),
            tr("dialog.startup_error.body", error=exc),
        )
        sys.exit(1)

    i18n.init(config.language)
    log_file = _setup_logging(config)

    from .autostart import sync_autostart
    sync_autostart(config.autostart)

    try:
        from .app import App
        App(config).run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.exception("Fatal error — application will exit.")
        _show_error_dialog(
            tr("dialog.fatal.title"),
            tr("dialog.fatal.body", error=exc, log_file=log_file),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
