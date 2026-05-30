"""
feed.config — thin shim over lib.sf_paths (ADR-031, solo-first pivot).

The CORE path/handle/schema resolution moved to `lib.sf_paths` — the framework-wide
single source of truth that outlives the Activity Feed. This module re-exports that
core and keeps only the FEED-ONLY helpers (the activity-feed clone path + per-clone
local state) that live and die with `feed/`.

Kept as a shim so `feed/{writer,reader,bootstrap,...}` and their tests keep importing
`from feed import config` unchanged. The feed module + this shim are removed wholesale
in Commit 2; `lib.sf_paths` is the durable home for everything re-exported here.

Re-exported CORE (defined in lib.sf_paths): FRAMEWORK_ROOT_ENV, DEFAULT_FRAMEWORK_ROOT,
framework_root, wiki_path, framework_version / FRAMEWORK_VERSION /
FALLBACK_FRAMEWORK_VERSION, EXPECTED_IDENTITY_SCHEMA_VERSION, HANDLE_RE, validate_handle,
handle, HandleNotConfiguredError, InvalidHandleError, SchemaVersionMismatchError, and the
_parse_*_frontmatter helpers.
"""

from __future__ import annotations

from pathlib import Path

# CORE (framework-wide) — single source of truth in lib.sf_paths.
from lib.sf_paths import *  # noqa: F401,F403  (re-export core path/handle/schema API)

# Underscore frontmatter helpers are skipped by `import *`; re-export explicitly for
# back-compat with feed.writer (config._parse_schema_version_from_frontmatter).
from lib.sf_paths import (  # noqa: F401
    _parse_field_from_frontmatter,
    _parse_handle_from_frontmatter,
    _parse_schema_version_from_frontmatter,
)

# `framework_root` arrives via the star import (it is in lib.sf_paths.__all__); the
# FEED-ONLY helpers below call it.
from lib.sf_paths import framework_root


# --- FEED-ONLY symbols (deleted with feed/ in Commit 2) ----------------------

EXPECTED_FEED_SCHEMA_VERSION = 1
"""Schema version this build of `feed/` expects on <handle>.log.md files.
Matches `schemas.json#page_types["feed-entry"].current`. Writer + reader assert
against this before touching a file. Mismatch surfaces to the user as a migration
prompt ("run /sf:update") rather than a silent malformed write."""


def local_path() -> Path:
    """Return the local activity-feed clone path.

    This is what `onboarding-2`'s Stage 3 consumes via `RepoState.local_path` so it
    doesn't need to know the path convention. Other modules call this to find the clone.
    """
    return framework_root() / "activity-feed"


def state_dir() -> Path:
    """Return the per-session state directory.

    Houses session-<id>.json files written by /sf:disable-feed.
    Read by `is_skip_active()` to honor the session-level kill switch.
    """
    return framework_root() / "state"


FEED_LOCAL_ONLY_FILES = (".queue.log", ".state.json", ".queue.log.lock")
"""Files that live INSIDE the activity-feed clone but must NEVER be committed to the
shared repo. They are per-clone local state (offline queue + per-friend push stats) and
differ from friend to friend. Committing them caused the C3 corruption: each clone's
`.state.json` diverges → the next cross-friend `git pull --rebase` hits an unresolvable
JSON conflict → the shared channel locks up for everyone (REVIEW-v1.0-preship §C3).

Single source of truth. Two consumers keep these local (defense-in-depth, ADR-018):
  1. `feed.bootstrap._write_bootstrap_files` emits a committed `.gitignore` from this
     tuple, so every clone (including joiners who clone the repo) inherits it.
  2. `feed.io_github._stage_and_commit` defensively `git reset`s these paths after
     `git add -A`, so they can never be committed even if a clone's `.gitignore` is
     missing or hand-deleted."""


def queue_log_path() -> Path:
    """Return the offline-queue log path, inside the activity-feed clone.

    Per team-lead pushback (2026-05-28): queue files live INSIDE local_path so deleting
    the clone is self-contained cleanup. `.queue.log` is local-only — see
    `FEED_LOCAL_ONLY_FILES` for how it is kept out of the shared repo (committed
    `.gitignore` + a defensive `git reset` backstop).
    """
    return local_path() / ".queue.log"


def state_json_path() -> Path:
    """Return the offline-queue state JSON path, inside the activity-feed clone.

    Per team-lead pushback (2026-05-28): also lives inside local_path. Tracks
    pending_commit_count + last successful pull/push timestamps. Local-only and kept
    out of the shared repo via `FEED_LOCAL_ONLY_FILES` (committed `.gitignore` + a
    defensive `git reset` backstop) — committing it corrupts cross-friend rebase (§C3).
    """
    return local_path() / ".state.json"
