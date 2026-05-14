"""Application orchestrator.

Threading model:
  - Main thread:   tkinter mainloop (required by tkinter on Windows)
  - Tray thread:   pystray (managed internally via run_detached)
  - Poller thread: daemon thread, fetches data every N seconds
"""

from __future__ import annotations

import logging
from typing import Optional

from .config import Config
from .models import UsageData
from .notifications import NotificationManager
from .poller import Poller
from .tray import TrayIcon
from .widget import Widget

logger = logging.getLogger(__name__)


class App:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._latest_data: Optional[UsageData] = None
        self._latest_error: Optional[str] = None

        self._notifier = NotificationManager(config.notification_thresholds)

        self._widget = Widget(
            on_refresh=self._on_refresh_requested,
            on_quit=self._quit,
        )

        self._tray = TrayIcon(
            on_click_open=self._widget.toggle,
            on_click_refresh=self._on_refresh_requested,
            on_quit=self._quit,
        )

        self._poller = Poller(
            config=config,
            on_data=self._on_data,
            on_error=self._on_error,
        )

    def run(self) -> None:
        """Start everything. Blocks until the user quits."""
        self._poller.start()
        self._tray.run()         # non-blocking — pystray manages its own thread
        self._widget.start()     # blocks main thread — tkinter requires the main thread on Windows

    def _on_data(self, data: UsageData) -> None:
        self._latest_data = data
        self._latest_error = None
        self._tray.update(data)
        self._notifier.process(data)
        self._widget.update(data)

    def _on_error(self, message: str) -> None:
        self._latest_error = message
        self._tray.set_error(message)
        self._widget.set_error(message)

    def _on_refresh_requested(self) -> None:
        self._poller.refresh_now()

    def _quit(self) -> None:
        logger.info("Quitting.")
        self._poller.stop()
        self._widget.stop()
        self._tray.stop()
