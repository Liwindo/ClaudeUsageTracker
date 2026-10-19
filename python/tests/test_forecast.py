"""Session forecast (R-widget-8): shared cases + the UsageData entry point."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_usage_monitor.forecast import (
    STATE_LASTS,
    STATE_NONE,
    STATE_RUNS_OUT,
    SessionForecaster,
)
from claude_usage_monitor.models import LimitInfo, UsageData

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "forecast_cases.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_shared_case(case):
    fc = SessionForecaster()
    result = None
    for t, percent, resets_at in case["obs"]:
        result = fc.observe(t, percent, resets_at)
    assert result.state == case["expect"]["state"]
    if result.state == STATE_RUNS_OUT:
        assert result.seconds == pytest.approx(case["expect"]["seconds"], abs=1e-6)


def _data(at: datetime, percent: int, resets_at: datetime, key: str = "five_hour") -> UsageData:
    li = LimitInfo(key=key, label="x", percent=percent, resets_at=resets_at)
    return UsageData(limits=[li], fetched_at=at)


def test_observe_data_uses_the_session_bucket_and_fetch_time():
    start = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    reset = start + timedelta(hours=4)
    fc = SessionForecaster()
    fc.observe_data(_data(start, 10, reset))
    result = fc.observe_data(_data(start + timedelta(minutes=10), 20, reset))
    assert result.state == STATE_RUNS_OUT
    assert result.seconds == pytest.approx(4800)  # 80 % left at 1 %/min


def test_observe_data_without_session_bucket_is_none():
    now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    fc = SessionForecaster()
    data = _data(now, 50, now + timedelta(days=2), key="seven_day")
    assert fc.observe_data(data).state == STATE_NONE


def test_idle_session_lasts_after_measuring():
    start = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    reset = start + timedelta(hours=2)
    fc = SessionForecaster()
    states = [
        fc.observe_data(_data(start + timedelta(seconds=30 * i), 40, reset)).state
        for i in range(25)
    ]
    assert states[:20] == [STATE_NONE] * 20   # first 10 min: measuring
    assert states[20:] == [STATE_LASTS] * 5
