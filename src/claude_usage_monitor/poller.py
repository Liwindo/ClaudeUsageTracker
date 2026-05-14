"""Background polling thread.

Runs fetch_all() on a configurable interval, calls registered callbacks
with the fresh UsageData or an error string. Thread-safe via threading.Event.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from .client import ClaudeClientError, SessionExpiredError, fetch_all
from .config import Config
from .firefox_cookies import (
    FirefoxCookieError,
    build_cookie_header,
    extract_org_id,
    get_claude_cookies,
)
from .models import UsageData

logger = logging.getLogger(__name__)

OnDataCallback = Callable[[UsageData], None]
OnErrorCallback = Callable[[str], None]


class Poller:
    """Periodic background worker that fetches claude.ai usage data.

    Usage:
        poller = Poller(config, on_data=my_fn, on_error=err_fn)
        poller.start()
        # … later …
        poller.stop()
    """

    def __init__(
        self,
        config: Config,
        on_data: OnDataCallback,
        on_error: OnErrorCallback,
    ) -> None:
        self._config = config
        self._on_data = on_data
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="poller")
        self._force_event = threading.Event()

    def start(self) -> None:
        logger.info("Poller starting (interval=%ds)", self._config.poll_interval_seconds)
        self._thread.start()

    def stop(self) -> None:
        logger.info("Poller stopping.")
        self._stop_event.set()
        self._force_event.set()   # unblock any waiting sleep
        self._thread.join(timeout=5)

    def refresh_now(self) -> None:
        """Trigger an immediate poll outside the normal schedule."""
        self._force_event.set()

    def _loop(self) -> None:
        # Poll immediately on start, then wait for the interval.
        while not self._stop_event.is_set():
            self._poll()
            # Wait for either the interval to elapse or a forced refresh.
            self._force_event.wait(timeout=self._config.poll_interval_seconds)
            self._force_event.clear()

    def _poll(self) -> None:
        logger.debug("Poll cycle starting.")
        try:
            cookies = get_claude_cookies(self._config.firefox_profile)
            org_id = extract_org_id(cookies)
            cookie_header = build_cookie_header(cookies)
            data = fetch_all(org_id=org_id, cookie_header=cookie_header)
            logger.info(
                "Poll OK: highest=%d%% tier=%s",
                data.highest_percent,
                data.subscription_tier,
            )
            self._on_data(data)
        except SessionExpiredError as exc:
            msg = str(exc)
            logger.warning("Session expired: %s", msg)
            self._on_error(msg)
        except FirefoxCookieError as exc:
            msg = str(exc)
            logger.warning("Firefox cookie error: %s", msg)
            self._on_error(msg)
        except ClaudeClientError as exc:
            msg = str(exc)
            logger.warning("API error: %s", msg)
            self._on_error(msg)
        except Exception as exc:
            msg = f"Unexpected error: {exc}"
            logger.exception("Unhandled exception in poll cycle.")
            self._on_error(msg)
