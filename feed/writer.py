"""
feed.writer — append-only writes to the friend's own <handle>.log.md.

Per team-lead arbitration (2026-05-28), the public surface is THREE separate functions
keyed by entry kind, NOT a polymorphic single entrypoint. Reasons:
- Type signature self-documents what's required per kind (no nullable mishmash)
- No runtime `kind` validation branch
- Adding new kinds = new function, doesn't touch existing dispatchers
- Symmetric with the read API (already split by purpose)

    feed_write_session_start(*, handle, cwd, schema_version=1, skip=False,
                             timestamp=None, continuation_hint=None) -> FeedWriteResult
    feed_write_session_end(*, handle, project, task_brief, files_touched,
                           schema_version=1, skip=False, timestamp=None) -> FeedWriteResult
    feed_write_release(*, handle, version, note, schema_version=1, skip=False,
                       timestamp=None) -> FeedWriteResult

The polymorphic dispatcher (`_write_entry_dispatch`) is kept as a PRIVATE engine that
all three public functions delegate to — preserves the working impl, just exposes a
cleaner surface.

Skip semantics: when skip=True, function is a no-op returning FeedWriteResult(
    success=True, entry_id="", pushed=False, queued=False, error=None, violation=None
). Per ADR-021, "skip" means no local write AND no remote push.

Idempotency: entry_id = SHA-256(handle | kind | ts_minute | summary[:40])[:16].
The writer checks for this id in the existing log file before appending; same-args
twice within the same minute → no duplicate row.

Format validation runs BEFORE any write — on FormatViolation we return success=False
with violation=<reason> so the consolidate skill can re-prompt the LLM.

Bootstrap pre-check: if the local clone hasn't been initialized (no .git directory),
returns success=False with violation="not-bootstrapped" so the caller can surface
"run /sf:install Stage 3" instead of generic auth/network error messaging.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from feed import config, io_github
from feed.format import (
    FeedEntryKind,
    FormatViolation,
    build_end_entry,
    build_release_entry,
    build_start_entry,
)


@dataclass(frozen=True)
class FeedWriteResult:
    """Return shape of all three writer functions. Locked per team-lead arbitration."""

    success: bool
    entry_id: str
    pushed: bool
    queued: bool = False
    error: Optional[str] = None
    violation: Optional[str] = None


SCHEMA_HEADER_TEMPLATE = """---
schema_version: {version}
framework_version: {framework_version}
type: feed-entry
handle: {handle}
---

"""
"""File-top YAML frontmatter for new <handle>.log.md files. Per team-lead decision
(2026-05-28): file-top frontmatter, not per-entry. Schema fields required by
distribution-2's `schemas.json` "feed-entry" page-type: schema_version (int),
framework_version (semver string), type (literal "feed-entry"), handle (kebab-case).
"""


# === PUBLIC API ============================================================
# Three separate functions per team-lead arbitration. Each has a tight, typed
# signature appropriate to its entry kind. All delegate to `_write_entry_dispatch`.


def feed_write_session_start(
    *,
    handle: str,
    cwd: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: Optional[datetime] = None,
    continuation_hint: Optional[str] = None,
) -> FeedWriteResult:
    """Write a session-start entry to <handle>.log.md.

    Called by lifecycle's wake-up hook after reading the friends' tails. Posts the
    "## [ts] start | handle | working in <cwd>" line + optional continuation hint.

    Skip honored: when skip=True, returns success=True with empty entry_id (no-op).
    Caller computes skip via `feed.is_skip_active(wrap_flag=False)`.

    Format violations (overlong continuation_hint, etc) → success=False, violation=<reason>.
    Bootstrap missing (no .git in local_path) → success=False, violation="not-bootstrapped".
    """
    return _write_entry_dispatch(
        handle=handle,
        kind="start",
        project=None,
        summary="",
        files_touched=None,
        cwd=cwd,
        continuation_hint=continuation_hint,
        schema_version=schema_version,
        skip=skip,
        timestamp=timestamp,
    )


def feed_write_session_end(
    *,
    handle: str,
    project: str,
    task_brief: str,
    files_touched: list[str],
    schema_version: int = 1,
    skip: bool = False,
    timestamp: Optional[datetime] = None,
) -> FeedWriteResult:
    """Write a session-end entry to <handle>.log.md.

    Called by `/sf:wrap` after the consolidate skill drafts a structured summary.
    Posts "Worked on <project> — <brief>." + "Touched: <files-csv>." body lines.

    The terse format is the privacy mechanism (ADR-021). All four params are required:
    - `task_brief` must be 1-2 sentences, no code, no Error:/Traceback, ≤300-ish chars
    - `files_touched` must be non-empty; >8 files render as "…and N more"

    Validation failures return success=False with `violation` set to one of:
    "too-long", "forbidden-substring", "html-bleed", "shape-mismatch", "missing-files",
    "schema-mismatch", "not-bootstrapped".
    """
    return _write_entry_dispatch(
        handle=handle,
        kind="end",
        project=project,
        summary=task_brief,
        files_touched=files_touched,
        cwd=None,
        continuation_hint=None,
        schema_version=schema_version,
        skip=skip,
        timestamp=timestamp,
    )


def feed_write_release(
    *,
    handle: str,
    version: str,
    note: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: Optional[datetime] = None,
) -> FeedWriteResult:
    """Write a release-announcement entry to <handle>.log.md.

    Called by the framework maintainer when shipping a release (per ADR-019).
    Posts "## [ts] release | handle | framework | <version> shipped — <note>".

    Social convention v1: no role check. Any handle can post release entries. The
    friend group's GitHub collaborator list is the trust boundary.
    TODO(v2): role-based write_release authorization.
    """
    return _write_entry_dispatch(
        handle=handle,
        kind="release",
        project=version,   # encoded into the entry header
        summary=note,
        files_touched=None,
        cwd=None,
        continuation_hint=None,
        schema_version=schema_version,
        skip=skip,
        timestamp=timestamp,
    )


# === DETERMINISTIC FAKES ==================================================
# For lifecycle-2's cache-verification + unit tests. Same signatures as the real
# functions; never touch the filesystem or git; generate the same entry_id values.


def feed_write_session_start_fake(
    *,
    handle: str,
    cwd: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: Optional[datetime] = None,
    continuation_hint: Optional[str] = None,
) -> FeedWriteResult:
    """Deterministic fake of feed_write_session_start. No I/O. Honors skip correctly."""
    if skip:
        return _skip_result()
    ts = timestamp or datetime.now(timezone.utc)
    return FeedWriteResult(
        success=True,
        entry_id=compute_entry_id(handle, "start", ts, ""),
        pushed=False, queued=False, error=None, violation=None,
    )


def feed_write_session_end_fake(
    *,
    handle: str,
    project: str,
    task_brief: str,
    files_touched: list[str],
    schema_version: int = 1,
    skip: bool = False,
    timestamp: Optional[datetime] = None,
) -> FeedWriteResult:
    """Deterministic fake of feed_write_session_end. No I/O. Honors skip correctly."""
    if skip:
        return _skip_result()
    ts = timestamp or datetime.now(timezone.utc)
    return FeedWriteResult(
        success=True,
        entry_id=compute_entry_id(handle, "end", ts, task_brief),
        pushed=False, queued=False, error=None, violation=None,
    )


def feed_write_release_fake(
    *,
    handle: str,
    version: str,
    note: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: Optional[datetime] = None,
) -> FeedWriteResult:
    """Deterministic fake of feed_write_release. No I/O. Honors skip correctly."""
    if skip:
        return _skip_result()
    ts = timestamp or datetime.now(timezone.utc)
    return FeedWriteResult(
        success=True,
        entry_id=compute_entry_id(handle, "release", ts, note),
        pushed=False, queued=False, error=None, violation=None,
    )


# === PUBLIC UTILITY =======================================================


def compute_entry_id(
    handle: str,
    kind: FeedEntryKind,
    timestamp: datetime,
    summary: str,
) -> str:
    """Compute the idempotency key for a feed entry.

    Algorithm: SHA-256 of (handle | kind | ts_unix_minute | full-summary),
    truncated to 16 hex chars. Calling a writer twice with identical inputs within
    the same minute → identical entry_id → writer detects dup, returns existing entry.

    Per review finding F2 (2026-05-28): previously hashed `summary[:40]`, which
    caused silent drops when two distinct summaries shared a 40-char prefix in the
    same minute. Now hashes the FULL summary — the SHA-256 absorbs arbitrary input
    length cheaply, so there's no benefit to truncation and a clear loss from it.

    Exposed publicly so callers (e.g., lifecycle's wake-up hook, distribution's
    /sf:doctor) can compute expected ids for assertion or display.
    """
    ts_minute = int(timestamp.timestamp()) // 60
    material = f"{handle}|{kind}|{ts_minute}|{summary or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def rename_handle(old: str, new: str) -> bool:
    """Rename a friend's log file + identity file in the local activity-feed clone.

    Supports onboarding-2's edge case: Stage 3 collects an initial handle to bootstrap
    the feed, then Stage 4 (`/sf:interview`) lets the user revise it. This helper
    keeps the rename atomic on the local clone (caller pushes after).

    Renames:
        local_path/<old>.log.md      → local_path/<new>.log.md
        local_path/identities/<old>.md → local_path/identities/<new>.md (if present)

    Idempotent: if `<new>` files already exist (e.g., retry after a partial rename),
    returns False without overwriting. Otherwise returns True on success.

    Does NOT update entry-header `| handle |` content inside the renamed log file —
    that's a per-line edit we deliberately don't do for V1 (historical entries are
    snapshots of state at write time; ADR-018 chronological-invariant convention).
    The frontmatter `handle:` field IS updated so the file stays self-consistent.
    """
    repo = config.local_path()
    old_log = repo / f"{old}.log.md"
    new_log = repo / f"{new}.log.md"
    old_id = repo / "identities" / f"{old}.md"
    new_id = repo / "identities" / f"{new}.md"

    if new_log.exists() or new_id.exists():
        return False  # idempotency guard
    if not old_log.exists():
        return False

    text = old_log.read_text(encoding="utf-8")
    text = _rewrite_frontmatter_field(text, "handle", new)
    new_log.write_text(text, encoding="utf-8")
    old_log.unlink()

    if old_id.exists():
        new_id.parent.mkdir(parents=True, exist_ok=True)
        id_text = old_id.read_text(encoding="utf-8")
        id_text = _rewrite_frontmatter_field(id_text, "handle", new)
        new_id.write_text(id_text, encoding="utf-8")
        old_id.unlink()

    return True


# === PRIVATE ENGINE ========================================================
# All three public writers delegate here. Polymorphic by `kind`. Was the public
# API in the DM-sealed convergence; team-lead arbitration moved it to private.


def _write_entry_dispatch(
    *,
    handle: str,
    kind: FeedEntryKind,
    project: Optional[str],
    summary: str,
    files_touched: Optional[list[str]],
    cwd: Optional[str],
    continuation_hint: Optional[str],
    schema_version: int,
    skip: bool,
    timestamp: Optional[datetime],
) -> FeedWriteResult:
    """Internal dispatcher. Not part of the public API.

    The three feed_write_session_* functions normalize their args into this shape and
    call here. Validation, idempotency check, file append, commit, and push all live
    here so the public functions stay shape-focused.
    """
    if skip:
        return _skip_result()

    # M2/L7: reject a malformed handle before it reaches path construction
    # (`<local_path>/<handle>.log.md`) or the git commit message. The public writers take
    # `handle` as a param, so a direct caller could bypass config.handle()'s guard.
    try:
        config.validate_handle(handle)
    except config.InvalidHandleError as e:
        return FeedWriteResult(
            success=False, entry_id="", pushed=False, queued=False,
            error=str(e), violation="invalid-handle",
        )

    # Bootstrap pre-check: distinct from auth/network errors per lifecycle-2's ask.
    # Detected by absence of .git in local_path. Callers surface as "run /sf:install
    # Stage 3" — distinct UX from generic push failures.
    if not (config.local_path() / ".git").exists():
        return FeedWriteResult(
            success=False, entry_id="", pushed=False, queued=False,
            error=(
                f"Activity Feed clone not bootstrapped at {config.local_path()}. "
                "Run /sf:install Stage 3 to set it up."
            ),
            violation="not-bootstrapped",
        )

    ts = timestamp or datetime.now(timezone.utc)

    try:
        entry_block = _render_entry(
            handle=handle, kind=kind, project=project, summary=summary,
            files_touched=files_touched, cwd=cwd, continuation_hint=continuation_hint,
            timestamp=ts,
        )
    except FormatViolation as v:
        return FeedWriteResult(
            success=False, entry_id="", pushed=False, queued=False,
            error=str(v), violation=v.reason,
        )

    eid = compute_entry_id(handle, kind, ts, summary)
    try:
        log_path = _ensure_log_file(handle, schema_version=schema_version)
    except config.SchemaVersionMismatchError as e:
        return FeedWriteResult(
            success=False, entry_id="", pushed=False, queued=False,
            error=str(e), violation="schema-mismatch",
        )

    if _entry_already_present(log_path, eid):
        return FeedWriteResult(
            success=True, entry_id=eid, pushed=False, queued=False, error=None,
        )

    _append_entry(log_path, entry_block, entry_id=eid)

    push_result = io_github.push(commit_msg=f"{handle} {kind} {ts.strftime('%Y-%m-%d %H:%M')}")
    return FeedWriteResult(
        success=True,
        entry_id=eid,
        pushed=push_result.ok and not push_result.queued,
        queued=push_result.queued,
        error=push_result.error,
        violation=None,
    )


# === PRIVATE HELPERS =======================================================


def _skip_result() -> FeedWriteResult:
    """Single source of truth for the skip-return shape."""
    return FeedWriteResult(
        success=True, entry_id="", pushed=False, queued=False,
        error=None, violation=None,
    )


def _render_entry(
    *,
    handle: str,
    kind: FeedEntryKind,
    project: Optional[str],
    summary: str,
    files_touched: Optional[list[str]],
    cwd: Optional[str],
    continuation_hint: Optional[str],
    timestamp: datetime,
) -> str:
    """Dispatch to the appropriate builder based on kind. Raises FormatViolation."""
    if kind == "start":
        if not cwd:
            raise FormatViolation("missing-cwd", "kind='start' requires cwd")
        return build_start_entry(
            handle=handle,
            cwd_short=_short_cwd(cwd),
            timestamp=timestamp,
            continuation_hint=continuation_hint,
        )
    if kind == "end":
        if not project:
            raise FormatViolation("missing-project", "kind='end' requires project")
        if files_touched is None:
            raise FormatViolation("missing-files", "kind='end' requires files_touched")
        return build_end_entry(
            handle=handle,
            project=project,
            task_brief=summary,
            files_touched=files_touched,
            timestamp=timestamp,
        )
    if kind == "release":
        return build_release_entry(
            handle=handle, version=project or "?", note=summary, timestamp=timestamp,
        )
    raise FormatViolation("unknown-kind", f"unknown entry kind: {kind!r}")


def _short_cwd(cwd: str) -> str:
    home = str(Path.home())
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    if len(cwd) > 80:
        cwd = cwd[:77] + "..."
    return cwd


def _ensure_log_file(handle: str, *, schema_version: int) -> Path:
    """Return Path to <local_path>/<handle>.log.md, creating it with frontmatter if absent.

    Per distribution-2's coordination ask: asserts the EXISTING file's schema_version
    matches `EXPECTED_FEED_SCHEMA_VERSION`. Raises SchemaVersionMismatchError on drift.
    """
    log_path = config.local_path() / f"{handle}.log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not log_path.exists():
        header = SCHEMA_HEADER_TEMPLATE.format(
            version=schema_version,
            framework_version=config.framework_version(),
            handle=handle,
        )
        log_path.write_text(header, encoding="utf-8")
        return log_path

    text = log_path.read_text(encoding="utf-8")
    observed = config._parse_schema_version_from_frontmatter(text)
    if observed is not None and observed != config.EXPECTED_FEED_SCHEMA_VERSION:
        raise config.SchemaVersionMismatchError(
            log_path, observed, config.EXPECTED_FEED_SCHEMA_VERSION,
        )
    return log_path


def _entry_already_present(log_path: Path, entry_id: str) -> bool:
    if not log_path.exists():
        return False
    marker = f"<!-- entry_id: {entry_id} -->"
    try:
        return marker in log_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _append_entry(log_path: Path, entry_block: str, *, entry_id: str) -> None:
    marker = f"<!-- entry_id: {entry_id} -->"
    suffix = f"\n\n{entry_block}\n{marker}\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(suffix)
        f.flush()
        try:
            os.fsync(f.fileno())
        except (OSError, AttributeError):
            pass


def _rewrite_frontmatter_field(text: str, field: str, new_value: str) -> str:
    """Rewrite a YAML-frontmatter field's value, preserving the rest of the file."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return text
    prefix = f"{field}:"
    for i in range(1, len(lines)):
        stripped = lines[i].strip()
        if stripped == "---":
            break
        if stripped.startswith(prefix):
            nl = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f"{prefix} {new_value}{nl}"
            break
    return "".join(lines)
