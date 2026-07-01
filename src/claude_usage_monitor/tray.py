"""System tray icon with colour-coded circle based on session usage."""

from __future__ import annotations

import os
from typing import Callable

from PIL import Image, ImageDraw
import pystray

from . import __version__
from .config import log_file_path, _config_dir
from .i18n import tr
from .models import UsageData

_ICON_SIZE = 64

# NOTIFYICONDATAW.szTip is a fixed WCHAR[128] buffer (incl. NUL terminator);
# pystray passes the title through unclipped and ctypes raises ValueError for
# anything longer — which would make every poll cycle fail.
_MAX_TIP = 127


def _clip_tip(text: str) -> str:
    return text if len(text) <= _MAX_TIP else text[: _MAX_TIP - 1] + "…"

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
            # Disabled header line — shows which version is running.
            pystray.MenuItem(
                f"Claude Usage Tracker v{__version__}", None, enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.menu.show_hide"), self._open, default=True),
            pystray.MenuItem(tr("tray.menu.refresh"), self._refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.menu.view_log"), self._view_log),
            pystray.MenuItem(tr("tray.menu.open_appdata"), self._open_appdata),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.menu.quit"), self._quit),
        )
        icon = pystray.Icon(
            name="claude-usage-monitor",
            icon=_make_icon_image("grey"),
            title=_clip_tip(tr("tray.loading")),
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
        if not p.exists():
            # Touch an empty file so the click never appears to do nothing
            # (logging only writes once something is logged at the active level).
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        os.startfile(str(p))

    def _open_appdata(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d))

    def run(self) -> None:
        """Start the tray icon in its own thread (non-blocking)."""
        self._icon.run_detached()

    def stop(self) -> None:
        self._icon.stop()

    def update(self, data: UsageData) -> None:
        """Refresh icon colour and tooltip from fresh UsageData."""
        percent = data.session_percent
        if percent is None and data.limits:
            # No five_hour bucket in the response — fall back to the worst
            # bucket instead of showing a meaningless grey dot.
            percent = data.highest_percent
        self._icon.icon = _make_icon_image(_session_color(percent))
        self._icon.title = _clip_tip(data.tooltip_text())

    def set_error(self, message: str) -> None:
        """Switch to grey icon and show error in tooltip."""
        self._icon.icon = _make_icon_image("grey")
        self._icon.title = _clip_tip(tr("tray.error", message=message))
