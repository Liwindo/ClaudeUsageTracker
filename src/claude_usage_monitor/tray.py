"""System tray icon with colour-coded circle based on session usage."""

from __future__ import annotations

import os
from typing import Callable

from PIL import Image, ImageDraw
import pystray

from .config import log_file_path
from .models import UsageData

_ICON_SIZE = 64

_COLORS = {
    "green":  "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "red":    "#ef4444",
    "grey":   "#6b7280",
}


def _session_color(percent: int | None) -> str:
    if percent is None:
        return "grey"
    if percent >= 85:
        return "red"
    if percent >= 60:
        return "orange"
    if percent >= 40:
        return "yellow"
    return "green"


def _make_icon_image(color_name: str) -> Image.Image:
    """Filled circle on transparent background."""
    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, _ICON_SIZE - margin, _ICON_SIZE - margin],
        fill=_COLORS.get(color_name, _COLORS["grey"]),
    )
    return img


class TrayIcon:
    """Wrapper around pystray.Icon.

    Args:
        on_click_open:  called when the user clicks the icon (open popup).
        on_click_refresh: called when the user chooses "Refresh now".
        on_quit: called when the user chooses "Quit".
    """

    def __init__(
        self,
        on_click_open: Callable[[], None],
        on_click_refresh: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_click_open = on_click_open
        self._on_click_refresh = on_click_refresh
        self._on_quit = on_quit
        self._icon = self._build_icon()

    def _build_icon(self) -> pystray.Icon:
        menu = pystray.Menu(
            pystray.MenuItem("Show widget", self._open, default=True),
            pystray.MenuItem("Refresh now", self._refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("View log file", self._view_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        icon = pystray.Icon(
            name="claude-usage-monitor",
            icon=_make_icon_image("grey"),
            title="Claude Usage Monitor — loading…",
            menu=menu,
        )
        return icon

    # pystray callbacks run on the pystray internal thread
    def _open(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._on_click_open()

    def _refresh(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._on_click_refresh()

    def _quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._on_quit()

    def _view_log(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        p = log_file_path()
        if p.exists():
            os.startfile(str(p))

    def run(self) -> None:
        """Start the tray icon in its own thread (non-blocking)."""
        self._icon.run_detached()

    def stop(self) -> None:
        self._icon.stop()

    def update(self, data: UsageData) -> None:
        """Refresh icon colour and tooltip from fresh UsageData."""
        self._icon.icon = _make_icon_image(_session_color(data.session_percent))
        self._icon.title = data.tooltip_text()

    def set_error(self, message: str) -> None:
        """Switch to grey icon and show error in tooltip."""
        self._icon.icon = _make_icon_image("grey")
        short = message[:120] + "…" if len(message) > 120 else message
        self._icon.title = f"Error: {short}"
