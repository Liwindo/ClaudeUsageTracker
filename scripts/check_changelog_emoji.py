"""Fail if CHANGELOG.md uses an emoji that Windows 10 cannot draw.

Every release body on GitHub is that version's CHANGELOG.md section, and both
variants show those bodies in the update dialog (REQUIREMENTS.md R-life-6). The
dialog draws emoji with the system font. Windows 10's Segoe UI Emoji has no
glyphs for emoji from Unicode/Emoji 13 on (🪄, 🫠, 🪿, …), so those come out as
empty boxes, and joined sequences (ZWJ, skin tones, flags, keycaps) fall apart
into their pieces. Windows 11 users would never notice, so this check stops it
before a release: only the emoji below are allowed, each one checked by
screenshot in tkinter (Tk 9) and WPF on Windows 10.

The whole file is checked, not just ``## Unreleased``: users who are several
versions behind see the older sections too.

Usage:
    python scripts/check_changelog_emoji.py [path/to/CHANGELOG.md]

Stdlib only, works with any Python >= 3.9 (the release workflow runs it with the
runner's default interpreter). Exit 1 lists every offending character.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Rendered correctly by both dialogs on Windows 10 (verified by screenshot).
ALLOWED = frozenset("🔒🔧🐛✨🐍📦💄📝⚠✅❌🚀🎉")
VARIATION_SELECTOR_16 = "️"  # "⚠️" = ⚠ + VS16, draws fine

# Joiners and modifiers that build multi-part emoji; Windows 10 shows the parts.
_SEQUENCE_PARTS = {
    "‍": "zero-width joiner (emoji sequence)",
    "⃣": "keycap combiner",
}


def _is_emoji_like(cp: int) -> bool:
    return (
        0x2300 <= cp <= 0x23FF      # misc technical (⌚ ⏰ ⌛ …)
        or 0x2600 <= cp <= 0x27BF   # misc symbols + dingbats (✨ ✅ ⚠ …)
        or 0x2B00 <= cp <= 0x2BFF   # arrows/stars (⭐ ⬆ …)
        or 0x1F000 <= cp <= 0x1FFFF  # emoji blocks incl. flags and skin tones
        or 0xE0020 <= cp <= 0xE007F  # tag characters (subdivision flags)
    )


def find_problems(text: str) -> list[str]:
    """One message per disallowed character, with line and column."""
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for col, ch in enumerate(line, start=1):
            if ch in ALLOWED or ch == VARIATION_SELECTOR_16:
                continue
            reason = _SEQUENCE_PARTS.get(ch)
            if reason is None and _is_emoji_like(ord(ch)):
                reason = "emoji not in the Windows 10 allowlist"
            if reason is not None:
                name = unicodedata.name(ch, f"U+{ord(ch):04X}")
                problems.append(f"line {lineno}, col {col}: {ch!r} {name} — {reason}")
    return problems


def main(argv: list[str]) -> int:
    # A cp1252 console (Windows runner, piped output) cannot encode emoji;
    # escape them instead of crashing the check with UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    path = Path(argv[1]) if len(argv) > 1 else REPO_ROOT / "CHANGELOG.md"
    problems = find_problems(path.read_text(encoding="utf-8"))
    if problems:
        print(f"{path.name}: emoji the update dialog cannot draw on Windows 10:")
        for problem in problems:
            print(f"  {problem}")
        print("Allowed: " + " ".join(sorted(ALLOWED)) + "  (see the script docstring)")
        return 1
    print(f"OK: {path.name} only uses emoji that Windows 10 can draw.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
