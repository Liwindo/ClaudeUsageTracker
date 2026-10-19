"""Session forecast: does the 5-hour limit last until it resets? (R-widget-8)

Extrapolates the pace of the last ``WINDOW_S`` seconds of polls. Uses only
the data every poll already fetches — no extra request. The same rules live
in C# ``SessionForecast.cs``; both run the cases in
``tests/fixtures/forecast_cases.json``.

Utilization arrives in whole percent, so a pace is only trusted once the
samples span ``MIN_SPAN_S``. A moved ``resets_at`` means a new 5-hour window:
the samples of the old one must not feed the new pace.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import UsageData

WINDOW_S = 1800       # trailing window the pace is measured over
MIN_SPAN_S = 600      # shorter spans give no forecast (whole-percent steps)
NEW_WINDOW_S = 600    # resets_at moving further than this = new 5 h window

STATE_NONE = "none"          # nothing to show (measuring, at 100 %, window over)
STATE_LASTS = "lasts"        # the limit is not reached before the reset
STATE_RUNS_OUT = "runs_out"  # the limit is reached in `seconds` at this pace


@dataclass(frozen=True)
class Forecast:
    state: str
    seconds: float = 0.0


NONE = Forecast(STATE_NONE)


def estimate(samples: list[tuple[float, int]], resets_at: float) -> Forecast:
    """Forecast from ``(time, percent)`` samples of one window, oldest first.

    Times are seconds on any common clock (the callers use Unix time)."""
    if not samples:
        return NONE
    t, p = samples[-1]
    if p >= 100 or t >= resets_at:
        return NONE
    t0, p0 = samples[0]
    span = t - t0
    if span < MIN_SPAN_S:
        return NONE
    rise = p - p0
    if rise <= 0:
        return Forecast(STATE_LASTS)
    seconds = (100 - p) * span / rise
    if t + seconds >= resets_at:
        return Forecast(STATE_LASTS)
    return Forecast(STATE_RUNS_OUT, seconds)


class SessionForecaster:
    """Keeps the samples of the current 5-hour window. One caller thread."""

    def __init__(self) -> None:
        self._samples: list[tuple[float, int]] = []
        self._resets_at: float | None = None

    def observe(self, t: float, percent: int, resets_at: float) -> Forecast:
        new_window = (
            self._resets_at is None
            or abs(resets_at - self._resets_at) > NEW_WINDOW_S
            or (self._samples and t < self._samples[-1][0])  # clock went back
        )
        if new_window:
            self._samples.clear()
        self._resets_at = resets_at
        self._samples.append((t, percent))
        while self._samples[0][0] < t - WINDOW_S:
            self._samples.pop(0)
        return estimate(self._samples, resets_at)

    def observe_data(self, data: UsageData) -> Forecast:
        li = next((li for li in data.limits if li.key == "five_hour"), None)
        if li is None:
            return NONE
        return self.observe(
            data.fetched_at.timestamp(), li.percent, li.resets_at.timestamp()
        )
