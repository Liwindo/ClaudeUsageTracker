"""Persistent always-on-top mini-widget showing Claude usage statistics."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from .config import log_file_path
from .models import UsageData

# ── Design tokens ─────────────────────────────────────────────────────────────
_BG      = "#16161a"
_TEXT    = "#e6e6ea"
_DIM     = "#88888c"
_FOOT_C  = "#747478"
_BORDER  = "#29292c"
_TRACK   = "#242428"
_BTN_BG  = "#242428"
_BTN_HOV = "#323235"
# Status colours — identical to tray.py so widget and icon stay in sync
_OK      = "#22c55e"
_YELLOW  = "#eab308"
_WARN    = "#f97316"
_ALERT   = "#ef4444"

_FONT_LBL = ("Segoe UI", 8)
_FONT_PCT = ("Consolas", 11, "bold")
_FONT_FT  = ("Consolas", 8)
_FONT_BTN = ("Segoe UI", 8)

_W = 248
_POS_FILE = (
    Path.home() / "AppData" / "Roaming" / "claude-usage-monitor" / "widget_pos.json"
)

_WEEKLY_KEYS = [
    "seven_day", "seven_day_sonnet", "seven_day_opus",
    "seven_day_omelette", "seven_day_cowork",
]


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
    if secs < 15 * 60:    # < 15 min  → green
        return _OK
    if secs < 30 * 60:    # < 30 min  → yellow
        return _YELLOW
    if secs < 90 * 60:    # < 1.5 h   → orange
        return _WARN
    return _ALERT          # ≥ 1.5 h   → red


class Widget:
    """Always-on-top glass-dark usage widget."""

    def __init__(
        self,
        on_refresh: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_refresh = on_refresh
        self._on_quit = on_quit
        self._root: Optional[tk.Tk] = None

        # StringVars and label refs set in _build_ui
        self._var_s: Optional[tk.StringVar] = None
        self._var_w: Optional[tk.StringVar] = None
        self._var_ft: Optional[tk.StringVar] = None
        self._lbl_s: Optional[tk.Label] = None
        self._lbl_w: Optional[tk.Label] = None
        self._bar_s: Optional[tk.Canvas] = None
        self._bar_w: Optional[tk.Canvas] = None
        self._dot: Optional[tk.Label] = None
        self._buttons: list[tk.Button] = []

        self._dragging = False
        self._drag_x = self._drag_y = 0
        self._resizing = False
        self._resize_start_x = self._resize_start_y = 0
        self._resize_start_w = self._resize_start_h = 0
        self._min_w = 180
        self._min_h = 120
        self._grip: Optional[tk.Label] = None
        self._btns_visible = False
        self._last_data: Optional[UsageData] = None
        self._last_error: Optional[str] = None
        self._lbl_ft: Optional[tk.Label] = None
        self._tooltip_win: Optional[tk.Toplevel] = None

    # ── Public API (thread-safe) ──────────────────────────────────────────────

    def start(self) -> None:
        """Build the UI and run the Tk event loop. Blocks the calling thread."""
        root = tk.Tk()
        self._root = root
        root.title("Claude Status")
        root.configure(bg=_BG)
        root.overrideredirect(True)   # frameless — gives stable drag coordinates
        root.attributes("-topmost", True)
        root.withdraw()

        self._build_ui(root)
        self._restore_position(root)
        root.update_idletasks()
        self._min_h = root.winfo_height()
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

    def update(self, data: UsageData) -> None:
        if self._root:
            self._root.after(0, self._apply_data, data)

    def set_error(self, message: str) -> None:
        if self._root:
            self._root.after(0, self._apply_error, message)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, root: tk.Tk) -> None:
        card = tk.Frame(
            root, bg=_BG,
            highlightbackground=_BORDER, highlightthickness=1,
            padx=14, pady=12,
        )
        card.pack(fill="both", expand=True)

        tk.Label(
            card, text="Claude Usage Tracker",
            font=("Segoe UI", 9, "bold"), bg=_BG, fg=_TEXT, anchor="w",
        ).pack(fill="x", pady=(0, 8))

        self._var_s, self._lbl_s, self._bar_s = self._metric_row(card, "Session")
        tk.Frame(card, bg=_BG, height=8).pack()
        self._var_w, self._lbl_w, self._bar_w = self._metric_row(card, "Weekly")

        tk.Frame(card, bg=_BORDER, height=1).pack(fill="x", pady=(10, 0))

        foot = tk.Frame(card, bg=_BG)
        foot.pack(fill="x", pady=(8, 0))

        self._dot = tk.Label(foot, text="●", font=("Segoe UI", 7), bg=_BG, fg=_OK)
        self._dot.pack(side="left")

        self._var_ft = tk.StringVar(value="connecting…")
        self._lbl_ft = tk.Label(
            foot, textvariable=self._var_ft,
            font=_FONT_FT, bg=_BG, fg=_FOOT_C,
        )
        self._lbl_ft.pack(side="left", padx=(4, 0))

        self._build_buttons(foot)

        # Resize grip — placed at bottom-right corner, always relative
        self._grip = tk.Label(root, text="◢", cursor="size_nw_se",
                              bg=_BG, fg=_BORDER, font=("Segoe UI", 9))
        self._grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self._grip.bind("<ButtonPress-1>",   self._resize_start)
        self._grip.bind("<B1-Motion>",       self._resize_move)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)

        # Drag (check for buttons/grip in handler to avoid interfering)
        root.bind("<ButtonPress-1>",   self._drag_start)
        root.bind("<B1-Motion>",       self._drag_move)
        root.bind("<ButtonRelease-1>", self._drag_end)

        # Redraw bars whenever the window is resized
        root.bind("<Configure>", self._on_configure)

        # Right-click context menu
        ctx = tk.Menu(
            root, tearoff=0, bg="#1e1e22", fg=_TEXT,
            activebackground=_BTN_HOV, activeforeground=_TEXT,
        )
        ctx.add_command(label="Refresh", command=self._on_refresh)
        ctx.add_command(label="Quit",    command=self._on_quit)
        root.bind("<Button-3>", lambda e: ctx.tk_popup(e.x_root, e.y_root))

        # Hover polling (100 ms — simpler and more reliable than Enter/Leave bindings)
        self._poll_hover()

    def _metric_row(
        self, parent: tk.Frame, label: str
    ) -> tuple[tk.StringVar, tk.Label, tk.Canvas]:
        row = tk.Frame(parent, bg=_BG)
        row.pack(fill="x")

        top = tk.Frame(row, bg=_BG)
        top.pack(fill="x")
        tk.Label(top, text=label, font=_FONT_LBL, bg=_BG, fg=_DIM, anchor="w").pack(side="left")

        var = tk.StringVar(value="—")
        lbl = tk.Label(top, textvariable=var, font=_FONT_PCT, bg=_BG, fg=_ALERT, anchor="e")
        lbl.pack(side="right")

        track = tk.Frame(row, bg=_TRACK, height=3)
        track.pack(fill="x", pady=(4, 0))
        track.pack_propagate(False)
        bar = tk.Canvas(track, bg=_TRACK, height=3, highlightthickness=0)
        bar.pack(fill="both", expand=True)

        return var, lbl, bar

    def _build_buttons(self, foot: tk.Frame) -> None:
        frame = tk.Frame(foot, bg=_BG)
        frame.pack(side="right")

        for glyph, cmd in [("⟳", self._on_refresh), ("−", self._minimize), ("×", self._on_quit)]:
            btn = tk.Button(
                frame, text=glyph, command=cmd,
                font=_FONT_BTN,
                bg=_BG, fg=_BG,          # invisible until hover
                activebackground=_BTN_HOV, activeforeground=_TEXT,
                relief="flat", padx=3, pady=1, cursor="hand2", width=2,
            )
            btn.pack(side="left", padx=1)
            self._buttons.append(btn)

    # ── Tooltip (poll-based — <Enter>/<Leave> unreliable on overrideredirect) ──

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
            t, text=text, bg="#1e1e22", fg=_TEXT,
            font=_FONT_FT, relief="flat", padx=8, pady=5,
            wraplength=340, justify="left",
        )
        lbl.pack()
        t.update_idletasks()
        t.wm_geometry(f"+{x}+{y - t.winfo_height()}")
        self._tooltip_win = t

    def _hide_tooltip(self) -> None:
        if self._tooltip_win:
            self._tooltip_win.destroy()
            self._tooltip_win = None

    # ── Hover (polled) ────────────────────────────────────────────────────────

    def _poll_hover(self) -> None:
        if not self._root:
            return
        x, y = self._root.winfo_pointerxy()
        rx = self._root.winfo_rootx()
        ry = self._root.winfo_rooty()
        rw = self._root.winfo_width()
        rh = self._root.winfo_height()
        inside = rx <= x < rx + rw and ry <= y < ry + rh

        if inside and not self._btns_visible:
            self._btns_visible = True
            for btn in self._buttons:
                btn.configure(fg=_FOOT_C, bg=_BTN_BG)
        elif not inside and self._btns_visible:
            self._btns_visible = False
            for btn in self._buttons:
                btn.configure(fg=_BG, bg=_BG)

        # Tooltip: show when mouse is over the footer label and there's an error
        if self._last_error and self._lbl_ft:
            lx = self._lbl_ft.winfo_rootx()
            ly = self._lbl_ft.winfo_rooty()
            lw = self._lbl_ft.winfo_width()
            lh = self._lbl_ft.winfo_height()
            over_label = lx <= x < lx + lw and ly <= y < ly + lh
            if over_label:
                self._show_tooltip()
            else:
                self._hide_tooltip()
        elif self._tooltip_win:
            self._hide_tooltip()

        self._root.after(100, self._poll_hover)

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
        self._resizing = False

    def _on_configure(self, e: tk.Event) -> None:
        if e.widget is not self._root:
            return
        # Redraw bars so the fill width matches the new window width
        if self._last_data:
            s = self._last_data.session_percent
            w = self._find_weekly(self._last_data)
            if s is not None and self._bar_s:
                self._draw_bar(self._bar_s, s, _pct_color(s))
            if w is not None and self._bar_w:
                self._draw_bar(self._bar_w, w, _pct_color(w))

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
        self._last_data = data
        self._last_error = None
        s = data.session_percent
        w = self._find_weekly(data)

        self._set_metric(self._var_s, self._lbl_s, self._bar_s, s)
        self._set_metric(self._var_w, self._lbl_w, self._bar_w, w)

        li = next((li for li in data.limits if li.key == "five_hour"), None)
        self._var_ft.set(f"reset {li.reset_countdown}" if li else "active")

        # Dot color: closer to reset = greener (limit refreshes soon = good)
        self._dot.configure(fg=_reset_color(li))

    def _apply_error(self, message: str) -> None:
        self._last_error = message
        self._set_metric(self._var_s, self._lbl_s, self._bar_s, None)
        self._set_metric(self._var_w, self._lbl_w, self._bar_w, None)
        lc = message.lower()
        if "expired" in lc or "401" in lc:
            short = "Session expired — open claude.ai in Firefox"
        elif "403" in lc or "cloudflare" in lc:
            short = "Blocked by Cloudflare — visit claude.ai in Firefox"
        elif "cookie" in lc or "firefox" in lc:
            short = "Log in to claude.ai in Firefox first"
        elif "429" in lc or "rate" in lc:
            short = "Rate limited — waiting for next poll"
        elif "network" in lc or "connect" in lc or "timeout" in lc:
            short = "Network error — check connection"
        else:
            short = "Error — hover here for details"
        self._var_ft.set(short)
        self._dot.configure(fg=_ALERT)

    def _set_metric(
        self,
        var: Optional[tk.StringVar],
        lbl: Optional[tk.Label],
        bar: Optional[tk.Canvas],
        pct: Optional[int],
    ) -> None:
        if var is None:
            return
        if pct is None:
            var.set("—")
            lbl.configure(fg=_ALERT)
            bar.delete("all")
        else:
            color = _pct_color(pct)
            var.set(f"{pct}%")
            lbl.configure(fg=color)
            self._draw_bar(bar, pct, color)

    def _draw_bar(self, bar: tk.Canvas, pct: int, color: str) -> None:
        bar.update_idletasks()
        w = bar.winfo_width() or (_W - 30)
        bar.delete("all")
        fill_w = max(1, int(w * min(pct, 100) / 100))
        bar.create_rectangle(0, 0, fill_w, 3, fill=color, outline="")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_weekly(data: UsageData) -> Optional[int]:
        for key in _WEEKLY_KEYS:
            for li in data.limits:
                if li.key == key:
                    return li.percent
        # fallback: first non-session limit
        for li in data.limits:
            if li.key != "five_hour":
                return li.percent
        return None

    def _minimize(self) -> None:
        """Hide the widget — restore via tray icon left-click."""
        if self._root:
            self._root.withdraw()
