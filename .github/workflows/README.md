# Workflows

| Workflow | Purpose |
| --- | --- |
| `ci.yml` | Python variant: lock check, dependency validation, locale, emoji and docs checks, tests; Dependabot automerge |
| `ci-csharp.yml` | C# variant: xunit tests, locale and docs checks; Dependabot automerge |
| `release.yml` | Version bump, CHANGELOG stamp, tag, tests, builds of both variants, draft release |
| `release-integrity.yml` | Re-verifies the signed update manifest on publish and daily |
| `shipped-dependencies.yml` | Files what the published EXE ships as the dependency-graph snapshot |
| `python-pin-watch.yml` | Goes red when a newer CPython patch of the pinned version exists |
| `cpython-3-14-10-watch.yml` | Temporary: comments on issue #46 once uv offers CPython 3.14.10; removed with that bump |

Signing and publishing a release stay local; see the C# README, "Secure in-app updates & release signing".
