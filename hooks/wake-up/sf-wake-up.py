#!/usr/bin/env python3
"""
sf-wake-up.py — Startup-Framework SessionStart wake-up hook.

Per ADR-008 (verified 2026-05-28 — see hooks/wake-up/verify/REPORT-evidence.md):
emits a wiki context payload via `hookSpecificOutput.additionalContext` to be
injected into the conversation layer as a system-reminder. The cacheable
system-prompt prefix is unmodified; cache benefit is preserved across sessions.

Locked path convention (per team-lead 2026-05-28):
  - Framework root: ~/.startup-framework/
  - Wiki: ~/.startup-framework/wiki/
  - Activity Feed: ~/.startup-framework/activity-feed/

Operating model per CC_API_NOTES.md:
  1. Read stdin JSON (CC's SessionStart event)
  2. Resolve cwd → project context (if any)
  3. Read master + project wiki indices, recent log tails
  4. Read friends'-activity tail from feed module (silent-degrade per feed-2's contract)
  5. Compose additionalContext payload; truncate to <5K tokens
  6. Emit JSON to stdout; exit 0
  7. NEVER raise — graceful failure logs to stderr + emits empty context

Idempotency: hook is read-only on the wiki (writes go via feed module).
Order-insensitive: no dependency on other plugins' hooks.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from pathlib import Path

# Late import: keep hook startup fast (avoid importing lib/ unless needed)


# Per CC SessionStart matcher: "source" enum is startup/resume/clear/compact
# We fire on startup AND compact (re-injection after context compaction), but
# NOT on resume or clear (those have their own state). The matcher is set in
# the hooks.json registration.

logger = logging.getLogger("sf-wake-up")

# Log to ~/.startup-framework/logs/wake-up-<date>.log (stderr fallback)
def _setup_logging() -> None:
    log_dir = Path.home() / ".startup-framework" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        log_path = log_dir / f"wake-up-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
        handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _build_feed_callback(*, cwd: str):
    """
    Build the fetch_feed_tail callable consumed by compose_wake_up_context.

    Per team-lead's locked sequence (#13 task description):
      1. feed.pull() 10s timeout best-effort (never blocks the session)
      2. feed.feed_write_session_start(handle, cwd, schema_version=1, skip=...)
      3. feed.feed_read_friends_tails(handle, n_per_friend=5, include_self=True,
                                       max_tokens=2500, refresh=False)

    Returns a callable that returns the rendered friends-activity block
    (including freshness header from FriendsTail.formatted_header).

    Silent-degrade per feed-2's contract:
      - HandleNotConfiguredError / SchemaVersionMismatchError → return ""
      - feed module not importable → return ""
      - pull / write_session_start failures → log but continue with read
      - read returns empty list → return ""

    All exceptions caught inside; never propagates up.
    """
    def fetch_tail() -> str:
        try:
            from feed import (
                feed_read_friends_tails,
                feed_write_session_start,
                is_skip_active,
                pull as feed_pull,
            )
            from feed.config import (
                HandleNotConfiguredError,
                SchemaVersionMismatchError,
                handle as get_handle,
            )
        except ImportError:
            logger.info("feed module unavailable; skipping feed integration")
            return ""

        # Resolve handle (silent-degrade on identity not bootstrapped)
        try:
            handle = get_handle()
        except (HandleNotConfiguredError, SchemaVersionMismatchError) as exc:
            logger.info("feed identity not configured (%s); skipping feed integration",
                        type(exc).__name__)
            return ""
        except Exception:  # noqa: BLE001 — defensive
            logger.warning("get_handle raised unexpected exception", exc_info=True)
            return ""

        # Step 1: best-effort pull
        try:
            feed_pull()
        except Exception:  # noqa: BLE001
            logger.info("feed.pull failed silently; proceeding with local clone",
                        exc_info=True)

        # Step 2: write session-start entry
        try:
            skip_active, _reason = is_skip_active()
            feed_write_session_start(
                handle=handle,
                cwd=cwd,
                schema_version=1,
                skip=skip_active,
            )
        except Exception:  # noqa: BLE001
            logger.info("feed_write_session_start failed silently", exc_info=True)

        # Step 3: read friends tail (refresh=False since pull just happened)
        try:
            tail = feed_read_friends_tails(
                own_handle=handle,
                n_per_friend=5,
                include_self=True,
                max_tokens=2500,
                refresh=False,
            )
        except Exception:  # noqa: BLE001
            logger.warning("feed_read_friends_tails failed silently", exc_info=True)
            return ""

        return _render_friends_tail(tail)

    return fetch_tail


def _render_friends_tail(tail) -> str:
    """
    Render a FriendsTail dataclass into a markdown block per the lifecycle ↔
    feed contract (rider 1: freshness header inline + per-friend bullets via
    feed.format_entry_one_line).

    Falls back gracefully when the tail is empty or feed.format_entry_one_line
    is unavailable.
    """
    formatted_header = getattr(tail, "formatted_header", None)
    friends = getattr(tail, "friends", None) or {}
    stale = bool(getattr(tail, "stale", False))

    if not formatted_header or not friends:
        return ""

    lines: list[str] = [formatted_header]
    if stale:
        lines.append("*(feed data may be stale — last sync was >24h ago)*")
        lines.append("")

    try:
        from feed import format_entry_one_line
    except ImportError:
        format_entry_one_line = None

    for handle_key, entries in friends.items():
        if not entries:
            continue
        for entry in entries:
            if format_entry_one_line is not None:
                try:
                    lines.append(format_entry_one_line(entry))
                    continue
                except Exception:  # noqa: BLE001
                    pass
            # Fallback rendering
            entry_handle = getattr(entry, "handle", handle_key)
            entry_summary = getattr(entry, "summary", "") or getattr(entry, "raw_line", "")
            lines.append(f"- {entry_handle}: {entry_summary}")

    return "\n".join(lines).rstrip() + "\n"


def _resolve_wiki_root() -> Path:
    """
    Resolve the wiki root with an explicit three-way fallback matching the
    shell scripts' `${SF_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}}`
    (see skills/sf-update/scripts/snapshot.sh:23).

    Order: SF_WIKI_ROOT → CLAUDE_PLUGIN_OPTION_WIKIROOT → $HOME/.startup-framework/wiki.

    Each env var is `.strip()`-guarded so empty/whitespace counts as unset
    (stricter than bash's `:-`, which only treats truly-empty as unset). This
    closes the C1 bug: the old `Path(os.environ.get("SF_WIKI_ROOT","")) or (...)`
    never fell back because `Path("")` is `PosixPath('.')` (truthy), so
    CLAUDE_PLUGIN_OPTION_WIKIROOT was ignored and wiki_root silently became CWD.

    Each resolved value is also passed through os.path.expandvars + expanduser
    before becoming a Path. The plugin.json userConfig default is the literal
    string `${HOME}/.startup-framework/wiki`; if Claude Code forwards it to
    CLAUDE_PLUGIN_OPTION_WIKIROOT without expanding `${HOME}`, `Path(val)` would
    otherwise be a broken literal-`${HOME}` path — the same C1 failure class one
    layer down. expandvars handles `${HOME}`/`$HOME`; expanduser handles `~`.
    Harmless no-op if CC already expands ("never trust external data").
    """
    for var in ("SF_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT"):
        val = os.environ.get(var, "").strip()
        if val:
            return Path(os.path.expanduser(os.path.expandvars(val)))
    return Path.home() / ".startup-framework" / "wiki"


def main() -> int:
    """
    Entry point.

    Reads stdin JSON; emits stdout JSON. Always returns 0 (graceful failure
    is the load-bearing safety invariant — never abort the session).
    """
    _setup_logging()

    # Read CC's SessionStart event payload
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("could not parse stdin JSON: %s", exc)
        event = {}

    cwd = event.get("cwd") or os.getcwd()
    source = event.get("source", "")

    # Locked path: ~/.startup-framework/wiki/ (resolved via explicit three-way
    # fallback — see _resolve_wiki_root for the C1 bug this closes).
    wiki_root = _resolve_wiki_root()

    # Feed integration callback per team-lead's locked 8-step sequence (#13):
    # pull → write_session_start → read_friends_tails. All silent-degrade per
    # feed-2's read-side asymmetry contract.
    fetch_feed_tail = _build_feed_callback(cwd=cwd)

    # Compose the context payload.
    #
    # Import path: the script lives at hooks/wake-up/sf-wake-up.py with `lib/`
    # right next to it. Python can't resolve `from hooks.wake_up.lib import ...`
    # because the parent dir `wake-up` has a dash. We add THIS script's dir
    # to sys.path and import `lib` directly. Bug caught by the end-to-end
    # smoke test 2026-05-28 — unit tests passed via relative imports but the
    # standalone-script invocation path was broken.
    try:
        script_dir = Path(__file__).resolve().parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        from lib import compose_wake_up_context  # type: ignore[import-not-found]

        context_text = compose_wake_up_context(
            cwd=Path(cwd),
            wiki_root=wiki_root,
            source=source,
            fetch_feed_tail=fetch_feed_tail,
        )
    except Exception:  # noqa: BLE001 — load-bearing graceful failure
        logger.error("compose failed:\n%s", traceback.format_exc())
        context_text = ""

    # Emit the hook output JSON per CC_API_NOTES.md §4.2
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context_text,
        }
    }
    try:
        json.dump(output, sys.stdout)
        sys.stdout.write("\n")
    except OSError as exc:
        logger.error("could not write stdout: %s", exc)
        return 0  # still exit 0 to not abort the session

    logger.info(
        "wake-up emitted %d chars of additionalContext (source=%s, cwd=%s)",
        len(context_text), source, cwd,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
