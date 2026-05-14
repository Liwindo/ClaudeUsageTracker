"""HTTP client for claude.ai internal usage endpoints.

All endpoints here are REVERSE-ENGINEERED and undocumented by Anthropic.
They may break without notice if Anthropic changes their internal API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .models import UsageData

logger = logging.getLogger(__name__)

_BASE = "https://claude.ai/api"
_TIMEOUT = httpx.Timeout(15.0)

# Must match the browser that owns the Firefox session, otherwise Cloudflare
# may reject the request even with a valid cf_clearance cookie.
# REVERSE-ENGINEERED: update if you see systematic 403s after browser updates.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) "
    "Gecko/20100101 Firefox/138.0"
)

_BASE_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://claude.ai/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class ClaudeClientError(Exception):
    """Raised for recoverable API errors (network, auth, schema)."""


class SessionExpiredError(ClaudeClientError):
    """Raised when Cloudflare or claude.ai rejects the session (401/403)."""


def _make_headers(cookie_header: str) -> dict[str, str]:
    return {**_BASE_HEADERS, "Cookie": cookie_header}


def _check_response(resp: httpx.Response, endpoint: str) -> dict[str, Any]:
    """Raise a typed error for non-2xx responses, return parsed JSON."""
    if resp.status_code in (401, 403):
        raise SessionExpiredError(
            f"{endpoint} returned {resp.status_code}. "
            "Your Firefox session may have expired or Cloudflare blocked the request. "
            "Open claude.ai in Firefox to refresh the session."
        )
    if resp.status_code == 429:
        raise ClaudeClientError(
            f"{endpoint} returned 429 (rate limited). Backing off."
        )
    if not resp.is_success:
        raise ClaudeClientError(
            f"{endpoint} returned unexpected status {resp.status_code}: "
            f"{resp.text[:200]}"
        )
    try:
        return resp.json()
    except Exception as exc:
        raise ClaudeClientError(
            f"{endpoint} returned non-JSON response: {resp.text[:200]}"
        ) from exc


def fetch_subscription_tier(
    client: httpx.Client,
    org_id: str,
    cookie_header: str,
) -> str:
    """Fetch the user's subscription tier from the bootstrap endpoint.

    REVERSE-ENGINEERED: endpoint and response schema are not publicly documented.
    Returns a tier string like 'claude_pro', 'claude_max', 'claude_free', etc.
    """
    url = f"{_BASE}/bootstrap/{org_id}/app_start?statsig_hashing_algorithm=djb2"
    logger.debug("GET %s", url)
    try:
        resp = client.get(url, headers=_make_headers(cookie_header))
    except httpx.RequestError as exc:
        raise ClaudeClientError(f"Network error fetching bootstrap: {exc}") from exc

    data = _check_response(resp, "bootstrap/app_start")

    memberships: list[dict[str, Any]] = (
        data.get("account", {}).get("memberships", [])
    )
    for membership in memberships:
        org = membership.get("organization", {})
        if org.get("uuid") == org_id:
            capabilities: list[str] = org.get("capabilities", [])
            # Capabilities list contains strings like 'claude_pro', 'claude_max', …
            for cap in ("claude_max", "claude_pro", "claude_team", "claude_free"):
                if cap in capabilities:
                    return cap
            # Fallback: use rate_limit_tier if present
            tier = org.get("rate_limit_tier")
            if tier:
                return str(tier)

    logger.warning("Could not determine subscription tier from bootstrap response.")
    return "unknown"


def fetch_usage(
    client: httpx.Client,
    org_id: str,
    cookie_header: str,
    subscription_tier: str = "unknown",
) -> UsageData:
    """Fetch current usage limits from the internal /usage endpoint.

    REVERSE-ENGINEERED: endpoint and response schema are not publicly documented.
    The response contains buckets like five_hour, seven_day, seven_day_omelette, …
    with utilization.parsedValue (integer 0–100) and resets_at (ISO-8601).
    """
    url = f"{_BASE}/organizations/{org_id}/usage"
    logger.debug("GET %s", url)
    try:
        resp = client.get(url, headers=_make_headers(cookie_header))
    except httpx.RequestError as exc:
        raise ClaudeClientError(f"Network error fetching usage: {exc}") from exc

    data = _check_response(resp, "organizations/usage")
    logger.debug("Usage response: %s", data)
    return UsageData.from_api_response(data, subscription_tier=subscription_tier)


def fetch_all(
    org_id: str,
    cookie_header: str,
) -> UsageData:
    """Single entry point: fetches tier + usage and returns a UsageData.

    Creates a short-lived httpx.Client per call so the caller does not need
    to manage connection lifecycle.
    """
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=False) as client:
        try:
            tier = fetch_subscription_tier(client, org_id, cookie_header)
        except ClaudeClientError as exc:
            logger.warning("Could not fetch subscription tier: %s", exc)
            tier = "unknown"

        return fetch_usage(client, org_id, cookie_header, subscription_tier=tier)
