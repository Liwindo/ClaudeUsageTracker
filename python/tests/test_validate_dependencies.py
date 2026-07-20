"""Unit tests for scripts/validate_dependencies.py.

Each check gets a red fixture (must produce a finding) and a green fixture
(must stay silent). The GitHub API is faked — the live path runs in CI and
via manual `uv run python scripts/validate_dependencies.py` invocations.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location(
    "validate_dependencies", REPO_ROOT / "scripts" / "validate_dependencies.py"
)
vd = importlib.util.module_from_spec(spec)
# dataclass resolution needs the module registered before exec (python/cpython#121941)
sys.modules[spec.name] = vd
spec.loader.exec_module(vd)

SHA_A = "a" * 40
SHA_B = "b" * 40


def refs_from(text, path=Path("wf.yml")):
    return vd.parse_uses(path, text)


# --- parse_uses -------------------------------------------------------------

def test_parse_uses_extracts_action_ref_and_marker():
    text = f"      - uses: astral-sh/setup-uv@{SHA_A} # v8.3.2\n"
    (ref,) = refs_from(text)
    assert ref.action == "astral-sh/setup-uv"
    assert ref.ref == SHA_A
    assert ref.marker == "v8.3.2"
    assert ref.repo == "astral-sh/setup-uv"


def test_parse_uses_handles_tag_pin_and_subpath():
    text = "      - uses: actions/checkout@v7\n        with:\n          fetch-depth: 0\n"
    (ref,) = refs_from(text)
    assert ref.action == "actions/checkout"
    assert ref.ref == "v7"
    assert ref.marker is None

    (sub,) = refs_from(f"- uses: owner/repo/sub/dir@{SHA_A} # v1\n")
    assert sub.repo == "owner/repo"


# --- check_pins -------------------------------------------------------------

def test_third_party_tag_pin_is_a_finding():
    refs = refs_from("      - uses: softprops/action-gh-release@v3\n")
    findings = vd.check_pins(refs)
    assert len(findings) == 1
    assert "not pinned to a commit SHA" in findings[0]


def test_sha_pin_without_marker_is_a_finding():
    refs = refs_from(f"      - uses: astral-sh/setup-uv@{SHA_A}\n")
    findings = vd.check_pins(refs)
    assert len(findings) == 1
    assert "marker" in findings[0]


def test_first_party_tag_pin_and_marked_sha_pin_pass():
    text = (
        "      - uses: actions/checkout@v7\n"
        f"      - uses: astral-sh/setup-uv@{SHA_A} # v8.3.2\n"
    )
    assert vd.check_pins(refs_from(text)) == []


# --- check_comment_staleness ------------------------------------------------

def test_version_in_comment_above_uses_is_a_finding():
    text = (
        "      # Pinned to the v8.2.0 commit SHA (supply-chain hardening).\n"
        f"      - uses: astral-sh/setup-uv@{SHA_A} # v8.3.2\n"
    )
    findings = vd.check_comment_staleness(Path("wf.yml"), text)
    assert len(findings) == 1
    assert "version-free" in findings[0]


def test_version_free_comment_above_uses_passes():
    text = (
        "      # Non-immutable action: pinned to a commit SHA; Dependabot bumps\n"
        "      # the SHA and the trailing version marker together.\n"
        f"      - uses: astral-sh/setup-uv@{SHA_A} # v8.3.2\n"
    )
    assert vd.check_comment_staleness(Path("wf.yml"), text) == []


def test_version_in_unrelated_header_comment_passes():
    text = (
        "# Pushing a tag like v1.4.0 runs the tests and builds the EXE.\n"
        "on:\n"
        "  push:\n"
        f"      - uses: astral-sh/setup-uv@{SHA_A} # v8.3.2\n"
    )
    assert vd.check_comment_staleness(Path("wf.yml"), text) == []


# --- verify_pins_against_tags -----------------------------------------------

def _fake_fetch(status_map):
    def fetch(url):
        for needle, (code, status) in status_map.items():
            if needle in url:
                return code, {"status": status} if status else {}
        raise AssertionError(f"unexpected URL {url}")

    return fetch


def _marked_ref(sha=SHA_A, marker="v1.0.0"):
    (ref,) = refs_from(f"- uses: owner/repo@{sha} # {marker}\n")
    return ref


def test_identical_and_ahead_pins_pass():
    refs = [_marked_ref(SHA_A, "v1.0.0"), _marked_ref(SHA_B, "v3")]
    fetch = _fake_fetch({SHA_A: (200, "identical"), SHA_B: (200, "ahead")})
    assert vd.verify_pins_against_tags(refs, fetch=fetch) == []


def test_diverged_pin_is_a_finding():
    findings = vd.verify_pins_against_tags(
        [_marked_ref()], fetch=_fake_fetch({SHA_A: (200, "diverged")})
    )
    assert len(findings) == 1
    assert "diverged" in findings[0]


def test_unknown_sha_or_tag_is_a_finding():
    findings = vd.verify_pins_against_tags(
        [_marked_ref()], fetch=_fake_fetch({SHA_A: (404, None)})
    )
    assert len(findings) == 1
    assert "not found" in findings[0]


def test_duplicate_pins_are_verified_once():
    calls = []

    def fetch(url):
        calls.append(url)
        return 200, {"status": "identical"}

    refs = [_marked_ref(), _marked_ref()]
    assert vd.verify_pins_against_tags(refs, fetch=fetch) == []
    assert len(calls) == 1


# --- check_dependabot_config ------------------------------------------------

def _write_repo(tmp_path, dependabot_text):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "dependabot.yml").write_text(dependabot_text, encoding="utf-8")
    return tmp_path


GOOD_DEPENDABOT = (
    "version: 2\n"
    "updates:\n"
    "  - package-ecosystem: uv\n"
    "    ignore:\n"
    "      - dependency-name: pyinstaller\n"
    '        update-types: ["version-update:semver-major"]\n'
    "  - package-ecosystem: github-actions\n"
)


def test_current_dependabot_config_passes(tmp_path):
    root = _write_repo(tmp_path, GOOD_DEPENDABOT)
    assert vd.check_dependabot_config(root) == []


def test_missing_ecosystem_and_missing_pyinstaller_ignore_are_findings(tmp_path):
    root = _write_repo(tmp_path, "version: 2\nupdates:\n  - package-ecosystem: uv\n")
    findings = vd.check_dependabot_config(root)
    assert any("github-actions" in f for f in findings)
    assert any("pyinstaller" in f for f in findings)


def test_missing_dependabot_config_is_a_finding(tmp_path):
    (tmp_path / ".github").mkdir()
    findings = vd.check_dependabot_config(tmp_path)
    assert len(findings) == 1
    assert "missing" in findings[0]


# --- check_python_pin ---------------------------------------------------------

def test_matching_python_pin_passes(tmp_path):
    (tmp_path / ".python-version").write_text("3.14.4\n", encoding="utf-8")
    assert vd.check_python_pin(tmp_path, running="3.14.4") == []


def test_mismatching_python_pin_is_a_finding(tmp_path):
    (tmp_path / ".python-version").write_text("3.14.4\n", encoding="utf-8")
    findings = vd.check_python_pin(tmp_path, running="3.12.1")
    assert len(findings) == 1
    assert "3.12.1" in findings[0]


def test_interpreter_matches_repo_python_pin():
    # The venv/CI interpreter must actually be the pinned one — this is the
    # live Cloudflare-403 guard, not a fixture.
    assert vd.check_python_pin(REPO_ROOT) == []


# --- main (end to end against the real repo) ---------------------------------

def test_main_offline_passes_on_this_repo(capsys):
    assert vd.main(["--offline"]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out


def test_main_reports_findings_on_a_broken_repo(tmp_path, capsys):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        "      # Pinned to the v8.2.0 commit SHA.\n"
        "      - uses: softprops/action-gh-release@v3\n",
        encoding="utf-8",
    )
    assert vd.main(["--offline", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "not pinned to a commit SHA" in out
    assert "version-free" in out
    assert "dependabot" in out.lower()
    assert ".python-version" in out
