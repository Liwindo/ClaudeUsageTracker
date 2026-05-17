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
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageTk

from .config import log_file_path
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
_BAR_H   = 6      # rounded-pill progress bar height
_DOT_PX  = 14     # status dot canvas size (incl. halo)
_RADIUS  = 10     # outer window corner radius
_POS_FILE = (
    Path.home() / "AppData" / "Roaming" / "claude-usage-monitor" / "widget_pos.json"
)

_WEEKLY_KEYS = [
    "seven_day", "seven_day_sonnet", "seven_day_opus",
    "seven_day_omelette", "seven_day_cowork",
]


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
        self._buttons: list[tk.Button] = []

        self._dragging = False
        self._drag_x = self._drag_y = 0
        self._resizing = False
        self._resize_start_x = self._resize_start_y = 0
        self._resize_start_w = self._resize_start_h = 0
        self._min_w = 200
        self._min_h = 140
        self._grip: Optional[tk.Label] = None
        self._last_size: tuple[int, int] = (0, 0)

        self._btn_fade_step = 0  # 0..6 — 0 hidden, 6 fully shown
        self._btn_fade_target = 0
        self._fade_job: Optional[str] = None

        self._last_data: Optional[UsageData] = None
        self._last_error: Optional[str] = None
        self._tooltip_win: Optional[tk.Toplevel] = None

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
        self._min_h = root.winfo_height()

        _apply_round_corners(root)

        root.deiconify()
        root.mainloop()

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)

    def restore(self) -> None:
        """Show the widget if it was hidden."""
        if self._root:
            self._root.after(0, self._root.deiconify)
            self._root.after(0, lambda: self._root.attributes("-topmost", True))

    def toggle(self) -> None:
        """Show the widget if hidden, hide it if visible."""
        if self._root:
            def _do():
                if self._root.state() == "withdrawn":
                    self._root.deiconify()
                    self._root.attributes("-topmost", True)
                else:
                    self._root.withdraw()
            self._root.after(0, _do)

    def update(self, data: UsageData) -> None:
        if self._root:
            self._root.after(0, self._apply_data, data)

    def set_error(self, message: str) -> None:
        if self._root:
            self._root.after(0, self._apply_error, message)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, root: tk.Tk) -> None:
        # Vertical-gradient surface, simulated via stacked 1px bands.
        # IMPORTANT: pack bottom bands first (side="bottom"), then top bands
        # (side="top"), so the "expand" card fills the middle correctly.
        tk.Frame(root, bg=_BG_SHADOW, height=1).pack(fill="x", side="bottom")
        tk.Frame(root, bg=_BG_BASE,   height=1).pack(fill="x", side="bottom")
        tk.Frame(root, bg=_BG_RIM,    height=1).pack(fill="x", side="top")
        tk.Frame(root, bg=_BG_SHEEN,  height=1).pack(fill="x", side="top")

        card = tk.Frame(root, bg=_BG, padx=18, pady=14)
        card.pack(fill="both", expand=True)

        tk.Label(
            card, text="Claude Usage Tracker",
            font=_FONT_TITLE, bg=_BG, fg=_TEXT, anchor="w",
        ).pack(fill="x", pady=(0, 10))

        self._var_s, self._lbl_s, self._bar_s = self._metric_row(card, "Session")
        tk.Frame(card, bg=_BG, height=10).pack()
        self._var_w, self._lbl_w, self._bar_w = self._metric_row(card, "Weekly")

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

        self._var_ft = tk.StringVar(value="connecting…")
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
        ctx.add_command(label="Refresh", command=self._on_refresh)
        ctx.add_command(label="Quit",    command=self._on_quit)
        root.bind("<Button-3>", lambda e: ctx.tk_popup(e.x_root, e.y_root))

        self._poll_hover()

    def _metric_row(
        self, parent: tk.Frame, label: str
    ) -> tuple[tk.StringVar, tk.Label, tk.Label]:
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

        return var, lbl, bar

    def _build_buttons(self, foot: tk.Frame) -> None:
        frame = tk.Frame(foot, bg=_BG)
        frame.pack(side="right")
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
        text = f"{self._last_error}\n\nLog: {log_file_path()}"
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

    def _poll_hover(self) -> None:
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

        if self._last_error and self._lbl_ft:
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
        h = max(self._min_h, self._resize_start_h + (e.y_root - self._resize_start_y))
        self._root.geometry(f"{w}x{h}")

    def _resize_end(self, _e=None) -> None:
        if self._resizing:
            self._save_position()
            _apply_round_corners(self._root)
        self._resizing = False

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
            except Exception:
                pass
        root.update_idletasks()
        if h > 0:
            root.geometry(f"{w}x{h}+{x}+{y}")
        else:
            root.geometry(f"{w}x{root.winfo_reqheight()}+{x}+{y}")

    def _save_position(self) -> None:
        if not self._root:
            return
        try:
            _POS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _POS_FILE.write_text(json.dumps({
                "x": self._root.winfo_x(),
                "y": self._root.winfo_y(),
                "w": self._root.winfo_width(),
                "h": self._root.winfo_height(),
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
        self._var_ft.set(f"reset {li.reset_countdown}" if li else "active")
        self._set_dot_color(_reset_color(li))

    def _apply_error(self, message: str) -> None:
        if self._var_ft is None or self._dot is None:
            return
        self._last_error = message
        self._set_metric(self._var_s, self._lbl_s, self._bar_s, None)
        self._set_metric(self._var_w, self._lbl_w, self._bar_w, None)
        self._set_divider()
        lc = message.lower()
        if "expired" in lc or "401" in lc:
            short = "Session expired — open claude.ai in Firefox"
        elif "403" in lc or "cloudflare" in lc:
            short = "Blocked by Cloudflare — visit claude.ai in Firefox"
        elif "cookie" in lc or "firefox" in lc or "log in" in lc:
            short = "Log in to claude.ai in Firefox first"
        elif "429" in lc or "rate" in lc:
            short = "Rate limited — waiting for next poll"
        elif "network" in lc or "connect" in lc or "timeout" in lc:
            short = "Network error — check connection"
        else:
            short = "Error — hover here for details"
        self._var_ft.set(short)
        self._set_dot_color(_ALERT)

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
