"""The update dialog (REQUIREMENTS.md R-life-6 / R-life-7).

It must be unmistakably branded as *this* app (logo plus name), list the
offered versions with the installed one underneath, show the selected
version's notes read-only, and cope with a truncated list and with notes that
could not be loaded. The tests use a real (withdrawn) Tk root and skip where Tk
is unavailable, like the other widget tests. Looks are checked by screenshot,
not here.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")

import claude_usage_monitor.widget as W
from claude_usage_monitor import update_dialog as UD
from claude_usage_monitor.release_notes import select_notes
from claude_usage_monitor.widget import Widget, _asset_path

RELEASES = [
    {"tag_name": "v9.2.0", "body": "### Fixes\n\n- **Fixed** the thing\n- Second item"},
    {"tag_name": "v9.1.0", "body": "- Only in nine one"},
    {"tag_name": "v9.0.0", "body": "- The installed one"},
]


def _notes(current="9.0.0", latest="9.2.0", releases=RELEASES, **kw):
    return select_notes(releases, current, latest, **kw)


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


def _texts(win) -> list[str]:
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


def _dialog(root, notes, **kw):
    kw.setdefault("current_version", "9.0.0")
    return UD.UpdateDialog(root, "9.2.0", "https://github.com/x", notes, **kw)


def test_tile_logo_asset_exists_and_loads(widget):
    assert _asset_path("logo_tile.png").exists(), "bundled logo_tile.png is missing"
    photo = UD.load_logo(48)
    assert photo is not None
    assert photo.width() == 48 and photo.height() == 48


def test_dialog_shows_logo_and_branding(widget):
    w, root = widget
    w._show_update_dialog("9.9.9", "https://example.com", on_skip=lambda: None, notes=None)
    win = w._update_win
    assert win is not None
    # The logo image is attached AND a reference is held so Tk can't GC it.
    assert getattr(win, "_logo_ref", None) is not None
    texts = _texts(win)
    assert "Claude Usage Tracker" in texts, texts
    assert "Update available" in texts, texts
    assert any("9.9.9" in t for t in texts), texts


def test_closing_frees_the_widget_slot(widget):
    w, root = widget
    w._show_update_dialog("9.9.9", "https://example.com", notes=None)
    assert w._update_win is not None
    w._show_update_dialog("9.9.9", "https://example.com", notes=None)  # no second dialog
    w._update_win.event_generate("<Escape>")
    root.update()
    assert w._update_win is None


def test_missing_logo_does_not_break_dialog(widget, monkeypatch):
    """A broken/absent asset must degrade to a text-only header, never crash."""
    monkeypatch.setattr(W, "_asset_path", lambda name: W.Path("does-not-exist.png"))
    _, root = widget
    d = _dialog(root, _notes())
    assert getattr(d.win, "_logo_ref", None) is None
    assert "Claude Usage Tracker" in _texts(d.win)


def test_lists_offered_versions_and_the_installed_one(widget):
    _, root = widget
    d = _dialog(root, _notes())
    assert [r.cget("text") for r in d._rows] == ["9.2.0", "9.1.0"]
    texts = _texts(d.win)
    assert "VERSIONS" in texts
    assert "9.0.0 → 9.2.0" in texts
    assert "9.0.0" in texts and "installed" in texts


def test_selecting_a_version_shows_its_notes(widget):
    _, root = widget
    d = _dialog(root, _notes())
    content = d._text.get("1.0", "end")
    assert "Fixed the thing" in content and "Fixes" in content
    assert d._title.cget("text") == "Version 9.2.0"
    assert d._chip.winfo_manager() == "pack"  # "latest" chip on the newest

    d.select(1)
    assert d._title.cget("text") == "Version 9.1.0"
    assert "Only in nine one" in d._text.get("1.0", "end")
    assert d._chip.winfo_manager() == ""      # chip gone for older versions
    assert d._rows[1].cget("fg") == W._OK and d._rows[0].cget("fg") == W._TEXT


def test_arrow_keys_move_the_selection_and_clamp(widget):
    _, root = widget
    d = _dialog(root, _notes())
    d.win.event_generate("<Down>")
    d.win.event_generate("<Down>")  # already last
    assert d._selected == 1
    d.win.event_generate("<Up>")
    d.win.event_generate("<Up>")    # already first
    assert d._selected == 0


def test_notes_are_read_only_plain_text(widget):
    """R-net-8: no editing, and no tag that could act as a link."""
    _, root = widget
    d = _dialog(root, _notes())
    assert str(d._text.cget("state")) == "disabled"
    assert set(d._text.tag_names()) <= {
        "sel", "para", "bullet0", "bullet1", "bold", "heading", "dot", "first"}
    # "tag bind <tag>" lists the events bound to a tag: none may be.
    assert not any(d._text.tk.call(d._text._w, "tag", "bind", t) for t in d._text.tag_names())


def test_truncated_list_points_to_github(widget):
    _, root = widget
    notes = _notes(max_releases=1)
    assert notes.truncated
    d = _dialog(root, notes)
    assert len(d._rows) == 1
    assert "Older changes are listed on GitHub." in _texts(d.win)


def test_unavailable_notes_show_the_hint_and_no_list(widget):
    _, root = widget
    d = _dialog(root, None)
    texts = _texts(d.win)
    assert d._rows == []
    assert "VERSIONS" not in texts
    assert any(t.startswith("The release notes could not be loaded") for t in texts)
    assert d._title.cget("text") == "Version 9.2.0"
    assert "installed" in texts  # the installed version is still shown


def test_skip_only_when_offered_and_it_closes(widget):
    _, root = widget
    assert "Skip version" not in _texts(_dialog(root, _notes()).win)

    calls: list[str] = []
    d = _dialog(root, _notes(), on_skip=lambda: calls.append("skip"),
                on_closed=lambda: calls.append("closed"))
    d._skip()
    assert calls == ["skip", "closed"]
    assert not d.win.winfo_exists()


def test_window_is_resizable_with_a_floor(widget):
    _, root = widget
    d = _dialog(root, _notes())
    assert d.win.resizable() == (True, True)
    min_w, min_h = d.win.minsize()
    assert min_w >= UD._MIN_WIDTH and min_h >= UD._MIN_HEIGHT
