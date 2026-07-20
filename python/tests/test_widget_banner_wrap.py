"""Responsive peak-hour banner: the warning text must stay fully visible at any
widget width, with the window height growing to fit the wrapped lines.

These use a real (withdrawn) Tk root because the wrapping is genuine font/layout
behaviour — `winfo_reqheight()` reflects the wrapped line count without the
window ever being mapped, so the test needs no display and is safe in CI. It
skips cleanly where Tk cannot initialise at all.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")

import claude_usage_monitor.widget as W
from claude_usage_monitor.widget import Widget


@pytest.fixture()
def widget(tmp_path, monkeypatch):
    """A built Widget on a withdrawn Tk root, forced into the peak window."""
    monkeypatch.setattr(W, "_peak_hour_window_local", lambda: ("05:00", "11:00"))
    monkeypatch.setattr(W, "_POS_FILE", tmp_path / "widget_pos.json")
    # The image caches are module-global and hold PhotoImages bound to whatever
    # Tk interpreter first built them. Each test spins up a fresh root, so clear
    # them or the next build hits 'image "pyimageN" doesn't exist'. (The real app
    # only ever has one root, so this never bites in production.)
    W._bar_cache.clear()
    W._dot_cache.clear()
    W._div_cache.clear()
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no usable Tcl/Tk in this environment
        pytest.skip(f"Tk unavailable: {exc}")
    root.overrideredirect(True)

    w = Widget(on_refresh=lambda: None, on_quit=lambda: None)
    w._root = root
    w._build_ui(root)
    root.update_idletasks()
    # Seed the authoritative banner-free frame, as start()/restore would.
    w._min_h = root.winfo_reqheight()
    w._base_x = w._base_y = 0
    w._base_h = w._min_h
    root.deiconify()
    root.update()
    try:
        yield w, root
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def _show_at_width(w, root, width: int) -> None:
    """Pretend the user resized the widget to `width` and (re)fit the banner.

    The window is mapped at the given width so `_banner_wraplength()` reads it
    back from winfo_width(), exactly as it does after a real user resize.
    """
    w._base_w = width
    root.geometry(f"{width}x{w._base_h}+0+0")
    root.update()
    if not w._peak_visible:
        w._refresh_peak_banner()
    else:
        w._refit_height()
    root.update()


def test_narrow_widget_wraps_banner_and_grows_height(widget):
    w, root = widget

    _show_at_width(w, root, 440)
    wide_banner_h = w._peak_banner.winfo_reqheight()
    wide_req = root.winfo_reqheight()
    wide_disp_h = w._displayed_target()[3]
    # The whole banner is visible: the window is at least the natural height.
    assert wide_disp_h >= wide_req

    _show_at_width(w, root, 200)  # the widget's minimum width
    narrow_banner_h = w._peak_banner.winfo_reqheight()
    narrow_req = root.winfo_reqheight()
    narrow_disp_h = w._displayed_target()[3]

    # The bug: without wraplength the label never wrapped, so its height (and
    # the window height) stayed constant while text was clipped off the side.
    assert narrow_banner_h > wide_banner_h, "banner did not wrap when narrowed"
    assert narrow_disp_h > wide_disp_h, "window height did not grow to fit wrap"
    assert narrow_disp_h >= narrow_req, "wrapped banner would be clipped"


@pytest.mark.parametrize("width", [440, 320, 256, 220, 200])
def test_full_banner_always_fits_the_window(widget, width):
    w, root = widget
    _show_at_width(w, root, width)
    req_h = root.winfo_reqheight()
    # extra is exactly the inflation over the banner-free frame, and the
    # displayed height covers the natural requirement -> nothing is clipped.
    assert w._extra_h == max(0, req_h - w._base_h)
    assert w._displayed_target()[3] >= req_h


def test_wraplength_tracks_width(widget):
    w, root = widget
    _show_at_width(w, root, 256)
    wrap_256 = w._peak_banner.cget("wraplength")
    _show_at_width(w, root, 200)
    wrap_200 = w._peak_banner.cget("wraplength")
    # Narrower widget -> smaller wrap width -> banner reflows.
    assert wrap_200 < wrap_256
    assert wrap_200 == max(40, 200 - 2 * W._CARD_PADX - 2)


def test_banner_renders_minutes_from_window(widget, monkeypatch):
    w, root = widget
    # Half-hour zones (e.g. UTC+5:30) put the peak window off the full hour —
    # the banner must render the minutes it is given, not a hard-coded ":00".
    monkeypatch.setattr(W, "_peak_hour_window_local", lambda: ("17:30", "23:30"))
    w._refresh_peak_banner()
    assert "17:30 – 23:30" in w._peak_banner.cget("text")


def test_peak_window_local_returns_wall_clock_strings(monkeypatch):
    from datetime import datetime as real_dt, timedelta

    # Any weekday morning inside the 05–11 PT window.
    d = real_dt(2026, 7, 1, 7, 23, tzinfo=W._PEAK_TZ)
    while d.weekday() >= 5:
        d += timedelta(days=1)

    class FixedDatetime(real_dt):
        @classmethod
        def now(cls, tz=None):
            return d

    monkeypatch.setattr(W, "datetime", FixedDatetime)
    window = W._peak_hour_window_local()
    assert window is not None
    start, end = window
    base = d.replace(minute=0, second=0, microsecond=0)
    assert start == f"{base.replace(hour=5).astimezone():%H:%M}"
    assert end == f"{base.replace(hour=11).astimezone():%H:%M}"


def test_banner_renders_in_configured_language(widget):
    from claude_usage_monitor import i18n

    w, root = widget
    try:
        i18n.init("de")
        w._refresh_peak_banner()
        root.update()
        text = w._peak_banner.cget("text")
        assert "Stoßzeit" in text and "05:00 – 11:00" in text
    finally:
        i18n.init("en")


def test_long_footer_error_wraps_and_window_grows(widget):
    from claude_usage_monitor import i18n

    w, root = widget
    _show_at_width(w, root, 200)
    single_line_h = w._lbl_ft.winfo_reqheight()
    try:
        i18n.init("de")
        # The longest localised error short ("Von Cloudflare blockiert — …").
        w._apply_error("organizations/usage returned 403: Cloudflare blocked")
        root.update()
        lbl = w._lbl_ft
        # The label must wrap instead of running off the right edge …
        assert lbl.cget("wraplength") > 0
        assert lbl.winfo_reqwidth() <= 200 - 2 * W._CARD_PADX, (
            "footer text is wider than the widget — clipped"
        )
        assert lbl.winfo_reqheight() > single_line_h, "footer did not wrap"
        # … and the window must grow so the wrapped lines are fully visible.
        assert w._displayed_target()[3] >= root.winfo_reqheight()
    finally:
        i18n.init("en")


def test_footer_shrinks_back_after_short_status(widget):
    w, root = widget
    _show_at_width(w, root, 200)
    w._apply_error("organizations/usage returned 403: Cloudflare blocked")
    root.update()
    grown = w._displayed_target()[3]
    # A short status afterwards must give the extra footer height back.
    w._var_ft.set("active")
    w._refit_height()
    root.update()
    assert w._displayed_target()[3] < grown
    assert w._displayed_target()[3] >= root.winfo_reqheight()


def test_expired_session_shows_waiting_for_first_message(widget):
    from datetime import datetime, timedelta, timezone

    from claude_usage_monitor.models import LimitInfo, UsageData

    w, root = widget
    li = LimitInfo(
        key="five_hour", label="Session (5h)", percent=0,
        resets_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
    )
    w._apply_data(UsageData(limits=[li]))
    root.update()
    # The old composition produced "reset resetting…"; the expired session is
    # its own state: nothing resets until the user sends the first message.
    assert w._var_ft.get() == "Waiting for first message"


def test_running_session_still_shows_countdown(widget):
    from datetime import datetime, timedelta, timezone

    from claude_usage_monitor.models import LimitInfo, UsageData

    w, root = widget
    li = LimitInfo(
        key="five_hour", label="Session (5h)", percent=40,
        resets_at=datetime.now(tz=timezone.utc)
        + timedelta(hours=2, minutes=5, seconds=30),
    )
    w._apply_data(UsageData(limits=[li]))
    root.update()
    assert w._var_ft.get() == "reset 2h 5m"


def test_version_label_is_hover_revealed_like_buttons(widget):
    w, root = widget
    # At rest the version label is invisible (foreground == background)…
    assert w._lbl_ver.cget("fg") == W._BG
    # …fully hovered it matches the footer buttons' revealed colour…
    w._btn_fade_step = w._btn_fade_target = 6
    w._tick_button_fade()
    assert w._lbl_ver.cget("fg") == W._FOOT_C
    assert w._lbl_ver.cget("fg") == w._buttons[0].cget("fg")
    # …and it hides again when the pointer leaves.
    w._btn_fade_step = w._btn_fade_target = 0
    w._tick_button_fade()
    assert w._lbl_ver.cget("fg") == W._BG
