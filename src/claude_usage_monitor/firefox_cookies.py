"""Read claude.ai session cookies directly from Firefox's cookie store.

Firefox stores cookies unencrypted in an SQLite database at:
  %APPDATA%\\Mozilla\\Firefox\\Profiles\\<profile>\\cookies.sqlite

We copy the file before reading to avoid issues with Firefox's file lock.
No credentials are stored; cookies are read fresh before every poll cycle.
"""

from __future__ import annotations

import configparser
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path


_FIREFOX_APPDATA = Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox"
_CLAUDE_HOST = "claude.ai"


class FirefoxCookieError(Exception):
    """Raised when cookies cannot be read from Firefox's profile."""


def _find_default_profile() -> Path:
    """Locate the default Firefox profile directory on Windows."""
    profiles_ini = _FIREFOX_APPDATA / "profiles.ini"
    if not profiles_ini.exists():
        raise FirefoxCookieError(
            f"Firefox profiles.ini not found at {profiles_ini}. "
            "Is Firefox installed?"
        )

    cfg = configparser.ConfigParser()
    cfg.read(profiles_ini, encoding="utf-8")

    # Prefer the profile marked as Default=1 in an [Install…] section,
    # then fall back to the first profile with Default=1, then any profile.
    install_default: str | None = None
    for section in cfg.sections():
        if section.startswith("Install"):
            install_default = cfg[section].get("Default")
            break

    if install_default:
        candidate = _FIREFOX_APPDATA / install_default
        if candidate.is_dir():
            return candidate

    # Fallback: scan [Profile*] sections
    for section in cfg.sections():
        if not section.startswith("Profile"):
            continue
        profile_cfg = cfg[section]
        relative = profile_cfg.get("IsRelative", "1") == "1"
        path_str = profile_cfg.get("Path", "")
        profile_path = (
            _FIREFOX_APPDATA / path_str if relative else Path(path_str)
        )
        if profile_path.is_dir():
            return profile_path

    raise FirefoxCookieError("No usable Firefox profile directory found.")


def _copy_cookies_db(profile_dir: Path) -> Path:
    """Copy cookies.sqlite to a temp file and return its path.

    Firefox keeps a write-lock on the live DB; reading the copy avoids
    'database is locked' errors without touching the original.
    """
    src = profile_dir / "cookies.sqlite"
    if not src.exists():
        raise FirefoxCookieError(
            f"cookies.sqlite not found in Firefox profile: {profile_dir}\n"
            "Make sure Firefox has been launched at least once."
        )

    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    shutil.copy2(src, tmp.name)
    return Path(tmp.name)


def _query_cookies(db_path: Path, host: str) -> dict[str, str]:
    """Return all non-expired cookies for *host* as {name: value}."""
    now_seconds = int(time.time())
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            """
            SELECT name, value
            FROM   moz_cookies
            WHERE  host LIKE ?
              AND  expiry > ?
            """,
            (f"%{host}%", now_seconds),
        )
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def get_claude_cookies(profile_dir: Path | None = None) -> dict[str, str]:
    """Return current claude.ai cookies from Firefox.

    Args:
        profile_dir: Override the auto-detected Firefox profile directory.

    Returns:
        Dict of cookie name → value for all non-expired claude.ai cookies.

    Raises:
        FirefoxCookieError: If the profile or cookie DB cannot be found/read.
    """
    resolved = profile_dir or _find_default_profile()
    tmp_db = _copy_cookies_db(resolved)
    try:
        cookies = _query_cookies(tmp_db, _CLAUDE_HOST)
    finally:
        tmp_db.unlink(missing_ok=True)

    if not cookies:
        raise FirefoxCookieError(
            "No claude.ai cookies found in Firefox. "
            "Please log in to claude.ai in Firefox first."
        )
    return cookies


def extract_org_id(cookies: dict[str, str]) -> str:
    """Pull the organisation UUID from the lastActiveOrg cookie."""
    org_id = cookies.get("lastActiveOrg", "").strip('"')
    if not org_id:
        raise FirefoxCookieError(
            "lastActiveOrg cookie not found. "
            "Visit claude.ai in Firefox to set an active organisation."
        )
    return org_id


def build_cookie_header(cookies: dict[str, str]) -> str:
    """Serialise the cookie dict to an HTTP Cookie header string."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())
