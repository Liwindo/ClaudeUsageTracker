"""Release notes for the update dialog, taken from the GitHub release bodies.

The source is always the live GitHub releases API — nothing is bundled — so an
edited release text on GitHub is what users see. The release workflow fills each
body from that version's CHANGELOG.md section, i.e. a small Markdown subset:
``###`` headings, ``-`` bullets (one nesting level), ``**bold**``, ``*emphasis*``,
`` `code` `` and ``[links](…)``.

A release body is UNTRUSTED under the compromised-GitHub model (REQUIREMENTS.md
§13, R-net-8). It is therefore only ever turned into plain text plus a bold flag:
no HTML, no clickable links (a link keeps just its text), invisible format
characters such as a BOM or bidi overrides are dropped, and the amount shown is
capped. Everything here is pure, so it is exhaustively unit-tested — the C#
variant (ReleaseNotes.cs) runs the same cases from
``python/tests/fixtures/release_notes_cases.json``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

# At most this many versions are listed; older ones are summed up by a
# "see GitHub" line. Generous for anyone who updates now and then, and it keeps
# the dialog quick to read.
MAX_RELEASES = 10
# Hard caps against an oversized (hostile or accidental) body.
MAX_BLOCKS = 150        # blocks over all versions
MAX_BLOCK_CHARS = 1500  # code points per block, longer text ends in "…"

_ZWJ = "‍"  # keeps emoji sequences like 👨‍👩‍👧 together, so it survives

_HEADING = re.compile(r"#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_BULLET = re.compile(r"[-*+][ \t]+(.*)$")
_ORDERED = re.compile(r"\d{1,9}[.)][ \t]+")
_RULE = re.compile(r"(?:-[ \t]*){3,}$|(?:\*[ \t]*){3,}$|(?:_[ \t]*){3,}$")
# The workflow appends "**Full Changelog**: <compare URL>" — a link the dialog
# cannot open anyway, so the line is dropped.
_FULL_CHANGELOG = re.compile(r"\**full changelog\**\s*:", re.IGNORECASE)
_LINK = re.compile(r"!?\[([^\[\]]*)\]\([^()\s]*(?:[ \t]+\"[^\"]*\")?\)")
_AUTOLINK = re.compile(r"<(https?://[^<>\s]+)>")
_ASCII_PUNCT = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


@dataclass(frozen=True)
class Span:
    text: str
    bold: bool = False


@dataclass(frozen=True)
class Block:
    kind: str                # "heading" | "bullet" | "text"
    spans: tuple[Span, ...]
    level: int = 0           # bullet nesting, 0 or 1


@dataclass(frozen=True)
class VersionNotes:
    version: str             # without a leading "v", e.g. "2.2.5"
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class ReleaseNotes:
    versions: tuple[VersionNotes, ...]  # newest first, never empty
    truncated: bool                     # more changes exist than are shown


# ── Sanitising ───────────────────────────────────────────────────────────────

def sanitize(text: str) -> str:
    """Normalise line endings and drop characters that must never reach the UI:
    control characters (a tab becomes a space), format characters such as a BOM
    or bidi overrides (except the emoji joiner ZWJ), and lone surrogates."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for ch in text:
        if ch == "\n":
            out.append(ch)
        elif ch == "\t":
            out.append(" ")
        elif ch == _ZWJ:
            out.append(ch)
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            continue
        else:
            out.append(ch)
    return "".join(out)


# ── Inline Markdown ──────────────────────────────────────────────────────────

def _atoms(text: str) -> list[tuple[str, bool]]:
    """Split inline text into (char, literal) pairs. Literal chars (escaped, or
    inside a code span) can never act as emphasis markers. Links keep only their
    text, autolinks only their URL text."""
    atoms: list[tuple[str, bool]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] in _ASCII_PUNCT:
            atoms.append((text[i + 1], True))
            i += 2
            continue
        if ch == "`":
            run = 1
            while i + run < n and text[i + run] == "`":
                run += 1
            close = _find_backtick_run(text, i + run, run)
            if close < 0:
                atoms.extend((c, True) for c in text[i:i + run])
                i += run
                continue
            content = text[i + run:close]
            if len(content) >= 2 and content[0] == " " and content[-1] == " " and content.strip():
                content = content[1:-1]
            atoms.extend((c, True) for c in content)
            i = close + run
            continue
        if ch in "[!":
            m = _LINK.match(text, i)
            if m:
                atoms.extend(_atoms(m.group(1)))
                i = m.end()
                continue
        if ch == "<":
            m = _AUTOLINK.match(text, i)
            if m:
                atoms.extend((c, True) for c in m.group(1))
                i = m.end()
                continue
        atoms.append((ch, False))
        i += 1
    return atoms


def _find_backtick_run(text: str, start: int, run: int) -> int:
    """Index of the next backtick run of exactly ``run`` length, or -1."""
    i, n = start, len(text)
    while i < n:
        if text[i] != "`":
            i += 1
            continue
        j = i
        while j < n and text[j] == "`":
            j += 1
        if j - i == run:
            return i
        i = j
    return -1


def _is_word(ch: str | None) -> bool:
    return ch is not None and (ch.isalpha() or ch.isdecimal())


def _is_space(ch: str | None) -> bool:
    return ch is None or ch.isspace()


def parse_inline(text: str) -> tuple[Span, ...]:
    """``**bold**``/``__bold__`` → bold spans; ``*em*``/``_em_`` lose their
    markers (no italics in the dialog); unmatched markers stay literal."""
    atoms = _atoms(text)
    # Marker runs: (start, length, kind, can_open, can_close).
    markers: list[tuple[int, int, str, bool, bool]] = []
    i, n = 0, len(atoms)
    while i < n:
        ch, literal = atoms[i]
        if literal or ch not in "*_":
            i += 1
            continue
        j = i
        while j < n and atoms[j] == (ch, False):
            j += 1
        length = j - i
        if length <= 3:
            prev = atoms[i - 1][0] if i > 0 else None
            nxt = atoms[j][0] if j < n else None
            # A run of three is strong + emphasis ("***x***").
            pieces = {1: [(i, 1)], 2: [(i, 2)], 3: [(i, 2), (i + 2, 1)]}[length]
            for start, size in pieces:
                can_open = not _is_space(nxt)
                can_close = not _is_space(prev)
                if size == 1 or ch == "_":
                    # Emphasis and underscores never apply inside a word
                    # (snake_case, 5*3*2).
                    can_open = can_open and not _is_word(prev)
                    can_close = can_close and not _is_word(nxt)
                kind = ("strong" if size == 2 else "em") + ch
                markers.append((start, size, kind, can_open, can_close))
        i = j

    # Pair openers with the next closer of the same kind; the rest stay literal.
    pending: dict[str, int] = {}
    paired: dict[int, str] = {}  # atom index → "bold" toggle or "drop"
    for start, length, kind, can_open, can_close in markers:
        if kind in pending and can_close:
            opener = pending.pop(kind)
            effect = "bold" if kind.startswith("strong") else "drop"
            paired[opener] = effect
            paired[start] = effect
        elif can_open:
            pending[kind] = start

    spans: list[Span] = []
    buf: list[str] = []
    bold = False
    lengths = {m[0]: m[1] for m in markers}
    i = 0
    while i < n:
        effect = paired.get(i)
        if effect is not None:
            if effect == "bold":
                if buf:
                    spans.append(Span("".join(buf), bold))
                    buf = []
                bold = not bold
            i += lengths[i]
            continue
        buf.append(atoms[i][0])
        i += 1
    if buf:
        spans.append(Span("".join(buf), bold))
    return _merge(spans)


def _merge(spans: list[Span]) -> tuple[Span, ...]:
    """Join neighbours with the same weight and drop empty spans."""
    out: list[Span] = []
    for span in spans:
        if not span.text:
            continue
        if out and out[-1].bold == span.bold:
            out[-1] = Span(out[-1].text + span.text, span.bold)
        else:
            out.append(span)
    return tuple(out)


def _clip(spans: tuple[Span, ...]) -> tuple[Span, ...]:
    """Trim the outer whitespace of a block and cap its length."""
    out: list[Span] = []
    budget = MAX_BLOCK_CHARS
    for span in spans:
        if budget <= 0:
            break
        text = span.text
        if len(text) > budget:
            text = text[:budget].rstrip() + "…"
            budget = 0
        else:
            budget -= len(text)
        out.append(Span(text, span.bold))
    if out:
        out[0] = Span(out[0].text.lstrip(), out[0].bold)
        out[-1] = Span(out[-1].text.rstrip(), out[-1].bold)
    return _merge(out)


# ── Blocks ───────────────────────────────────────────────────────────────────

def parse_body(body: str) -> tuple[Block, ...]:
    """Turn one release body into display blocks."""
    blocks: list[Block] = []
    kind: str | None = None
    level = 0
    parts: list[str] = []

    def flush() -> None:
        nonlocal kind, parts
        if kind is not None:
            spans = _clip(parse_inline(" ".join(parts)))
            if spans:
                blocks.append(Block(kind, spans, level))
        kind, parts = None, []

    in_quote = False
    for raw in sanitize(body).split("\n"):
        line = raw.rstrip()
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        # A "> " quote is shown as an ordinary paragraph of its own.
        quote = stripped.startswith(">")
        if quote:
            stripped = stripped[1:].lstrip(" ")
            indent = 0
        if quote != in_quote:
            flush()
            in_quote = quote
        if not stripped:
            flush()
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()  # fence lines themselves carry nothing to show
            continue
        if _FULL_CHANGELOG.match(stripped) or _RULE.match(stripped):
            flush()
            continue
        m = _HEADING.match(stripped)
        if m:
            flush()
            kind, level, parts = "heading", 0, [m.group(1)]
            flush()
            continue
        m = _BULLET.match(stripped)
        if m:
            flush()
            kind, level, parts = "bullet", (1 if indent >= 2 else 0), [m.group(1)]
            continue
        if _ORDERED.match(stripped):
            flush()  # a numbered item starts its own line, number kept
            kind, level, parts = "text", 0, [stripped]
            continue
        if kind is None:
            kind, level = "text", 0
        parts.append(stripped)
    flush()
    return tuple(blocks)


# ── Choosing the releases ────────────────────────────────────────────────────

def _version_key(tag: str) -> tuple[int, ...] | None:
    # ASCII digits, at most 9 per part, so both variants read the same tags
    # (C# parses into an int).
    m = re.match(r"v?([0-9]{1,9}(?:\.[0-9]{1,9})*)$", tag.strip())
    if not m:
        return None
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()  # "1.2.0" and "1.2" are the same version
    return tuple(parts)


def select_notes(
    payload: object, current_version: str, latest_version: str,
    max_releases: int = MAX_RELEASES,
) -> ReleaseNotes | None:
    """From a ``GET /releases`` payload, the notes of every published release
    newer than the running version and not newer than the latest one, newest
    first. ``None`` when nothing usable is there, so the dialog can say the
    notes are unavailable instead of showing an empty box."""
    current = _version_key(current_version)
    latest = _version_key(latest_version)
    if current is None or latest is None:
        return None
    return _select(payload, lambda key: current < key <= latest, max_releases)


def select_history(payload: object, max_releases: int = MAX_RELEASES) -> ReleaseNotes | None:
    """Every published release, newest first: the tray menu's "Release notes"
    (R-life-8). Same rules as select_notes, without the version window."""
    return _select(payload, lambda key: True, max_releases)


def _select(
    payload: object, wanted: Callable[[tuple[int, ...]], bool], max_releases: int,
) -> ReleaseNotes | None:
    if not isinstance(payload, list):
        return None
    found: dict[tuple[int, ...], tuple[str, tuple[Block, ...]]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("draft") is True or item.get("prerelease") is True:
            continue
        tag = item.get("tag_name")
        body = item.get("body")
        if not isinstance(tag, str) or not isinstance(body, str):
            continue
        key = _version_key(tag)
        if key is None or key in found or not wanted(key):
            continue
        blocks = parse_body(body)
        if blocks:
            found[key] = (tag.strip().lstrip("vV"), blocks)

    ordered = [found[k] for k in sorted(found, reverse=True)]
    truncated = len(ordered) > max_releases
    versions: list[VersionNotes] = []
    budget = MAX_BLOCKS
    for version, blocks in ordered[:max_releases]:
        if budget <= 0:
            truncated = True
            break
        if len(blocks) > budget:
            blocks = blocks[:budget]
            truncated = True
        budget -= len(blocks)
        versions.append(VersionNotes(version, blocks))
    if not versions:
        return None
    return ReleaseNotes(tuple(versions), truncated)
