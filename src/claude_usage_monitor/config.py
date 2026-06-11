"""Configuration management.

Config file location: %APPDATA%\\claude-usage-monitor\\config.toml  (Windows)
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

logger = logging.getLogger(__name__)


def _config_dir() -> Path:
    # Windows: %APPDATA%\claude-usage-monitor. Respect the env var — profiles
    # redirected via group policy don't live under Path.home().
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "claude-usage-monitor"


def _default_config_path() -> Path:
    return _config_dir() / "config.toml"


def log_file_path() -> Path:
    return _config_dir() / "app.log"


@dataclass
class Config:
    poll_interval_seconds: int = 30
    notification_thresholds: list[int] = field(default_factory=lambda: [80, 95])
    firefox_profile_path: str = ""
    log_level: str = "WARNING"
    # Override the User-Agent sent to claude.ai (empty = built-in default).
    # Lets users match their installed Firefox version without a rebuild if
    # Cloudflare starts blocking after a browser update.
    user_agent: str = ""
    # Check GitHub once per app start for a newer release and offer to open
    # the release page.
    update_check: bool = True
    # Release version the user chose to skip via the update dialog's
    # "Skip version" button. Set automatically; cleared by a newer release.
    skip_update_version: str = ""
    # Start with Windows (HKCU Run key). Only effective for the packaged EXE;
    # the registry entry is synced to this value on every app start.
    autostart: bool = False

    # Internal: not written to TOML
    _path: Path = field(default_factory=_default_config_path, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load config from TOML file, or return defaults if file absent."""
        resolved = path or _default_config_path()
        if not resolved.exists():
            cfg = cls(_path=resolved)
            cfg.save()          # write defaults on first run
            return cfg

        with open(resolved, "rb") as f:
            data: dict[str, Any] = tomllib.load(f)

        # Floor at 10 s: 0 or a negative value would make Event.wait() return
        # immediately and turn the poll loop into a busy loop against claude.ai.
        interval = max(10, int(data.get("poll_interval_seconds", 30)))
        # Coerce to int here — string thresholds from a hand-edited TOML would
        # otherwise raise TypeError on every threshold comparison at poll time.
        thresholds = [int(t) for t in data.get("notification_thresholds", [80, 95])]

        cfg = cls(
            poll_interval_seconds=interval,
            notification_thresholds=thresholds,
            firefox_profile_path=str(data.get("firefox_profile_path", "")),
            log_level=str(data.get("log_level", "WARNING")),
            user_agent=str(data.get("user_agent", "")),
            update_check=bool(data.get("update_check", True)),
            skip_update_version=str(data.get("skip_update_version", "")),
            autostart=bool(data.get("autostart", False)),
            _path=resolved,
        )

        # Migrate config files from older versions: if any option is missing
        # (i.e. it was added in a later release), rewrite the file with the
        # full key set so new options show up with their default values and
        # the user only ever has to change a value, never add a key.
        # Best-effort — a read-only file must not prevent startup.
        missing = set(cfg._to_dict()) - set(data)
        if missing:
            try:
                cfg.save()
                logger.info(
                    "Config migrated: added missing option(s) %s with defaults.",
                    ", ".join(sorted(missing)),
                )
            except OSError as exc:
                logger.warning("Could not migrate config file: %s", exc)

        return cfg

    def _to_dict(self) -> dict[str, Any]:
        """All persistable options. save() writes exactly this key set, and
        load() uses it to detect options missing from older config files."""
        return {
            "poll_interval_seconds": self.poll_interval_seconds,
            "notification_thresholds": self.notification_thresholds,
            "firefox_profile_path": self.firefox_profile_path,
            "log_level": self.log_level,
            "user_agent": self.user_agent,
            "update_check": self.update_check,
            "skip_update_version": self.skip_update_version,
            "autostart": self.autostart,
        }

    def save(self) -> None:
        """Persist current config to TOML."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            tomli_w.dump(self._to_dict(), f)

    @property
    def firefox_profile(self) -> Path | None:
        p = self.firefox_profile_path.strip()
        return Path(p) if p else None
