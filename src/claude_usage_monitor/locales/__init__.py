"""Translation catalogs — one module per language.

To add a language: copy ``en.py``, translate every value (keys and
``{placeholder}`` names must stay identical), then import and register the
module below. ``tests/test_i18n.py`` enforces that every catalog has exactly
the English key set with matching placeholders.

The imports are deliberately explicit (no importlib scanning) so PyInstaller
bundles every catalog into the frozen EXE.
"""

from __future__ import annotations

from . import de, en, es, fr, it, nl, pl, pt, ru

CATALOGS: dict[str, dict[str, str]] = {
    "de": de.STRINGS,
    "en": en.STRINGS,
    "es": es.STRINGS,
    "fr": fr.STRINGS,
    "it": it.STRINGS,
    "nl": nl.STRINGS,
    "pl": pl.STRINGS,
    "pt": pt.STRINGS,
    "ru": ru.STRINGS,
}
