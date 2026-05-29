"""
feed.config — single source of truth for paths + handle resolution.

Other modules (writer, reader, bootstrap) and skills (/sf:catch-up, /sf:disable-feed)
import from here so the framework path convention lives in exactly one place.

Per team-lead (2026-05-28):
- Framework root: ~/.startup-framework/
- Activity feed clone: ~/.startup-framework/activity-feed/
- Per-session state files: ~/.startup-framework/state/session-<id>.json

Per ADR-018 §"Identity in the activity feed" + onboarding-2's identity.md.tmpl:
- The friend's handle lives in YAML frontmatter at the top of wiki/identity.md
  under the key `handle:`. We read that.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


# --- path constants (NOT to be reproduced elsewhere — import from here) ---

FRAMEWORK_ROOT_ENV = "SF_FRAMEWORK_ROOT"
"""Env-var override for the framework root path. Lets tests + distribution remap."""

DEFAULT_FRAMEWORK_ROOT = Path.home() / ".startup-framework"
"""Default framework root per team-lead decision (2026-05-28)."""

FALLBACK_FRAMEWORK_VERSION = "1.0.0"
"""Fallback used when no installed-plugin metadata is reachable. Matches
distribution-2's schemas.json top-level value for v1.0.0. Tests pinned to this."""


def framework_version() -> str:
    """Return the installed framework version.

    Resolution order (per distribution-2's coordination message, 2026-05-28):
      1. CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION env var (cleanest interface)
      2. CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json "version" field
      3. FALLBACK_FRAMEWORK_VERSION constant

    Never raises — falls back at each layer if a source is unreadable. Used by the
    writer when stamping `framework_version:` into new <handle>.log.md frontmatter.
    """
    # Layer 1: explicit env var
    env_val = os.environ.get("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "").strip()
    if env_val:
        return env_val

    # Layer 2: plugin.json
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if plugin_root:
        plugin_json = Path(plugin_root) / ".claude-plugin" / "plugin.json"
        if plugin_json.exists():
            try:
                text = plugin_json.read_text(encoding="utf-8")
                # Minimal JSON parse for "version": "..." — avoid pulling json dep
                # for one field, since /sf:doctor and tests are perf-sensitive paths.
                import re as _re
                m = _re.search(r'"version"\s*:\s*"([^"]+)"', text)
                if m:
                    return m.group(1)
            except OSError:
                pass

    # Layer 3: fallback
    return FALLBACK_FRAMEWORK_VERSION


# Back-compat alias — referenced by older code; new code should call framework_version().
FRAMEWORK_VERSION = FALLBACK_FRAMEWORK_VERSION
"""Deprecated. Prefer `framework_version()`. Kept as a fallback string for code paths
that need a const literal at import time (e.g., docstrings/templates). The function
form is authoritative; this constant only matches when no env-var/plugin.json override
applies."""

EXPECTED_FEED_SCHEMA_VERSION = 1
"""Schema version this build of `feed/` expects on <handle>.log.md files.
Matches `schemas.json#page_types["feed-entry"].current`. Writer + reader assert
against this before touching a file. Mismatch surfaces to the user as a migration
prompt ("run /sf:update") rather than a silent malformed write."""

EXPECTED_IDENTITY_SCHEMA_VERSION = 1
"""Schema version this build expects on wiki/identity.md.
Matches `schemas.json#page_types["identity"].current`. config.handle() asserts
against this so a schema bump surfaces as a clear error instead of a silent parse."""


def framework_root() -> Path:
    """Return the framework root directory.

    Honors SF_FRAMEWORK_ROOT env var if set (for tests + distribution remapping);
    otherwise returns ~/.startup-framework/.
    """
    override = os.environ.get(FRAMEWORK_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_FRAMEWORK_ROOT


def local_path() -> Path:
    """Return the local activity-feed clone path.

    This is what `onboarding-2`'s Stage 3 consumes via `RepoState.local_path` so it
    doesn't need to know the path convention. Other modules call this to find the clone.
    """
    return framework_root() / "activity-feed"


def wiki_path() -> Path:
    """Return the friend's local wiki path.

    Used by `handle()` to read `wiki/identity.md`. Owned conceptually by sf-distribution
    but exposed here for convenience.
    """
    return framework_root() / "wiki"


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


# --- handle resolution (reads wiki/identity.md frontmatter `handle:` field) ---


class HandleNotConfiguredError(RuntimeError):
    """Raised when wiki/identity.md doesn't exist or doesn't have a `handle:` field.

    Indicates onboarding's identity-bootstrap (Stage 4) hasn't run, OR the friend
    manually edited identity.md and broke the schema. Caller should surface a clear
    message pointing the user at /sf:interview.
    """


class InvalidHandleError(HandleNotConfiguredError):
    """Raised when a handle is present but malformed (doesn't match HANDLE_RE).

    A malformed handle is a path-traversal / malformed-commit-message risk (M2/L7): it
    flows into `<local_path>/<handle>.log.md`, `identities/<handle>.md`, and git commit
    messages. /sf:interview validates the pattern at input; we enforce it at every use so
    a hand-edited identity.md can't escape the feed directory.

    Subclasses HandleNotConfiguredError so existing `except HandleNotConfiguredError`
    handlers (sf-recall, sf-wrap) catch it with the same /sf:interview remediation.
    """


class SchemaVersionMismatchError(RuntimeError):
    """Raised when a file's `schema_version` frontmatter field doesn't match what
    this build of the feed module expects (`EXPECTED_*_SCHEMA_VERSION`).

    Caller (typically onboarding Stage 1 pre-flight or feed's writer drift-check)
    should surface to the user: "your wiki schema is at N but framework expects M;
    run /sf:update to migrate" — per ADR-027 + distribution-2's coordination.

    Attributes:
        path: the file with the mismatched version
        found: the version observed in the file
        expected: the version this build expects
    """

    def __init__(self, path: Path, found: int, expected: int) -> None:
        self.path = path
        self.found = found
        self.expected = expected
        super().__init__(
            f"{path} has schema_version={found}; this framework expects {expected}. "
            "Run /sf:update to migrate."
        )


HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
"""The handle contract: a lowercase letter followed by lowercase letters, digits, and
hyphens. Mirrors the pattern /sf:interview validates at input. Enforced at every use of
the handle (M2) so a hand-edited identity.md can't introduce a path-traversal value."""


def validate_handle(value: str) -> str:
    """Return `value` unchanged if it matches HANDLE_RE; otherwise raise InvalidHandleError.

    The handle is load-bearing for filesystem paths (`<handle>.log.md`,
    `identities/<handle>.md`) and git commit messages, so a malformed value is a
    path-traversal vector (M2/L7). We reject rather than sanitize-and-fall-back (unlike
    sf-note's local-only notes): the feed handle is identity and must be correct, not
    silently rewritten.
    """
    if not isinstance(value, str) or not HANDLE_RE.match(value):
        raise InvalidHandleError(
            f"handle {value!r} is invalid; it must match ^[a-z][a-z0-9-]*$ "
            "(a lowercase letter, then lowercase letters/digits/hyphens). "
            "Run /sf:interview to set a valid handle."
        )
    return value


def handle(*, strict_schema: bool = True) -> str:
    """Return the friend's handle, read from wiki/identity.md frontmatter.

    Args:
        strict_schema: when True (default), also asserts the file's `schema_version`
            matches EXPECTED_IDENTITY_SCHEMA_VERSION and raises SchemaVersionMismatchError
            on drift. Set to False for repair-mode tooling that needs to read the handle
            from a stale-schema file.

    Raises:
        HandleNotConfiguredError: identity.md is missing or has no `handle:` field
        InvalidHandleError: handle is present but malformed (M2; subclass of the above)
        SchemaVersionMismatchError: schema_version frontmatter field doesn't match

    The handle is the load-bearing identifier for everything in the feed:
    <handle>.log.md, identities/<handle>.md, the "| hazar |" in each entry header.
    """
    identity_md = wiki_path() / "identity.md"
    if not identity_md.exists():
        raise HandleNotConfiguredError(
            f"{identity_md} does not exist. Run /sf:interview to bootstrap your identity."
        )

    text = identity_md.read_text(encoding="utf-8")

    if strict_schema:
        observed_schema = _parse_schema_version_from_frontmatter(text)
        if observed_schema is not None and observed_schema != EXPECTED_IDENTITY_SCHEMA_VERSION:
            raise SchemaVersionMismatchError(
                identity_md, observed_schema, EXPECTED_IDENTITY_SCHEMA_VERSION,
            )

    parsed = _parse_handle_from_frontmatter(text)
    if not parsed:
        raise HandleNotConfiguredError(
            f"{identity_md} has no `handle:` field in YAML frontmatter. "
            "Run /sf:interview to repair, or hand-edit the frontmatter."
        )
    # M2: enforce the handle format at use (path-safety), independent of strict_schema —
    # a malformed handle is dangerous regardless of the file's schema_version.
    return validate_handle(parsed)


def _parse_schema_version_from_frontmatter(text: str) -> int | None:
    """Extract integer `schema_version` from YAML frontmatter. Returns None if absent."""
    value_str = _parse_field_from_frontmatter(text, "schema_version")
    if value_str is None:
        return None
    try:
        return int(value_str)
    except ValueError:
        return None


def _parse_field_from_frontmatter(text: str, field: str) -> str | None:
    """Generic frontmatter field reader. Returns the raw string value (sans quotes)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    prefix = f"{field}:"
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return None
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return value or None
    return None


def _parse_handle_from_frontmatter(text: str) -> str | None:
    """Extract the `handle:` value from YAML frontmatter at the top of a markdown file.

    Deliberately minimal — we don't pull in pyyaml just to read one field. Frontmatter
    format per onboarding-2's identity.md.tmpl:

        ---
        title: "..."
        type: identity
        schema_version: 1
        framework_version: "..."
        handle: hazar
        name: "..."
        ...
        ---

    Returns None if no frontmatter block, or frontmatter has no `handle:` line.
    """
    return _parse_field_from_frontmatter(text, "handle")
