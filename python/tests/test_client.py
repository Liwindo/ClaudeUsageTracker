"""Client: subscription-tier fetching must degrade, never abort the usage poll."""

from claude_usage_monitor import client as cl


class FakeResp:
    status_code = 200
    is_success = True
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    def get(self, url, headers=None):
        return FakeResp(self._payload)


def _tier(payload, org_id="org-x"):
    cl._tier_cache.clear()
    return cl._cached_tier(FakeClient(payload), org_id, "cookie=1")


def test_tier_parsed_from_capabilities():
    payload = {"account": {"memberships": [{"organization": {
        "uuid": "org-x", "capabilities": ["chat", "claude_pro"],
    }}]}}
    assert _tier(payload) == "claude_pro"


def test_unexpected_bootstrap_shape_degrades_to_unknown():
    # "account": null used to raise AttributeError past _cached_tier's narrow
    # except clause and abort the whole poll — the tier is cosmetic and must
    # degrade to "unknown" instead.
    assert _tier({"account": None}) == "unknown"
    assert _tier({"account": {"memberships": None}}) == "unknown"
