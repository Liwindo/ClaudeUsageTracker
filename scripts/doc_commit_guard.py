"""Claude Code PreToolUse hook: no `git commit` without a doc review.

Wired up in the local, untracked .claude/settings.json for the Bash and
PowerShell tools (Claude Code settings are not committed). The entry:

    {"hooks": {"PreToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{
      "type": "command", "shell": "bash", "timeout": 60,
      "command": "input=$(cat); printf '%s' \"$input\" | grep -Eq 'git[^\"]*commit' || exit 0; printf '%s' \"$input\" | uv run --no-project python \"$CLAUDE_PROJECT_DIR/scripts/doc_commit_guard.py\""
    }]}]}}

For any command that runs `git commit` it

  1. denies the commit while scripts/check_docs.py finds a gap, and
  2. denies it until the docs of the current changes were reviewed with
     scripts/doc_sweep.py and acknowledged (`doc_sweep.py --ack`). The ack is a
     digest of the changes, so editing anything afterwards asks again.

Every other command passes untouched. The match is on the command text, so a
command that merely contains "git commit" (a heredoc writing a test, say) is
blocked too: erring towards a review is the point. Write such text with the
file tools instead. This exists because docs fell behind
three times in a row: they were updated from memory instead of being swept
(REQUIREMENTS.md R-rel-7). Humans committing outside Claude Code are covered by
CI (check_docs.py) and the pull-request checklist instead.

Reads the hook JSON on stdin, prints a hook decision on stdout. Stdlib only.
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_docs  # noqa: E402
import doc_sweep  # noqa: E402

# `git commit`, also after `cd x &&`, `git -C dir commit` or `git -c k=v commit`.
_COMMIT = re.compile(r"(?:^|[\s;&|(])git(?:\s+-[Cc]\s+\S+)*\s+commit\b")

# Enough of the sweep to see what is affected; the full list is one command away.
_MAX_REASON_CHARS = 6000


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def decide(command: str) -> dict | None:
    """The hook decision for one command; None lets it through."""
    if not _COMMIT.search(command):
        return None
    try:
        problems = check_docs.find_problems()
        if problems:
            return _deny("Commit blocked: scripts/check_docs.py found undocumented things "
                         "(R-rel-7):\n  " + "\n  ".join(problems)
                         + "\nDocument them, then commit again.")
        if doc_sweep.ack_matches():
            return None
        out = io.StringIO()
        with redirect_stdout(out):
            doc_sweep.main([])
        sweep = out.getvalue()
    except Exception as exc:  # fail closed for commits: no review, no commit
        return _deny(f"Commit blocked: the doc review check could not run ({exc}).")
    if len(sweep) > _MAX_REASON_CHARS:
        sweep = sweep[:_MAX_REASON_CHARS] + "\n[... cut; run the sweep for the full list]"
    return _deny(
        "Commit blocked until the docs of these changes are reviewed (R-rel-7).\n"
        "1. Run `uv run python scripts/doc_sweep.py --term \"<feature words>\"` "
        "(one --term per concept the change touches) and read EVERY snippet.\n"
        "2. Fix every line that is no longer true, including older stale ones.\n"
        "3. Run `uv run python scripts/doc_sweep.py --ack`, then commit again "
        "(any later edit needs a new review).\n\n" + sweep)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    decision = decide(command) if isinstance(command, str) else None
    if decision is not None:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
