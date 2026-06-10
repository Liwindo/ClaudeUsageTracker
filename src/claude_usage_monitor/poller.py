"""Background polling thread.

Runs fetch_all() on a configurable interval, calls registered callbacks
with the fresh UsageData or an error string. Thread-safe via threading.Event.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from .client import (
    ClaudeClientError,
    RateLimitedError,
    SessionExpiredError,
    fetch_all,
)
from .config import Config
from .firefox_cookies import (
    CookieError,
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
    """Periodic background worker that fetches claude.ai usage data."""

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
        # Doubles after each consecutive 429, resets to 1 on success.
        # A manual "Refresh now" still bypasses the wait via _force_event.
        self._backoff_factor = 1

    def start(self) -> None:
        logger.info("Poller starting (interval=%ds)", self._config.poll_interval_seconds)
        self._thread.start()

    def stop(self) -> None:
        logger.info("Poller stopping.")
        self._stop_event.set()
        self._force_event.set()
        # stop() can run on the Tk thread (quit button): keep the join short —
        # an in-flight HTTP request may take up to 15 s, and the daemon thread
        # dies with the process anyway.
        self._thread.join(timeout=1)

    def refresh_now(self) -> None:
        """Trigger an immediate poll outside the normal schedule."""
        self._force_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._poll()
            timeout = self._config.poll_interval_seconds * self._backoff_factor
            self._force_event.wait(timeout=timeout)
            self._force_event.clear()

    def _poll(self) -> None:
        logger.debug("Poll cycle starting.")
        try:
            cookies = get_claude_cookies(self._config.firefox_profile)
            org_id = extract_org_id(cookies)
            cookie_header = build_cookie_header(cookies)
            data = fetch_all(
                org_id=org_id,
                cookie_header=cookie_header,
                user_agent=self._config.user_agent or None,
            )
            logger.info(
                "Poll OK: highest=%d%% tier=%s",
                data.highest_percent,
                data.subscription_tier,
            )
            self._backoff_factor = 1
            self._on_data(data)
        except RateLimitedError as exc:
            self._backoff_factor = min(self._backoff_factor * 2, 16)
            msg = str(exc)
            logger.warning(
                "Rate limited: %s (next poll in %ds)",
                msg,
                self._config.poll_interval_seconds * self._backoff_factor,
            )
            self._on_error(msg)
        except SessionExpiredError as exc:
            msg = str(exc)
            logger.warning("Session expired: %s", msg)
            self._on_error(msg)
        except (FirefoxCookieError, CookieError) as exc:
            msg = str(exc)
            logger.warning("Browser cookie error: %s", msg)
            self._on_error(msg)
        except ClaudeClientError as exc:
            msg = str(exc)
            logger.warning("API error: %s", msg)
            self._on_error(msg)
        except Exception as exc:
            msg = f"Unexpected error: {exc}"
            logger.exception("Unhandled exception in poll cycle.")
            self._on_error(msg)
