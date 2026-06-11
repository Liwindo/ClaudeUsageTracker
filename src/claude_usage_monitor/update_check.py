"""Startup check for a newer release on GitHub.

Queries the public GitHub REST API once per app start and compares the
latest release tag against the running version. Any network/API/parsing
problem is logged and swallowed — the check must never affect normal
operation, and unauthenticated API access (60 requests/hour) is plenty
for one call per launch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from . import __version__

logger = logging.getLogger(__name__)

_REPO = "Liwindo/ClaudeUsageTracker"
_RELEASES_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
REPO_RELEASES_URL = f"https://github.com/{_REPO}/releases/latest"

_TIMEOUT = httpx.Timeout(10.0)


@dataclass
class UpdateInfo:
    latest_version: str   # tag without leading 'v', e.g. "1.3.0"
    url: str              # release page to open in the browser


def _parse_version(version: str) -> tuple[int, ...]:
    """'v1.2.0' / '1.2' → (1, 2, 0) / (1, 2). Empty tuple if unparseable."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", version.strip())
    if not m:
        return ()
    return tuple(int(part) for part in m.group(1).split("."))


def _is_newer(remote: str, local: str) -> bool:
    r, l = _parse_version(remote), _parse_version(local)
    if not r or not l:
        return False
    # Pad to equal length so '1.2' vs '1.2.0' compares equal instead of
    # shorter-tuple-is-less.
    width = max(len(r), len(l))
    return r + (0,) * (width - len(r)) > l + (0,) * (width - len(l))


def check_for_update(skip_version: str = "") -> UpdateInfo | None:
    """Return UpdateInfo if GitHub has a newer release than the running
    version, else None. Never raises.

    Args:
        skip_version: A version the user chose to skip via the update dialog.
            That exact release is silently ignored; anything newer than it
            still triggers the dialog.
    """
    try:
        resp = httpx.get(
            _RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                # GitHub's API rejects requests without a User-Agent.
                "User-Agent": "claude-usage-monitor",
            },
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.info("Update check: GitHub returned %d.", resp.status_code)
            return None
        data = resp.json()
    except Exception as exc:
        logger.info("Update check failed: %s", exc)
        return None

    tag = str(data.get("tag_name", "")).strip()
    if not tag or not _is_newer(tag, __version__):
        logger.debug(
            "Update check: %s is up to date (latest: %s).",
            __version__, tag or "?",
        )
        return None

    latest = tag.lstrip("vV")
    if skip_version and latest == skip_version.lstrip("vV"):
        logger.info("Update %s available but skipped by user preference.", latest)
        return None

    url = str(data.get("html_url") or REPO_RELEASES_URL)
    logger.info("Update available: %s (running %s).", tag, __version__)
    return UpdateInfo(latest_version=latest, url=url)
