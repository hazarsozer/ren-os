#!/usr/bin/env python3
"""
Helper script invoked by the /sf:disable-feed skill.

Marks the current session as feed-disabled by writing the per-session state file that
feed.skip.is_skip_active() honors. Also reports whether a session-start entry has
already been pushed (so the user knows their boat has partially sailed per ADR-021
§"Deletion is hard").

Usage:
    python3 -m scripts.mark_disabled
    python3 -m scripts.mark_disabled --session-id custom-id --reason "stealth-work"

Exit codes:
    0 = marked successfully
    1 = error writing state file (rare; surfaces an actionable error)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make the repo's `feed` package importable from this script location regardless of
# how the user invokes us (`python scripts/mark_disabled.py` vs module path).
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent.parent  # scripts/ → sf-disable-feed/ → skills/ → repo
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from feed import config, skip  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark the current Claude Code session as feed-disabled.")
    parser.add_argument(
        "--session-id",
        default=os.environ.get("CLAUDE_SESSION_ID", "default"),
        help="Override session id. Defaults to $CLAUDE_SESSION_ID or 'default'.",
    )
    parser.add_argument(
        "--reason",
        default="user-disabled",
        help="Reason string written into the state file. Default: 'user-disabled'.",
    )
    args = parser.parse_args()

    # Check if a start-entry was already pushed for this handle — if so, warn the user
    already_pushed = _start_entry_already_pushed_today()

    try:
        skip.mark_session_disabled(session_id=args.session_id, reason=args.reason)
    except OSError as e:
        print(f"ERROR: failed to write state file: {e}", file=sys.stderr)
        return 1

    state_file = config.state_dir() / f"session-{args.session_id}.json"
    print(f"[sf-disable-feed] session marked as feed-disabled: {state_file}")
    print("  All subsequent feed_write_entry calls in this session will be no-ops.")
    print("  This includes /sf:wrap (no end-entry will be pushed).")

    if already_pushed:
        print()
        print("WARNING: a session-start entry was already pushed to the Activity Feed earlier")
        print("         in this session. That entry CANNOT be removed without coordinating a")
        print("         git history rewrite + force-push (per ADR-021).")
        print("         Disable-feed prevents FUTURE writes only.")
        print()
        print("         For full removal, see the ADR-021 deletion procedure or coordinate")
        print("         with the friend group via Slack/Discord/WhatsApp.")

    return 0


def _start_entry_already_pushed_today() -> bool:
    """Heuristic check: does the current handle's <handle>.log.md contain a start entry
    with today's date? If so, the wake-up hook ran and we already announced ourselves.
    """
    try:
        handle = config.handle()
    except Exception:
        return False  # handle not configured; nothing to check

    log_file = config.local_path() / f"{handle}.log.md"
    if not log_file.exists():
        return False

    try:
        text = log_file.read_text(encoding="utf-8")
    except OSError:
        return False

    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    return f"## [{today}" in text and "start |" in text


if __name__ == "__main__":
    sys.exit(main())
