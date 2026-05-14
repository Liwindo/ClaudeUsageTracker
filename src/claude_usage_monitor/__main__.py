"""Entry point: python -m claude_usage_monitor"""

from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config, log_file_path


def _show_error_dialog(title: str, message: str) -> None:
    """Show a modal Windows error dialog. Works even if tkinter failed to start."""
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


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
    root.setLevel(getattr(logging, config.log_level, logging.WARNING))
    root.addHandler(handler)

    return log_file


def main() -> None:
    try:
        config = Config.load()
    except Exception as exc:
        _show_error_dialog(
            "Claude Usage Monitor — Startup Error",
            f"Failed to load configuration:\n\n{exc}",
        )
        sys.exit(1)

    log_file = _setup_logging(config)

    try:
        from .app import App
        App(config).run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.exception("Fatal error — application will exit.")
        _show_error_dialog(
            "Claude Usage Monitor — Fatal Error",
            f"The application crashed and must close.\n\n"
            f"{exc}\n\n"
            f"Full details in the log file:\n{log_file}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
