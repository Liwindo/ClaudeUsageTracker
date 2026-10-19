"""Fail when the docs miss something that exists in the repo.

Checks what can be checked mechanically, so a doc can never silently fall
behind the code (REQUIREMENTS.md R-rel-7):

  - every Python module of the package is named in python/README.md
  - every C# source/data file of the app is named in csharp/README.md
  - every bundled asset is named in its variant's README
  - every script in scripts/ is named in a tracked doc (scripts/README.md)
  - every workflow in .github/workflows/ is named in a tracked doc
    (.github/workflows/README.md)
  - every Python config key is documented in python/README.md "Configuration"

Prose ("the dialog offers to …") cannot be checked this way; that is what
scripts/doc_sweep.py is for. CLAUDE.md is gitignored, so it never counts as a
doc here: what only CLAUDE.md says, nobody else can read.

Usage:
    python scripts/check_docs.py

Stdlib only, works with any Python >= 3.9 (CI runs it with the runner's
default interpreter; config.py is parsed via ast, nothing is imported).
Exit 1 lists every gap.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_PKG = REPO_ROOT / "python" / "src" / "claude_usage_monitor"
CS_APP = REPO_ROOT / "csharp" / "ClaudeUsageTracker"
PY_README = REPO_ROOT / "python" / "README.md"
CS_README = REPO_ROOT / "csharp" / "README.md"

_SKIP_DIRS = {"__pycache__", "bin", "obj", ".venv", "node_modules", "build", "dist"}


def tracked_docs(root: Path = REPO_ROOT) -> list[Path]:
    """The Markdown files that ship with the repo (CLAUDE.md is gitignored)."""
    docs = [p for p in root.glob("*.md") if p.name != "CLAUDE.md"]
    for folder in ("python", "csharp", "scripts"):
        docs += sorted((root / folder).glob("*.md"))
    docs += sorted((root / ".github").rglob("*.md"))
    return docs


def _files(folder: Path, suffixes: tuple[str, ...] | None = None) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.name not in _SKIP_DIRS
        and (suffixes is None or p.suffix in suffixes)
    )


def config_keys(config_py: Path) -> list[str]:
    """Public fields of the Config dataclass in config.py."""
    tree = ast.parse(config_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Config":
            return [
                stmt.target.id for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                and not stmt.target.id.startswith("_")
            ]
    raise LookupError("no Config class in config.py")


def find_problems(root: Path = REPO_ROOT) -> list[str]:
    pkg = root / PY_PKG.relative_to(REPO_ROOT)
    app = root / CS_APP.relative_to(REPO_ROOT)
    py_readme = (root / PY_README.relative_to(REPO_ROOT)).read_text(encoding="utf-8")
    cs_readme = (root / CS_README.relative_to(REPO_ROOT)).read_text(encoding="utf-8")
    all_docs = "\n".join(p.read_text(encoding="utf-8") for p in tracked_docs(root))
    problems: list[str] = []

    def need(name: str, text: str, where: str, what: str) -> None:
        if name not in text:
            problems.append(f"{what} {name} is not named in {where}")

    for f in _files(pkg, (".py",)):
        if f.name != "__init__.py":
            need(f.name, py_readme, "python/README.md", "Python module")
    for f in _files(app, (".cs", ".json", ".manifest")):
        need(f.name, cs_readme, "csharp/README.md", "C# file")
    for f in _files(pkg / "assets"):
        need(f.name, py_readme, "python/README.md", "Python asset")
    for f in _files(app / "Assets"):
        need(f.name, cs_readme, "csharp/README.md", "C# asset")
    for f in _files(root / "scripts", (".py", ".ps1", ".sh", ".bat")):
        need(f.name, all_docs, "any tracked doc", "Script")
    for f in _files(root / ".github" / "workflows", (".yml", ".yaml")):
        need(f.name, all_docs, "any tracked doc", "Workflow")
    for key in config_keys(pkg / "config.py"):
        if not re.search(rf"(?m)^#?\s*{re.escape(key)}\s*=", py_readme):
            problems.append(f"Config key {key} is not documented in python/README.md")
    return problems


def main() -> int:
    problems = find_problems()
    if problems:
        print("Docs are missing things that exist in the repo:")
        for problem in problems:
            print(f"  {problem}")
        print("Name each one where it belongs (see the script docstring).")
        return 1
    print("OK: every module, file, asset, script, workflow and config key is documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
