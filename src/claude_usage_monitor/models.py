"""Data models for claude.ai usage API responses.

All field names mirror the actual /api/organizations/{orgId}/usage response
(reverse-engineered — may break if Anthropic changes the schema).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# Anthropic uses internal codenames for some model-specific weekly buckets.
# Mapping is inferred from context; "omelette" appears to be Opus-class.
# REVERSE-ENGINEERED: update if Anthropic renames these.
_CODENAME_LABELS: dict[str, str] = {
    "five_hour": "Session (5h)",
    "seven_day": "Weekly",
    "seven_day_opus": "Opus Weekly",
    "seven_day_sonnet": "Sonnet Weekly",
    "seven_day_omelette": "Opus Weekly",       # internal codename
    "seven_day_cowork": "Teams Weekly",         # internal codename
    "seven_day_oauth_apps": "OAuth Apps Weekly",
    "iguana_necktie": "Unknown (iguana_necktie)",
    "tangelo": "Unknown (tangelo)",
    "omelette_promotional": "Opus Promo",
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
            return "resetting…"
        h, remainder = divmod(secs, 3600)
        m = remainder // 60
        if h:
            return f"{h}h {m}m"
        return f"{m}m"

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
        label = _CODENAME_LABELS.get(key, f"Unknown ({key})")
        percent = cls._parse_utilization(data.get("utilization", 0))
        try:
            resets_at = datetime.fromisoformat(data["resets_at"])
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

        Only non-null buckets that appear in _CODENAME_LABELS are included.
        Unknown non-null keys are included with a generic label so nothing
        silently disappears if Anthropic adds new buckets.
        REVERSE-ENGINEERED: schema inferred from real response.
        """
        limits: list[LimitInfo] = []
        known_keys = set(_CODENAME_LABELS.keys()) | {"extra_usage"}

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

    def status_color(self) -> str:
        """Return a color name matching the threshold rules."""
        p = self.highest_percent
        if p >= 95:
            return "red"
        if p >= 80:
            return "orange"
        if p >= 50:
            return "yellow"
        return "green"

    def tooltip_text(self) -> str:
        """Short one-line tooltip for the tray icon."""
        parts = [f"{li.label} {li.percent}%" for li in self.limits]
        return " · ".join(parts) if parts else "No data"
