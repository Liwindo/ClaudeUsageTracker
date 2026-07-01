"""Data models for claude.ai usage API responses.

All field names mirror the actual /api/organizations/{orgId}/usage response
(reverse-engineered — may break if Anthropic changes the schema).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .i18n import tr


# Anthropic uses internal codenames for some model-specific weekly buckets.
# Mapping is inferred from context; "omelette" appears to be Opus-class.
# Values are translation keys (see locales/en.py); unmapped buckets get
# "bucket.unknown". The dict order doubles as the display sort order.
# REVERSE-ENGINEERED: update if Anthropic renames these.
_CODENAME_LABELS: dict[str, str] = {
    "five_hour": "bucket.session",
    "seven_day": "bucket.weekly",
    "seven_day_opus": "bucket.opus_weekly",
    "seven_day_sonnet": "bucket.sonnet_weekly",
    "seven_day_omelette": "bucket.opus_weekly",     # internal codename
    "seven_day_cowork": "bucket.teams_weekly",      # internal codename
    "seven_day_oauth_apps": "bucket.oauth_weekly",
    "iguana_necktie": "bucket.unknown",
    "tangelo": "bucket.unknown",
    "omelette_promotional": "bucket.opus_promo",
}


@dataclass
class LimitInfo:
    """One usage bucket (e.g. five_hour, seven_day_omelette)."""

    key: str
    label: str
    percent: int          # 0–100, already parsed by the API
    resets_at: datetime

    @property
    def resets_in_seconds(self) -> float:
        now = datetime.now(tz=timezone.utc)
        delta = self.resets_at - now
        return max(0.0, delta.total_seconds())

    @property
    def reset_countdown(self) -> str:
        """Human-readable countdown string, e.g. '3h 42m'."""
        secs = int(self.resets_in_seconds)
        if secs <= 0:
            return tr("countdown.resetting")
        h, remainder = divmod(secs, 3600)
        m = remainder // 60
        if h:
            return tr("countdown.hours_minutes", hours=h, minutes=m)
        return tr("countdown.minutes", minutes=m)

    @classmethod
    def _parse_utilization(cls, raw: Any) -> int:
        """Extract integer percent from the utilization field.

        As of 2026-05 the API returns a plain float already in 0–100 range
        (e.g. 13.0 = 13 %).  Earlier responses used a dict with parsedValue/source;
        that branch is kept for backwards compatibility.
        REVERSE-ENGINEERED: schema inferred from real response.
        """
        if isinstance(raw, dict):
            parsed = raw.get("parsedValue")
            if parsed is not None:
                return int(parsed)
            source = raw.get("source")
            if source is not None:
                return int(float(source))
        if isinstance(raw, (int, float)):
            return int(float(raw))
        return 0

    @classmethod
    def from_api(cls, key: str, data: dict[str, Any]) -> LimitInfo:
        # `key` is only interpolated by the "bucket.unknown" template;
        # str.format ignores it for the fixed labels.
        label = tr(_CODENAME_LABELS.get(key, "bucket.unknown"), key=key)
        percent = cls._parse_utilization(data.get("utilization", 0))
        try:
            resets_at = datetime.fromisoformat(data["resets_at"])
            if resets_at.tzinfo is None:
                # A naive datetime would make resets_in_seconds raise TypeError
                # (aware minus naive) on every countdown render.
                resets_at = resets_at.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            resets_at = datetime.now(tz=timezone.utc)
        return cls(key=key, label=label, percent=percent, resets_at=resets_at)


@dataclass
class UsageData:
    """Parsed snapshot of all claude.ai usage limits."""

    limits: list[LimitInfo] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    subscription_tier: str = "unknown"

    @classmethod
    def from_api_response(
        cls,
        payload: dict[str, Any],
        subscription_tier: str = "unknown",
    ) -> UsageData:
        """Parse the raw /usage JSON into a UsageData instance.

        Every non-null dict bucket is included — unknown keys get a generic
        "Unknown (…)" label so nothing silently disappears if Anthropic adds
        new buckets. Only the non-bucket key `extra_usage` is skipped.
        REVERSE-ENGINEERED: schema inferred from real response.
        """
        limits: list[LimitInfo] = []

        for key, value in payload.items():
            if key == "extra_usage":
                continue
            if value is None:
                continue
            if not isinstance(value, dict):
                continue
            limits.append(LimitInfo.from_api(key, value))

        # Stable display order: session first, then weekly buckets
        _order = list(_CODENAME_LABELS.keys())
        limits.sort(key=lambda li: _order.index(li.key) if li.key in _order else 999)

        return cls(limits=limits, subscription_tier=subscription_tier)

    @property
    def highest_percent(self) -> int:
        """The worst-case utilization across all active buckets."""
        if not self.limits:
            return 0
        return max(li.percent for li in self.limits)

    @property
    def session_percent(self) -> int | None:
        """Percent for the five-hour session bucket, or None if absent."""
        for li in self.limits:
            if li.key == "five_hour":
                return li.percent
        return None

    def tooltip_text(self) -> str:
        """Short one-line tooltip for the tray icon."""
        parts = [f"{li.label} {li.percent}%" for li in self.limits]
        return " · ".join(parts) if parts else tr("tooltip.no_data")
