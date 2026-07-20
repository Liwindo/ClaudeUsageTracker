"""Widget peak-banner geometry invariants (the v1.4.1 downward-creep fix).

These exercise the pure logic that the bug lived in â€” the authoritative
banner-free frame (`_base_*`), its bottom-anchored display geometry, and the
persistence path â€” without a live Tk window. Tk geometry round-trips through
Windows are platform/timing dependent and belong in a manual/integration check,
not a deterministic unit test; the regression-critical maths is pure.
"""
from __future__ import annotations

import json

import pytest

from claude_usage_monitor import widget as W
from claude_usage_monitor.widget import Widget


def _make_widget():
    # Widget.__init__ touches no Tk; safe to construct headless.
    return Widget(on_refresh=lambda: None, on_quit=lambda: None)


def test_displayed_target_without_banner_is_the_base_frame():
    w = _make_widget()
    w._base_x, w._base_y, w._base_w, w._base_h = 600, 400, 256, 186
    w._extra_h = 0
    assert w._displayed_target() == (600, 400, 256, 186)


def test_displayed_target_with_banner_preserves_bottom_edge():
    # The bug: growing the banner pushed the bottom DOWN instead of the top UP.
    w = _make_widget()
    w._base_x, w._base_y, w._base_w, w._base_h = 600, 400, 256, 186
    w._extra_h = 27
    x, y, width, h = w._displayed_target()
    assert (x, width) == (600, 256)          # x and width never change
    assert y == 400 - 27                       # top moves UP by the banner height
    assert h == 186 + 27                       # height grows by the banner height
    assert y + h == 400 + 186                  # bottom edge is preserved


@pytest.mark.parametrize("base", [
    (600, 400, 256, 186), (0, 0, 200, 140), (2260, 1194, 299, 197), (-50, 30, 256, 200),
])
@pytest.mark.parametrize("extra", [0, 1, 14, 27, 60])
def test_displayed_target_invariants(base, extra):
    w = _make_widget()
    w._base_x, w._base_y, w._base_w, w._base_h = base
    w._extra_h = extra
    x, y, width, h = w._displayed_target()
    bx, by, bw, bh = base
    assert x == bx and width == bw             # horizontal frame untouched
    assert x + width == bx + bw
    assert y + h == by + bh                    # bottom edge always preserved
    assert h >= bh                             # banner only ever adds height


def test_save_persists_banner_free_base_even_while_banner_shown(tmp_path, monkeypatch):
    # The drift bug corrupted the saved y by reconstructing it from live winfo
    # during the banner cascade. Persistence must come straight from _base_*,
    # so a showing banner (extra > 0) can never leak into the saved frame.
    monkeypatch.setattr(W, "_POS_FILE", tmp_path / "widget_pos.json")
    w = _make_widget()
    w._root = object()                          # truthy; _save_position needs no Tk
    w._base_x, w._base_y, w._base_w, w._base_h = 600, 400, 256, 186
    w._extra_h = 27                    # banner up â€” must NOT affect the save
    w._minimized = False
    w._save_position()
    saved = json.loads((tmp_path / "widget_pos.json").read_text())
    assert saved == {"x": 600, "y": 400, "w": 256, "h": 186, "minimized": False}


def test_save_then_restore_data_round_trips(tmp_path, monkeypatch):
    # Persisted frame must read back identically (no off-by-banner drift).
    monkeypatch.setattr(W, "_POS_FILE", tmp_path / "widget_pos.json")
    w = _make_widget()
    w._root = object()
    w._base_x, w._base_y, w._base_w, w._base_h = 2260, 1194, 299, 197
    w._extra_h = 0
    w._minimized = True
    w._save_position()
    saved = json.loads((tmp_path / "widget_pos.json").read_text())
    assert (saved["x"], saved["y"], saved["w"], saved["h"]) == (2260, 1194, 299, 197)
    assert saved["minimized"] is True
