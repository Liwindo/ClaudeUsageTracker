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


def test_non_200_returns_none():
    with _with_response(404, {}):
        assert uc.check_for_update() is None


def test_network_error_returns_none():
    with mock.patch.object(uc.httpx, "get", side_effect=OSError("offline")):
        assert uc.check_for_update() is None
