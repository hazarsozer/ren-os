"""
feed.skip — single source of truth for the opt-out chain.

Per ADR-021. Three independent surfaces, highest precedence wins:

1. /sf:disable-feed  → writes ~/.startup-framework/state/session-<id>.json with skip_feed=true
2. SF_SKIP_FEED=1   → process-tree env var
3. --skip-feed      → per-/sf:wrap CLI flag (passed in as wrap_flag arg)

If any is active, `is_skip_active()` returns (True, <reason>). Callers
(feed_write_entry, hooks, skills) MUST gate their writes on this single function so
behavior stays consistent and observable.

This is the ONE module that ships a real implementation in the scaffold phase (task #17)
— it has no git/network dependencies, so it's safe to release early. Lifecycle-2's
cache-verification needs deterministic skip behavior to test against.
"""

from __future__ import annotations

import json
import os
from typing import Literal

from feed import config


SkipReason = Literal["session-disabled", "env-var", "wrap-flag", "not-skipping"]

SF_SKIP_FEED_ENV = "SF_SKIP_FEED"
"""Env var name. Set to '1', 'true', 'yes' (case-insensitive) to enable. Anything else = disabled."""

CLAUDE_SESSION_ID_ENV = "CLAUDE_SESSION_ID"
"""Env var Claude Code populates with the current session ID. Used to locate the
per-session state file written by /sf:disable-feed. If unset, session-disabled check
falls back to the most-recent state file (best effort)."""


def is_skip_active(wrap_flag: bool = False) -> tuple[bool, SkipReason]:
    """Return (skip?, reason) per the precedence chain.

    Args:
        wrap_flag: True if /sf:wrap was called with --skip-feed. Lowest precedence.

    Returns:
        Tuple of (bool, reason string). When skip is True, the reason is one of:
        - "session-disabled" — /sf:disable-feed state file says skip
        - "env-var"          — SF_SKIP_FEED is truthy
        - "wrap-flag"        — the wrap_flag arg was True
        When skip is False, reason is "not-skipping".

    The precedence is evaluated highest-first, so /sf:disable-feed wins over env var
    wins over wrap-flag. This matters for the diagnostic message — we want to tell the
    user the FIRST reason, not the last, so they know which lever they pulled.
    """
    if _session_disabled():
        return True, "session-disabled"
    if _env_var_set():
        return True, "env-var"
    if wrap_flag:
        return True, "wrap-flag"
    return False, "not-skipping"


def _env_var_set() -> bool:
    """Return True if SF_SKIP_FEED env var is set to a truthy value."""
    value = os.environ.get(SF_SKIP_FEED_ENV, "")
    return value.strip().lower() in ("1", "true", "yes")


def _session_disabled() -> bool:
    """Return True if the current session has been disabled via /sf:disable-feed.

    Implementation: looks for ~/.startup-framework/state/session-<id>.json with
    skip_feed=true. The session ID is read from CLAUDE_SESSION_ID env var if set;
    otherwise we fall back to the most-recent state file (best-effort fallback for
    test environments where the env var isn't set).
    """
    state_file = _session_state_file()
    if state_file is None or not state_file.exists():
        return False
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Malformed state file — fail open (do not skip). User can re-run /sf:disable-feed.
        return False
    return bool(data.get("skip_feed", False))


def _session_state_file():
    """Return the Path of the current session's state file, or None if undetermined.

    Resolution: CLAUDE_SESSION_ID env var → ~/.startup-framework/state/session-<id>.json

    Per F6 review fix (2026-05-28): the previous fallback to "most-recent state file"
    when CLAUDE_SESSION_ID was unset caused cross-session marker leak — a friend's
    `/sf:disable-feed` from session A could silently disable session B in any env
    where the env var wasn't set. We now fail open: missing env var → return None →
    `_session_disabled()` returns False → only env-var and wrap-flag skip surfaces
    remain active.

    Tests that need to verify session-disabled behavior must explicitly set
    CLAUDE_SESSION_ID (see test_session_disabled_marker_triggers_skip).
    """
    state_dir = config.state_dir()
    session_id = os.environ.get(CLAUDE_SESSION_ID_ENV, "").strip()
    if not session_id:
        return None
    return state_dir / f"session-{session_id}.json"


def mark_session_disabled(session_id: str | None = None, reason: str = "user-disabled") -> None:
    """Write the session-disabled marker. Called by /sf:disable-feed.

    Idempotent — writes the same content every time for a given (session_id, reason).
    """
    import time

    state_dir = config.state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    sid = session_id or os.environ.get(CLAUDE_SESSION_ID_ENV, "default")
    state_file = state_dir / f"session-{sid}.json"

    payload = {
        "skip_feed": True,
        "reason": reason,
        "timestamp": int(time.time()),
    }
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
