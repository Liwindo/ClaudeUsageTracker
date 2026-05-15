"""Desktop notification logic.

Fires a system notification when a threshold is crossed (upward) or
when a limit resets (drops significantly below a previously fired threshold).
Uses plyer for cross-platform notifications.
"""

from __future__ import annotations

import logging

from .models import UsageData

logger = logging.getLogger(__name__)


def _notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Claude Usage Tracker",
            timeout=8,
        )
    except Exception as exc:
        # Notifications failing must never crash the app.
        logger.warning("Desktop notification failed: %s", exc)


class NotificationManager:
    """Tracks which thresholds have already fired to avoid spam.

    Args:
        thresholds: Sorted list of integer percent thresholds, e.g. [80, 95].
    """

    # Hysteresis band (percent) below the threshold required to re-arm a fired
    # notification. Without this, a value oscillating around the threshold
    # (e.g. 94 ⇄ 95 with threshold=95) would spam notifications every poll.
    _HYSTERESIS = 10

    def __init__(self, thresholds: list[int]) -> None:
        self._thresholds = sorted(thresholds)
        # Set of (bucket_key, threshold) pairs that have already fired.
        self._fired: set[tuple[str, int]] = set()

    def process(self, data: UsageData) -> None:
        """Check data against thresholds and fire notifications as needed."""
        for li in data.limits:
            for threshold in self._thresholds:
                key = (li.key, threshold)
                if li.percent >= threshold:
                    if key not in self._fired:
                        self._fired.add(key)
                        self._fire_threshold(li.label, li.percent, threshold)
                elif key in self._fired and li.percent < threshold - self._HYSTERESIS:
                    # Meaningful drop below the hysteresis band: re-arm and
                    # announce the reset. Stays armed until value re-crosses.
                    self._fired.discard(key)
                    self._fire_reset(li.label, li.percent)

    def _fire_threshold(self, label: str, percent: int, threshold: int) -> None:
        logger.info("Notification: %s reached %d%% (threshold %d%%)", label, percent, threshold)
        _notify(
            title=f"Claude Usage — {label} at {percent}%",
            message=(
                f"You've reached {threshold}% of your {label} limit.\n"
                "Consider wrapping up or waiting for the reset."
            ),
        )

    def _fire_reset(self, label: str, percent: int) -> None:
        logger.info("Notification: %s reset (now %d%%)", label, percent)
        _notify(
            title=f"Claude Usage — {label} reset",
            message=f"{label} limit has reset. Current usage: {percent}%.",
        )
