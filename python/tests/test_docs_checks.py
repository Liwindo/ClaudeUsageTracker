"""scripts/check_docs.py and scripts/doc_sweep.py (REQUIREMENTS.md R-rel-7):
the docs must name everything that exists, and a change must surface every
doc line that talks about what it touched."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cd = _load("check_docs")
ds = _load("doc_sweep")
guard = _load("doc_commit_guard")


# ── check_docs ───────────────────────────────────────────────────────────────

def test_the_real_repo_documents_everything():
    assert cd.find_problems() == []


def _fake_repo(tmp_path: Path) -> Path:
    pkg = tmp_path / "python" / "src" / "claude_usage_monitor"
    (pkg / "assets").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "widget.py").write_text("", encoding="utf-8")
    (pkg / "assets" / "logo.png").write_bytes(b"")
    (pkg / "config.py").write_text(
        "class Config:\n    poll_interval_seconds: int = 30\n    _path: str = ''\n",
        encoding="utf-8")
    app = tmp_path / "csharp" / "ClaudeUsageTracker"
    (app / "Assets").mkdir(parents=True)
    (app / "Program.cs").write_text("", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "tool.py").write_text("", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("", encoding="utf-8")
    (tmp_path / "python" / "README.md").write_text(
        "widget.py config.py logo.png\npoll_interval_seconds = 30\n", encoding="utf-8")
    (tmp_path / "csharp" / "README.md").write_text("Program.cs\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("tool.py ci.yml\n", encoding="utf-8")
    return tmp_path


def test_complete_fake_repo_passes(tmp_path):
    assert cd.find_problems(_fake_repo(tmp_path)) == []


def test_each_kind_of_gap_is_reported(tmp_path):
    root = _fake_repo(tmp_path)
    pkg = root / "python" / "src" / "claude_usage_monitor"
    (pkg / "update_dialog.py").write_text("", encoding="utf-8")
    (pkg / "assets" / "logo_tile.png").write_bytes(b"")
    (root / "csharp" / "ClaudeUsageTracker" / "UpdateDialog.cs").write_text("", encoding="utf-8")
    (root / "csharp" / "ClaudeUsageTracker" / "Assets" / "logo_tile.ico").write_bytes(b"")
    (root / "scripts" / "new_tool.ps1").write_text("", encoding="utf-8")
    (root / ".github" / "workflows" / "watch.yml").write_text("", encoding="utf-8")
    (pkg / "config.py").write_text(
        "class Config:\n    poll_interval_seconds: int = 30\n    new_key: bool = True\n",
        encoding="utf-8")
    problems = "\n".join(cd.find_problems(root))
    for missing in ("update_dialog.py", "logo_tile.png", "UpdateDialog.cs", "logo_tile.ico",
                    "new_tool.ps1", "watch.yml", "new_key"):
        assert missing in problems, missing


def test_claude_md_does_not_count_as_documentation(tmp_path):
    """CLAUDE.md is gitignored: naming something only there documents nothing."""
    root = _fake_repo(tmp_path)
    (root / "scripts" / "secret_tool.py").write_text("", encoding="utf-8")
    (root / "CLAUDE.md").write_text("secret_tool.py\n", encoding="utf-8")
    assert any("secret_tool.py" in p for p in cd.find_problems(root))


# ── doc_sweep ────────────────────────────────────────────────────────────────

def test_terms_from_a_changed_module():
    terms, words = ds.terms_for(
        ["python/src/claude_usage_monitor/update_dialog.py", "README.md"], "HEAD", False, [])
    assert {"update_dialog.py", "update_dialog", "update dialog"} <= set(terms)
    assert {"update", "dialog"} <= set(words)
    assert "README.md" not in terms  # docs are what is searched, not search terms


def test_short_locale_files_add_no_noise():
    terms, words = ds.terms_for(
        ["python/src/claude_usage_monitor/locales/it.py"], "HEAD", False, [])
    assert terms == [] and words == []


def test_terms_match_whole_names_only():
    assert ds._pattern("es.py").search("firefox_cookies.py") is None
    assert ds._pattern("es.py").search("see `es.py` here")
    assert ds._pattern("notes").search("footnotes") is None
    assert ds._pattern("update dialog").search("The Update Dialog shows")


def test_released_changelog_sections_are_not_searched(tmp_path):
    doc = tmp_path / "CHANGELOG.md"
    doc.write_text("# Changelog\n\n## Unreleased\n\n- new dialog\n\n## 1.0.0 — x\n\n- old dialog\n",
                   encoding="utf-8")
    assert [text for _, text in ds.doc_lines(doc)] == ["", "- new dialog", ""]


def test_common_single_words_are_reported_not_listed(tmp_path):
    doc = tmp_path / "README.md"
    doc.write_text("\n".join(["update"] * (ds.MAX_WORD_LINES + 1) + ["dialog"]), encoding="utf-8")
    assert ds.split_words([doc], ["update", "dialog"]) == (["dialog"], ["update"])


def test_stale_prose_next_to_a_hit_is_shown(tmp_path, capsys):
    """The miss that prompted this script: python/README.md described the
    dialog in a config comment two lines above the update_check key."""
    doc = tmp_path / "README.md"
    doc.write_text(
        "intro\n\n# If one is found, a\n# dialog offers to open the release page.\n"
        "update_check = true\n\n\n\nunrelated\n", encoding="utf-8")
    hits = ds.sweep([doc], ["update_check"])
    ds.print_snippets(doc, hits[doc])
    out = capsys.readouterr().out
    assert "> " in out and "update_check = true" in out
    assert "dialog offers to open the release page" in out  # context line
    assert "unrelated" not in out


def test_ack_digest_changes_with_any_edit(tmp_path, monkeypatch):
    """The ack covers exactly one state: a new untracked file invalidates it."""
    before = ds.changes_digest()
    probe = ROOT / "scratch_digest_probe.txt"
    probe.write_text("x", encoding="utf-8")
    try:
        assert ds.changes_digest() != before
    finally:
        probe.unlink()
    assert ds.changes_digest() == before


# ── doc_commit_guard (the Claude Code commit hook) ───────────────────────────

import pytest  # noqa: E402

_COMMIT = "git " + "commit"  # split so this file's own text never trips the hook


@pytest.mark.parametrize("command", [
    "ls -la", "git status", "git log --grep " + "commit", "echo committed", "git diff HEAD",
])
def test_guard_ignores_everything_but_commits(command, monkeypatch):
    monkeypatch.setattr(guard.check_docs, "find_problems",
                        lambda: pytest.fail("must not even check"))
    assert guard.decide(command) is None


@pytest.mark.parametrize("command", [
    _COMMIT + " -m x", 'cd "D:/x" && ' + _COMMIT + ' -m "y"', "git -C . commit --amend",
    "git -c user.name=a commit -m x", "(git add -A; " + _COMMIT + " -m x)",
])
def test_guard_blocks_an_unreviewed_commit(command, monkeypatch):
    monkeypatch.setattr(guard.check_docs, "find_problems", lambda: [])
    monkeypatch.setattr(guard.doc_sweep, "ack_matches", lambda: False)
    monkeypatch.setattr(guard.doc_sweep, "main", lambda argv: print("SWEEP OUTPUT") or 0)
    out = guard.decide(command)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "doc_sweep.py --ack" in out["permissionDecisionReason"]
    assert "SWEEP OUTPUT" in out["permissionDecisionReason"]


def test_guard_lets_a_reviewed_commit_through(monkeypatch):
    monkeypatch.setattr(guard.check_docs, "find_problems", lambda: [])
    monkeypatch.setattr(guard.doc_sweep, "ack_matches", lambda: True)
    assert guard.decide(_COMMIT + " -m x") is None


def test_guard_blocks_while_check_docs_fails_even_if_acked(monkeypatch):
    monkeypatch.setattr(guard.check_docs, "find_problems", lambda: ["Script x.py is not named"])
    monkeypatch.setattr(guard.doc_sweep, "ack_matches", lambda: True)
    reason = guard.decide(_COMMIT + " -m x")["hookSpecificOutput"]["permissionDecisionReason"]
    assert "x.py is not named" in reason


def test_guard_fails_closed_when_the_check_breaks(monkeypatch):
    def boom():
        raise RuntimeError("git missing")
    monkeypatch.setattr(guard.check_docs, "find_problems", boom)
    reason = guard.decide(_COMMIT + " -m x")["hookSpecificOutput"]["permissionDecisionReason"]
    assert "could not run" in reason and "git missing" in reason


def test_local_settings_wire_the_guard_for_bash_and_powershell():
    import json
    path = ROOT / ".claude" / "settings.json"
    if not path.exists():  # local only, not tracked (CI has none)
        pytest.skip("no local .claude/settings.json")
    settings = json.loads(path.read_text(encoding="utf-8"))
    entry = settings["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash|PowerShell"
    assert "scripts/doc_commit_guard.py" in entry["hooks"][0]["command"]
