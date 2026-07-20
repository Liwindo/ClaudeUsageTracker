"""The startup update dialog must be unmistakably branded as *this* app.

Earlier the dialog only named the app in the (easy-to-miss) title bar. These
tests pin the branding down: the bundled logo asset resolves and loads, and the
dialog actually shows the logo image plus an "Update available" header next to
the app name. They use a real (withdrawn) Tk root and skip where Tk is
unavailable, like the other widget tests.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")

import claude_usage_monitor.widget as W
from claude_usage_monitor.widget import Widget, _asset_path


@pytest.fixture()
def widget(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_POS_FILE", tmp_path / "widget_pos.json")
    W._bar_cache.clear()
    W._dot_cache.clear()
    W._div_cache.clear()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.overrideredirect(True)
    root.withdraw()
    w = Widget(on_refresh=lambda: None, on_quit=lambda: None)
    w._root = root
    w._build_ui(root)
    root.update_idletasks()
    w._min_h = root.winfo_reqheight()
    w._base_x = w._base_y = 0
    w._base_h = w._min_h
    try:
        yield w, root
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def _all_label_texts(win) -> list[str]:
    """Every Label's text anywhere in the dialog's widget tree."""
    texts: list[str] = []
    stack = list(win.winfo_children())
    while stack:
        node = stack.pop()
        if isinstance(node, tk.Label):
            try:
                texts.append(str(node.cget("text")))
            except tk.TclError:
                pass
        stack.extend(node.winfo_children())
    return texts


def test_logo_asset_exists_and_loads(widget):
    w, _root = widget
    assert _asset_path("logo.png").exists(), "bundled logo.png is missing"
    photo = w._load_logo(48)
    assert photo is not None
    assert photo.width() == 48 and photo.height() == 48


def test_dialog_shows_logo_and_branding(widget):
    w, root = widget
    w._show_update_dialog("9.9.9", "https://example.com", on_skip=lambda: None)
    win = w._update_win
    assert win is not None
    # The logo image is attached AND a reference is held so Tk can't GC it.
    assert getattr(win, "_logo_ref", None) is not None
    root.update_idletasks()

    texts = _all_label_texts(win)
    assert "Claude Usage Tracker" in texts, texts
    assert "Update available" in texts, texts
    assert any("9.9.9" in t for t in texts), texts


def test_missing_logo_does_not_break_dialog(widget, monkeypatch):
    """A broken/absent asset must degrade to a text-only header, never crash."""
    monkeypatch.setattr(W, "_asset_path", lambda name: W.Path("does-not-exist.png"))
    w, root = widget
    w._show_update_dialog("9.9.9", "https://example.com")
    win = w._update_win
    assert win is not None
    assert getattr(win, "_logo_ref", None) is None  # no image loaded
    texts = _all_label_texts(win)
    assert "Claude Usage Tracker" in texts  # name still present in the body
