"""Persistent always-on-top mini-widget showing Claude usage statistics.

Renders a premium opaque "glass" surface: a 5-band vertical gradient simulated
via stacked Frames (rim highlight → sheen → body → base → shadow), rounded
outer corners via DWM (Win11) / SetWindowRgn (Win10), and Pillow-rendered
progress bars, status dot, and divider for antialiasing and gradient effects.
Rounded corners are best-effort — they degrade to square corners on failure.
"""

from __future__ import annotations

import ctypes
import json
import sys
import tkinter as tk
import webbrowser
from tkinter import messagebox
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .config import _config_dir, log_file_path
from .i18n import tr
from .models import UsageData

# ── Design tokens — opaque vertical-gradient palette ──────────────────────────
# Top → bottom gradient simulation (5 bands stacked top-to-bottom):
_BG_RIM     = "#2c2c36"   # 1 px — rim highlight (top edge catches light)
_BG_SHEEN   = "#1e1e26"   # 1 px — soft sheen step
_BG         = "#16161c"   # body — main card surface
_BG_BASE    = "#10101a"   # 1 px — base transition
_BG_SHADOW  = "#08080d"   # 1 px — deep shadow line at bottom edge

_TEXT     = "#ececf2"
_DIM      = "#9494a0"
_FOOT_C   = "#7a7a84"
_BORDER   = "#2e2e38"
_TRACK    = "#1f1f27"
_BTN_BG   = "#26262e"
_BTN_HOV  = "#34343e"

# Status colours — identical to tray.py so widget and icon stay in sync
_OK      = "#22c55e"
_YELLOW  = "#eab308"
_WARN    = "#f97316"
_ALERT   = "#ef4444"

_FONT_TITLE = ("Segoe UI", 10, "bold")
_FONT_LBL   = ("Segoe UI", 8)
_FONT_PCT   = ("Consolas", 11, "bold")
_FONT_FT    = ("Consolas", 8)
_FONT_BTN   = ("Segoe UI", 9)

_W       = 256
_CARD_PADX = 18   # inner horizontal padding of the card frame
_BAR_H   = 6      # rounded-pill progress bar height
_DOT_PX  = 14     # status dot canvas size (incl. halo)
_RADIUS  = 10     # outer window corner radius
_POS_FILE = _config_dir() / "widget_pos.json"

_WEEKLY_KEYS = [
    "seven_day", "seven_day_sonnet", "seven_day_opus",
    "seven_day_omelette", "seven_day_cowork",
]

# Anthropic's published peak hours: weekdays 05:00–11:00 Pacific Time.
# Defined in PT so DST shifts (and the asymmetric US-vs-rest-of-world DST
# transition weeks) convert correctly to whatever local zone the OS reports.
_PEAK_TZ = ZoneInfo("America/Los_Angeles")
_PEAK_PT_START = 5
_PEAK_PT_END = 11  # exclusive


def _peak_hour_window_local() -> Optional[tuple[str, str]]:
    """If now lies inside Anthropic's peak window, return its (start, end)
    wall-clock times in the OS's local zone as "HH:MM" strings for display.
    Returns None otherwise.

    The local zone is read from the OS at each call via the no-arg form of
    `astimezone()`, so the displayed times adapt automatically to wherever the
    user runs the tool — no hard-coded Europe/Berlin assumption. Minutes are
    part of the result because half-hour zones (e.g. UTC+5:30) land the window
    off the full hour — a hard-coded ":00" would display it 30 min wrong.
    """
    now_pt = datetime.now(_PEAK_TZ)
    if now_pt.weekday() >= 5:  # Sat/Sun
        return None
    if not (_PEAK_PT_START <= now_pt.hour < _PEAK_PT_END):
        return None
    base = now_pt.replace(minute=0, second=0, microsecond=0)
    start_local = base.replace(hour=_PEAK_PT_START).astimezone()
    end_local = base.replace(hour=_PEAK_PT_END).astimezone()
    return f"{start_local:%H:%M}", f"{end_local:%H:%M}"


# ── Asset loading ─────────────────────────────────────────────────────────────

def _asset_path(name: str) -> Path:
    """Absolute path to a bundled asset, in both source and frozen layouts.

    PyInstaller copies the package (`datas=[('src/claude_usage_monitor',
    'claude_usage_monitor')]`) into the onefile temp dir, so when frozen the
    assets live under `sys._MEIPASS/claude_usage_monitor/assets/`. From source
    they sit next to this module.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "claude_usage_monitor" / "assets"
    else:
        base = Path(__file__).parent / "assets"
    return base / name


# ── Colour helpers ────────────────────────────────────────────────────────────

def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex(c1)
    r2, g2, b2 = _hex(c2)
    return (
        f"#{int(r1 + (r2 - r1) * t):02x}"
        f"{int(g1 + (g2 - g1) * t):02x}"
        f"{int(b1 + (b2 - b1) * t):02x}"
    )


def _pct_color(pct: int) -> str:
    if pct >= 85:
        return _ALERT
    if pct >= 60:
        return _WARN
    if pct >= 40:
        return _YELLOW
    return _OK


def _reset_color(li) -> str:
    """Green = reset imminent (limit refreshes soon), red = far away."""
    if li is None:
        return _OK
    secs = li.resets_in_seconds
    if secs < 15 * 60:
        return _OK
    if secs < 30 * 60:
        return _YELLOW
    if secs < 90 * 60:
        return _WARN
    return _ALERT


def _virtual_screen_bounds() -> tuple[int, int, int, int]:
    """(x, y, w, h) of the Windows virtual desktop spanning all monitors.

    winfo_screenwidth/-height only cover the primary monitor, which would
    yank a deliberately-on-second-monitor widget back onto the primary.
    Returns (0, 0, 0, 0) on failure (callers must check w/h > 0).
    """
    try:
        u = ctypes.windll.user32
        # SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN/SM_CX…/SM_CY… = 76/77/78/79
        return (
            u.GetSystemMetrics(76), u.GetSystemMetrics(77),
            u.GetSystemMetrics(78), u.GetSystemMetrics(79),
        )
    except Exception:
        return (0, 0, 0, 0)


# ── Rounded outer corners (Windows; best-effort) ──────────────────────────────

def _apply_round_corners(root: tk.Tk, radius: int = _RADIUS) -> None:
    """Round the window's outer corners. Win11 → DWM; Win10 → SetWindowRgn."""
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    except Exception:
        return

    # Win11: native DWM rounded corners (DWMWA_WINDOW_CORNER_PREFERENCE = 33)
    try:
        import sys
        is_win11 = sys.getwindowsversion().build >= 22000
    except Exception:
        is_win11 = False
    if is_win11:
        try:
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)
            )
            return
        except Exception:
            pass

    # Win10 fallback: clip the HWND to a rounded-rect region
    try:
        w = root.winfo_width()
        h = root.winfo_height()
        if w <= 0 or h <= 0:
            return
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, w + 1, h + 1, radius * 2, radius * 2
        )
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


# ── Pillow renderers (cached) ─────────────────────────────────────────────────

_bar_cache: dict[tuple, "ImageTk.PhotoImage"] = {}
_dot_cache: dict[str, "ImageTk.PhotoImage"] = {}
_div_cache: dict[int, "ImageTk.PhotoImage"] = {}


def _render_bar(width: int, pct: int, color: str) -> Image.Image:
    """Pill-shaped progress bar with gradient fill, fully antialiased."""
    h = _BAR_H
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = h // 2
    track_rgb = _hex(_TRACK)
    d.rounded_rectangle((0, 0, width - 1, h - 1), radius=r, fill=(*track_rgb, 255))

    fw = max(0, int(width * min(pct, 100) / 100))
    if fw >= 1:
        c = _hex(color)
        cd = tuple(max(0, int(x * 0.72)) for x in c)
        grad = Image.new("RGBA", (fw, h))
        gd = ImageDraw.Draw(grad)
        denom = max(1, fw - 1)
        for x in range(fw):
            t = x / denom
            r2 = int(cd[0] + (c[0] - cd[0]) * t)
            g2 = int(cd[1] + (c[1] - cd[1]) * t)
            b2 = int(cd[2] + (c[2] - cd[2]) * t)
            gd.line([(x, 0), (x, h)], fill=(r2, g2, b2, 255))
        mask = Image.new("L", (fw, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, fw - 1, h - 1), radius=r, fill=255
        )
        img.paste(grad, (0, 0), mask)
    return img


def _render_dot(color: str, size: int = _DOT_PX) -> Image.Image:
    """Status dot with a soft radial glow halo."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    c = _hex(color)
    outer = size / 2
    for r in range(int(outer), 2, -1):
        a = int(40 * (1 - r / outer))
        if a > 0:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*c, a))
    cr = 2.6
    d.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=(*c, 255))
    return img


def _render_divider(width: int) -> Image.Image:
    """1px line whose alpha fades to 0 at both ends."""
    img = Image.new("RGBA", (width, 1), (0, 0, 0, 0))
    bc = _hex(_BORDER)
    d = ImageDraw.Draw(img)
    denom = max(1, width - 1)
    for x in range(width):
        t = 1.0 - abs((x / denom) * 2 - 1)
        a = int(220 * t)
        if a > 0:
            d.point((x, 0), fill=(*bc, a))
    return img


def _bar_image(width: int, pct: int, color: str) -> "ImageTk.PhotoImage":
    width = max(8, (width // 4) * 4)
    key = (width, pct, color)
    img = _bar_cache.get(key)
    if img is None:
        img = ImageTk.PhotoImage(_render_bar(width, pct, color))
        _bar_cache[key] = img
        if len(_bar_cache) > 120:
            try:
                _bar_cache.pop(next(iter(_bar_cache)))
            except Exception:
                pass
    return img


def _dot_image(color: str) -> "ImageTk.PhotoImage":
    img = _dot_cache.get(color)
    if img is None:
        img = ImageTk.PhotoImage(_render_dot(color))
        _dot_cache[color] = img
    return img


def _div_image(width: int) -> "ImageTk.PhotoImage":
    width = max(8, (width // 4) * 4)
    img = _div_cache.get(width)
    if img is None:
        img = ImageTk.PhotoImage(_render_divider(width))
        _div_cache[width] = img
        if len(_div_cache) > 24:
            try:
                _div_cache.pop(next(iter(_div_cache)))
            except Exception:
                pass
    return img


class Widget:
    """Always-on-top glass widget with acrylic / mica blur on Windows."""

    def __init__(
        self,
        on_refresh: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_refresh = on_refresh
        self._on_quit = on_quit
        self._root: Optional[tk.Tk] = None

        self._var_s: Optional[tk.StringVar] = None
        self._var_w: Optional[tk.StringVar] = None
        self._var_ft: Optional[tk.StringVar] = None
        self._lbl_s: Optional[tk.Label] = None
        self._lbl_w: Optional[tk.Label] = None
        self._bar_s: Optional[tk.Label] = None
        self._bar_w: Optional[tk.Label] = None
        self._dot: Optional[tk.Label] = None
        self._div: Optional[tk.Label] = None
        self._lbl_ft: Optional[tk.Label] = None
        self._lbl_ver: Optional[tk.Label] = None  # version — hover-revealed
        self._peak_banner: Optional[tk.Label] = None
        self._session_row: Optional[tk.Frame] = None
        self._peak_visible: bool = False
        # Height delta added by wrapped content (peak banner and/or a footer
        # status text that wrapped to multiple lines).
        self._extra_h: int = 0
        self._buttons: list[tk.Button] = []
        self._btn_frame: Optional[tk.Frame] = None

        self._dragging = False
        self._drag_x = self._drag_y = 0
        self._resizing = False
        self._resize_start_x = self._resize_start_y = 0
        self._resize_start_w = self._resize_start_h = 0
        self._min_w = 200
        self._min_h = 140
        self._grip: Optional[tk.Label] = None
        self._last_size: tuple[int, int] = (0, 0)

        # Authoritative banner-free window frame (top-left + size) the user
        # controls via drag/resize. Persistence AND the banner grow/shrink
        # derive from THIS, never from live winfo readings: on overrideredirect
        # windows Windows can momentarily revert the position half of a combined
        # size+move geometry change while honoring the size half (during the
        # <Configure>/SetWindowRgn cascade). Reconstructing the natural frame
        # from winfo at that instant drifts the saved y downward by the banner
        # height on every peak toggle and restart.
        self._base_x: int = 0
        self._base_y: int = 0
        self._base_w: int = _W
        self._base_h: int = 0

        self._btn_fade_step = 0  # 0..6 — 0 hidden, 6 fully shown
        self._btn_fade_target = 0
        self._fade_job: Optional[str] = None

        self._last_data: Optional[UsageData] = None
        self._last_error: Optional[str] = None
        self._tooltip_win: Optional[tk.Toplevel] = None
        self._update_win: Optional[tk.Toplevel] = None
        self._minimized: bool = False

    # ── Public API (thread-safe) ──────────────────────────────────────────────

    def start(self) -> None:
        """Build the UI and run the Tk event loop. Blocks the calling thread."""
        root = tk.Tk()
        self._root = root
        root.title("Claude Status")
        root.configure(bg=_BG)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.withdraw()

        self._build_ui(root)
        self._restore_position(root)
        root.update_idletasks()
        # Use the natural required height as the floor — winfo_height() could
        # be smaller if the user had previously over-shrunk the widget via the
        # resize grip, which would later clip the footer (and its buttons).
        self._min_h = max(root.winfo_height(), root.winfo_reqheight())

        _apply_round_corners(root)

        if not self._minimized:
            root.deiconify()
        # Render any snapshot that arrived before the UI existed (the first
        # poll usually completes before tk.Tk() is up). Scheduled via after()
        # so it runs inside the mainloop, after the window is mapped.
        if self._last_error is not None:
            root.after(0, self._apply_error, self._last_error)
        elif self._last_data is not None:
            root.after(0, self._apply_data, self._last_data)
        # Evaluate peak window only after `_min_h` is captured from the natural
        # (banner-free) layout, so shrink-back at end-of-peak knows the floor.
        # Defer via after() so the initial deiconify + <Configure> + SetWindowRgn
        # pipeline has fully settled before we attempt the banner's bottom-anchored
        # geometry shift. Running grow synchronously here races with Windows'
        # post-map position handling, which reverts the y-shift back to the
        # restored y and leaves the bottom edge floating downward by `delta`.
        root.after(0, self._tick_peak_banner)
        root.mainloop()

    def _post(self, callback, *args) -> bool:
        """Schedule *callback* on the Tk thread; tolerate shutdown races.

        Callers live on the poller / pystray threads. `after()` on a destroyed
        root raises TclError (and RuntimeError in rare interpreter-teardown
        windows) — swallowing those here keeps a late poll result from killing
        the poller thread during quit.
        """
        root = self._root
        if not root:
            return False
        try:
            root.after(0, callback, *args)
            return True
        except (RuntimeError, tk.TclError):
            return False

    def stop(self) -> None:
        if self._root:
            self._post(self._root.destroy)

    def toggle(self) -> None:
        """Show the widget if hidden, hide it if visible."""
        if self._root:
            def _do():
                if self._root.state() == "withdrawn":
                    self._root.deiconify()
                    self._root.attributes("-topmost", True)
                    self._minimized = False
                    self._refresh_peak_banner()
                else:
                    self._root.withdraw()
                    self._minimized = True
                self._save_position()
            self._post(_do)

    def update(self, data: UsageData) -> None:
        if not self._post(self._apply_data, data):
            # The first poll usually finishes before start() has built the UI —
            # buffer the snapshot so start() renders it instead of "connecting…".
            self._last_data = data
            self._last_error = None

    def set_error(self, message: str) -> None:
        if not self._post(self._apply_error, message):
            self._last_error = message

    def _load_logo(self, px: int) -> Optional[ImageTk.PhotoImage]:
        """Return the app logo scaled to `px`×`px`, or None if it can't load.

        A missing/corrupt asset must never block the update dialog, so any
        failure is logged-by-omission and the caller falls back to text only.
        """
        try:
            img = Image.open(_asset_path("logo.png")).convert("RGBA")
            img = img.resize((px, px), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def notify_update(
        self,
        latest_version: str,
        url: str,
        on_skip: Optional[Callable[[], None]] = None,
    ) -> None:
        """Show a dialog offering to open the GitHub release page. Thread-safe.

        Args:
            on_skip: Called (on the Tk thread) when the user chooses
                "Skip version" — the dialog never reappears for this release.
        """
        self._post(self._show_update_dialog, latest_version, url, on_skip)

    def notify_message(self, title: str, body: str, kind: str = "info") -> None:
        """Show a simple modal info/warning box on the Tk thread. Thread-safe.

        Used by the manual "Check for updates" action to report "up to date" or
        "check failed" (the "available" case uses the richer update dialog).
        """
        self._post(self._show_message, title, body, kind)

    def _show_message(self, title: str, body: str, kind: str) -> None:
        if not self._root:
            return
        if kind == "warning":
            messagebox.showwarning(title, body, parent=self._root)
        else:
            messagebox.showinfo(title, body, parent=self._root)

    def _show_update_dialog(
        self,
        latest_version: str,
        url: str,
        on_skip: Optional[Callable[[], None]] = None,
    ) -> None:
        if self._update_win is not None or not self._root:
            return
        win = tk.Toplevel(self._root)
        self._update_win = win
        # Short title — the full app name lives in the (branded) body, and a long
        # title gets clipped in the narrow window. The logo icon keeps it identifiable.
        win.title(tr("update.window_title"))
        win.configure(bg=_BG, padx=22, pady=18)
        win.resizable(False, False)
        win.attributes("-topmost", True)

        # ── Branded header: app logo + name, so it is unmistakably *this* app
        # that is reporting the update (the title bar alone is easy to miss).
        header = tk.Frame(win, bg=_BG)
        header.pack(fill="x", pady=(0, 14))

        logo = self._load_logo(48)
        if logo is not None:
            # Hold a reference on the window so Tk doesn't garbage-collect it.
            win._logo_ref = logo  # type: ignore[attr-defined]
            tk.Label(header, image=logo, bg=_BG, bd=0).pack(side="left", padx=(0, 12))
            try:
                win.iconphoto(False, logo)  # brand the taskbar / title bar too
            except tk.TclError:
                pass

        brand = tk.Frame(header, bg=_BG)
        brand.pack(side="left", fill="y")
        tk.Label(
            brand, text="Claude Usage Tracker",
            font=_FONT_TITLE, bg=_BG, fg=_TEXT, anchor="w",
        ).pack(fill="x")
        tk.Label(
            brand, text=tr("update.available"),
            font=_FONT_LBL, bg=_BG, fg=_OK, anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Hairline divider under the header for a finished, card-like look.
        tk.Frame(win, bg=_BORDER, height=1).pack(fill="x", pady=(0, 14))

        tk.Label(
            win, text=tr("update.version_available", version=latest_version),
            font=_FONT_TITLE, bg=_BG, fg=_TEXT, anchor="w",
        ).pack(fill="x")
        tk.Label(
            win, text=tr("update.running_version", version=__version__),
            font=_FONT_LBL, bg=_BG, fg=_DIM, anchor="w",
        ).pack(fill="x", pady=(4, 14))

        def _close() -> None:
            self._update_win = None
            win.destroy()

        def _open_repo() -> None:
            webbrowser.open(url)
            _close()

        def _skip() -> None:
            if on_skip is not None:
                on_skip()
            _close()

        row = tk.Frame(win, bg=_BG)
        row.pack(fill="x")
        # side="right" packs right-to-left: Cancel ends up rightmost,
        # matching the Windows [primary] [secondary] [cancel] button order.
        buttons = [(tr("update.cancel"), _close)]
        if on_skip is not None:
            buttons.append((tr("update.skip"), _skip))
        buttons.append((tr("update.open_github"), _open_repo))
        for text, cmd in buttons:
            tk.Button(
                row, text=text, command=cmd,
                font=_FONT_BTN, bg=_BTN_BG, fg=_TEXT,
                activebackground=_BTN_HOV, activeforeground=_TEXT,
                relief="flat", padx=12, pady=3, cursor="hand2",
                bd=0, highlightthickness=0,
            ).pack(side="right", padx=(8, 0))

        win.protocol("WM_DELETE_WINDOW", _close)
        win.bind("<Escape>", lambda e: _close())

        # Size to content, then never shrink below it, so the window always
        # matches what it contains (and the short title never gets clipped).
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        win.minsize(w, h)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, root: tk.Tk) -> None:
        # Vertical-gradient surface, simulated via stacked 1px bands.
        # IMPORTANT: pack bottom bands first (side="bottom"), then top bands
        # (side="top"), so the "expand" card fills the middle correctly.
        tk.Frame(root, bg=_BG_SHADOW, height=1).pack(fill="x", side="bottom")
        tk.Frame(root, bg=_BG_BASE,   height=1).pack(fill="x", side="bottom")
        tk.Frame(root, bg=_BG_RIM,    height=1).pack(fill="x", side="top")
        tk.Frame(root, bg=_BG_SHEEN,  height=1).pack(fill="x", side="top")

        card = tk.Frame(root, bg=_BG, padx=_CARD_PADX, pady=14)
        card.pack(fill="both", expand=True)

        title_row = tk.Frame(card, bg=_BG)
        title_row.pack(fill="x", pady=(0, 10))
        tk.Label(
            title_row, text="Claude Usage Tracker",
            font=_FONT_TITLE, bg=_BG, fg=_TEXT, anchor="w",
        ).pack(side="left")
        # Version label — like the footer buttons, it stays invisible (fg == bg)
        # until the pointer is over the widget, then fades in via _tick_button_fade.
        self._lbl_ver = tk.Label(
            title_row, text=f"v{__version__}",
            font=_FONT_LBL, bg=_BG, fg=_BG, anchor="e",
        )
        self._lbl_ver.pack(side="right")

        # Peak-hour banner — packed dynamically only while the window is active.
        self._peak_banner = tk.Label(
            card, text="", font=_FONT_LBL, bg=_BG, fg=_WARN, anchor="w",
        )

        self._var_s, self._lbl_s, self._bar_s, self._session_row = self._metric_row(
            card, tr("widget.metric.session")
        )
        tk.Frame(card, bg=_BG, height=10).pack()
        self._var_w, self._lbl_w, self._bar_w, _ = self._metric_row(
            card, tr("widget.metric.weekly")
        )

        # Gradient divider (fades at the edges) — sits in its own 1px tall band
        div_band = tk.Frame(card, bg=_BG, height=1)
        div_band.pack(fill="x", pady=(12, 8))
        div_band.pack_propagate(False)
        self._div = tk.Label(div_band, bg=_BG, bd=0, highlightthickness=0)
        self._div.place(x=0, y=0, relwidth=1, height=1)

        foot = tk.Frame(card, bg=_BG)
        foot.pack(fill="x")

        # Status dot — Pillow image with glow halo
        self._dot = tk.Label(foot, bg=_BG, bd=0, highlightthickness=0)
        self._dot.pack(side="left")
        self._set_dot_color(_OK)

        self._var_ft = tk.StringVar(value=tr("widget.status.connecting"))
        self._lbl_ft = tk.Label(
            foot, textvariable=self._var_ft,
            font=_FONT_FT, bg=_BG, fg=_FOOT_C,
        )
        self._lbl_ft.pack(side="left", padx=(6, 0))

        self._build_buttons(foot)

        # Resize grip — bottom-right corner, only visible on hover indirectly
        self._grip = tk.Label(root, text="◢", cursor="size_nw_se",
                              bg=_BG, fg=_BORDER, font=("Segoe UI", 9))
        self._grip.place(relx=1.0, rely=1.0, anchor="se", x=-3, y=-3)
        self._grip.bind("<ButtonPress-1>",   self._resize_start)
        self._grip.bind("<B1-Motion>",       self._resize_move)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)

        # Drag (handler checks for buttons/grip to avoid interfering)
        root.bind("<ButtonPress-1>",   self._drag_start)
        root.bind("<B1-Motion>",       self._drag_move)
        root.bind("<ButtonRelease-1>", self._drag_end)
        root.bind("<Configure>", self._on_configure)

        ctx = tk.Menu(
            root, tearoff=0, bg="#1c1c20", fg=_TEXT,
            activebackground=_BTN_HOV, activeforeground=_TEXT,
            bd=0, relief="flat",
        )
        ctx.add_command(label=tr("widget.menu.refresh"), command=self._on_refresh)
        ctx.add_command(label=tr("widget.menu.quit"), command=self._on_quit)
        root.bind("<Button-3>", lambda e: ctx.tk_popup(e.x_root, e.y_root))

        self._poll_hover()

    def _tick_peak_banner(self) -> None:
        """Re-check the peak-hour state and re-schedule. Runs once per minute.

        Wrapped in try/finally so that an exception during the refresh cannot
        kill the tick chain (which previously also broke the hover poll on the
        same event loop and caused buttons to appear frozen).
        """
        if not self._root:
            return
        try:
            self._refresh_peak_banner()
        finally:
            if self._root:
                self._root.after(60_000, self._tick_peak_banner)

    def _refresh_peak_banner(self) -> None:
        """Apply the current peak-hour state to the banner, then refit the
        window height to all wrapped content. Idempotent."""
        if not self._root or self._peak_banner is None or self._minimized:
            return
        window = _peak_hour_window_local()
        if window is None:
            if self._peak_visible:
                self._peak_banner.pack_forget()
                self._peak_visible = False
        else:
            start, end = window
            text = tr("widget.peak_banner", start=start, end=end)
            self._peak_banner.configure(text=text)
            if not self._peak_visible and self._session_row is not None:
                self._peak_banner.pack(
                    fill="x", pady=(0, 8), before=self._session_row,
                )
                self._peak_visible = True
        self._refit_height()

    def _banner_wraplength(self, width: Optional[int] = None) -> int:
        """Pixel width the banner text may occupy before wrapping, derived from
        the current (or given target) window width minus the card padding."""
        if width is None:
            width = self._root.winfo_width() if self._root else 0
            if width <= 1:
                width = self._base_w
        # -2 fudge for the Label's own default internal padding.
        return max(40, width - 2 * _CARD_PADX - 2)

    def _set_banner_wrap(self, width: Optional[int] = None) -> None:
        """Wrap the peak banner to the current content width so its full text is
        always visible, however narrow the widget is. Left-justify the wrapped
        lines. Height is taken care of by the callers via `winfo_reqheight()`."""
        if self._peak_banner is None or not self._root:
            return
        self._peak_banner.configure(
            wraplength=self._banner_wraplength(width), justify="left"
        )

    def _footer_wraplength(self, width: Optional[int] = None) -> int:
        """Pixel width the footer status text may occupy before wrapping:
        window width minus card padding, the status dot, the dot→label gap,
        and the footer buttons (always packed, merely hover-hidden)."""
        if width is None:
            width = self._root.winfo_width() if self._root else 0
            if width <= 1:
                width = self._base_w
        used = 2 * _CARD_PADX + 6 + 2  # card padding + dot→label gap + fudge
        if self._dot is not None:
            used += self._dot.winfo_reqwidth()
        if self._btn_frame is not None:
            used += self._btn_frame.winfo_reqwidth()
        return max(40, width - used)

    def _set_footer_wrap(self, width: Optional[int] = None) -> None:
        """Wrap the footer status line (error shorts are the longest texts —
        translations can exceed the widget width) instead of clipping it."""
        if self._lbl_ft is None or not self._root:
            return
        self._lbl_ft.configure(
            wraplength=self._footer_wraplength(width), justify="left"
        )

    def _refit_height(self) -> None:
        """Resize the window so ALL wrapped content — peak banner and footer
        status line — is fully shown, keeping the bottom edge anchored — the
        top edge moves up by the content's extra height.

        The content is wrapped to the current width first, then the natural
        height WITH the wrapped content drives the extra height. Geometry is
        derived from the authoritative content-free frame (`_base_*`), not from
        live winfo, and re-asserted after the resize cascade settles (see
        `_post_refit`) so a position-revert by Windows can no longer drift the
        bottom edge downward. Handles both grow (content needs more room) and
        shrink (widget got wider / status text got shorter). A no-op refresh
        (this runs on every poll) changes nothing and schedules no callback.
        """
        if not self._root:
            return
        if self._peak_visible:
            self._set_banner_wrap()
        self._set_footer_wrap()
        self._root.update_idletasks()  # let the wrapped labels reach reqheight
        req_h = self._root.winfo_reqheight()  # natural height WITH the content
        extra = max(0, req_h - self._base_h)
        changed = extra != self._extra_h
        self._extra_h = extra
        tx, ty, tw, th = self._displayed_target()
        cur = (
            self._root.winfo_x(), self._root.winfo_y(),
            self._root.winfo_width(), self._root.winfo_height(),
        )
        if (tx, ty, tw, th) != cur:
            self._root.geometry(f"{tw}x{th}+{tx}+{ty}")
            changed = True
        # IMPORTANT: do NOT call update() here — calling it synchronously from a
        # Tk after()-callback re-enters the event loop and, on Win10, deadlocks
        # against the <Configure> + SetWindowRgn cascade this triggers. Defer
        # save + position re-assert to the next idle slot, after the geometry
        # change has been honored.
        if changed:
            self._root.after_idle(self._post_refit)

    def _displayed_target(self) -> tuple[int, int, int, int]:
        """The geometry the window SHOULD currently have, given the base frame
        and whether wrapped content is occupying extra height (bottom-anchored)."""
        if self._extra_h > 0:
            return (
                self._base_x,
                self._base_y - self._extra_h,
                self._base_w,
                self._base_h + self._extra_h,
            )
        return (self._base_x, self._base_y, self._base_w, self._base_h)

    def _reassert_geometry(self) -> None:
        """Snap the window back to its intended geometry if Windows drifted it.

        Windows can revert the position half of a combined size+move on an
        overrideredirect window while honoring the size half, leaving the
        bottom edge floating down by the banner height. Re-setting the geometry
        (size unchanged ⇒ `_on_configure` early-returns, so no cascade) fixes
        it. Skipped mid-drag/-resize so it never fights the user.
        """
        if not self._root or self._dragging or self._resizing:
            return
        tx, ty, tw, th = self._displayed_target()
        cur = (
            self._root.winfo_x(), self._root.winfo_y(),
            self._root.winfo_width(), self._root.winfo_height(),
        )
        if cur != (tx, ty, tw, th):
            self._root.geometry(f"{tw}x{th}+{tx}+{ty}")

    def _post_refit(self) -> None:
        """Re-assert geometry, persist, and re-evaluate hover after a content
        refit resized the window.

        `_apply_round_corners` is intentionally NOT called here — the size
        change already triggered `<Configure>` which re-clips the region.
        Calling it again would invalidate the window region a second time and
        force a Win10 redraw that briefly fights with the fade animation.
        """
        if not self._root:
            return
        # Correct any position-revert from the resize cascade BEFORE persisting,
        # so the saved frame can never inherit a drifted value. A second check a
        # beat later catches a late revert (position-only ⇒ no cascade).
        self._reassert_geometry()
        self._save_position()
        # Re-evaluate hover against the new geometry RIGHT NOW so the buttons
        # reflect their correct state immediately, rather than waiting up to
        # 80 ms for the next `_poll_hover` tick (which can read intermittently
        # stale winfo_root* values during the transition).
        self._eval_hover()
        self._root.after(60, self._reassert_geometry)

    def _metric_row(
        self, parent: tk.Frame, label: str
    ) -> tuple[tk.StringVar, tk.Label, tk.Label, tk.Frame]:
        row = tk.Frame(parent, bg=_BG)
        row.pack(fill="x")

        top = tk.Frame(row, bg=_BG)
        top.pack(fill="x")
        tk.Label(top, text=label, font=_FONT_LBL, bg=_BG, fg=_DIM, anchor="w").pack(side="left")

        var = tk.StringVar(value="—")
        lbl = tk.Label(top, textvariable=var, font=_FONT_PCT, bg=_BG, fg=_ALERT, anchor="e")
        lbl.pack(side="right")

        # Pillow image hosted on a Label gives us proper AA + gradients
        track = tk.Frame(row, bg=_BG, height=_BAR_H)
        track.pack(fill="x", pady=(5, 0))
        track.pack_propagate(False)
        bar = tk.Label(track, bg=_BG, bd=0, highlightthickness=0)
        bar.place(x=0, y=0, relwidth=1, relheight=1)

        return var, lbl, bar, row

    def _build_buttons(self, foot: tk.Frame) -> None:
        frame = tk.Frame(foot, bg=_BG)
        frame.pack(side="right")
        self._btn_frame = frame
        for glyph, cmd in [("⟳", self._on_refresh), ("−", self._minimize), ("×", self._on_quit)]:
            btn = tk.Button(
                frame, text=glyph, command=cmd,
                font=_FONT_BTN, bg=_BG, fg=_BG,
                activebackground=_BTN_HOV, activeforeground=_TEXT,
                relief="flat", padx=4, pady=1, cursor="hand2", width=2,
                bd=0, highlightthickness=0,
            )
            btn.pack(side="left", padx=1)
            self._buttons.append(btn)

    # ── Image-backed setters ──────────────────────────────────────────────────

    def _set_bar(self, bar: Optional[tk.Label], pct: Optional[int], color: str) -> None:
        if bar is None:
            return
        w = bar.winfo_width()
        if w <= 1:
            # widget not laid out yet — use a reasonable default
            w = _W - 36
        if pct is None:
            img = _bar_image(w, 0, _OK)
        else:
            img = _bar_image(w, pct, color)
        bar.configure(image=img)
        bar.image = img  # keep ref so Tk doesn't GC the PhotoImage

    def _set_dot_color(self, color: str) -> None:
        if self._dot is None:
            return
        img = _dot_image(color)
        self._dot.configure(image=img)
        self._dot.image = img

    def _set_divider(self) -> None:
        if not self._div:
            return
        w = self._div.winfo_width()
        if w <= 1:
            w = _W - 36
        img = _div_image(w)
        self._div.configure(image=img)
        self._div.image = img

    # ── Tooltip ───────────────────────────────────────────────────────────────

    def _show_tooltip(self) -> None:
        if self._tooltip_win or not self._last_error or not self._lbl_ft:
            return
        text = f"{self._last_error}\n\n" + tr("widget.tooltip.log", path=log_file_path())
        x = self._lbl_ft.winfo_rootx()
        y = self._lbl_ft.winfo_rooty() - 8
        t = tk.Toplevel(self._root)
        t.wm_overrideredirect(True)
        t.attributes("-topmost", True)
        lbl = tk.Label(
            t, text=text, bg="#1c1c20", fg=_TEXT,
            font=_FONT_FT, relief="flat", padx=10, pady=6,
            wraplength=340, justify="left",
            bd=0, highlightthickness=1, highlightbackground=_BORDER,
        )
        lbl.pack()
        t.update_idletasks()
        t.wm_geometry(f"+{x}+{y - t.winfo_height()}")
        self._tooltip_win = t

    def _hide_tooltip(self) -> None:
        if self._tooltip_win:
            self._tooltip_win.destroy()
            self._tooltip_win = None

    # ── Hover / button fade ───────────────────────────────────────────────────

    def _eval_hover(self) -> None:
        """Set the fade target from the current mouse vs widget bounds. Idempotent."""
        if not self._root:
            return
        x, y = self._root.winfo_pointerxy()
        rx, ry = self._root.winfo_rootx(), self._root.winfo_rooty()
        rw, rh = self._root.winfo_width(), self._root.winfo_height()
        inside = rx <= x < rx + rw and ry <= y < ry + rh
        target = 6 if inside else 0
        if target != self._btn_fade_target:
            self._btn_fade_target = target
            self._start_button_fade()

    def _poll_hover(self) -> None:
        if not self._root:
            return
        self._eval_hover()

        if self._last_error and self._lbl_ft:
            x, y = self._root.winfo_pointerxy()
            lx, ly = self._lbl_ft.winfo_rootx(), self._lbl_ft.winfo_rooty()
            lw, lh = self._lbl_ft.winfo_width(), self._lbl_ft.winfo_height()
            if lx <= x < lx + lw and ly <= y < ly + lh:
                self._show_tooltip()
            else:
                self._hide_tooltip()
        elif self._tooltip_win:
            self._hide_tooltip()

        self._root.after(80, self._poll_hover)

    def _start_button_fade(self) -> None:
        if self._fade_job:
            try:
                self._root.after_cancel(self._fade_job)
            except Exception:
                pass
            self._fade_job = None
        self._tick_button_fade()

    def _tick_button_fade(self) -> None:
        if self._btn_fade_step < self._btn_fade_target:
            self._btn_fade_step += 1
        elif self._btn_fade_step > self._btn_fade_target:
            self._btn_fade_step -= 1

        t = self._btn_fade_step / 6
        fg = _lerp_hex(_BG, _FOOT_C, t)
        bg = _lerp_hex(_BG, _BTN_BG, t)
        for btn in self._buttons:
            btn.configure(fg=fg, bg=bg)
        # Version label rides the same fade — revealed only on hover.
        if self._lbl_ver is not None:
            self._lbl_ver.configure(fg=fg)

        if self._btn_fade_step != self._btn_fade_target:
            self._fade_job = self._root.after(22, self._tick_button_fade)
        else:
            self._fade_job = None

    # ── Drag ─────────────────────────────────────────────────────────────────

    def _drag_start(self, e: tk.Event) -> None:
        if isinstance(e.widget, tk.Button) or e.widget is self._grip:
            self._dragging = False
            return
        self._dragging = True
        self._drag_x = e.x_root - self._root.winfo_x()
        self._drag_y = e.y_root - self._root.winfo_y()

    def _drag_move(self, e: tk.Event) -> None:
        if not self._dragging:
            return
        self._root.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _drag_end(self, _e=None) -> None:
        if self._dragging:
            self._sync_base_from_window()
            self._save_position()
        self._dragging = False

    # ── Resize ────────────────────────────────────────────────────────────────

    def _resize_start(self, e: tk.Event) -> None:
        self._resizing = True
        self._resize_start_x = e.x_root
        self._resize_start_y = e.y_root
        self._resize_start_w = self._root.winfo_width()
        self._resize_start_h = self._root.winfo_height()

    def _resize_move(self, e: tk.Event) -> None:
        if not self._resizing:
            return
        w = max(self._min_w, self._resize_start_w + (e.x_root - self._resize_start_x))
        # Reflow the wrapped content (banner + footer status) for the new width
        # so the height floor below grows to keep every wrapped line visible —
        # narrowing must not clip text.
        if self._peak_visible:
            self._set_banner_wrap(w)
        self._set_footer_wrap(w)
        self._root.update_idletasks()
        # winfo_reqheight is layout-natural (depends on wraplength, not the
        # not-yet-applied width), so it already reflects the new line count.
        floor = max(self._min_h, self._root.winfo_reqheight())
        h = max(floor, self._resize_start_h + (e.y_root - self._resize_start_y))
        self._root.geometry(f"{w}x{h}")

    def _resize_end(self, _e=None) -> None:
        if self._resizing:
            # Recompute the wrapped content's footprint for the FINAL width
            # before syncing the base frame, so `_sync_base_from_window` strips
            # the right amount of height (and the saved frame matches the
            # wrapped layout).
            if self._peak_visible:
                self._set_banner_wrap()
            self._set_footer_wrap()
            self._root.update_idletasks()
            req_h = self._root.winfo_reqheight()
            h = self._root.winfo_height()
            # The content's claim over the natural single-line frame …
            delta = max(0, req_h - self._min_h)
            # … is stripped from the user's height to get the base frame. If
            # the user's height leaves slack beyond the content requirement,
            # the slack stays in the base (extra = req_h - base would be ≤ 0),
            # so the next `_refit_height` cannot shrink the window they just
            # set. This keeps extra consistent with the refit formula.
            provisional_base = max(self._min_h, h - delta)
            self._extra_h = max(0, req_h - provisional_base)
            self._sync_base_from_window()
            self._save_position()
            _apply_round_corners(self._root)
        self._resizing = False

    def _sync_base_from_window(self) -> None:
        """Refresh the authoritative frame from a user-initiated move/resize.

        Reading winfo is safe here: drag and resize do not trigger the banner
        geometry cascade, so the live values are reliable. The banner's extra
        height (if showing) is stripped back out so the stored frame stays
        banner-free.
        """
        if not self._root:
            return
        x, y = self._root.winfo_x(), self._root.winfo_y()
        w, h = self._root.winfo_width(), self._root.winfo_height()
        if self._extra_h > 0:
            y += self._extra_h
            h -= self._extra_h
        self._base_x, self._base_y = x, y
        self._base_w = w
        self._base_h = max(self._min_h, h)

    def _on_configure(self, e: tk.Event) -> None:
        if e.widget is not self._root:
            return
        # SetWindowRgn (used for Win10 rounded corners) re-fires <Configure>;
        # gate redraws on a real size change to avoid an event cascade.
        size = (self._root.winfo_width(), self._root.winfo_height())
        if size == self._last_size:
            return
        self._last_size = size

        if self._last_data:
            s = self._last_data.session_percent
            w = self._find_weekly(self._last_data)
            if s is not None:
                self._set_bar(self._bar_s, s, _pct_color(s))
            if w is not None:
                self._set_bar(self._bar_w, w, _pct_color(w))
        self._set_divider()
        # Re-clip the Win10 rounded region to the new size. (Win11 DWM corners
        # are size-independent so this is a no-op there.)
        _apply_round_corners(self._root)

    # ── Position persistence ──────────────────────────────────────────────────

    def _restore_position(self, root: tk.Tk) -> None:
        root.update_idletasks()
        x = root.winfo_screenwidth() - _W - 16
        y = 16
        w, h = _W, 0
        if _POS_FILE.exists():
            try:
                pos = json.loads(_POS_FILE.read_text())
                x, y = int(pos["x"]), int(pos["y"])
                w = int(pos.get("w", _W))
                h = int(pos.get("h", 0))
                self._minimized = bool(pos.get("minimized", False))
            except Exception:
                pass
        # Saved coords may point at a monitor that no longer exists — clamp
        # into the virtual desktop so the widget is never unreachable.
        vx, vy, vw, vh = _virtual_screen_bounds()
        if vw > 0 and vh > 0:
            x = max(vx, min(x, vx + vw - 60))
            y = max(vy, min(y, vy + vh - 40))
        root.update_idletasks()
        # Never start below the natural content height — otherwise the footer
        # (buttons) is clipped from the first frame onward.
        req_h = root.winfo_reqheight()
        final_h = max(h, req_h) if h > 0 else req_h
        root.geometry(f"{w}x{final_h}+{x}+{y}")
        # Seed the authoritative banner-free frame from the restored geometry.
        self._base_x, self._base_y = x, y
        self._base_w, self._base_h = w, final_h

    def _save_position(self) -> None:
        """Persist the authoritative banner-free frame.

        Always written from `_base_*` (kept in sync on restore/drag/resize),
        never from live winfo — which is 0 while withdrawn and unreliable
        during the banner geometry cascade. This is what keeps the saved y from
        drifting downward across peak toggles and restarts.
        """
        if not self._root:
            return
        try:
            _POS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _POS_FILE.write_text(json.dumps({
                "x": self._base_x,
                "y": self._base_y,
                "w": self._base_w,
                "h": self._base_h,
                "minimized": self._minimized,
            }))
        except Exception:
            pass

    # ── State updates (always called on the Tk thread via after()) ────────────

    def _apply_data(self, data: UsageData) -> None:
        if self._var_ft is None or self._dot is None:
            return
        self._last_data = data
        self._last_error = None
        s = data.session_percent
        w = self._find_weekly(data)

        self._set_metric(self._var_s, self._lbl_s, self._bar_s, s)
        self._set_metric(self._var_w, self._lbl_w, self._bar_w, w)
        self._set_divider()

        li = next((li for li in data.limits if li.key == "five_hour"), None)
        if li is None:
            status = tr("widget.status.active")
        elif li.resets_in_seconds <= 0:
            # The 5 h window has ended; claude.ai starts a new one only with
            # the first token use, so there is no countdown to show.
            status = tr("widget.status.waiting_first_message")
        else:
            status = tr("widget.status.reset_in", countdown=li.reset_countdown)
        self._var_ft.set(status)
        self._set_dot_color(_reset_color(li))
        # Re-evaluate the peak-hour banner on every poll (manual or scheduled)
        # so a clock change is reflected within the poll interval, not the
        # 60 s banner tick.
        self._refresh_peak_banner()

    def _apply_error(self, message: str) -> None:
        if self._var_ft is None or self._dot is None:
            return
        self._last_error = message
        self._set_metric(self._var_s, self._lbl_s, self._bar_s, None)
        self._set_metric(self._var_w, self._lbl_w, self._bar_w, None)
        self._set_divider()
        # The keyword matching runs against the raw (deliberately untranslated,
        # English) exception texts from client.py / firefox_cookies.py — only
        # the short text shown to the user is localised.
        lc = message.lower()
        if "expired" in lc or "401" in lc:
            short = tr("widget.error.session_expired")
        elif "403" in lc or "cloudflare" in lc:
            short = tr("widget.error.cloudflare")
        elif "cookie" in lc or "firefox" in lc or "log in" in lc:
            short = tr("widget.error.login")
        elif "429" in lc or "rate" in lc:
            short = tr("widget.error.rate_limited")
        elif "network" in lc or "connect" in lc or "timeout" in lc:
            short = tr("widget.error.network")
        else:
            short = tr("widget.error.generic")
        self._var_ft.set(short)
        self._set_dot_color(_ALERT)
        self._refresh_peak_banner()

    def _set_metric(
        self,
        var: Optional[tk.StringVar],
        lbl: Optional[tk.Label],
        bar: Optional[tk.Label],
        pct: Optional[int],
    ) -> None:
        if var is None:
            return
        if pct is None:
            var.set("—")
            if lbl is not None:
                lbl.configure(fg=_ALERT)
            self._set_bar(bar, None, _OK)
        else:
            color = _pct_color(pct)
            var.set(f"{pct}%")
            if lbl is not None:
                lbl.configure(fg=color)
            self._set_bar(bar, pct, color)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_weekly(data: UsageData) -> Optional[int]:
        """Worst-case weekly utilization across all known weekly buckets.

        On Max plans the API exposes multiple model-specific weekly buckets
        (e.g. seven_day_opus + seven_day_sonnet). Returning just the first one
        could under-report; we surface the most-used bucket instead.
        """
        weekly_percents = [
            li.percent for li in data.limits
            if li.key in _WEEKLY_KEYS
        ]
        if weekly_percents:
            return max(weekly_percents)
        non_session = [li.percent for li in data.limits if li.key != "five_hour"]
        return max(non_session) if non_session else None

    def _minimize(self) -> None:
        """Hide the widget — restore via tray icon left-click."""
        if self._root:
            self._root.withdraw()
            self._minimized = True
            self._save_position()
