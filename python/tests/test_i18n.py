"""i18n: catalog completeness, placeholder consistency, and robust fallbacks.

The completeness checks are what makes "adding a language = one file" safe:
a catalog with a missing key, an extra key, or a mistyped placeholder fails
here instead of degrading silently at runtime.
"""

from __future__ import annotations

import string

import pytest

from claude_usage_monitor import i18n
from claude_usage_monitor.i18n import CATALOGS, tr


@pytest.fixture(autouse=True)
def _reset_language():
    # i18n state is module-global; never leak a language into other tests.
    yield
    i18n.init("en")


def _placeholders(template: str) -> set[str]:
    return {
        field for _, field, _, _ in string.Formatter().parse(template)
        if field is not None
    }


def test_expected_languages_present():
    assert set(CATALOGS) == {"en", "de", "es", "fr", "it", "nl", "pl", "pt", "ru"}


@pytest.mark.parametrize("lang", sorted(CATALOGS))
def test_catalog_matches_english_key_set(lang):
    assert set(CATALOGS[lang]) == set(CATALOGS["en"]), (
        f"{lang} catalog keys diverge from en"
    )


@pytest.mark.parametrize("lang", sorted(CATALOGS))
def test_placeholders_match_english(lang):
    for key, template in CATALOGS[lang].items():
        assert _placeholders(template) == _placeholders(CATALOGS["en"][key]), (
            f"{lang}:{key} placeholders diverge from en"
        )


@pytest.mark.parametrize("lang", sorted(CATALOGS))
def test_no_empty_translations(lang):
    for key, template in CATALOGS[lang].items():
        assert template.strip(), f"{lang}:{key} is empty"


def test_init_switches_language_and_tr_translates():
    assert i18n.init("de") == "de"
    assert i18n.active_language() == "de"
    assert tr("tray.menu.quit") == "Beenden"
    assert tr("tray.error", message="x") == "Fehler: x"


def test_init_is_case_insensitive_and_trims():
    assert i18n.init("  DE ") == "de"


def test_unsupported_language_falls_back_to_english():
    assert i18n.init("klingon") == "en"
    assert tr("tray.menu.quit") == "Quit"


def test_auto_resolves_to_a_supported_language():
    assert i18n.init("auto") in CATALOGS
    assert i18n.init("") in CATALOGS


def test_unknown_key_returns_key():
    assert tr("no.such.key") == "no.such.key"


def test_missing_key_falls_back_to_english_catalog(monkeypatch):
    monkeypatch.setitem(i18n.CATALOGS, "de", {})  # simulate an outdated catalog
    i18n.init("de")
    assert tr("tray.menu.quit") == "Quit"


def test_bad_placeholder_in_translation_falls_back(monkeypatch):
    broken = dict(CATALOGS["de"])
    broken["tray.error"] = "Fehler: {wrong_name}"
    monkeypatch.setitem(i18n.CATALOGS, "de", broken)
    i18n.init("de")
    # Translator typo must not raise — the English template steps in.
    assert tr("tray.error", message="x") == "Error: x"


def test_langid_mapping():
    assert i18n._code_from_langid(0x0407) == "de"   # de-DE
    assert i18n._code_from_langid(0x0C07) == "de"   # de-AT
    assert i18n._code_from_langid(0x0409) == "en"   # en-US
    assert i18n._code_from_langid(0x0416) == "pt"   # pt-BR
    assert i18n._code_from_langid(0x0411) is None   # ja-JP — not shipped


def test_detect_system_language_returns_supported_code():
    assert i18n.detect_system_language() in CATALOGS


def test_german_end_to_end_labels():
    from claude_usage_monitor.models import LimitInfo

    i18n.init("de")
    info = LimitInfo.from_api("five_hour", {"utilization": 13.0, "resets_at": None})
    assert info.label == "Sitzung (5 h)"
    unknown = LimitInfo.from_api("brand_new_bucket", {"utilization": 1, "resets_at": None})
    assert unknown.label == "Unbekannt (brand_new_bucket)"
