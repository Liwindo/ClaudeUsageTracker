"""Fail if the portable C# EXE bundles an outdated .NET runtime.

The portable EXE is self-contained: it carries its own copy of .NET and WPF,
and that copy is never updated on the user's PC. Which runtime it gets depends
on the SDK the build happens to use, so a release could silently ship an old
runtime with known security holes (2.2.4 shipped 10.0.10 while 10.0.13 was
current). This check reads the runtime packs recorded in the EXE and compares
them with the latest runtime of the same channel in Microsoft's official
release metadata (REQUIREMENTS.md R-rel-8).

If Microsoft has just released a runtime that the SDK on the runner does not
bundle yet, the release fails; use "Re-run failed jobs" later. The check fails
closed: no metadata, no release.

Usage:
    python scripts/check_bundled_runtime.py path/to/ClaudeUsageTracker-Portable-X.Y.Z.exe

Stdlib only, works with any Python >= 3.9 (the release workflow runs it with the
runner's default interpreter). Exit 1 names the outdated or missing runtime.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

# The two runtimes a self-contained WPF app consists of.
REQUIRED = ("Microsoft.NETCore.App", "Microsoft.WindowsDesktop.App")

_PACK = re.compile(rb"runtimepack\.(Microsoft\.[A-Za-z.]+)\.Runtime\.win-x64/(\d+\.\d+\.\d+)")
_METADATA = "https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/{channel}/releases.json"


def bundled_runtimes(exe: bytes) -> dict[str, set[str]]:
    """Runtime name -> versions recorded in the EXE's embedded .deps.json."""
    found: dict[str, set[str]] = {}
    for name, version in _PACK.findall(exe):
        found.setdefault(name.decode(), set()).add(version.decode())
    return found


def find_problems(found: dict[str, set[str]], latest: str) -> list[str]:
    problems = []
    for name in REQUIRED:
        versions = found.get(name)
        if not versions:
            problems.append(f"{name}: no runtime pack found in the EXE")
        elif versions != {latest}:
            problems.append(f"{name}: bundles {', '.join(sorted(versions))}, latest is {latest}")
    return problems


def latest_runtime(channel: str) -> str:
    with urllib.request.urlopen(_METADATA.format(channel=channel), timeout=30) as resp:
        return json.load(resp)["latest-runtime"]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    found = bundled_runtimes(Path(argv[0]).read_bytes())
    versions = sorted(v for vs in found.values() for v in vs)
    if not versions:
        print(f"No .NET runtime pack found in {argv[0]}")
        return 1
    channel = ".".join(versions[0].split(".")[:2])
    latest = latest_runtime(channel)
    problems = find_problems(found, latest)
    if problems:
        print("The portable EXE does not bundle the current .NET runtime:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"OK: the portable EXE bundles .NET {latest}, the latest {channel} runtime.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
