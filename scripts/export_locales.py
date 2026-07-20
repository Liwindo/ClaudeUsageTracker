"""Keep the C# locale catalogs in sync with the Python ones.

The Python variant's locale modules (python/src/claude_usage_monitor/locales/
<lang>.py, each defining STRINGS: dict[str, str]) are the single source of
truth for every string BOTH variants show. The C# variant loads flat JSON
catalogs (csharp/ClaudeUsageTracker/Locales/<lang>.json) that are a SUPERSET:
they also contain C#-only strings (settings dialog, toast hint, ...) that have
no Python counterpart and are maintained directly in the JSON files.

Rules enforced per language:
  - every Python key must exist in the C# catalog
  - for keys present in both, the values must be identical
  - C#-only keys are left alone (their cross-language consistency is covered
    by the C# test suite: key-set and placeholder parity against en.json)

Usage:
    python scripts/export_locales.py --check   # verify only, exit 1 on drift
    python scripts/export_locales.py --write   # sync drifted values/keys

Stdlib only, works with any Python >= 3.9 (CI runs it with the runner's
default interpreter; the catalogs are parsed via ast, nothing is imported).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_LOCALES = REPO_ROOT / "python" / "src" / "claude_usage_monitor" / "locales"
CS_LOCALES = REPO_ROOT / "csharp" / "ClaudeUsageTracker" / "Locales"


def load_python_catalog(path: Path) -> dict[str, str]:
    """Extract the STRINGS dict literal without importing the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "STRINGS":
                strings = ast.literal_eval(node.value)
                if not isinstance(strings, dict):
                    raise TypeError(f"{path.name}: STRINGS is not a dict")
                return strings
    raise LookupError(f"{path.name}: no STRINGS assignment found")


def sync_language(lang: str, write: bool) -> list[str]:
    """Return a list of problems for one language (empty = in sync)."""
    py_catalog = load_python_catalog(PY_LOCALES / f"{lang}.py")
    cs_path = CS_LOCALES / f"{lang}.json"
    if not cs_path.exists():
        return [f"{lang}: {cs_path.relative_to(REPO_ROOT)} is missing"]
    cs_catalog = json.loads(cs_path.read_text(encoding="utf-8"))

    problems = []
    for key, value in py_catalog.items():
        if key not in cs_catalog:
            problems.append(f"{lang}: key {key!r} missing in the C# catalog")
        elif cs_catalog[key] != value:
            problems.append(
                f"{lang}: value drift for {key!r}\n"
                f"    python: {value!r}\n"
                f"    csharp: {cs_catalog[key]!r}"
            )

    if problems and write:
        # Preserve the existing key order (and all C#-only keys); new Python
        # keys are appended. Order is irrelevant to the C# loader, this just
        # keeps diffs minimal.
        for key, value in py_catalog.items():
            cs_catalog[key] = value
        cs_path.write_text(
            json.dumps(cs_catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"{lang}: synced {cs_path.relative_to(REPO_ROOT)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify only")
    mode.add_argument("--write", action="store_true", help="sync the JSONs")
    args = parser.parse_args()

    languages = sorted(p.stem for p in PY_LOCALES.glob("*.py") if p.stem != "__init__")
    if not languages:
        print(f"FAIL: no locale modules found under {PY_LOCALES}", file=sys.stderr)
        return 1

    all_problems = []
    for lang in languages:
        all_problems.extend(sync_language(lang, write=args.write))

    if all_problems and args.check:
        print(f"FAIL: {len(all_problems)} locale drift(s) between python/ and csharp/:")
        for problem in all_problems:
            print(f"  {problem}")
        print("Run: python scripts/export_locales.py --write")
        return 1
    if not all_problems:
        print(f"OK: {len(languages)} C# catalogs carry the Python strings verbatim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
