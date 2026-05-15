"""Configuration management.

Config file location: %APPDATA%\\claude-usage-monitor\\config.toml  (Windows)
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w


def _config_dir() -> Path:
    # Windows: %APPDATA%\claude-usage-monitor
    base = Path.home() / "AppData" / "Roaming"
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

        return cls(
            poll_interval_seconds=int(data.get("poll_interval_seconds", 30)),
            notification_thresholds=list(data.get("notification_thresholds", [80, 95])),
            firefox_profile_path=str(data.get("firefox_profile_path", "")),
            log_level=str(data.get("log_level", "WARNING")),
            _path=resolved,
        )

    def save(self) -> None:
        """Persist current config to TOML."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "poll_interval_seconds": self.poll_interval_seconds,
            "notification_thresholds": self.notification_thresholds,
            "firefox_profile_path": self.firefox_profile_path,
            "log_level": self.log_level,
        }
        with open(self._path, "wb") as f:
            tomli_w.dump(data, f)

    @property
    def firefox_profile(self) -> Path | None:
        p = self.firefox_profile_path.strip()
        return Path(p) if p else None
