"""List every doc line that a change touches, so none is overlooked.

check_docs.py covers what can be checked mechanically. Prose ("a dialog offers
to open the release page") cannot be, and that is how stale docs slip through:
whoever updates the docs searches for the names they are adding, not for the
sentences that describe the behaviour they changed. This script derives the
search terms from the change itself and prints every hit in every tracked doc.
Each hit then needs a deliberate decision: still true, or update it
(REQUIREMENTS.md R-rel-7).

Terms come from:
  - every changed or new non-doc file: its name, its stem and the words in it
    (update_dialog.py -> "update_dialog.py", "update_dialog", "update dialog",
    "update", "dialog")
  - changed English UI strings (python/src/claude_usage_monitor/locales/en.py),
    old and new text
  - changed config keys (python/src/claude_usage_monitor/config.py)
  - --term, for the feature words of the change ("release notes")

Usage:
    python scripts/doc_sweep.py                  # working tree vs HEAD, plus untracked files
    python scripts/doc_sweep.py --base master    # everything since master
    python scripts/doc_sweep.py --staged         # what the next commit contains
    python scripts/doc_sweep.py --term "release notes" --term dialog
    python scripts/doc_sweep.py --ack            # record: the docs of the current
                                                 # changes were reviewed

--ack writes a digest of the uncommitted changes (vs HEAD, untracked files
included) to .git/doc-sweep-ack. scripts/doc_commit_guard.py, the Claude Code
commit hook, lets a commit through only while that digest still matches, so
any edit after the review asks for a new one.

Stdlib only. Exits 0 even with hits: it is a review aid, the decision is the
reader's. Exits 2 only when git itself fails.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_docs import REPO_ROOT, tracked_docs  # noqa: E402

EN_LOCALE = "python/src/claude_usage_monitor/locales/en.py"
CONFIG_PY = "python/src/claude_usage_monitor/config.py"

# Words too generic to say anything about which doc line is affected.
_STOP = {
    "test", "tests", "case", "cases", "file", "files", "json", "main", "init",
    "data", "base", "core", "util", "utils", "helper", "helpers", "index",
    "readme", "python", "csharp", "claude", "usage", "tracker", "monitor",
    "src", "app", "csproj", "slnx", "fixtures", "assets", "scripts", "github",
    "workflows", "locales", "props", "docs",
}


def _git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def changes_digest() -> str:
    """SHA-256 over every uncommitted change: the tracked diff against HEAD
    and the content of each untracked file. Equal digests = same changes."""
    h = hashlib.sha256()
    diff = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=REPO_ROOT,
                          capture_output=True)
    if diff.returncode != 0:
        raise RuntimeError(f"git diff failed: {diff.stderr.decode(errors='replace').strip()}")
    h.update(diff.stdout)
    for name in sorted(_git("ls-files", "--others", "--exclude-standard")):
        h.update(name.encode("utf-8") + b"\0")
        path = REPO_ROOT / name
        if path.is_file():
            h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def ack_path() -> Path:
    git_dir = Path(_git("rev-parse", "--git-dir")[0])
    return (git_dir if git_dir.is_absolute() else REPO_ROOT / git_dir) / "doc-sweep-ack"


def ack_matches() -> bool:
    """True while the recorded review still covers exactly the current changes."""
    path = ack_path()
    return path.is_file() and path.read_text(encoding="ascii").strip() == changes_digest()


def changed_files(base: str, staged: bool) -> list[str]:
    if staged:
        return _git("diff", "--cached", "--name-only")
    files = _git("diff", "--name-only", base)
    files += _git("ls-files", "--others", "--exclude-standard")
    return sorted(set(files))


def _diff_lines(base: str, staged: bool, path: str) -> list[str]:
    args = ["diff", "--cached" if staged else base, "--", path]
    return [line for line in _git(*args)
            if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def _words(stem: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
    return [w.lower() for w in re.split(r"[\s_.\-]+", spaced) if w]


def terms_for(files: list[str], base: str, staged: bool,
              extra: list[str]) -> tuple[list[str], list[str]]:
    """(specific terms, single words). Specific terms are always searched;
    single words only where they are rare enough to point at something."""
    terms: set[str] = set(t.strip() for t in extra if t.strip())
    words_out: set[str] = set()
    for path in files:
        name = Path(path).name
        if name.endswith(".md"):
            continue
        stem = Path(path).stem
        words = _words(stem)
        if len(stem) >= 4:
            terms.add(name)  # it.py, de.py: too short to mean anything
        if len(words) > 1 and not all(w in _STOP for w in words):
            terms.update({stem, " ".join(words)})
        words_out.update(w for w in words if len(w) >= 4 and w not in _STOP)
    if EN_LOCALE in files:
        for line in _diff_lines(base, staged, EN_LOCALE):
            m = re.search(r'"[\w.]+"\s*:\s*"(.*)"', line)
            if m:
                text = re.sub(r"\s+", " ", re.sub(r"\{\w+\}", "", m.group(1))).strip(" .")
                if len(text.split()) >= 2:  # "latest", "Versions": too generic alone
                    terms.add(text)
    if CONFIG_PY in files:
        for line in _diff_lines(base, staged, CONFIG_PY):
            m = re.match(r"[+-]\s+([a-z][a-z0-9_]+)\s*:\s*[A-Za-z]", line)
            if m:
                terms.add(m.group(1))
    order = lambda t: (-len(t), t.lower())  # noqa: E731
    return sorted(terms, key=order), sorted(words_out - terms, key=order)


def doc_lines(doc: Path) -> list[tuple[int, str]]:
    """Numbered lines of a doc. For CHANGELOG.md only the ``## Unreleased``
    block counts: released sections are history and never get updated."""
    lines = list(enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1))
    if doc.name != "CHANGELOG.md":
        return lines
    out, inside = [], False
    for no, line in lines:
        if line.startswith("## "):
            inside = line.strip().lower() == "## unreleased"
        elif inside:
            out.append((no, line))
    return out


def _pattern(term: str) -> re.Pattern[str]:
    # Whole terms only: "notes" must not match "footnotes", nor "es.py" the
    # end of "cookies.py".
    return re.compile(rf"(?<![\w.-]){re.escape(term)}(?![\w-])", re.IGNORECASE)


# A single word matching more doc lines than this says nothing about which
# line is affected ("update" in this repo); it is reported, not listed.
MAX_WORD_LINES = 25


def split_words(docs: list[Path], words: list[str]) -> tuple[list[str], list[str]]:
    """(rare words to search, common words to report)."""
    rare, common = [], []
    for word in words:
        pattern = _pattern(word)
        count = sum(1 for doc in docs for _, line in doc_lines(doc) if pattern.search(line))
        (common if count > MAX_WORD_LINES else rare).append(word)
    return rare, common


def sweep(docs: list[Path], terms: list[str]) -> dict[Path, list[tuple[int, list[str], str]]]:
    patterns = [(t, _pattern(t)) for t in terms]
    hits: dict[Path, list[tuple[int, list[str], str]]] = {}
    for doc in docs:
        rows = []
        for no, line in doc_lines(doc):
            found = [t for t, p in patterns if p.search(line)]
            if found:
                rows.append((no, found, line.strip()))
        hits[doc] = rows
    return hits


CONTEXT = 2  # lines shown around each hit: a stale sentence often sits next to the hit


def print_snippets(doc: Path, rows: list[tuple[int, list[str], str]]) -> None:
    """Hits with CONTEXT lines around them, overlapping snippets merged; hit
    lines are marked with '>' and their terms."""
    if not rows:
        return
    text = dict(doc_lines(doc))
    found = {no: terms for no, terms, _ in rows}
    spans: list[list[int]] = []
    for no in sorted(found):
        lo, hi = no - CONTEXT, no + CONTEXT
        if spans and lo <= spans[-1][1] + 1:
            spans[-1][1] = hi
        else:
            spans.append([lo, hi])
    for lo, hi in spans:
        print("  ...")
        for no in range(lo, hi + 1):
            if no not in text:
                continue
            if no in found:
                print(f"> {no:>4}: [{', '.join(found[no][:4])}] {text[no].strip()[:170]}")
            else:
                print(f"  {no:>4}:  {text[no].strip()[:170]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="HEAD", help="compare against this ref (default HEAD)")
    parser.add_argument("--staged", action="store_true", help="only what is staged for commit")
    parser.add_argument("--term", action="append", default=[], help="extra search term (repeatable)")
    parser.add_argument("--ack", action="store_true",
                        help="record that the docs of the current changes were reviewed")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    if args.ack:
        try:
            ack_path().write_text(changes_digest() + "\n", encoding="ascii")
        except RuntimeError as exc:
            print(exc)
            return 2
        print("Recorded: the docs of the current changes were reviewed. "
              "Any further edit needs a new review.")
        return 0

    try:
        files = changed_files(args.base, args.staged)
        terms, words = terms_for(files, args.base, args.staged, args.term)
    except RuntimeError as exc:
        print(exc)
        return 2
    docs = tracked_docs()
    local = REPO_ROOT / "CLAUDE.md"
    if local.exists():
        docs.append(local)
    if not files:
        print("No changes found.")
        return 0

    rare, common = split_words(docs, words)
    changed = set(files)
    hits = sweep(docs, terms + rare)
    print(f"{len(files)} changed file(s); searched for {len(terms) + len(rare)} terms:")
    print("  " + ", ".join(terms + rare))
    if common:
        print(f"Too common to list (> {MAX_WORD_LINES} lines each): " + ", ".join(common))
        print("  If the change is about one of them, narrow it with --term \"<phrase>\".")
    untouched_with_hits = []
    for doc in docs:
        rel = doc.relative_to(REPO_ROOT).as_posix()
        rows = hits[doc]
        state = "changed" if rel in changed else "NOT changed"
        if doc == local:
            state += ", gitignored (local only)"
        print(f"\n== {rel}  [{state}]  {len(rows)} hit line(s)")
        print_snippets(doc, rows)
        if rows and rel not in changed:
            untouched_with_hits.append(rel)
    print("\nEvery line above needs a decision: still true, or update it.")
    if untouched_with_hits:
        print("Docs with hits that this change does not touch yet: "
              + ", ".join(untouched_with_hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
