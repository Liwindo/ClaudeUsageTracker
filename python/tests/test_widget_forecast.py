"""Session forecast in the widget (R-widget-8): after the session label, in
full or not at all.

Real (withdrawn-then-mapped) Tk root like test_widget_banner_wrap.py, because
whether the text fits is genuine font measurement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

tk = pytest.importorskip("tkinter")

import claude_usage_monitor.widget as W
from claude_usage_monitor import i18n
from claude_usage_monitor.forecast import (
    NONE,
    STATE_LASTS,
    STATE_RUNS_OUT,
    Forecast,
)
from claude_usage_monitor.models import LimitInfo, UsageData
from claude_usage_monitor.widget import Widget

# The longest countdown a runs-out forecast can show inside a 5 h window.
_LONGEST = Forecast(STATE_RUNS_OUT, 4 * 3600 + 59 * 60)
_LASTS = Forecast(STATE_LASTS)


@pytest.fixture()
def build(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_peak_hour_window_local", lambda: None)
    monkeypatch.setattr(W, "_POS_FILE", tmp_path / "widget_pos.json")
    previous = i18n.active_language()
    roots = []

    def _build(language: str = "en", width: int = W._W):
        i18n.init(language)
        W._bar_cache.clear()
        W._dot_cache.clear()
        W._div_cache.clear()
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            pytest.skip(f"Tk unavailable: {exc}")
        roots.append(root)
        root.overrideredirect(True)
        w = Widget(on_refresh=lambda: None, on_quit=lambda: None)
        w._root = root
        w._build_ui(root)
        root.update_idletasks()
        w._base_x = w._base_y = 0
        w._base_h = w._min_h = root.winfo_reqheight()
        _resize(w, root, width)
        return w, root

    yield _build
    i18n.init(previous)
    for root in roots:
        try:
            root.destroy()
        except tk.TclError:
            pass


def _resize(w, root, width: int) -> None:
    w._base_w = width
    root.geometry(f"{width}x{w._base_h}+0+0")
    root.deiconify()
    root.update()


def _data(percent: int = 99) -> UsageData:
    now = datetime.now(tz=timezone.utc)
    return UsageData(limits=[
        LimitInfo("five_hour", "s", percent, now + timedelta(hours=4, minutes=59)),
        LimitInfo("seven_day", "w", 100, now + timedelta(days=3)),
    ])


def _shown(w) -> str:
    return w._lbl_fc.cget("text")


@pytest.mark.parametrize("language", sorted(i18n.CATALOGS))
@pytest.mark.parametrize("forecast", [_LONGEST, _LASTS], ids=["runs_out", "lasts"])
def test_longest_forecast_fits_the_default_width(build, language, forecast):
    w, root = build(language)
    w._apply_data(_data(99), forecast)
    root.update()
    assert _shown(w), f"{language}: {W.forecast_text(forecast)[0]!r} does not fit"
    # And the label row really has room for it: nothing overlaps the percent.
    assert w._lbl_fc.winfo_x() + w._lbl_fc.winfo_width() <= w._lbl_s.winfo_x()


def test_runs_out_text_and_colour(build):
    w, root = build("en")
    w._apply_data(_data(50), Forecast(STATE_RUNS_OUT, 4800))
    assert _shown(w) == " · limit in 1h 20m"
    assert w._lbl_fc.cget("fg") == W._WARN


def test_lasts_text_and_colour(build):
    w, root = build("de")
    w._apply_data(_data(50), _LASTS)
    assert _shown(w) == " · reicht bis Reset"
    assert w._lbl_fc.cget("fg") == W._DIM


def test_no_forecast_shows_nothing(build):
    w, root = build("en")
    w._apply_data(_data(50), NONE)
    assert _shown(w) == ""


def test_too_narrow_hides_instead_of_clipping_and_comes_back(build):
    w, root = build("en")
    w._apply_data(_data(50), _LONGEST)
    assert _shown(w)
    _resize(w, root, 150)
    assert _shown(w) == ""
    _resize(w, root, W._W)
    assert _shown(w)


def test_error_clears_the_forecast(build):
    w, root = build("en")
    w._apply_data(_data(50), _LASTS)
    w._apply_error("Network error fetching usage: timeout")
    assert _shown(w) == ""


def test_update_before_start_buffers_the_forecast():
    w = Widget(on_refresh=lambda: None, on_quit=lambda: None)
    w.update(_data(50), _LASTS)   # no Tk root yet: buffered for start()
    assert w._last_forecast == _LASTS
