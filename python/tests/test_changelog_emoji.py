"""scripts/check_changelog_emoji.py: CHANGELOG emoji must render on Windows 10,
because every section ends up in the update dialog (REQUIREMENTS.md R-rel-6)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_changelog_emoji", ROOT / "scripts" / "check_changelog_emoji.py"
)
ce = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ce
spec.loader.exec_module(ce)


def test_the_real_changelog_passes():
    assert ce.find_problems((ROOT / "CHANGELOG.md").read_text(encoding="utf-8")) == []


def test_section_emoji_and_plain_symbols_are_fine():
    text = "### 🔒 Security\n### ✨ New\n- ⚠️ careful → ≥ — … äöü"
    assert ce.find_problems(text) == []


def test_newer_emoji_is_rejected_with_position():
    problems = ce.find_problems("ok\n### 🪄 Magic")
    assert len(problems) == 1
    assert problems[0].startswith("line 2, col 5:")
    assert "allowlist" in problems[0]


def test_sequences_are_rejected():
    assert ce.find_problems("🐦‍🔥")  # phoenix: ZWJ + allowed-looking parts
    assert ce.find_problems("👍🏽")         # skin tone modifier
    assert ce.find_problems("🇩🇪")          # flag (regional indicators)
    assert ce.find_problems("1️⃣")  # keycap


def test_main_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.md"
    good.write_text("### 🐛 Bug fixes\n", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("### 🫠 Oops\n", encoding="utf-8")
    assert ce.main(["x", str(good)]) == 0
    assert ce.main(["x", str(bad)]) == 1
    assert "MELTING FACE" in capsys.readouterr().out
