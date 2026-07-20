"""Pure tray helpers (no pystray icon is created)."""

from claude_usage_monitor.tray import _MAX_TIP, _clip_tip, _session_color


def test_clip_tip_short_passthrough():
    assert _clip_tip("short") == "short"


def test_clip_tip_long_is_clamped():
    clipped = _clip_tip("x" * 500)
    assert len(clipped) == _MAX_TIP
    assert clipped.endswith("…")


def test_clip_tip_exact_limit_untouched():
    text = "x" * _MAX_TIP
    assert _clip_tip(text) == text


def test_session_color_boundaries():
    assert _session_color(None) == "grey"
    assert _session_color(0) == "green"
    assert _session_color(39) == "green"
    assert _session_color(40) == "yellow"
    assert _session_color(59) == "yellow"
    assert _session_color(60) == "orange"
    assert _session_color(84) == "orange"
    assert _session_color(85) == "red"
    assert _session_color(100) == "red"
