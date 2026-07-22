"""Application orchestrator.

Threading model:
  - Main thread:   tkinter mainloop (required by tkinter on Windows)
  - Tray thread:   pystray (managed internally via run_detached)
  - Poller thread: daemon thread, fetches data every N seconds
"""

from __future__ import annotations

import logging
import threading
import time

from .config import Config
from .models import UsageData
from .notifications import NotificationManager
from .poller import Poller
from .tray import TrayIcon
from . import __version__
from .i18n import tr
from .update_check import (
    STATUS_AVAILABLE,
    STATUS_UP_TO_DATE,
    check_detailed,
    check_for_update,
)
from .widget import Widget

logger = logging.getLogger(__name__)


class App:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._notifier = NotificationManager(config.notification_thresholds)

        self._widget = Widget(
            on_refresh=self._on_refresh_requested,
            on_quit=self._quit,
        )

        self._tray = TrayIcon(
            on_click_open=self._widget.toggle,
            on_click_refresh=self._on_refresh_requested,
            on_check_updates=self._on_check_updates_requested,
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
        if self._config.update_check:
            threading.Thread(
                target=self._check_updates, daemon=True, name="update-check"
            ).start()
        self._widget.start()     # blocks main thread — tkinter requires the main thread on Windows

    def _on_data(self, data: UsageData) -> None:
        self._tray.update(data)
        self._notifier.process(data)
        self._widget.update(data)

    def _on_error(self, message: str) -> None:
        self._tray.set_error(message)
        self._widget.set_error(message)

    def _on_refresh_requested(self) -> None:
        self._poller.refresh_now()

    def _check_updates(self) -> None:
        """One-shot background check; shows the update dialog if needed.

        Delayed a few seconds so the GitHub request never competes with the
        UI startup and the dialog appears after the widget is on screen.
        Runs on a daemon thread — Widget.notify_update handles the cross-
        thread hand-off and tolerates a quit happening in the meantime.
        """
        time.sleep(3)
        info = check_for_update(skip_version=self._config.skip_update_version)
        if info:
            self._widget.notify_update(
                info.latest_version,
                info.url,
                on_skip=lambda v=info.latest_version: self._skip_update(v),
            )

    def _on_check_updates_requested(self) -> None:
        """Manual 'Check for updates' from the tray menu. Runs the check on a
        daemon thread and reports all three outcomes distinctly — a newer
        release opens the update dialog, otherwise a short message says
        up-to-date or that the check failed (so a network error never
        masquerades as 'up to date'). Ignores the skip preference: a manual
        check always surfaces a newer release."""
        threading.Thread(
            target=self._check_updates_now, daemon=True, name="update-check-manual"
        ).start()

    def _check_updates_now(self) -> None:
        result = check_detailed(skip_version="")
        if result.status == STATUS_AVAILABLE and result.info is not None:
            info = result.info
            self._widget.notify_update(
                info.latest_version,
                info.url,
                on_skip=lambda v=info.latest_version: self._skip_update(v),
            )
        elif result.status == STATUS_UP_TO_DATE:
            self._widget.notify_message(
                tr("update.window_title"),
                tr("update.up_to_date", version=__version__),
                kind="info",
            )
        else:
            self._widget.notify_message(
                tr("update.window_title"),
                tr("update.check_failed"),
                kind="warning",
            )

    def _skip_update(self, version: str) -> None:
        """Persist the user's choice to skip *version* (update dialog button)."""
        logger.info("User skipped update %s.", version)
        self._config.skip_update_version = version
        try:
            self._config.save()
        except OSError as exc:
            logger.warning("Could not persist skipped version: %s", exc)

    def _quit(self) -> None:
        logger.info("Quitting.")
        self._poller.stop()
        self._widget.stop()
        self._tray.stop()
