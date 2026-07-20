"""Parsing of the reverse-engineered /usage response."""

from datetime import datetime, timedelta, timezone

from claude_usage_monitor.models import LimitInfo, UsageData


def li(key="five_hour", percent=50):
    return LimitInfo(
        key=key, label=key, percent=percent,
        resets_at=datetime.now(tz=timezone.utc),
    )


def test_utilization_plain_float():
    info = LimitInfo.from_api("five_hour", {"utilization": 13.0, "resets_at": None})
    assert info.percent == 13


def test_utilization_legacy_dict_parsed_value():
    info = LimitInfo.from_api(
        "five_hour", {"utilization": {"parsedValue": 42}, "resets_at": None}
    )
    assert info.percent == 42


def test_utilization_legacy_dict_source():
    info = LimitInfo.from_api(
        "five_hour", {"utilization": {"source": "7.5"}, "resets_at": None}
    )
    assert info.percent == 7


def test_utilization_garbage_defaults_to_zero():
    info = LimitInfo.from_api("five_hour", {"utilization": "n/a", "resets_at": None})
    assert info.percent == 0


def test_naive_resets_at_is_treated_as_utc():
    info = LimitInfo.from_api(
        "five_hour", {"utilization": 50, "resets_at": "2030-01-01T00:00:00"}
    )
    assert info.resets_at.tzinfo is not None
    assert info.resets_in_seconds > 0  # must not raise aware-minus-naive


def test_unknown_bucket_gets_generic_label():
    info = LimitInfo.from_api("brand_new_bucket", {"utilization": 1, "resets_at": None})
    assert "brand_new_bucket" in info.label


def test_from_api_response_skips_extra_usage_and_nulls():
    data = UsageData.from_api_response({
        "five_hour": {"utilization": 12, "resets_at": "2030-01-01T00:00:00+00:00"},
        "seven_day": None,
        "extra_usage": {"foo": 1},
        "new_bucket": {"utilization": 3, "resets_at": None},
    })
    keys = [x.key for x in data.limits]
    assert "five_hour" in keys
    assert "new_bucket" in keys
    assert "extra_usage" not in keys
    assert "seven_day" not in keys


def test_highest_and_session_percent():
    data = UsageData(limits=[li("five_hour", 30), li("seven_day", 80)])
    assert data.highest_percent == 80
    assert data.session_percent == 30
    assert UsageData().highest_percent == 0
    assert UsageData().session_percent is None


def test_reset_countdown_format():
    info = li()
    assert info.reset_countdown  # never empty, never raises


def test_reset_countdown_expired_is_plain_zero():
    # Callers decide what an expired window means (the widget shows its own
    # "waiting for first message" state); the countdown itself must stay a
    # duration and never a sentence fragment like "resetting…".
    info = LimitInfo(
        key="five_hour", label="x", percent=0,
        resets_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    assert info.reset_countdown == "0m"
