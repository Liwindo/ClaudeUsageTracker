"""Cookie-store reading: host matching, container precedence, schema fallback.

Runs against a synthetic but real SQLite `moz_cookies` table — no Firefox
install needed — so the security-relevant host filter and the container-merge
order are proven, not assumed.
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from claude_usage_monitor.firefox_cookies import (
    CookieError,
    _query_cookies,
    build_cookie_header,
    extract_org_id,
)

FUTURE = int(time.time()) + 100_000
PAST = int(time.time()) - 100


def _make_db(tmp_path, rows, with_origin_attributes=True):
    db = tmp_path / "cookies.sqlite"
    conn = sqlite3.connect(db)
    if with_origin_attributes:
        conn.execute(
            "CREATE TABLE moz_cookies "
            "(name TEXT, value TEXT, host TEXT, expiry INTEGER, originAttributes TEXT)"
        )
        conn.executemany("INSERT INTO moz_cookies VALUES (?,?,?,?,?)", rows)
    else:
        conn.execute(
            "CREATE TABLE moz_cookies (name TEXT, value TEXT, host TEXT, expiry INTEGER)"
        )
        conn.executemany("INSERT INTO moz_cookies VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def test_host_match_excludes_lookalikes_and_expired(tmp_path):
    # Host-only, leading-dot domain and a real subdomain match; lookalike
    # domains and expired rows must not.
    db = _make_db(tmp_path, [
        ("sessionKey", "S1", "claude.ai", FUTURE, ""),
        ("lastActiveOrg", "ORG", ".claude.ai", FUTURE, ""),
        ("sub", "X", "app.claude.ai", FUTURE, ""),
        ("evil", "E", "notclaude.ai", FUTURE, ""),
        ("evil2", "E2", "claude.ai.evil.com", FUTURE, ""),
        ("stale", "OLD", "claude.ai", PAST, ""),
    ])
    assert _query_cookies(db, "claude.ai") == {
        "sessionKey": "S1", "lastActiveOrg": "ORG", "sub": "X",
    }


def test_default_container_wins_over_container_session(tmp_path):
    # A Firefox container row must not shadow the regular (default-container)
    # login: the empty-originAttributes row wins the dict merge.
    db = _make_db(tmp_path, [
        ("sessionKey", "CONTAINER", "claude.ai", FUTURE, "^userContextId=2"),
        ("sessionKey", "DEFAULT", "claude.ai", FUTURE, ""),
    ])
    assert _query_cookies(db, "claude.ai")["sessionKey"] == "DEFAULT"


def test_legacy_schema_without_origin_attributes(tmp_path):
    # Very old Firefox profiles lack the originAttributes column; the query
    # falls back and still returns live cookies.
    db = _make_db(tmp_path, [
        ("sessionKey", "L1", "claude.ai", FUTURE),
        ("old", "O", "claude.ai", PAST),
    ], with_origin_attributes=False)
    assert _query_cookies(db, "claude.ai") == {"sessionKey": "L1"}


def test_extract_org_id_validates_and_normalises_uuid():
    valid = "1234abcd-12ab-34cd-56ef-1234567890ab"
    # Quoted + upper-case in the cookie → stripped, lower-cased, validated.
    assert extract_org_id({"lastActiveOrg": f'"{valid.upper()}"'}) == valid


@pytest.mark.parametrize("cookies", [
    {},                                   # missing cookie
    {"lastActiveOrg": ""},                # empty
    {"lastActiveOrg": "not-a-uuid"},      # malformed — must not reach the URL
    {"lastActiveOrg": "1234abcd-12ab-34cd-56ef-1234567890ab/extra"},
])
def test_extract_org_id_rejects_bad_values(cookies):
    with pytest.raises(CookieError):
        extract_org_id(cookies)


def test_build_cookie_header():
    assert build_cookie_header({"a": "1", "b": "2"}) == "a=1; b=2"
