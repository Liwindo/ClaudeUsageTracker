"""Manage the Windows autostart entry (HKCU Run key).

The registry entry is synced to the `autostart` config value on every app
start, so a moved EXE re-registers itself with the fresh path automatically.
"""

from __future__ import annotations

import logging
import sys
import winreg

logger = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "ClaudeUsageTracker"


def sync_autostart(enabled: bool) -> None:
    """Make the HKCU Run entry match *enabled*. Never raises.

    Only the packaged EXE registers itself — a python.exe/venv path would
    break as soon as the checkout moves, so source runs just log a hint and
    leave any existing EXE registration untouched.
    """
    frozen = bool(getattr(sys, "frozen", False))
    if enabled and not frozen:
        logger.warning(
            "autostart = true has no effect when running from source; "
            "build the EXE (build_exe.bat) and run that instead."
        )
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, _VALUE_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"'
                )
                logger.info("Autostart entry set: %s", sys.executable)
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                    logger.info("Autostart entry removed.")
                except FileNotFoundError:
                    pass  # was never registered — nothing to do
    except OSError as exc:
        logger.warning("Could not update autostart registry entry: %s", exc)
