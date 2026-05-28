"""
feed.reader — tail reads across <handle>.log.md files.

Real implementation (task #19). Replaces scaffold stubs from task #17.

Per the locked contract:

    feed_read_friends_tails(own_handle, n_per_friend=5, include_self=True,
                            since=None, max_tokens=None, refresh=True) -> FriendsTail
    feed_read_tail(n=10, exclude_handle=None, since=None, refresh=True) -> list[FeedEntry]
    read_all_entries(since=None, from_handles=None, project_filter=None) -> list[FeedEntry]

FriendsTail includes `formatted_header` ("## Activity Feed — recent friend activity
(synced 2h ago)") so the wake-up hook doesn't have to compute relative-time strings.

Per team-lead (2026-05-28): `max_tokens` defaults to None. Lifecycle's wake-up hook
will pass `max_tokens=2500`. Truncation policy: drop OLDEST friend-activity entries
first; set `FriendsTail.truncated=True` when truncation happens.

Parsing: each entry is a markdown block starting with `## [YYYY-MM-DD HH:MM] kind | handle | desc`.
Entries may have optional body lines. We parse with regex + state machine. No PyYAML
dependency — the schema_version is read with a tiny line scanner (same approach as
config.handle()).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from feed import config, io_github
from feed.format import FeedEntry, FeedEntryKind


# --- result type ------------------------------------------------------------


@dataclass(frozen=True)
class FriendsTail:
    """Return shape of feed_read_friends_tails."""

    friends: dict[str, list[FeedEntry]]
    fetched_at: datetime
    stale: bool
    formatted_header: str
    truncated: bool = False


# --- constants --------------------------------------------------------------

STALE_AFTER_HOURS = 24
"""Last successful pull older than this → mark stale per lifecycle-2 rider 1."""

DEFAULT_N_PER_FRIEND = 5
DEFAULT_FLAT_N = 10

# Header pattern: "## [2026-05-28 14:30] start | hazar | working in ~/Dev/sidecar/"
HEADER_RE = re.compile(
    r"^## \[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] "
    r"(?P<kind>start|end|release) \| "
    r"(?P<handle>[^|]+?) \| "
    r"(?P<desc>.+)$"
)

# End-entry body lines: "Worked on <project> — <brief>." + "Touched: <files>."
END_PROJECT_BRIEF_RE = re.compile(r"^Worked on (?P<project>.+?) — (?P<brief>.+?)\.$")
END_FILES_RE = re.compile(r"^Touched: (?P<files>.+?)\.$")

# Start-entry "working in <cwd>" suffix in description
START_CWD_RE = re.compile(r"^working in (?P<cwd>.+)$")

# Rough char-to-token ratio for max_tokens truncation budget. Conservative: 4 chars/token.
CHARS_PER_TOKEN = 4


# --- public API -------------------------------------------------------------


def feed_read_friends_tails(
    own_handle: str,
    *,
    n_per_friend: int = DEFAULT_N_PER_FRIEND,
    include_self: bool = True,
    since: Optional[datetime] = None,
    max_tokens: Optional[int] = None,
    refresh: bool = True,
    local_path: Optional[Path] = None,
) -> FriendsTail:
    """Read the last N entries per friend, return per-friend bucketed view.

    Used by the wake-up hook with `refresh=False, max_tokens=2500` for the silent-friend
    coverage problem.

    Truncation: when max_tokens is set and the rendered total would exceed the cap,
    drop OLDEST entries (oldest across all friends) one at a time until under budget.
    Sets `FriendsTail.truncated=True`.

    V2 trigger (per lifecycle-2 rider 2): when len(friends) > 10, this should auto-scale
    (active friends get n_per_friend, quiet friends get 1). NOT YET IMPLEMENTED — flagged
    in the docstring per the contract; out of scope for V1.
    """
    repo = local_path or config.local_path()
    pull_stale = False
    if refresh:
        result = io_github.pull()
        if not result.ok:
            pull_stale = True

    stale = pull_stale or _is_stale_by_age(repo)
    fetched_at = io_github.last_pull_at(repo) or datetime.now(timezone.utc)

    # Bucket per-friend entries (most recent first per friend)
    friends: dict[str, list[FeedEntry]] = {}
    for log_path in sorted(repo.glob("*.log.md")):
        handle = log_path.stem.removesuffix(".log")
        if handle == own_handle and not include_self:
            continue
        entries = list(_parse_log_file(log_path))
        # Filter by `since` if provided
        if since is not None:
            entries = [e for e in entries if e.timestamp >= since]
        # Keep most recent n_per_friend (entries are returned in chronological order)
        if n_per_friend > 0:
            entries = entries[-n_per_friend:]
        if entries:
            friends[handle] = entries

    truncated = False
    if max_tokens is not None:
        friends, truncated = _truncate_to_budget(friends, max_tokens=max_tokens)

    header = _format_header(fetched_at, stale=stale)
    return FriendsTail(
        friends=friends,
        fetched_at=fetched_at,
        stale=stale,
        formatted_header=header,
        truncated=truncated,
    )


def feed_read_tail(
    n: int = DEFAULT_FLAT_N,
    *,
    exclude_handle: Optional[str] = None,
    since: Optional[datetime] = None,
    refresh: bool = True,
    local_path: Optional[Path] = None,
) -> list[FeedEntry]:
    """Flat chronological tail across all friends' logs (descending — newest first).

    Used by /sf:doctor, /sf:recall, and any future mid-session browsers.
    """
    repo = local_path or config.local_path()
    if refresh:
        io_github.pull()

    all_entries: list[FeedEntry] = []
    for log_path in sorted(repo.glob("*.log.md")):
        handle = log_path.stem.removesuffix(".log")
        if exclude_handle and handle == exclude_handle:
            continue
        all_entries.extend(_parse_log_file(log_path))

    if since is not None:
        all_entries = [e for e in all_entries if e.timestamp >= since]

    # Sort descending (newest first), take top n
    all_entries.sort(key=lambda e: e.timestamp, reverse=True)
    return all_entries[:n]


def read_all_entries(
    *,
    since: Optional[datetime] = None,
    from_handles: Optional[list[str]] = None,
    project_filter: Optional[str] = None,
    refresh: bool = False,
    local_path: Optional[Path] = None,
) -> list[FeedEntry]:
    """Return all entries matching the filters. Used by /sf:catch-up.

    Default `refresh=False` because /sf:catch-up calls pull() explicitly + handles its
    own staleness messaging (per plan §4.2 step 1).
    """
    repo = local_path or config.local_path()
    if refresh:
        io_github.pull()

    all_entries: list[FeedEntry] = []
    for log_path in sorted(repo.glob("*.log.md")):
        handle = log_path.stem.removesuffix(".log")
        if from_handles is not None and handle not in from_handles:
            continue
        all_entries.extend(_parse_log_file(log_path))

    if since is not None:
        all_entries = [e for e in all_entries if e.timestamp >= since]
    if project_filter:
        lowered = project_filter.lower()
        all_entries = [
            e for e in all_entries
            if (e.project or "").lower().find(lowered) != -1
            or lowered in (e.summary or "").lower()
        ]

    all_entries.sort(key=lambda e: e.timestamp)
    return all_entries


# --- parser -----------------------------------------------------------------


def _parse_log_file(path: Path) -> Iterable[FeedEntry]:
    """Parse a <handle>.log.md into FeedEntry objects, in chronological order.

    Skips the YAML frontmatter (if any) and yields one FeedEntry per `## [..]` block.
    Body lines for end-entries are parsed into project / brief / files; start-entries
    have their description field populated; release entries get their description as-is.

    Tolerates malformed entries: a header without parsable body still yields a FeedEntry
    with summary=description text, files=(). We don't crash on bad logs.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return

    lines = text.splitlines()
    i = 0
    n = len(lines)

    # Skip optional YAML frontmatter at top. Per F3 review fix (2026-05-28):
    # If the opening `---` has no closing `---` within a reasonable bound (50 lines),
    # the previous impl walked to EOF and silently treated the entire file as empty.
    # Now: cap the scan, emit a warning to stderr, and parse from line 0 instead.
    if lines and lines[0].strip() == "---":
        FRONTMATTER_MAX_LINES = 50
        scan_end = min(n, FRONTMATTER_MAX_LINES + 1)
        closing_idx = None
        for j in range(1, scan_end):
            if lines[j].strip() == "---":
                closing_idx = j
                break
        if closing_idx is None:
            # Malformed frontmatter — fall back to parsing from line 0 + warn
            import sys
            print(
                f"[feed.reader] WARNING: {path} has opening --- but no closing --- "
                f"within {FRONTMATTER_MAX_LINES} lines. Parsing from line 0; "
                "entries before any real frontmatter close may be missed if any.",
                file=sys.stderr,
            )
            i = 0
        else:
            i = closing_idx + 1  # skip closing ---

    current_header_match: Optional[re.Match] = None
    current_body: list[str] = []

    def emit():
        if current_header_match is None:
            return None
        return _build_entry_from_header_and_body(current_header_match, current_body)

    while i < n:
        line = lines[i]
        m = HEADER_RE.match(line)
        if m:
            entry = emit()
            if entry is not None:
                yield entry
            current_header_match = m
            current_body = []
        elif current_header_match is not None:
            # Skip the idempotency marker comments
            if line.strip().startswith("<!-- entry_id:"):
                pass
            else:
                current_body.append(line)
        i += 1

    entry = emit()
    if entry is not None:
        yield entry


def _build_entry_from_header_and_body(
    header_match: re.Match, body_lines: list[str]
) -> FeedEntry:
    """Construct a FeedEntry from a parsed header + body lines."""
    ts_str = header_match.group("ts")
    kind: FeedEntryKind = header_match.group("kind")  # type: ignore[assignment]
    handle = header_match.group("handle").strip()
    desc = header_match.group("desc").strip()
    raw_line = header_match.group(0)

    # Parse timestamp (logs use local-friendly "YYYY-MM-DD HH:MM"; treat as UTC for
    # consistency. Friends in different timezones still get comparable ordering since
    # writer uses UTC throughout.)
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        ts = datetime.now(timezone.utc)

    project: Optional[str] = None
    summary: Optional[str] = None
    files: tuple[str, ...] = ()

    # Strip blank lines around body
    body = [ln for ln in body_lines if ln.strip()]

    if kind == "start":
        # Description has "working in <cwd>" pattern
        m = START_CWD_RE.match(desc)
        if m:
            summary = f"working in {m.group('cwd')}"
            project = _project_from_cwd(m.group("cwd"))
        else:
            summary = desc
    elif kind == "end":
        # Body should be: "Worked on <project> — <brief>." + "Touched: <files>."
        for line in body:
            pm = END_PROJECT_BRIEF_RE.match(line.strip())
            if pm:
                project = pm.group("project").strip()
                summary = pm.group("brief").strip()
                continue
            fm = END_FILES_RE.match(line.strip())
            if fm:
                files = _parse_files_field(fm.group("files"))
                continue
    elif kind == "release":
        summary = desc  # full description carries version + note

    return FeedEntry(
        handle=handle,
        kind=kind,
        timestamp=ts,
        project=project,
        summary=summary,
        files=files,
        raw_line=raw_line,
    )


def _parse_files_field(text: str) -> tuple[str, ...]:
    """Parse the "Touched: <csv>" body. Strip the "…and N more" suffix if present."""
    # Strip overflow suffix
    text = re.sub(r"\s*…and \d+ more\s*$", "", text)
    return tuple(f.strip() for f in text.split(",") if f.strip())


def _project_from_cwd(cwd: str) -> Optional[str]:
    """Heuristic project name extraction from a cwd path.

    Looks for "Dev/<name>" pattern; falls back to the trailing path component.
    """
    parts = [p for p in cwd.replace("~", "").split("/") if p]
    if "Dev" in parts:
        idx = parts.index("Dev")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return parts[-1] if parts else None


# --- staleness + formatting -------------------------------------------------


def _is_stale_by_age(repo: Path) -> bool:
    """True if the last successful pull is >STALE_AFTER_HOURS ago (or never)."""
    last = io_github.last_pull_at(repo)
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last) > timedelta(hours=STALE_AFTER_HOURS)


def _format_header(fetched_at: datetime, *, stale: bool) -> str:
    """Render the section header for the wake-up message.

    Format: "## Activity Feed — recent friend activity (synced 2h ago)"
    Or:     "## Activity Feed — recent friend activity (sync stale, last 3d ago)"
    """
    rel = _relative_time(fetched_at)
    if stale:
        return f"## Activity Feed — recent friend activity (sync stale, last {rel})"
    return f"## Activity Feed — recent friend activity (synced {rel})"


def format_entry_one_line(entry: FeedEntry) -> str:
    """Render a FeedEntry as a single bullet line for in-conversation display.

    Output format (per lifecycle-2's spec, locked 2026-05-28):

        "- friend-b · 2h ago · sidecar — Stripe webhook handler"

    Components, separated by middle-dot ` · `:
      - `- ` prefix (bullet marker, matches /sf:catch-up style)
      - handle
      - relative time (from format_relative_time)
      - project (omitted for release entries — summary already carries version)
      - em-dash `—` separator
      - summary (or raw_line fallback if summary missing)

    Files-touched is NOT included — lifecycle-2's design call: "Files-touched
    probably belongs only in /sf:catch-up's expanded view, not the one-line."
    Callers wanting files render them separately.

    Single-line guarantee: no embedded newlines. If summary contains \\n, replace
    with " · " to preserve display integrity.

    Usable by /sf:recall, /sf:doctor, wake-up's debug output, future browsers.
    """
    parts = [f"- {entry.handle}", format_relative_time(entry.timestamp)]
    # Release entries: summary carries "framework | v1.3.0 shipped — see CHANGELOG"
    # already; including project=None or version twice is noisy. Skip project segment.
    if entry.kind != "release":
        parts.append(entry.project or "(unscoped)")

    head = " · ".join(parts)
    summary = (entry.summary or entry.raw_line or "").replace("\n", " · ")
    return f"{head} — {summary}"


def format_relative_time(ts: datetime) -> str:
    """Render a relative-time string. "just now", "2m ago", "3h ago", "2d ago".

    Public utility — exposed for callers (wake-up hook header, /sf:catch-up footer,
    /sf:recall "related recent activity" section, distribution-2's /sf:doctor) that
    want a consistent string format across surfaces. Single source of truth keeps
    "2h ago" vs "2 hours ago" vs "120m ago" drift from creeping in.
    """
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = now - ts
    seconds = int(delta.total_seconds())
    if seconds < 30:
        return "just now"
    if seconds < 60 * 60:
        return f"{seconds // 60}m ago"
    if seconds < 24 * 60 * 60:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


# Internal alias — kept as `_relative_time` for back-compat with existing call sites
# inside the module. New callers should use `format_relative_time`.
_relative_time = format_relative_time


# --- truncation -------------------------------------------------------------


def _truncate_to_budget(
    friends: dict[str, list[FeedEntry]], *, max_tokens: int
) -> tuple[dict[str, list[FeedEntry]], bool]:
    """Shrink the friends dict to fit max_tokens. Preserve at least one entry per
    friend (per F4 review fix); if still over budget, trim entry summaries.

    Strategy:
      1. While over budget AND any friend has >1 entry: drop oldest entry from a
         multi-entry friend.
      2. If still over budget AND only singletons remain: trim summary text on the
         remaining entries (keep handle/timestamp/kind, replace summary with truncated).

    This guarantees per-friend coverage — a silent friend with only one entry won't
    be silently zeroed out under aggressive truncation. The "summary trim" fallback
    preserves the existence of the entry; the LLM consuming the wake-up payload
    still sees that the friend was active, even if the brief is shortened.
    """
    if not friends:
        return friends, False

    budget_chars = max_tokens * CHARS_PER_TOKEN
    current = _estimate_chars(friends)
    if current <= budget_chars:
        return friends, False

    # Work on a deep-enough copy
    working: dict[str, list[FeedEntry]] = {h: list(es) for h, es in friends.items()}
    truncated = False

    # Phase 1: drop oldest from friends with >1 entry
    def _candidate_for_drop() -> tuple[str, int] | None:
        """Pick (handle, index_in_list) of the oldest entry from a friend with >1 entry.
        Returns None if every friend has only 1 entry left."""
        best: tuple[str, int, datetime] | None = None
        for h, entries in working.items():
            if len(entries) <= 1:
                continue  # protected: preserve this friend's only entry
            # Oldest entry in this friend's list (entries are chronological asc)
            ts = entries[0].timestamp
            if best is None or ts < best[2]:
                best = (h, 0, ts)
        if best is None:
            return None
        return best[0], best[1]

    while current > budget_chars:
        cand = _candidate_for_drop()
        if cand is None:
            break  # phase 1 exhausted — all friends down to 1 entry
        h, idx = cand
        dropped = working[h].pop(idx)
        current -= _estimate_entry_chars(dropped)
        truncated = True

    # Phase 2: still over budget AND only singletons → trim summary text per friend
    if current > budget_chars:
        # Compute how much we need to shave per remaining entry on average
        total_entries = sum(len(es) for es in working.values())
        if total_entries > 0:
            overshoot = current - budget_chars
            shave_per_entry = max(1, overshoot // total_entries + 1)
            for h, entries in working.items():
                for idx, e in enumerate(entries):
                    if e.summary and len(e.summary) > shave_per_entry + 10:
                        new_summary = e.summary[: max(10, len(e.summary) - shave_per_entry)] + "…"
                        # FeedEntry is frozen; rebuild with truncated summary
                        from dataclasses import replace
                        entries[idx] = replace(e, summary=new_summary)
            truncated = True

    return working, truncated


def _estimate_chars(friends: dict[str, list[FeedEntry]]) -> int:
    return sum(_estimate_entry_chars(e) for entries in friends.values() for e in entries)


def _estimate_entry_chars(entry: FeedEntry) -> int:
    """Estimate rendered size of an entry. Uses raw_line + body summary as proxy."""
    base = len(entry.raw_line) + 2  # raw line + newline + blank
    if entry.summary:
        base += len(entry.summary) + 16  # "Worked on x — y." overhead
    if entry.files:
        base += sum(len(f) for f in entry.files) + 2 * len(entry.files)
    return base


# --- fake (kept for back-compat with task #17 callers; same interface) -----


def feed_read_friends_tails_fake(
    own_handle: str,
    *,
    n_per_friend: int = DEFAULT_N_PER_FRIEND,
    include_self: bool = True,
    since: Optional[datetime] = None,
    max_tokens: Optional[int] = None,
    refresh: bool = True,
) -> FriendsTail:
    """Deterministic fake of feed_read_friends_tails for tests + cache-verification.

    Returns a fixed 2-friend × 3-entry FriendsTail with stable timestamps.
    Useful for lifecycle-2's Arm B deterministic-payload condition.
    """
    ref = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)

    own_entries = [
        FeedEntry(
            handle=own_handle, kind="start", timestamp=ref, project="sidecar",
            summary="working in ~/Dev/sidecar/", files=(),
            raw_line=f"## [2026-05-28 14:30] start | {own_handle} | working in ~/Dev/sidecar/",
        ),
        FeedEntry(
            handle=own_handle, kind="end", timestamp=ref, project="sidecar",
            summary="JWT middleware finished",
            files=("src/auth/jwt.ts", "src/api/login.ts"),
            raw_line=f"## [2026-05-28 14:30] end | {own_handle} | session complete",
        ),
        FeedEntry(
            handle=own_handle, kind="start", timestamp=ref, project="sidecar",
            summary="working in ~/Dev/sidecar/", files=(),
            raw_line=f"## [2026-05-28 14:30] start | {own_handle} | working in ~/Dev/sidecar/",
        ),
    ]
    other_entries = [
        FeedEntry(
            handle="friend-b", kind="start", timestamp=ref, project="sidecar",
            summary="working in ~/Dev/sidecar/", files=(),
            raw_line="## [2026-05-28 14:30] start | friend-b | working in ~/Dev/sidecar/",
        ),
        FeedEntry(
            handle="friend-b", kind="end", timestamp=ref, project="sidecar",
            summary="Stripe webhook handler", files=("src/api/webhooks/stripe.ts",),
            raw_line="## [2026-05-28 14:30] end | friend-b | session complete",
        ),
        FeedEntry(
            handle="friend-b", kind="start", timestamp=ref, project="restore",
            summary="working in ~/Dev/restore/", files=(),
            raw_line="## [2026-05-28 14:30] start | friend-b | working in ~/Dev/restore/",
        ),
    ]

    friends: dict[str, list[FeedEntry]] = {"friend-b": other_entries}
    if include_self:
        friends[own_handle] = own_entries

    return FriendsTail(
        friends=friends,
        fetched_at=ref,
        stale=False,
        formatted_header="## Activity Feed — recent friend activity (synced just now)",
        truncated=False,
    )
