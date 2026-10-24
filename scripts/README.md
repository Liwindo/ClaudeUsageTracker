# scripts/

Shared tooling for both variants. Each script's docstring or header has the details.

| Script | Purpose |
| --- | --- |
| `export_locales.py` | Syncs the C# locale catalogs from the Python source; CI runs `--check` |
| `bump_version.ps1` | Sets the version of both variants in lockstep (run by `release.yml`) |
| `check_changelog.ps1` | Local build guard: the current version has a CHANGELOG section |
| `check_changelog_emoji.py` | CHANGELOG emoji must render on Windows 10 (they end up in the update dialog) |
| `check_docs.py` | Docs name every module, file, asset, script, workflow and config key (CI) |
| `doc_sweep.py` | Lists every doc line a change touches, for review; `--ack` records the review |
| `doc_commit_guard.py` | Claude Code hook: no commit before `check_docs.py` passes and the sweep is acknowledged |
| `validate_dependencies.py` | Post-Dependabot validation of action pins, lock file and the build Python |
| `generate_update_key.ps1` | One-time setup of the offline update-signing key |
| `publish_release.ps1` | Signs the update manifest locally and publishes the draft release |
| `shipped_snapshot.py` | Dependency-graph snapshot of what a published release actually ships |
