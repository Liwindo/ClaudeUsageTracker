"""Runtime translation of user-visible strings.

One catalog per language lives in the ``locales`` package; adding a language
means adding one file there and registering it in ``locales/__init__.py``.
Log messages and exception texts deliberately stay English — logs must remain
readable for support, and the widget's error classifier matches on the English
exception wording.

The active language defaults to English until ``init()`` is called, so tests
and library use are deterministic regardless of the host system's locale.
"""

from __future__ import annotations

import ctypes
import logging
import os

from .locales import CATALOGS

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"

_active_language = DEFAULT_LANGUAGE

# Primary-language part of a Windows LANGID (low 10 bits) → catalog code.
# Constants from winnt.h (LANG_GERMAN = 0x07, …); stable since Windows 2000.
_LANGID_PRIMARY: dict[int, str] = {
    0x07: "de",
    0x09: "en",
    0x0A: "es",
    0x0C: "fr",
    0x10: "it",
    0x13: "nl",
    0x15: "pl",
    0x16: "pt",
    0x19: "ru",
}


def _code_from_langid(langid: int) -> str | None:
    return _LANGID_PRIMARY.get(langid & 0x3FF)


def detect_system_language() -> str:
    """Best-effort detection of the user's display language.

    Windows: GetUserDefaultUILanguage (the actual Windows display language,
    independent of regional/format settings). Elsewhere (dev machines, CI):
    the usual locale environment variables. Falls back to English.
    """
    try:
        code = _code_from_langid(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        if code:
            return code
    except Exception:
        pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        code = value.replace("-", "_").split("_")[0].lower()
        if code in CATALOGS:
            return code
    return DEFAULT_LANGUAGE


def init(language: str) -> str:
    """Set the active language and return the resolved code.

    ``language`` is a catalog code ("de", "en", …) or "auto"/"" for system
    detection. Unsupported values log a warning and fall back to English —
    a config typo must never break startup.
    """
    global _active_language
    code = (language or "auto").strip().lower()
    if code in ("auto", ""):
        code = detect_system_language()
    if code not in CATALOGS:
        logger.warning(
            "Unsupported language %r — falling back to English. Available: %s",
            language, ", ".join(sorted(CATALOGS)),
        )
        code = DEFAULT_LANGUAGE
    _active_language = code
    return code


def active_language() -> str:
    return _active_language


def tr(key: str, /, **kwargs: object) -> str:
    """Translate ``key`` into the active language and fill placeholders.

    Never raises: a key missing from the active catalog falls back to the
    English catalog, an unknown key returns the key itself, and a template
    whose placeholders don't match the given kwargs (translator typo) falls
    back to the English template.
    """
    template = CATALOGS[_active_language].get(key)
    if template is None:
        template = CATALOGS[DEFAULT_LANGUAGE].get(key)
        if template is None:
            logger.warning("Missing translation key: %s", key)
            return key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        logger.warning(
            "Bad placeholders in %s catalog for key %s", _active_language, key
        )
        try:
            return CATALOGS[DEFAULT_LANGUAGE][key].format(**kwargs)
        except Exception:
            return template
