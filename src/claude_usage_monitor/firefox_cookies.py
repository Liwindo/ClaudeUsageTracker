"""Read claude.ai session cookies directly from Firefox's cookie store.

Firefox stores cookies unencrypted in an SQLite database at:
  %APPDATA%\\Mozilla\\Firefox\\Profiles\\<profile>\\cookies.sqlite

The database is opened read-only via SQLite URI (mode=ro). Firefox's WAL
journal mode allows concurrent reads without needing a file copy.
"""

from __future__ import annotations

import configparser
import re
import sqlite3
import time
from pathlib import Path

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


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


def _query_cookies(db_path: Path, host: str) -> dict[str, str]:
    """Read all non-expired cookies for *host* directly without copying.

    Matches the exact host and any subdomain (host-only `claude.ai` and
    domain cookies stored as `.claude.ai` / `.sub.claude.ai`). An earlier
    `LIKE '%host%'` pattern would have matched unrelated domains like
    `notclaude.ai` or `evil-claude.ai.example.com`.
    """
    now_seconds = int(time.time())
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                """
                SELECT name, value
                FROM   moz_cookies
                WHERE  (host = ? OR host = ? OR host LIKE ?)
                  AND  expiry > ?
                """,
                (host, f".{host}", f"%.{host}", now_seconds),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise FirefoxCookieError(
            f"Could not read Firefox cookie database: {exc}"
        ) from exc


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
    db_path = resolved / "cookies.sqlite"
    if not db_path.exists():
        raise FirefoxCookieError(
            f"cookies.sqlite not found in Firefox profile: {resolved}\n"
            "Make sure Firefox has been launched at least once."
        )

    cookies = _query_cookies(db_path, _CLAUDE_HOST)
    if not cookies:
        raise FirefoxCookieError(
            "No claude.ai cookies found in Firefox. "
            "Please log in to claude.ai in Firefox first."
        )
    return cookies


class CookieError(Exception):
    """Browser-agnostic cookie error used for org-ID failures."""


def extract_org_id(cookies: dict[str, str]) -> str:
    """Pull the organisation UUID from the lastActiveOrg cookie.

    The value is validated as a canonical UUID before being returned so it
    cannot smuggle extra path segments into the API URL.
    """
    org_id = cookies.get("lastActiveOrg", "").strip('"').lower()
    if not org_id:
        raise CookieError(
            "lastActiveOrg cookie not found. "
            "Visit claude.ai in your browser to set an active organisation."
        )
    if not _UUID_RE.match(org_id):
        raise CookieError(
            "lastActiveOrg cookie is not a valid UUID. "
            "Open claude.ai in Firefox to refresh the session."
        )
    return org_id


def build_cookie_header(cookies: dict[str, str]) -> str:
    """Serialise the cookie dict to an HTTP Cookie header string."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())
