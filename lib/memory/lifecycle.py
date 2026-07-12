"""
lib.memory.lifecycle — 90-day decay at wrap (Task 17, RenOS 0.5.3 "learning
brain").

Conservative decay, archive-never-delete (built on Task 16's `archive_page`):
a data-plane page (never `global/`, never already `archive/`, never
quarantined) with no active salience boost is a decay candidate once BOTH
its last journal write AND its last miss-log fetch (if any) are older than
`DECAY_WINDOW_DAYS`. Absence of a fetch record does NOT protect a page — no
one has asked for it back, which is itself the decay signal — but the
miss-log read is a single all-or-nothing gate: if it's unreadable (I/O
error), `decay_candidates` returns `[]` entirely rather than guessing per
page, per the spec's "conservative" mandate.

Salience mirrors `hooks/wake-up/wakeup._salient_pages`'s window semantics
(same SALIENCE_WINDOW_DAYS value, same "any applied queue entry with
proposal.salience=True, ts within window" rule) rather than importing it —
`hooks/wake-up/` is a hyphenated package path (import needs `importlib`,
`skills/wrap/lib/__init__.py::_run_wiki_health_sweep` is the precedent for
that dance) and, more importantly, `lib/` importing from `hooks/` would
invert the framework's layering (hooks depend on lib, never the reverse).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib import ren_paths
from lib.instrument import collect
from lib.memory import archive, journal, locks, quarantine, queue

DECAY_WINDOW_DAYS = 90
DECAY_MAX_PER_WRAP = 5

# Mirrors hooks/wake-up/wakeup.SALIENCE_WINDOW_DAYS — see module docstring
# for why this isn't imported directly.
_SALIENCE_WINDOW_DAYS = 30

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, _TS_FMT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _data_plane_pages(root) -> list[str]:
    """Every `*.md` wiki-relative path under `root`, excluding `archive/` and
    `global/` (same rglob-and-filter pattern used by `quarantine`, `revert`,
    `promotion` — there's no shared "list all data-plane pages" helper)."""
    pages = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        top = rel.split("/", 1)[0]
        if top in ("archive", "global"):
            continue
        pages.append(rel)
    return pages


def _salient_pages(now: datetime) -> set[str]:
    try:
        entries = queue.all_entries()
    except Exception:  # noqa: BLE001 - decay must never crash on queue read
        return set()

    result: set[str] = set()
    for entry in entries:
        if not (entry.status == "applied" and entry.proposal.salience and entry.proposal.page):
            continue
        entry_time = _parse_ts(entry.ts)
        if entry_time is None or now - entry_time <= timedelta(days=_SALIENCE_WINDOW_DAYS):
            result.add(entry.proposal.page)
    return result


def _last_write_ts(rel: str) -> datetime | None:
    latest: datetime | None = None
    for entry in journal.entries(page=rel):
        entry_time = _parse_ts(entry.get("ts"))
        if entry_time is not None and (latest is None or entry_time > latest):
            latest = entry_time
    return latest


def decay_candidates(now: datetime) -> list[str]:
    """Data-plane pages eligible for 90-day decay, oldest-write-first.

    Conservative I/O rule: if the miss-log (`collect.read(kind=KIND_L3_FETCH)`)
    is unreadable, returns `[]` — decay is skipped entirely for this call,
    never partially.
    """
    try:
        fetch_entries = collect.read(kind=collect.KIND_L3_FETCH)
    except OSError:
        return []

    last_fetch_by_page: dict[str, datetime] = {}
    for entry in fetch_entries:
        page = entry.get("page")
        if not page:
            continue
        entry_time = _parse_ts(entry.get("ts"))
        if entry_time is None:
            continue
        if page not in last_fetch_by_page or entry_time > last_fetch_by_page[page]:
            last_fetch_by_page[page] = entry_time

    root = ren_paths.wiki_root()
    salient = _salient_pages(now)

    candidates: list[tuple[datetime, str]] = []
    for rel in _data_plane_pages(root):
        if archive.is_archived(rel) or rel in salient:
            continue

        write_ts = _last_write_ts(rel)
        if write_ts is None or now - write_ts <= timedelta(days=DECAY_WINDOW_DAYS):
            continue

        fetch_ts = last_fetch_by_page.get(rel)
        if fetch_ts is not None and now - fetch_ts <= timedelta(days=DECAY_WINDOW_DAYS):
            continue

        try:
            content = ren_paths.safe_join(root, rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if quarantine.is_quarantined(content):
            continue

        candidates.append((write_ts, rel))

    candidates.sort(key=lambda pair: pair[0])
    return [rel for _, rel in candidates]


def run_decay(session: str) -> list[dict]:
    """Archive up to `DECAY_MAX_PER_WRAP` decay candidates (oldest first),
    `reason="decay-90d"`. A single page's `archive_page` call failing (most
    plausibly `locks.LostUpdate` from a concurrent write racing the sweep) is
    skipped, not fatal — the rest of the batch still runs. Returns the moves
    that actually landed; never raises."""
    now = datetime.now(timezone.utc)
    moves: list[dict] = []
    for rel in decay_candidates(now)[:DECAY_MAX_PER_WRAP]:
        try:
            moves.append(archive.archive_page(rel, session, reason="decay-90d"))
        except (locks.LostUpdate, ValueError, OSError):
            continue
    return moves


__all__ = ["DECAY_WINDOW_DAYS", "DECAY_MAX_PER_WRAP", "decay_candidates", "run_decay"]
