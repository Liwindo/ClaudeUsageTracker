"""Report the dependencies a published C# release actually ships to GitHub.

GitHub's dependency graph cannot see inside the portable EXE. Static parsing
of the .csproj yields only the direct PackageReferences, and automatic
dependency submission restores on an ubuntu runner with whatever SDK is
current there: it reported linux-x64 and ASP.NET Core runtime packs that never
ship, and missed the win-x64 .NET and WindowsDesktop runtimes the
self-contained EXE bundles at the version of the SDK that built the release.

The single-file EXE embeds the app's .deps.json, which lists exactly what was
bundled: every NuGet package plus the runtime packs at their real versions.
This script extracts it and turns it into a dependency-submission snapshot, so
Dependabot alerts describe the published release and close only once a fixed
release is published - not when master merely builds with a newer SDK.

Usage:
    python scripts/shipped_snapshot.py --exe ClaudeUsageTracker-Portable-X.Y.Z.exe \\
        --tag vX.Y.Z --sha <default-branch head> --job-id <run id> -o snapshot.json

Stdlib only, any Python >= 3.9: .github/workflows/shipped-dependencies.yml runs
it with the runner's default interpreter and posts the result to the
dependency-submission API.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# A newer snapshot replaces an older one only for the same correlator AND
# detector name, so both must stay stable across releases.
CORRELATOR = "shipped-release-csharp-portable"
DETECTOR_NAME = "shipped-release-deps-json"
DETECTOR_VERSION = "1.0.0"
DETECTOR_URL = "https://github.com/Liwindo/ClaudeUsageTracker/blob/master/scripts/shipped_snapshot.py"
MANIFEST_NAME = "ClaudeUsageTracker-Portable (published release)"
MANIFEST_PATH = "csharp/ClaudeUsageTracker/ClaudeUsageTracker.csproj"

DEPS_MARKER = b'"runtimeTarget"'
# The app's deps.json is a few KB; the window only bounds the decode.
DEPS_WINDOW = 4 * 1024 * 1024


def extract_deps_json(blob: bytes) -> dict:
    """Find the app's .deps.json embedded (uncompressed) in a single-file EXE.

    A bundle can carry more than one deps-shaped object; the app's own is the
    one that declares a library of type "project". Exactly one must match.
    """
    decoder = json.JSONDecoder()
    candidates = []
    pos = blob.find(DEPS_MARKER)
    while pos != -1:
        start = blob.rfind(b"{", 0, pos)
        if start != -1:
            text = blob[start:start + DEPS_WINDOW].decode("utf-8", errors="replace")
            try:
                obj, _ = decoder.raw_decode(text)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict) and "libraries" in obj and "targets" in obj:
                libs = obj["libraries"].values()
                if any(lib.get("type") == "project" for lib in libs):
                    candidates.append(obj)
        pos = blob.find(DEPS_MARKER, pos + 1)
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one app deps.json in the EXE, found {len(candidates)}")
    return candidates[0]


def _split_key(key: str) -> tuple[str, str]:
    name, sep, version = key.partition("/")
    if not sep or not name or not version:
        raise ValueError(f"malformed deps.json library key: {key!r}")
    return name, version


def _purl(name: str, version: str) -> str:
    return f"pkg:nuget/{name}@{version}"


def build_snapshot(deps: dict, *, tag: str, sha: str, ref: str, job_id: str,
                   scanned: str, asset_name: str, job_url: str | None = None) -> dict:
    """Turn a deps.json into a dependency-submission snapshot for the release."""
    target_name = deps["runtimeTarget"]["name"]
    target = deps["targets"][target_name]
    libraries = deps["libraries"]

    projects = [k for k, v in libraries.items() if v.get("type") == "project"]
    if len(projects) != 1:
        raise ValueError(f"expected one project library, found {projects}")
    project_key = projects[0]

    # Guard against reporting the wrong asset under this tag.
    _, project_version = _split_key(project_key)
    if project_version != tag.removeprefix("v"):
        raise ValueError(f"EXE is version {project_version}, but the release tag is {tag}")

    direct = {f"{n}/{v}" for n, v in target[project_key].get("dependencies", {}).items()}

    resolved = {}
    for key, lib in sorted(libraries.items()):
        kind = lib.get("type")
        if kind == "project":
            continue
        if kind not in ("package", "runtimepack"):
            # Fail loudly: a red run keeps the previous snapshot, a guessed
            # mapping would put a wrong one in the graph.
            raise ValueError(f"unknown deps.json library type {kind!r} for {key}")
        name, version = _split_key(key)
        if kind == "runtimepack":
            # deps.json key "runtimepack.Microsoft.NETCore.App.Runtime.win-x64"
            # is the NuGet package the advisories are filed against.
            name = name.removeprefix("runtimepack.")
        children = target.get(key, {}).get("dependencies", {})
        resolved[name] = {
            "package_url": _purl(name, version),
            # The runtime packs are bundled into the EXE by the publish itself.
            "relationship": "direct" if key in direct or kind == "runtimepack" else "indirect",
            "scope": "runtime",
            "dependencies": sorted(_purl(n, v) for n, v in children.items()),
        }

    job = {"correlator": CORRELATOR, "id": job_id}
    if job_url:
        job["html_url"] = job_url
    return {
        "version": 0,
        "job": job,
        "sha": sha,
        "ref": ref,
        "detector": {"name": DETECTOR_NAME, "version": DETECTOR_VERSION, "url": DETECTOR_URL},
        "scanned": scanned,
        "metadata": {"release": tag, "asset": asset_name, "runtimeTarget": target_name},
        "manifests": {
            MANIFEST_NAME: {
                "name": MANIFEST_NAME,
                "file": {"source_location": MANIFEST_PATH},
                "resolved": resolved,
            }
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", type=Path, required=True, help="published portable single-file EXE")
    parser.add_argument("--tag", required=True, help="release tag the EXE belongs to, e.g. v2.2.4")
    parser.add_argument("--sha", required=True, help="commit the snapshot is filed under (default-branch head)")
    parser.add_argument("--ref", default="refs/heads/master", help="branch Dependabot alerts are computed for")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--job-url")
    parser.add_argument("--scanned", help="ISO-8601 timestamp (default: now, UTC)")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)

    deps = extract_deps_json(args.exe.read_bytes())
    scanned = args.scanned or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot = build_snapshot(deps, tag=args.tag, sha=args.sha, ref=args.ref, job_id=args.job_id,
                              scanned=scanned, asset_name=args.exe.name, job_url=args.job_url)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    resolved = snapshot["manifests"][MANIFEST_NAME]["resolved"]
    print(f"{args.exe.name} ({args.tag}): {len(resolved)} shipped components", file=sys.stderr)
    for entry in resolved.values():
        print(f"  {entry['relationship']:<8} {entry['package_url']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
