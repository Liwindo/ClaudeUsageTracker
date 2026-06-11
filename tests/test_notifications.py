"""Threshold / reset notification logic (no real toasts — _notify is mocked)."""

from datetime import datetime, timezone
from unittest import mock

import pytest

from claude_usage_monitor.models import LimitInfo, UsageData
from claude_usage_monitor.notifications import NotificationManager


def usage(percent, key="five_hour"):
    return UsageData(limits=[LimitInfo(
        key=key, label=key, percent=percent,
        resets_at=datetime.now(tz=timezone.utc),
    )])


@pytest.fixture
def toasts():
    with mock.patch(
        "claude_usage_monitor.notifications._notify"
    ) as m:
        yield m


def test_each_threshold_fires_once(toasts):
    nm = NotificationManager([80, 95])
    nm.process(usage(96))
    assert toasts.call_count == 2  # 80 and 95 crossed
    nm.process(usage(97))
    assert toasts.call_count == 2  # no repeat while above


def test_reset_toast_fires_once_per_bucket(toasts):
    nm = NotificationManager([80, 95])
    nm.process(usage(96))
    toasts.reset_mock()
    nm.process(usage(0))  # re-arms BOTH thresholds — but only one toast
    assert toasts.call_count == 1
    assert "reset" in toasts.call_args.kwargs["title"].lower()


def test_slow_decline_rearms_silently(toasts):
    nm = NotificationManager([80])
    nm.process(usage(85))
    toasts.reset_mock()
    for pct in (78, 74, 69):  # rolling window declining a few points per poll
        nm.process(usage(pct))
    assert toasts.call_count == 0
    nm.process(usage(82))  # re-crossing fires again after silent re-arm
    assert toasts.call_count == 1


def test_hysteresis_blocks_oscillation(toasts):
    nm = NotificationManager([95])
    nm.process(usage(95))
    toasts.reset_mock()
    for pct in (94, 95, 94, 95):  # oscillation around the threshold
        nm.process(usage(pct))
    assert toasts.call_count == 0


def test_looks_like_reset_boundaries():
    f = NotificationManager._looks_like_reset
    assert f(96, 0)        # sharp drop
    assert f(None, 3)      # near zero, no history
    assert f(40, 10)       # drop of >= 25 points
    assert not f(78, 69)   # slow decline
    assert not f(None, 69)  # no history, not near zero
