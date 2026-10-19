"""Release notes in the update dialog (REQUIREMENTS.md R-life-6 / R-net-8).

The parser cases live in fixtures/release_notes_cases.json, which the C# suite
runs as well, so both variants turn a GitHub release body into the same text.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

import claude_usage_monitor.update_check as uc
from claude_usage_monitor import release_notes as rn

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "release_notes_cases.json").read_text(encoding="utf-8")
)


def _spans(spans) -> list[list]:
    return [[s.text, s.bold] for s in spans]


def _blocks(blocks) -> list[dict]:
    return [{"kind": b.kind, "level": b.level, "spans": _spans(b.spans)} for b in blocks]


@pytest.mark.parametrize("case", CASES["sanitize"], ids=lambda c: c["name"])
def test_sanitize_cases(case):
    assert rn.sanitize(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["inline"], ids=lambda c: c["name"])
def test_inline_cases(case):
    assert _spans(rn.parse_inline(case["input"])) == case["expected"]


@pytest.mark.parametrize("case", CASES["blocks"], ids=lambda c: c["name"])
def test_block_cases(case):
    assert _blocks(rn.parse_body(case["input"])) == case["expected"]


@pytest.mark.parametrize("case", CASES["select"], ids=lambda c: c["name"])
def test_select_cases(case):
    notes = rn.select_notes(
        case["releases"], case["current"], case["latest"],
        max_releases=case.get("max_releases", rn.MAX_RELEASES),
    )
    if case["expected_versions"] is None:
        assert notes is None
        return
    assert notes is not None
    assert [v.version for v in notes.versions] == case["expected_versions"]
    assert notes.truncated is case["truncated"]
    if "first_block" in case:
        assert _spans(notes.versions[0].blocks[0].spans) == case["first_block"]


@pytest.mark.parametrize("case", CASES["history"], ids=lambda c: c["name"])
def test_history_cases(case):
    notes = rn.select_history(case["releases"])
    if case["expected_versions"] is None:
        assert notes is None
        return
    assert notes is not None
    assert [v.version for v in notes.versions] == case["expected_versions"]
    assert notes.truncated is case["truncated"]
    if "first_block" in case:
        assert _spans(notes.versions[0].blocks[0].spans) == case["first_block"]


def test_real_releases_parse_as_expected():
    """The actual GitHub release bodies (BOM in v1.3.0, CRLF and LF bodies, the
    'Full Changelog' footer, nested bullets) parse to the recorded result."""
    real = CASES["real"]
    notes = rn.select_notes(real["releases"], real["current"], real["latest"], max_releases=100)
    assert notes is not None
    got = [{"version": v.version, "blocks": _blocks(v.blocks)} for v in notes.versions]
    assert got == real["expected"]


def test_real_releases_leave_no_markdown_behind():
    real = CASES["real"]
    notes = rn.select_notes(real["releases"], real["current"], real["latest"], max_releases=100)
    assert notes is not None
    texts = [s.text for v in notes.versions for b in v.blocks for s in b.spans]
    for bad in ("**", "](", "﻿", "\r", "Full Changelog", "###"):
        assert not any(bad in t for t in texts), bad


def test_lone_surrogate_is_dropped():
    # json.loads turns an escaped lone surrogate into a real one; Tk would choke.
    assert rn.sanitize(json.loads('"a\\ud83db"')) == "ab"


def test_long_block_is_clipped():
    blocks = rn.parse_body("- " + "a" * (rn.MAX_BLOCK_CHARS + 100))
    text = blocks[0].spans[0].text
    assert text == "a" * rn.MAX_BLOCK_CHARS + "…"


def test_block_budget_truncates_over_all_versions():
    body = "\n".join(f"- item {i}" for i in range(100))
    releases = [{"tag_name": "v1.2.0", "body": body}, {"tag_name": "v1.1.0", "body": body}]
    notes = rn.select_notes(releases, "1.0.0", "1.2.0")
    assert notes is not None and notes.truncated
    assert sum(len(v.blocks) for v in notes.versions) == rn.MAX_BLOCKS


# ── Fetching (network mocked) ────────────────────────────────────────────────

class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _route(latest, listing):
    """httpx.get stand-in answering /releases/latest and the release list."""
    def get(url, **kwargs):
        if url == uc._RELEASES_API:
            return latest
        if url == uc._RELEASE_LIST_API:
            if isinstance(listing, Exception):
                raise listing
            return listing
        raise AssertionError(f"unexpected request: {url}")
    return mock.patch.object(uc.httpx, "get", side_effect=get)


_LATEST = FakeResp(200, {"tag_name": "v99.1.0", "html_url": "https://github.com/x/releases/tag/v99.1.0"})


def test_available_update_carries_notes_since_running_version():
    listing = FakeResp(200, [
        {"tag_name": "v99.1.0", "body": "### ✨ New\n\n- **Shiny** thing"},
        {"tag_name": "v99.0.0", "body": "- older fix"},
        {"tag_name": f"v{uc.__version__}", "body": "- the running one"},
    ])
    with _route(_LATEST, listing):
        result = uc.check_detailed()
    assert result.status == uc.STATUS_AVAILABLE
    notes = result.info.notes
    assert [v.version for v in notes.versions] == ["99.1.0", "99.0.0"]
    assert _spans(notes.versions[0].blocks[1].spans) == [["Shiny", True], [" thing", False]]


@pytest.mark.parametrize("listing", [
    FakeResp(403, {"message": "rate limited"}),
    FakeResp(200, {"message": "not a list"}),
    RuntimeError("network down"),
])
def test_notes_failure_still_reports_the_update(listing):
    with _route(_LATEST, listing):
        result = uc.check_detailed()
    assert result.status == uc.STATUS_AVAILABLE
    assert result.info.latest_version == "99.1.0"
    assert result.info.notes is None


def test_no_notes_request_when_up_to_date():
    latest = FakeResp(200, {"tag_name": f"v{uc.__version__}"})
    with _route(latest, AssertionError("must not fetch notes")) as get:
        result = uc.check_detailed()
    assert result.status == uc.STATUS_UP_TO_DATE
    assert get.call_count == 1
