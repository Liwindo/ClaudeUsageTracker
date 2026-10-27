"""scripts/check_bundled_runtime.py: the portable C# EXE must bundle the latest
.NET runtime of its channel (REQUIREMENTS.md R-rel-8)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_bundled_runtime", ROOT / "scripts" / "check_bundled_runtime.py"
)
br = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = br
spec.loader.exec_module(br)


def _exe(version_core: str, version_desktop: str) -> bytes:
    """What a single-file bundle's embedded .deps.json looks like, in junk."""
    return (b"MZ\x00\x01junk\"runtimepack.Microsoft.NETCore.App.Runtime.win-x64/"
            + version_core.encode() + b"\": {\x00 more junk "
            + b"\"runtimepack.Microsoft.WindowsDesktop.App.Runtime.win-x64/"
            + version_desktop.encode() + b"\": {\xff")


def test_reads_both_runtime_packs():
    assert br.bundled_runtimes(_exe("10.0.14", "10.0.14")) == {
        "Microsoft.NETCore.App": {"10.0.14"},
        "Microsoft.WindowsDesktop.App": {"10.0.14"},
    }


def test_current_runtime_passes():
    assert br.find_problems(br.bundled_runtimes(_exe("10.0.14", "10.0.14")), "10.0.14") == []


def test_outdated_runtime_fails():
    """The case this guards against: 2.3.1 shipped 10.0.13 after 10.0.14 existed."""
    problems = br.find_problems(br.bundled_runtimes(_exe("10.0.13", "10.0.13")), "10.0.14")
    assert len(problems) == 2
    assert "bundles 10.0.13, latest is 10.0.14" in problems[0]


def test_one_outdated_runtime_is_enough_to_fail():
    problems = br.find_problems(br.bundled_runtimes(_exe("10.0.14", "10.0.13")), "10.0.14")
    assert problems == ["Microsoft.WindowsDesktop.App: bundles 10.0.13, latest is 10.0.14"]


def test_framework_dependent_exe_fails():
    """An EXE without runtime packs is not self-contained, so it is no portable EXE."""
    assert len(br.find_problems(br.bundled_runtimes(b"MZ no packs here"), "10.0.14")) == 2


def test_main_compares_with_the_metadata_channel(tmp_path, monkeypatch):
    exe = tmp_path / "Portable.exe"
    exe.write_bytes(_exe("10.0.13", "10.0.13"))
    asked = []
    monkeypatch.setattr(br, "latest_runtime", lambda channel: asked.append(channel) or "10.0.14")
    assert br.main([str(exe)]) == 1
    assert asked == ["10.0"]
    exe.write_bytes(_exe("10.0.14", "10.0.14"))
    assert br.main([str(exe)]) == 0
