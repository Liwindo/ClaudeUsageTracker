"""The update dialog: the offered versions on the left, the selected version's
release notes on the right (REQUIREMENTS.md R-life-6 / R-life-7). With
``history=True`` it is the tray menu's read-only "Release notes" view
(R-life-8): every release, the installed one selected, no update actions.

Layout and colours match UpdateDialog.cs. tkinter has no rounded corners, so
rows and buttons are square here; everything else is the same. The window is
resizable, but its size is never remembered.

The release notes are untrusted text (R-net-8): they go into a read-only Text
widget as plain characters with a bold tag at most, and nothing in them is
clickable. The only way out of the dialog stays "Open GitHub", whose URL was
validated in update_check (R-net-7).
"""

from __future__ import annotations

import ctypes
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from . import __version__
from . import widget as W
from .i18n import tr
from .release_notes import ReleaseNotes, VersionNotes

# Default size; the user may resize, the size is not stored.
_WIDTH, _HEIGHT = 700, 470
_MIN_WIDTH, _MIN_HEIGHT = 560, 360
_SIDEBAR_W = 220
_PAD = 26

_F_BODY       = ("Segoe UI", 9)
_F_BODY_BOLD  = ("Segoe UI", 9, "bold")
_F_HEADING    = ("Segoe UI", 10, "bold")
_F_TITLE      = ("Segoe UI", 15, "bold")
_F_NAME       = ("Segoe UI", 10, "bold")
_F_SMALL      = ("Segoe UI", 8)
_F_SMALL_BOLD = ("Segoe UI", 8, "bold")

# DWMWA_USE_IMMERSIVE_DARK_MODE: 20 from Windows 10 20H1 on, 19 before that.
_DWM_DARK_MODE_ATTRS = (20, 19)


def load_logo(px: int) -> Optional[ImageTk.PhotoImage]:
    """The opaque tile logo at px×px, or None if it can't load. logo.png is a
    translucent tile in a dark glow that turns into a smudge at title-bar size;
    logo_tile.png is just the tile. A broken asset must never block the dialog."""
    try:
        img = Image.open(W._asset_path("logo_tile.png")).convert("RGBA")
        return ImageTk.PhotoImage(img.resize((px, px), Image.LANCZOS))
    except Exception:
        return None


def _dark_title_bar(win: tk.Toplevel) -> None:
    """Give the window the dark caption of the dialog body. Ignored where the
    attribute is unknown (older Windows); the dialog then keeps a light one."""
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        for attr in _DWM_DARK_MODE_ATTRS:
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)
            ) == 0:
                return
    except Exception:
        pass


def _scrollbar_style(win: tk.Misc) -> str:
    """A slim dark ttk scrollbar. The native Windows one is light grey and
    ignores colours, so its parts are borrowed from the 'clam' theme without
    switching the app's theme."""
    style = ttk.Style(win)
    name = "Notes.Vertical.TScrollbar"
    for element, source in (("Notes.trough", "Vertical.Scrollbar.trough"),
                            ("Notes.thumb", "Vertical.Scrollbar.thumb")):
        try:
            style.element_create(element, "from", "clam", source)
        except tk.TclError:
            pass  # created by an earlier dialog in this process
    style.layout(name, [("Notes.trough", {"sticky": "ns", "children": [
        ("Notes.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure(name, troughcolor=W._BG, background=W._BTN_HOV,
                    bordercolor=W._BG, lightcolor=W._BTN_HOV, darkcolor=W._BTN_HOV,
                    gripcount=0, arrowsize=8)
    style.map(name, background=[("active", "#4a4a58")])
    return name


class UpdateDialog:
    """Builds and shows the dialog on the Tk thread. ``win`` is the Toplevel."""

    def __init__(
        self,
        root: tk.Misc,
        latest_version: str,
        url: str,
        notes: Optional[ReleaseNotes],
        on_skip: Optional[Callable[[], None]] = None,
        on_closed: Optional[Callable[[], None]] = None,
        current_version: Optional[str] = None,
        history: bool = False,
    ) -> None:
        self._history = history
        self._latest = latest_version
        self._url = url
        self._notes = notes
        self._on_skip = on_skip
        self._on_closed = on_closed
        self._current = current_version or __version__
        self._rows: list[tk.Label] = []
        self._hovered: Optional[int] = None
        self._selected = 0
        self._text: Optional[tk.Text] = None

        win = tk.Toplevel(root)
        self.win = win
        win.withdraw()  # dark caption and size first, then show
        win.title(tr("update.notes_title" if history else "update.window_title"))
        win.configure(bg=W._BG)
        win.attributes("-topmost", True)
        self._set_icons()

        win.columnconfigure(2, weight=1)
        win.rowconfigure(0, weight=1)
        self._build_sidebar().grid(row=0, column=0, sticky="ns")
        tk.Frame(win, bg=W._DIVIDER, width=1).grid(row=0, column=1, sticky="ns")
        self._build_main().grid(row=0, column=2, sticky="nsew")

        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda e: self.close())
        if notes is not None:
            win.bind("<Up>", lambda e: self.select(self._selected - 1))
            win.bind("<Down>", lambda e: self.select(self._selected + 1))
            installed = [v.version for v in notes.versions]
            self.select(installed.index(self._current) if self._current in installed else 0)
        self._size_and_show()

    # ── Building ──────────────────────────────────────────────────────────────

    def _set_icons(self) -> None:
        icons = [p for p in (load_logo(32), load_logo(16)) if p is not None]
        if not icons:
            return
        self.win._icon_refs = icons  # type: ignore[attr-defined]  # keep from GC
        try:
            self.win.iconphoto(False, *icons)
        except tk.TclError:
            pass

    def _build_sidebar(self) -> tk.Frame:
        bg = W._SIDEBAR
        side = tk.Frame(self.win, bg=bg, padx=12, pady=20)
        # Fixes the column width; the labels below wrap inside it.
        tk.Frame(side, bg=bg, width=_SIDEBAR_W - 24, height=0).pack(fill="x")

        header = tk.Frame(side, bg=bg)
        header.pack(fill="x", padx=6)
        logo = load_logo(36)
        if logo is not None:
            self.win._logo_ref = logo  # type: ignore[attr-defined]  # keep from GC
            tk.Label(header, image=logo, bg=bg, bd=0).pack(side="left", padx=(0, 10))
        brand = tk.Frame(header, bg=bg)
        brand.pack(side="left", fill="y")
        tk.Label(brand, text="Claude Usage Tracker", font=_F_NAME, bg=bg,
                 fg=W._TEXT, anchor="w").pack(fill="x")
        if self._history:
            tk.Label(brand, text=tr("update.notes_title"), font=_F_SMALL, bg=bg,
                     fg=W._DIM, anchor="w").pack(fill="x")
        else:
            tk.Label(brand, text=tr("update.available"), font=_F_SMALL, bg=bg,
                     fg=W._OK, anchor="w").pack(fill="x")
            tk.Label(side, text=f"{self._current} → {self._latest}", font=_F_BODY,
                     bg=bg, fg=W._DIM, anchor="w").pack(fill="x", padx=6, pady=(12, 0))

        if self._notes is not None:
            tk.Label(side, text=tr("update.versions").upper(), font=_F_SMALL_BOLD,
                     bg=bg, fg=W._DIM, anchor="w").pack(fill="x", padx=6, pady=(18, 6))
            for i, version in enumerate(self._notes.versions):
                row = tk.Label(side, text=version.version, font=_F_BODY_BOLD,
                               anchor="w", padx=10, pady=6, cursor="hand2", bg=bg, fg=W._TEXT)
                row.pack(fill="x", pady=(0, 2))
                row.bind("<Button-1>", lambda e, i=i: self.select(i))
                row.bind("<Enter>", lambda e, i=i: self._hover(i))
                row.bind("<Leave>", lambda e: self._hover(None))
                self._rows.append(row)
            if self._notes.truncated:
                tk.Label(side, text=tr("update.notes_more"), font=_F_SMALL, bg=bg,
                         fg=W._DIM, anchor="w", justify="left",
                         wraplength=_SIDEBAR_W - 44).pack(fill="x", padx=10, pady=(8, 0))

        tk.Frame(side, bg=W._DIVIDER, height=1).pack(
            fill="x", padx=10, pady=(10 if self._notes is not None else 18, 4))
        installed = tk.Frame(side, bg=bg)
        installed.pack(fill="x", padx=10)
        tk.Label(installed, text=self._current, font=_F_BODY, bg=bg,
                 fg=W._DIM).pack(side="left")
        tk.Label(installed, text=tr("update.installed"), font=_F_SMALL, bg=bg,
                 fg=W._DIM).pack(side="right")

        if self._on_skip is not None:
            skip = tk.Label(side, text=tr("update.skip"), font=_F_BODY, bg=bg,
                            fg=W._DIM, anchor="w", padx=10, pady=6, cursor="hand2")
            skip.pack(side="bottom", fill="x")
            skip.bind("<Button-1>", lambda e: self._skip())
            skip.bind("<Enter>", lambda e: skip.configure(fg=W._TEXT))
            skip.bind("<Leave>", lambda e: skip.configure(fg=W._DIM))
        return side

    def _build_main(self) -> tk.Frame:
        main = tk.Frame(self.win, bg=W._BG)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        head = tk.Frame(main, bg=W._BG)
        head.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(20, 8))
        self._title = tk.Label(head, font=_F_TITLE, bg=W._BG, fg=W._TEXT, anchor="w")
        self._title.pack(side="left")
        self._chip = tk.Label(head, text=tr("update.latest"), font=_F_SMALL_BOLD,
                              bg=W._CHIP_BG, fg=W._OK, padx=6, pady=1)
        self._installed_chip = tk.Label(head, text=tr("update.installed"), font=_F_SMALL_BOLD,
                                        bg=W._BTN_BG, fg=W._DIM, padx=6, pady=1)

        if self._notes is not None:
            self._build_notes(main).grid(row=1, column=0, sticky="nsew", padx=(_PAD, 6))
        else:
            self._title.configure(text=tr("update.notes_version", version=self._latest))
            self._chip.pack(side="left", padx=(10, 0), pady=(4, 0))
            self._build_unavailable(main).grid(row=1, column=0, sticky="new",
                                               padx=_PAD, pady=(10, 0))

        tk.Frame(main, bg=W._DIVIDER, height=1).grid(row=2, column=0, sticky="ew")
        foot = tk.Frame(main, bg=W._BG, padx=_PAD, pady=14)
        foot.grid(row=3, column=0, sticky="ew")
        # side="right" packs right to left: the primary button ends up rightmost.
        self._button(foot, tr("update.open_github"), self._open_github, primary=True
                     ).pack(side="right")
        self._button(foot, tr("update.close" if self._history else "update.cancel"),
                     self.close).pack(side="right", padx=(0, 8))
        return main

    def _build_notes(self, parent: tk.Misc) -> tk.Frame:
        body = tk.Frame(parent, bg=W._BG)
        # Fixed slot for the scrollbar, so showing it never re-wraps the text.
        slot = tk.Frame(body, bg=W._BG, width=10)
        slot.pack(side="right", fill="y")
        slot.pack_propagate(False)
        text = tk.Text(
            body, width=1, height=1, wrap="word", font=_F_BODY, bg=W._BG, fg=W._BODY,
            bd=0, highlightthickness=0, relief="flat", padx=0, pady=0, spacing2=2,
            cursor="arrow", insertwidth=0, takefocus=0,
            selectbackground=W._BTN_HOV, inactiveselectbackground=W._BTN_HOV,
        )
        text.pack(side="left", fill="both", expand=True, padx=(0, 12))
        bar = ttk.Scrollbar(slot, orient="vertical", command=text.yview,
                            style=_scrollbar_style(self.win))

        def on_scroll(first: str, last: str) -> None:
            bar.set(first, last)
            if float(first) <= 0.0 and float(last) >= 1.0:
                bar.pack_forget()
            elif not bar.winfo_ismapped():
                bar.pack(fill="y", expand=True, pady=(0, 8))

        text.configure(yscrollcommand=on_scroll)
        # Creation order is tag priority: later tags win, so "heading" keeps
        # its font over "bold" and "first" drops the top gap.
        text.tag_configure("para", spacing1=8)
        text.tag_configure("bullet0", lmargin1=0, lmargin2=16, tabs=(16,), spacing1=6)
        text.tag_configure("bullet1", lmargin1=16, lmargin2=32, tabs=(32,), spacing1=4)
        text.tag_configure("bold", font=_F_BODY_BOLD, foreground=W._TEXT)
        text.tag_configure("heading", font=_F_HEADING, foreground=W._TEXT,
                           spacing1=14, spacing3=2)
        text.tag_configure("dot", foreground=W._OK)
        text.tag_configure("first", spacing1=2)
        self._text = text
        return body

    def _build_unavailable(self, parent: tk.Misc) -> tk.Frame:
        box = tk.Frame(parent, bg=W._INFO_BG, padx=16, pady=14)
        icon = tk.Canvas(box, width=18, height=18, bg=W._INFO_BG, highlightthickness=0)
        icon.create_oval(2, 2, 16, 16, outline=W._DIM, width=1.5)
        icon.create_line(9, 8, 9, 13, fill=W._DIM, width=1.5)
        icon.create_oval(8.2, 4.6, 9.8, 6.2, fill=W._DIM, outline=W._DIM)
        icon.pack(side="left", anchor="n", padx=(0, 12))
        msg = tk.Label(box, text=tr("update.notes_unavailable"), font=_F_BODY,
                       bg=W._INFO_BG, fg=W._BODY, justify="left", anchor="w",
                       wraplength=200)  # narrow at first: it must not set the min width
        msg.pack(side="left", fill="x", expand=True)
        box.bind("<Configure>", lambda e: msg.configure(wraplength=max(160, e.width - 70)))
        return box

    def _button(self, parent: tk.Misc, text: str, command: Callable[[], None],
                primary: bool = False) -> tk.Button:
        bg, hover, fg = ((W._OK, W._OK_HOV, W._ON_OK) if primary
                         else (W._BTN_BG, W._BTN_HOV, W._TEXT))
        button = tk.Button(
            parent, text=text, command=command,
            font=_F_BODY_BOLD if primary else _F_BODY, bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg, relief="flat", bd=0,
            highlightthickness=0, padx=16, pady=6, cursor="hand2",
        )
        button.bind("<Enter>", lambda e: button.configure(bg=hover))
        button.bind("<Leave>", lambda e: button.configure(bg=bg))
        return button

    def _size_and_show(self) -> None:
        win = self.win
        win.update_idletasks()
        req_w, req_h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.minsize(max(_MIN_WIDTH, req_w), max(_MIN_HEIGHT, req_h))
        w, h = max(_WIDTH, req_w), max(_HEIGHT, req_h)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        _dark_title_bar(win)
        win.deiconify()
        win.lift()

    # ── Behaviour ─────────────────────────────────────────────────────────────

    def select(self, index: int) -> None:
        """Show the notes of the index-th offered version (clamped)."""
        if self._notes is None or self._text is None:
            return
        index = max(0, min(index, len(self._notes.versions) - 1))
        self._selected = index
        version = self._notes.versions[index]
        self._title.configure(text=tr("update.notes_version", version=version.version))
        self._chip.pack_forget()
        self._installed_chip.pack_forget()
        if version.version == self._latest:
            self._chip.pack(side="left", padx=(10, 0), pady=(4, 0))
        if version.version == self._current:
            self._installed_chip.pack(side="left", padx=(10, 0), pady=(4, 0))
        for i in range(len(self._rows)):
            self._paint_row(i)
        self._render(version)

    def _hover(self, index: Optional[int]) -> None:
        previous, self._hovered = self._hovered, index
        for i in (previous, index):
            if i is not None:
                self._paint_row(i)

    def _paint_row(self, i: int) -> None:
        if i == self._selected:
            bg, fg = W._TRACK, W._OK
        elif i == self._hovered:
            bg, fg = W._ROW_HOV, W._TEXT
        else:
            bg, fg = W._SIDEBAR, W._TEXT
        self._rows[i].configure(bg=bg, fg=fg)

    def _render(self, version: VersionNotes) -> None:
        text = self._text
        assert text is not None
        text.configure(state="normal")
        text.delete("1.0", "end")
        for i, block in enumerate(version.blocks):
            if block.kind == "heading":
                base: tuple[str, ...] = ("heading",)
            elif block.kind == "bullet":
                base = (f"bullet{block.level}",)
            else:
                base = ("para",)
            if i == 0:
                base += ("first",)
            if block.kind == "bullet":
                text.insert("end", "•" if block.level == 0 else "◦", base + ("dot",))
                text.insert("end", "\t", base)
            for span in block.spans:
                text.insert("end", span.text, base + (("bold",) if span.bold else ()))
            text.insert("end", "\n", base)
        text.delete("end-2c")  # no empty line after the last block
        text.configure(state="disabled")
        text.yview_moveto(0)

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self._on_closed is not None:
            self._on_closed()

    def _open_github(self) -> None:
        webbrowser.open(self._url)
        self.close()

    def _skip(self) -> None:
        if self._on_skip is not None:
            self._on_skip()
        self.close()
