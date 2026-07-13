"""Post-Dependabot validation of everything a dependency bump can touch.

CI runs this on every push and pull request, and the automerge job only runs
after the test job succeeds — so a Dependabot PR can never auto-merge unless
every check below passes. Run locally with:

    uv run python scripts/validate_dependencies.py

Checks, per component:

  GitHub Actions (.github/workflows/*.yml)
    - Every third-party action is pinned to a 40-hex commit SHA and carries a
      trailing "# vX.Y.Z" marker (GitHub-owned "actions/*" may use tag pins,
      their releases are immutable).
    - Each pinned SHA is verified against its marker's tag via the GitHub
      compare API: "identical" or "ahead" (tag moved on, Dependabot will
      catch up) pass; "behind", "diverged" or an unknown SHA/tag fail —
      that is a lying marker or a poisoned pin.
    - Comment blocks directly above a "uses:" step must not contain version
      numbers: Dependabot updates the SHA and the trailing marker but never
      prose comments, so any version there goes stale on the next bump.

  Dependabot config (.github/dependabot.yml)
    - Still covers both the "uv" and "github-actions" ecosystems, and still
      ignores pyinstaller major bumps (those need a manual spec-file review).

  Python toolchain (.python-version)
    - The interpreter running this script matches the pin exactly. The pin is
      load-bearing: GitHub runners' default Python has an OpenSSL TLS
      fingerprint that Cloudflare blocks with 403 on claude.ai requests.

The Python package itself (pyproject.toml + uv.lock) is covered by separate
CI steps: "uv lock --check" proves the lockfile matches pyproject.toml, the
pytest suite proves the app works with the bumped versions, and Dependabot
PRs additionally get a PyInstaller smoke build of the EXE.

Exit code 0 = all checks pass; 1 = at least one FAIL line was printed.
--offline skips the GitHub API verification (for air-gapped local runs).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# GitHub-owned orgs whose actions have immutable releases; tag pins are fine.
FIRST_PARTY_OWNERS = {"actions", "github"}

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
USES_RE = re.compile(r"^(?P<indent>\s*(?:-\s+)?)uses:\s*(?P<spec>[^\s#]+)(?:\s*#\s*(?P<marker>\S+))?")
VERSION_MARKER_RE = re.compile(r"^v\d+(?:\.\d+)*$")
PROSE_VERSION_RE = re.compile(r"\bv\d+\.\d+(?:\.\d+)*\b")


@dataclass
class UsesRef:
    path: Path
    line_no: int  # 1-based
    action: str  # owner/repo or owner/repo/path
    ref: str  # SHA or tag
    marker: str | None  # trailing "# vX.Y.Z" comment, if any

    @property
    def owner(self) -> str:
        return self.action.split("/", 1)[0]

    @property
    def repo(self) -> str:
        # owner/repo[/path] -> owner/repo
        return "/".join(self.action.split("/")[:2])

    @property
    def where(self) -> str:
        return f"{self.path.name}:{self.line_no}"


def parse_uses(path: Path, text: str) -> list[UsesRef]:
    refs = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = USES_RE.match(line)
        if not m:
            continue
        spec = m.group("spec")
        if "@" not in spec:
            continue  # local composite action reference, nothing to pin
        action, ref = spec.rsplit("@", 1)
        refs.append(UsesRef(path, i, action, ref, m.group("marker")))
    return refs


def check_pins(refs: list[UsesRef]) -> list[str]:
    """Third-party actions must be SHA-pinned and carry a version marker."""
    findings = []
    for r in refs:
        if SHA_RE.match(r.ref):
            if not (r.marker and VERSION_MARKER_RE.match(r.marker)):
                findings.append(
                    f"{r.where}: SHA-pinned action {r.action} has no trailing"
                    ' "# vX.Y.Z" marker — Dependabot needs it to track updates'
                )
        elif r.owner not in FIRST_PARTY_OWNERS:
            findings.append(
                f"{r.where}: third-party action {r.action}@{r.ref} is not"
                " pinned to a commit SHA (tags can be moved, SHAs cannot)"
            )
    return findings


def check_comment_staleness(path: Path, text: str) -> list[str]:
    """Comment blocks directly above a uses: step must be version-free."""
    findings = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not USES_RE.match(line):
            continue
        j = i - 1
        while j >= 0 and lines[j].lstrip().startswith("#"):
            if PROSE_VERSION_RE.search(lines[j]):
                findings.append(
                    f"{path.name}:{j + 1}: comment above a uses: step contains a"
                    " version number — Dependabot never edits prose comments, so"
                    " this goes stale on the next bump; keep it version-free"
                )
            j -= 1
    return findings


def github_api_get(url: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, {}


def verify_pins_against_tags(refs: list[UsesRef], fetch=github_api_get) -> list[str]:
    """The pinned SHA must be the marker's tag commit, or an ancestor of it.

    compare/{sha}...{tag} status: "identical" = pin is exactly the tag;
    "ahead" = the tag moved on since the pin (a moving major tag like v3 —
    Dependabot bumps it on its next run, not an error). "behind"/"diverged"
    mean the marker lies about the pin; 404 means the SHA or tag does not
    exist in that repository — both are supply-chain red flags.
    """
    findings = []
    seen: set[tuple[str, str, str]] = set()
    for r in refs:
        if not SHA_RE.match(r.ref) or not (r.marker and VERSION_MARKER_RE.match(r.marker)):
            continue  # unpinned/unmarked cases are reported by check_pins
        key = (r.repo, r.ref, r.marker)
        if key in seen:
            continue
        seen.add(key)
        url = f"https://api.github.com/repos/{r.repo}/compare/{r.ref}...{r.marker}"
        status, body = fetch(url)
        if status == 404:
            findings.append(
                f"{r.where}: {r.action} — SHA {r.ref[:12]} or tag {r.marker} not"
                f" found in {r.repo}; the pin or its marker is wrong"
            )
        elif status != 200:
            findings.append(
                f"{r.where}: {r.action} — GitHub API returned HTTP {status}"
                f" comparing {r.ref[:12]} with {r.marker}; cannot verify the pin"
            )
        elif body.get("status") not in ("identical", "ahead"):
            findings.append(
                f"{r.where}: {r.action} — pinned SHA {r.ref[:12]} is"
                f" '{body.get('status')}' relative to tag {r.marker}; the marker"
                " does not describe this commit"
            )
    return findings


def check_dependabot_config(root: Path) -> list[str]:
    findings = []
    path = root / ".github" / "dependabot.yml"
    if not path.is_file():
        return [f"{path.name}: missing — Dependabot is not configured"]
    text = path.read_text(encoding="utf-8")
    for ecosystem in ("uv", "github-actions"):
        if not re.search(rf"package-ecosystem:\s*{ecosystem}\b", text):
            findings.append(
                f"{path.name}: ecosystem '{ecosystem}' is no longer covered —"
                " its dependencies would silently stop being updated"
            )
    if "pyinstaller" not in text or "semver-major" not in text:
        findings.append(
            f"{path.name}: the pyinstaller major-bump ignore is gone — majors"
            " need a manual spec-file review before merging"
        )
    return findings


def check_python_pin(root: Path, running: str | None = None) -> list[str]:
    path = root / ".python-version"
    if not path.is_file():
        return [
            ".python-version: missing — without the pin, GitHub runners use a"
            " Python whose TLS fingerprint Cloudflare blocks (HTTP 403)"
        ]
    pinned = path.read_text(encoding="utf-8").strip()
    running = running or platform.python_version()
    if running != pinned:
        return [
            f".python-version pins {pinned} but this run uses Python {running} —"
            " the Cloudflare-403 fix depends on the exact pinned version"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="skip GitHub API pin verification")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to validate")
    args = parser.parse_args(argv)

    findings: list[str] = []
    all_refs: list[UsesRef] = []
    workflows = sorted((args.root / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        findings.append(".github/workflows: no workflow files found")
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        refs = parse_uses(path, text)
        all_refs.extend(refs)
        findings.extend(check_pins(refs))
        findings.extend(check_comment_staleness(path, text))
    if args.offline:
        print("SKIP: GitHub API pin verification (--offline)")
    else:
        findings.extend(verify_pins_against_tags(all_refs))
    findings.extend(check_dependabot_config(args.root))
    findings.extend(check_python_pin(args.root))

    for finding in findings:
        print(f"FAIL: {finding}")
    if findings:
        print(f"\n{len(findings)} finding(s).")
        return 1
    print(f"OK: {len(all_refs)} action reference(s) across {len(workflows)} workflow(s), dependabot config and Python pin all validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
