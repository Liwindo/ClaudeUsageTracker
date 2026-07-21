<!-- Thanks for contributing! Keep the two variants (python/ + csharp/) in step. -->

## What & why

<!-- Short description of the change and the reason for it. -->

## Requirements checklist

- [ ] **Behavioural change?** If this adds, removes, or changes any user-observable
      behaviour or invariant, [`REQUIREMENTS.md`](../REQUIREMENTS.md) is updated in
      **this** PR (new `R-…` id, or an edit to an existing one). See its
      "Keeping this file complete" section.
- [ ] **Both variants?** Cross-variant behaviour is implemented in **both**
      `python/` and `csharp/` — or the requirement is marked `variant-specific`
      with a reason.
- [ ] **Proof.** New/changed behaviour has a test, or — for GUI/OS/timing code
      that can't be unit-tested — a note in the PR of the real scenario that was
      run and observed. The relevant `R-…` id is cited in the test name or PR.
- [ ] **CHANGELOG.** A user-facing entry is added under `## Unreleased` (only if
      the change is user-facing).
- [ ] Tests pass locally: `uv run pytest` (Python) and
      `dotnet test csharp/ClaudeUsageTracker.slnx` (C#).
