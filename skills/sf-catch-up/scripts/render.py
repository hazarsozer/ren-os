#!/usr/bin/env python3
"""
render.py — the /sf:catch-up skill's deterministic data renderer.

Pipeline per plan §4.2:
    1. Fetch  → feed.pull() best-effort
    2. Filter → feed.read_all_entries with --days / --from / project filters
    3. Group  → bucket by (project, handle) + compute overlap signal
    4. Render → structured markdown (data section only — LLM owns "Suggested next steps")

Output: rendered markdown on stdout, ready for the skill to wrap with an LLM-composed
"Suggested next steps" section. Per team-lead's pushback on plan §4.3, that LLM section
is capped at ≤5 bullets and explicitly marked as LLM-generated.

Exit codes:
    0 = success
    2 = feed not bootstrapped (caller surfaces "Run /sf:install Stage 3")
    3 = no entries matched filters (caller surfaces "no activity in window")
    1 = unexpected error (rare; stderr carries detail)

Usage examples:
    python3 -m scripts.render
    python3 -m scripts.render sidecar --days 7
    python3 -m scripts.render --from hazar --from friend-b --include-self
    python3 -m scripts.render --include-releases
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

# Make the repo's `feed` package importable
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent.parent  # scripts → sf-catch-up → skills → repo
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from feed import config, reader  # noqa: E402
from feed.format import FeedEntry  # noqa: E402
from feed.io_github import last_pull_at, pull  # noqa: E402


DEFAULT_DAYS = 30
"""Per plan §4.1 + ADR-020 §`/sf:catch-up`: 30-day default window."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Step 0: bootstrap check — distinct from "no entries" so caller can show
    # "Run /sf:install Stage 3" rather than a confusing empty result.
    if not (config.local_path() / ".git").exists():
        print(
            f"Activity Feed not bootstrapped at {config.local_path()}.\n"
            "Run /sf:install Stage 3 to set it up.",
            file=sys.stderr,
        )
        return 2

    # Step 1: pull (best-effort; never blocks)
    pull_result = pull()
    pull_stale = not pull_result.ok

    # Step 2: filter
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    own_handle = _resolve_own_handle()
    from_handles = args.from_ if args.from_ else None
    entries = reader.read_all_entries(
        since=since,
        from_handles=from_handles,
        project_filter=args.project,
        refresh=False,  # we already pulled above
    )

    # Apply self-exclusion + release-exclusion (default-off filters)
    if own_handle and not args.include_self:
        entries = [e for e in entries if e.handle != own_handle]
    if not args.include_releases:
        entries = [e for e in entries if e.kind != "release"]

    if not entries:
        print(_render_empty(args, pull_stale=pull_stale, stale_age=last_pull_at()))
        return 3

    # Step 3: group + compute overlap
    grouped = _group_by_project_handle(entries)
    overlaps = _detect_overlaps(entries)

    # Step 4: render
    rendered = _render(
        args=args,
        grouped=grouped,
        overlaps=overlaps,
        all_entries=entries,
        pull_stale=pull_stale,
        last_sync=last_pull_at(),
    )
    print(rendered)
    return 0


# === parser ===============================================================


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Build the /sf:catch-up CLI per plan §4.1."""
    p = argparse.ArgumentParser(
        prog="/sf:catch-up",
        description="Summarize recent Activity Feed entries by project and friend.",
    )
    p.add_argument(
        "project", nargs="?", default=None,
        help="Optional project substring filter (matches against cwd/project tag).",
    )
    p.add_argument(
        "--days", type=int, default=DEFAULT_DAYS,
        help=f"Look-back window in days (default: {DEFAULT_DAYS}).",
    )
    p.add_argument(
        "--from", dest="from_", action="append", default=[],
        help="Filter to one or more friends. Repeatable. Special value 'me' = own handle.",
    )
    p.add_argument(
        "--include-self", action="store_true",
        help="Include own entries in the summary (default: own entries excluded).",
    )
    p.add_argument(
        "--include-releases", action="store_true",
        help="Show framework release announcements (default: hidden).",
    )
    args = p.parse_args(argv)

    # Resolve 'me' shorthand in --from arguments
    own = _resolve_own_handle()
    if own and args.from_:
        args.from_ = [own if h == "me" else h for h in args.from_]
    return args


def _resolve_own_handle() -> str | None:
    """Read handle from wiki/identity.md. Return None if not yet configured.

    Uses strict_schema=False so a schema-drifted identity file still lets catch-up
    work in a degraded mode — better UX than refusing to run because of a future
    schema bump.
    """
    try:
        return config.handle(strict_schema=False)
    except Exception:
        return None


# === grouping + overlap ==================================================


def _group_by_project_handle(entries: Iterable[FeedEntry]) -> dict[str, dict[str, list[FeedEntry]]]:
    """Bucket entries → {project: {handle: [entries]}}. Untagged entries → '(unscoped)'.

    Excludes release entries — those are rendered in their own "## Releases" section
    by the caller. Keeping them out of the project-grouping prevents empty buckets
    showing "0 sessions" for projects where only a release happened.
    """
    grouped: dict[str, dict[str, list[FeedEntry]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        if entry.kind == "release":
            continue
        project = (entry.project or "(unscoped)").strip()
        grouped[project][entry.handle].append(entry)
    return grouped


def _detect_overlaps(entries: Iterable[FeedEntry]) -> dict[str, list[tuple[str, str, str]]]:
    """Compute file-level overlap signal: which files were touched by >1 handle.

    Returns {project: [(filename, handle_a, handle_b), ...]}.
    Pure lexical match — same filename in Touched: across different friends.
    """
    # Build: project → file → set[handle]
    file_touchers: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for entry in entries:
        if entry.kind != "end" or not entry.files:
            continue
        project = (entry.project or "(unscoped)").strip()
        for f in entry.files:
            file_touchers[project][f].add(entry.handle)

    overlaps: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for project, files in file_touchers.items():
        for fname, handles in files.items():
            if len(handles) > 1:
                handles_sorted = sorted(handles)
                # Emit each pair once
                for i in range(len(handles_sorted)):
                    for j in range(i + 1, len(handles_sorted)):
                        overlaps[project].append((fname, handles_sorted[i], handles_sorted[j]))
    return overlaps


# === renderers ===========================================================


def _render(
    *,
    args: argparse.Namespace,
    grouped: dict[str, dict[str, list[FeedEntry]]],
    overlaps: dict[str, list[tuple[str, str, str]]],
    all_entries: list[FeedEntry],
    pull_stale: bool,
    last_sync: datetime | None,
) -> str:
    """Build the full markdown output per plan §4.3."""
    lines: list[str] = []

    # Header
    filter_clauses = _filter_clauses(args)
    lines.append(f"# Activity Feed catch-up — last {args.days} days{filter_clauses}")
    lines.append("")

    # Stale warning banner (top, so user sees it before reading data)
    if pull_stale:
        lines.append(_render_stale_banner(last_sync))
        lines.append("")

    # Releases section (only when --include-releases was passed AND we have any)
    release_entries = [e for e in all_entries if e.kind == "release"]
    if args.include_releases and release_entries:
        lines.append("## Releases")
        lines.append("")
        for e in sorted(release_entries, key=lambda x: x.timestamp, reverse=True):
            ts_str = e.timestamp.strftime("%Y-%m-%d")
            lines.append(f"- {ts_str} — **{e.handle}** — {e.summary or '(no detail)'}")
        lines.append("")

    # By project — filter out release-only buckets (releases handled above)
    # Sort projects by total session count descending, then alphabetically
    project_order = sorted(
        grouped.keys(),
        key=lambda p: (-_total_sessions(grouped[p]), p),
    )

    if project_order:
        lines.append("## By project")
        lines.append("")

    for project in project_order:
        handles_map = grouped[project]
        session_count = _total_sessions(handles_map)
        friend_count = len(handles_map)
        lines.append(f"### {project} ({friend_count} friend{'s' if friend_count != 1 else ''}, {session_count} session{'s' if session_count != 1 else ''})")

        # Sort handles by most-recent activity descending
        handle_order = sorted(
            handles_map.keys(),
            key=lambda h: -max(e.timestamp.timestamp() for e in handles_map[h]),
        )

        for h in handle_order:
            handle_entries = handles_map[h]
            end_entries = [e for e in handle_entries if e.kind == "end"]
            most_recent_ts = max(e.timestamp for e in handle_entries)
            n_sessions = len([e for e in handle_entries if e.kind in ("start", "end")])
            lines.append(
                f"- **{h}** — {n_sessions} session{'s' if n_sessions != 1 else ''}, "
                f"most recent {most_recent_ts.strftime('%Y-%m-%d %H:%M')}"
            )
            # Show task briefs from end-entries (terse, no dates redundant)
            for e in end_entries[-3:]:  # last 3 task briefs per handle
                date_short = e.timestamp.strftime("%m/%d")
                summary = e.summary or "(no summary)"
                lines.append(f"  - {summary} ({date_short})")

        # Overlap warnings for this project
        for fname, h_a, h_b in overlaps.get(project, []):
            lines.append(
                f"- ⚠️ **Overlap**: {h_a} + {h_b} both touched `{fname}` "
                f"— check for divergence before parallel work"
            )
        lines.append("")

    # Footer: source attribution + sync timestamp
    lines.append("---")
    lines.append(_render_footer(all_entries, last_sync, pull_stale))

    return "\n".join(lines).rstrip() + "\n"


def _render_empty(
    args: argparse.Namespace, *, pull_stale: bool, stale_age: datetime | None
) -> str:
    filter_clauses = _filter_clauses(args)
    lines = [
        f"# Activity Feed catch-up — last {args.days} days{filter_clauses}",
        "",
    ]
    if pull_stale:
        lines.append(_render_stale_banner(stale_age))
        lines.append("")
    lines.append("No activity in the window matched your filters.")
    lines.append("")
    lines.append("Try widening: `/sf:catch-up --days 90` or remove `--from` / project filters.")
    return "\n".join(lines)


def _filter_clauses(args: argparse.Namespace) -> str:
    parts = []
    if args.project:
        parts.append(f", project~={args.project!r}")
    if args.from_:
        parts.append(f", from {'+'.join(args.from_)}")
    if args.include_self:
        parts.append(", including own")
    if args.include_releases:
        parts.append(", including releases")
    return "".join(parts)


def _render_stale_banner(last_sync: datetime | None) -> str:
    if last_sync is None:
        return "> ⚠️  **Stale data**: feed has never been synced. Showing what's on disk."
    age = reader._relative_time(last_sync)
    return f"> ⚠️  **Stale data**: pull failed; showing what was synced {age}."


def _render_footer(
    entries: list[FeedEntry], last_sync: datetime | None, pull_stale: bool
) -> str:
    # Per-handle entry counts
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.handle] += 1
    parts = [f"{h}.log.md ({n} entr{'ies' if n != 1 else 'y'})" for h, n in sorted(counts.items())]
    sources = ", ".join(parts) if parts else "no entries"
    sync_str = (
        reader._relative_time(last_sync) if last_sync else "never"
    )
    suffix = "(stale)" if pull_stale else ""
    return f"[feed] sources: {sources} · synced {sync_str} {suffix}".rstrip()


def _total_sessions(handles_map: dict[str, list[FeedEntry]]) -> int:
    """Count start+end entries across all handles in this project bucket."""
    return sum(
        len([e for e in entries if e.kind in ("start", "end")])
        for entries in handles_map.values()
    )


if __name__ == "__main__":
    sys.exit(main())
