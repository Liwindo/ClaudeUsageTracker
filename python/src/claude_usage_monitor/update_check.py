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
from urllib.parse import urlparse

import httpx

from . import __version__
from .release_notes import ReleaseNotes, select_history, select_notes

logger = logging.getLogger(__name__)

_REPO = "Liwindo/ClaudeUsageTracker"
_RELEASES_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
# The release list, for the notes of every version between the running and the
# latest one. 30 entries cover far more than the MAX_RELEASES that are shown.
_RELEASE_LIST_API = f"https://api.github.com/repos/{_REPO}/releases?per_page=30"
REPO_RELEASES_URL = f"https://github.com/{_REPO}/releases/latest"
# All releases: where "Open GitHub" leads from the release-notes view.
REPO_RELEASES_LIST_URL = f"https://github.com/{_REPO}/releases"

_TIMEOUT = httpx.Timeout(10.0)


@dataclass
class UpdateInfo:
    latest_version: str   # tag without leading 'v', e.g. "1.3.0"
    url: str              # release page to open in the browser
    # What changed since the running version; None when the notes could not be
    # loaded (the dialog then says so and points to GitHub).
    notes: ReleaseNotes | None = None


# Outcome of an update check, so the manual "check now" action can tell
# "up to date" apart from "the check failed" (a network error must never be
# reported to the user as "you are current").
STATUS_UP_TO_DATE = "up_to_date"
STATUS_AVAILABLE = "available"
STATUS_FAILED = "failed"


@dataclass
class UpdateResult:
    status: str                    # one of the STATUS_* constants
    info: UpdateInfo | None = None  # set only when status == STATUS_AVAILABLE


def _parse_version(version: str) -> tuple[int, ...]:
    """'v1.2.0' / '1.2' → (1, 2, 0) / (1, 2). Empty tuple if unparseable."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", version.strip())
    if not m:
        return ()
    return tuple(int(part) for part in m.group(1).split("."))


def _is_allowed_release_url(url: object) -> bool:
    """True only for an HTTPS URL whose host is exactly github.com — where GitHub
    release pages live. The release-page URL comes from the API's ``html_url``,
    which is untrusted under the "compromised GitHub" model: anything else —
    another host, a non-HTTPS scheme, or a ``file://``/UNC path that the OS
    "open" handler (os.startfile) would launch as a program rather than open in a
    browser — is rejected so the caller falls back to the app's own constant
    releases URL. See REQUIREMENTS.md R-net-7.
    """
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == "github.com"


def _is_newer(remote: str, local: str) -> bool:
    r, l = _parse_version(remote), _parse_version(local)
    if not r or not l:
        return False
    # Pad to equal length so '1.2' vs '1.2.0' compares equal instead of
    # shorter-tuple-is-less.
    width = max(len(r), len(l))
    return r + (0,) * (width - len(r)) > l + (0,) * (width - len(l))


def evaluate_release(
    data: object, skip_version: str = "", current_version: str = __version__
) -> UpdateResult:
    """Pure decision over an already-fetched release payload — no network, so it
    is exhaustively unit-testable. Distinguishes up-to-date from a malformed
    response (treated as a failed check) and honours skip_version.
    """
    # A non-dict body (error shape, proxy page parsed as a JSON list, …) is a
    # failed check, not "up to date".
    if not isinstance(data, dict):
        logger.info(
            "Update check: unexpected response shape (%s).", type(data).__name__
        )
        return UpdateResult(STATUS_FAILED)

    tag = str(data.get("tag_name", "")).strip()
    if not tag or not _is_newer(tag, current_version):
        logger.debug(
            "Update check: %s is up to date (latest: %s).",
            current_version, tag or "?",
        )
        return UpdateResult(STATUS_UP_TO_DATE)

    latest = tag.lstrip("vV")
    if skip_version and latest == skip_version.lstrip("vV"):
        logger.info("Update %s available but skipped by user preference.", latest)
        return UpdateResult(STATUS_UP_TO_DATE)

    # html_url is untrusted (compromised-GitHub model). Only open it if it is an
    # HTTPS github.com URL; otherwise fall back to our own constant so a hostile
    # value can never reach os.startfile via webbrowser.open. R-net-7.
    html_url = data.get("html_url")
    url = html_url if _is_allowed_release_url(html_url) else REPO_RELEASES_URL
    logger.info("Update available: %s (running %s).", tag, current_version)
    return UpdateResult(STATUS_AVAILABLE, UpdateInfo(latest_version=latest, url=url))


def _get_json(url: str) -> object:
    """GET a GitHub API URL and return the decoded JSON. Raises on any failure,
    including a non-200 status."""
    resp = httpx.get(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            # GitHub's API rejects requests without a User-Agent.
            "User-Agent": "claude-usage-monitor",
        },
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub returned {resp.status_code}")
    return resp.json()


def fetch_release_notes(
    latest_version: str, current_version: str = __version__
) -> ReleaseNotes | None:
    """The notes of every release after the running version up to the latest,
    read live from GitHub. Never raises: the notes are a convenience, so any
    failure just yields None and the update dialog still opens. R-life-6."""
    try:
        payload = _get_json(_RELEASE_LIST_API)
    except Exception as exc:
        logger.info("Release notes unavailable: %s", exc)
        return None
    notes = select_notes(payload, current_version, latest_version)
    if notes is None:
        logger.info("Release notes unavailable: no usable release body.")
    return notes


def fetch_release_history() -> ReleaseNotes | None:
    """Every published release with its notes, newest first, for the tray
    menu's "Release notes" (R-life-8). One request, made only when the user
    asks. Never raises: None makes the dialog say the notes are unavailable."""
    try:
        payload = _get_json(_RELEASE_LIST_API)
    except Exception as exc:
        logger.info("Release notes unavailable: %s", exc)
        return None
    notes = select_history(payload)
    if notes is None:
        logger.info("Release notes unavailable: no usable release body.")
    return notes


def check_detailed(skip_version: str = "") -> UpdateResult:
    """Query GitHub and report the outcome (up-to-date / available / failed).
    Never raises. Pass skip_version="" (the default) for a manual check so a
    previously-skipped release is still surfaced. When an update is available,
    its release notes are fetched as well before returning (this runs on a
    background thread), so the dialog opens complete.
    """
    try:
        data = _get_json(_RELEASES_API)
    except Exception as exc:
        logger.info("Update check failed: %s", exc)
        return UpdateResult(STATUS_FAILED)

    result = evaluate_release(data, skip_version=skip_version)
    if result.status == STATUS_AVAILABLE and result.info is not None:
        result.info.notes = fetch_release_notes(result.info.latest_version)
    return result


def check_for_update(skip_version: str = "") -> UpdateInfo | None:
    """Return UpdateInfo if GitHub has a newer release than the running
    version, else None. Never raises. Thin wrapper over check_detailed for the
    once-per-start path.

    Args:
        skip_version: A version the user chose to skip via the update dialog.
            That exact release is silently ignored; anything newer than it
            still triggers the dialog.
    """
    return check_detailed(skip_version).info
