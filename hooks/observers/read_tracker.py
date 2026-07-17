#!/usr/bin/env python3
"""
hooks/observers/read_tracker.py — PostToolUse observer: wiki page-read usage
events feed usage-aware decay (Task 5, RenOS 0.5.5 spec §4.3).

`lib.instrument.miss_log.log_read` (Task 4) records a direct page read as a
third usage signal alongside L3 fetches and wake-up surfacing — decay
(`lib.memory.lifecycle.decay_candidates`) treats a recently-read page as
recently touched, same as a recent write. This hook is what feeds it: a
PostToolUse observer, matcher `Read`, that records the read iff the file
resolves strictly inside `wiki_root()` and is not under `archive/` (an
archived page being read doesn't count as "still in active use").

Contract: PostToolUse runs AFTER the tool already executed — this hook is a
pure OBSERVER, never a gate. It ALWAYS exits 0 with NO stdout, so it can
never affect the tool result or surface stray output to the user. Every
failure path (bad JSON, missing field, unresolvable/traversal path,
ImportError of project deps) is caught and degrades to a silent no-op. A
missed read event is acceptable — decay still has fetches and wake-up
surfacing as signals; a broken Read-tool experience is not. That's also why,
unlike 0.5.4's wake-up B1 fix, this hook does NOT re-exec itself under `uv`
on missing deps: it just skips recording and exits 0, with a one-line note on
stderr for debugging (a friend running doctor-style diagnostics can grep for
it).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _ensure_plugin_root_on_path() -> None:
    """Put the repo root on sys.path[0] so `from lib... import ...` resolves
    in the installed runtime, same convention as hooks/guards/*.py."""
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    root = Path(os.path.expanduser(os.path.expandvars(val))) if val else Path(__file__).resolve().parents[2]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _resolve_wiki_relative(file_path: str) -> str | None:
    """Return the wiki-relative POSIX path for `file_path` if it resolves
    strictly INSIDE `wiki_root()` (symlinks resolved, traversal rejected) and
    is not under `archive/`; else None.

    Reuses `ren_paths.safe_join` for the resolution: `file_path` from a Read
    tool call is always absolute, and `safe_join`'s `base / rel` join is a
    no-op for an absolute `rel` (pathlib discards the base), so this collapses
    to "resolve `file_path`, then verify it's under `wiki_root()`" — the same
    traversal-rejection `safe_join` already gives every other caller.

    May raise ImportError (propagated to the caller) if `lib.ren_paths` isn't
    importable — that's a distinct failure mode from an unresolvable path and
    is handled by `main()`'s ImportError branch, not swallowed here.
    """
    if not file_path:
        return None

    _ensure_plugin_root_on_path()
    from lib import ren_paths

    wiki_root = ren_paths.wiki_root().resolve()
    try:
        resolved = ren_paths.safe_join(wiki_root, file_path)
    except (ren_paths.PathTraversalError, OSError, ValueError):
        return None

    rel = resolved.relative_to(wiki_root)
    if not rel.parts:
        return None  # resolves to wiki_root itself, not a page under it
    if rel.parts[0] == "archive":
        return None
    return rel.as_posix()


def _record_read(rel: str, session: str) -> None:
    """Import-and-call wrapper for `miss_log.log_read`, isolated so an
    ImportError here is unambiguously the "project deps unavailable" case."""
    from lib.instrument import miss_log

    miss_log.log_read(rel, session)


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return 0

    try:
        if (event.get("tool_name") or "") != "Read":
            return 0

        tool_input = event.get("tool_input") or {}
        file_path = tool_input.get("file_path") or ""
        session = event.get("session_id") or ""

        rel = _resolve_wiki_relative(file_path)
        if rel is None:
            return 0

        _record_read(rel, session)
    except ImportError as exc:
        print(f"ren-read-tracker: project deps unavailable, skipping: {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — load-bearing graceful failure: an
        # observer must never break the Read tool it's watching. A missed
        # read event degrades decay's signal quality, not correctness.
        print(f"WARNING: read_tracker observer failed internally, ignoring: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
