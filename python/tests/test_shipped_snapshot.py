"""Unit tests for scripts/shipped_snapshot.py.

The fixtures are small synthetic deps.json payloads embedded in fake binary
noise. The real-asset path (extracting from a published single-file EXE) was
checked against ClaudeUsageTracker-Portable-2.2.4.exe and runs in
.github/workflows/shipped-dependencies.yml on every published release.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Monorepo root (this file lives in python/tests/, the script in scripts/).
REPO_ROOT = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "shipped_snapshot", REPO_ROOT / "scripts" / "shipped_snapshot.py"
)
ss = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ss
spec.loader.exec_module(ss)

TARGET = ".NETCoreApp,Version=v10.0/win-x64"


def make_deps(version="2.2.4", extra_libraries=None):
    """A minimal app deps.json shaped like the SDK's single-file output."""
    libraries = {
        f"ClaudeUsageTrackerCS/{version}": {"type": "project"},
        "Microsoft.Data.Sqlite/10.0.10": {"type": "package"},
        "Microsoft.Data.Sqlite.Core/10.0.10": {"type": "package"},
        "runtimepack.Microsoft.NETCore.App.Runtime.win-x64/10.0.10": {"type": "runtimepack"},
    }
    libraries.update(extra_libraries or {})
    return {
        "runtimeTarget": {"name": TARGET},
        "targets": {
            TARGET: {
                f"ClaudeUsageTrackerCS/{version}": {
                    "dependencies": {"Microsoft.Data.Sqlite": "10.0.10"},
                },
                "Microsoft.Data.Sqlite/10.0.10": {
                    "dependencies": {"Microsoft.Data.Sqlite.Core": "10.0.10"},
                },
                "Microsoft.Data.Sqlite.Core/10.0.10": {},
                "runtimepack.Microsoft.NETCore.App.Runtime.win-x64/10.0.10": {"runtime": {}},
            }
        },
        "libraries": libraries,
    }


def embed(*objects):
    """Wrap JSON objects in binary noise the way a PE bundle would."""
    blob = b"MZ\x90\x00\xff\xfe" + b"\x00" * 64
    for obj in objects:
        blob += json.dumps(obj, indent=2).encode("utf-8") + b"\x00\xff\xd8junk{"
    return blob


def snapshot(deps, tag="v2.2.4"):
    return ss.build_snapshot(deps, tag=tag, sha="a" * 40, ref="refs/heads/master",
                             job_id="1", scanned="2026-10-17T00:00:00Z",
                             asset_name="ClaudeUsageTracker-Portable-2.2.4.exe")


def resolved(snap):
    return snap["manifests"][ss.MANIFEST_NAME]["resolved"]


# --- extract_deps_json -------------------------------------------------------

def test_extract_finds_the_app_deps_json_in_binary_noise():
    deps = make_deps()
    assert ss.extract_deps_json(embed(deps)) == deps


def test_extract_ignores_deps_shaped_objects_without_a_project():
    framework_deps = {"runtimeTarget": {"name": TARGET}, "targets": {}, "libraries": {
        "Microsoft.NETCore.App/10.0.10": {"type": "package"}}}
    deps = make_deps()
    assert ss.extract_deps_json(embed(framework_deps, deps)) == deps


def test_extract_rejects_an_exe_without_a_deps_json():
    with pytest.raises(ValueError, match="found 0"):
        ss.extract_deps_json(b"MZ\x00 no bundle here")


def test_extract_rejects_two_app_deps_json():
    with pytest.raises(ValueError, match="found 2"):
        ss.extract_deps_json(embed(make_deps(), make_deps()))


# --- build_snapshot ----------------------------------------------------------

def test_runtime_pack_is_reported_under_its_nuget_name():
    entry = resolved(snapshot(make_deps()))["Microsoft.NETCore.App.Runtime.win-x64"]
    # Advisories are filed against the package without the "runtimepack." prefix.
    assert entry["package_url"] == "pkg:nuget/Microsoft.NETCore.App.Runtime.win-x64@10.0.10"
    assert entry["relationship"] == "direct"
    assert entry["scope"] == "runtime"


def test_relationships_follow_the_project_dependencies():
    r = resolved(snapshot(make_deps()))
    assert r["Microsoft.Data.Sqlite"]["relationship"] == "direct"
    assert r["Microsoft.Data.Sqlite.Core"]["relationship"] == "indirect"
    assert r["Microsoft.Data.Sqlite"]["dependencies"] == ["pkg:nuget/Microsoft.Data.Sqlite.Core@10.0.10"]


def test_project_itself_is_not_reported_as_a_dependency():
    assert not any("ClaudeUsageTrackerCS" in k for k in resolved(snapshot(make_deps())))


def test_snapshot_identity_is_stable_across_releases():
    # Same correlator + detector name is what makes a new release replace the old snapshot.
    a, b = snapshot(make_deps("2.2.4")), snapshot(make_deps("2.2.5"), tag="v2.2.5")
    assert a["job"]["correlator"] == b["job"]["correlator"] == ss.CORRELATOR
    assert a["detector"]["name"] == b["detector"]["name"] == ss.DETECTOR_NAME
    assert a["ref"] == "refs/heads/master"


def test_rejects_an_exe_that_does_not_match_the_tag():
    with pytest.raises(ValueError, match="EXE is version 2.2.4, but the release tag is v2.2.3"):
        snapshot(make_deps("2.2.4"), tag="v2.2.3")


def test_rejects_unknown_library_types_instead_of_guessing():
    deps = make_deps(extra_libraries={"Something/1.0.0": {"type": "reference"}})
    with pytest.raises(ValueError, match="unknown deps.json library type 'reference'"):
        snapshot(deps)
