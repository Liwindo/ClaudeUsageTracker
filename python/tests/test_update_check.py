"""GitHub update check: version comparison and API branch handling."""

from unittest import mock

import claude_usage_monitor.update_check as uc
from claude_usage_monitor.update_check import _is_newer, _parse_version


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _with_response(status, payload):
    return mock.patch.object(uc.httpx, "get", return_value=FakeResp(status, payload))


def test_parse_version():
    assert _parse_version("v1.2.0") == (1, 2, 0)
    assert _parse_version("1.2") == (1, 2)
    assert _parse_version("  v2.0.1  ") == (2, 0, 1)
    assert _parse_version("garbage") == ()


def test_is_newer():
    assert _is_newer("v1.3.0", "1.2.0")
    assert _is_newer("2.0", "1.9.9")
    assert not _is_newer("v1.2.0", "1.2.0")
    assert not _is_newer("1.2", "1.2.0")  # equal after zero-padding
    assert not _is_newer("v1.1.9", "1.2.0")
    assert not _is_newer("not-a-version", "1.2.0")


def test_newer_release_returns_info():
    with _with_response(200, {"tag_name": "v99.0.0", "html_url": "https://x/v99"}):
        info = uc.check_for_update()
    assert info is not None
    assert info.latest_version == "99.0.0"
    assert info.url == "https://x/v99"


def test_same_version_returns_none():
    with _with_response(200, {"tag_name": f"v{uc.__version__}"}):
        assert uc.check_for_update() is None


def test_skipped_version_is_silenced():
    with _with_response(200, {"tag_name": "v99.0.0"}):
        assert uc.check_for_update(skip_version="99.0.0") is None
        assert uc.check_for_update(skip_version="v99.0.0") is None  # v-prefix tolerated


def test_newer_than_skipped_still_fires():
    with _with_response(200, {"tag_name": "v99.1.0"}):
        info = uc.check_for_update(skip_version="99.0.0")
    assert info is not None and info.latest_version == "99.1.0"


def test_missing_html_url_falls_back_to_releases_page():
    with _with_response(200, {"tag_name": "v99.0.0", "html_url": None}):
        info = uc.check_for_update()
    assert info is not None and info.url == uc.REPO_RELEASES_URL


def test_non_dict_body_returns_none():
    # A non-dict JSON body used to raise AttributeError on data.get() outside
    # the try block, breaking the function's never-raises contract.
    with _with_response(200, ["unexpected"]):
        assert uc.check_for_update() is None


def test_non_200_returns_none():
    with _with_response(404, {}):
        assert uc.check_for_update() is None


def test_network_error_returns_none():
    with mock.patch.object(uc.httpx, "get", side_effect=OSError("offline")):
        assert uc.check_for_update() is None


# ── Detailed result: the manual "check now" path must tell up-to-date apart
#    from a failed check, so a network error never reads as "you are current". ──


def test_evaluate_available_for_newer_tag():
    result = uc.evaluate_release(
        {"tag_name": "v99.0.0", "html_url": "https://x/v99"}, current_version="1.0.0"
    )
    assert result.status == uc.STATUS_AVAILABLE
    assert result.info is not None and result.info.latest_version == "99.0.0"


def test_evaluate_up_to_date_for_equal_or_older():
    assert uc.evaluate_release({"tag_name": "v1.0.0"}, current_version="1.0.0").status == uc.STATUS_UP_TO_DATE
    assert uc.evaluate_release({"tag_name": "v0.9.0"}, current_version="1.0.0").status == uc.STATUS_UP_TO_DATE


def test_evaluate_skipped_is_up_to_date_but_manual_still_surfaces():
    payload = {"tag_name": "v99.0.0"}
    assert uc.evaluate_release(payload, skip_version="99.0.0", current_version="1.0.0").status == uc.STATUS_UP_TO_DATE
    assert uc.evaluate_release(payload, skip_version="", current_version="1.0.0").status == uc.STATUS_AVAILABLE


def test_evaluate_non_dict_is_failed_not_up_to_date():
    # The crucial distinction: a malformed body must be FAILED, never a false
    # "up to date" that would hide a real (but unreadable) newer release.
    assert uc.evaluate_release(["unexpected"], current_version="1.0.0").status == uc.STATUS_FAILED
    assert uc.evaluate_release(None, current_version="1.0.0").status == uc.STATUS_FAILED


def test_check_detailed_non_200_is_failed():
    with _with_response(500, {}):
        assert uc.check_detailed().status == uc.STATUS_FAILED


def test_check_detailed_network_error_is_failed():
    with mock.patch.object(uc.httpx, "get", side_effect=OSError("offline")):
        assert uc.check_detailed().status == uc.STATUS_FAILED


def test_check_detailed_up_to_date():
    with _with_response(200, {"tag_name": f"v{uc.__version__}"}):
        assert uc.check_detailed().status == uc.STATUS_UP_TO_DATE
