"""
lib.memory.lifecycle — 90-day decay at wrap (Task 17, RenOS 0.5.3 "learning
brain"; usage-touch consumption added Task 4, RenOS 0.5.5).

Conservative decay, archive-never-delete (built on Task 16's `archive_page`):
a data-plane page (never `global/`, never already `archive/`, never
quarantined) with no active salience boost is a decay candidate once BOTH
its last journal write AND its last USAGE TOUCH (if any) are older than
`DECAY_WINDOW_DAYS`. A usage touch is any of three mechanical signals: an
on-demand L3 fetch (`collect.KIND_L3_FETCH`, via `miss_log.log_fetch`), a
wake-up injection that surfaced the page (`collect.KIND_WAKEUP_SURFACE`, via
`miss_log.log_surface` — list-valued `"pages"`, unlike the other two kinds'
single `"page"`), or a direct page read (`collect.KIND_PAGE_READ`, via
`miss_log.log_read`). Absence of ALL THREE does NOT protect a page — no one
has asked for it back, mechanically or by hand, which is itself the decay
signal — but reading the three usage-metric kinds is a single all-or-nothing
gate: if any is unreadable (I/O error), `decay_candidates` returns `[]`
entirely rather than guessing per page, per the spec's "conservative"
mandate.

Pruning: the metrics log already rotates by calendar month
(`collect._month_file`), so a long-running install's usage history is
naturally bounded without any explicit prune step here (YAGNI).

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
from lib.memory import archive, journal, locks, quarantine, queue, write_apply
from lib.memory.provenance import new_provenance, read_frontmatter_provenance

DECAY_WINDOW_DAYS = 90
DECAY_MAX_PER_WRAP = 5

# Task 18: consolidation of judge-confirmed duplicates. Stricter than the
# wrap-screen report threshold (JUDGE_MIN_CONFIDENCE in lib.memory.judge) —
# merging two pages is a bigger, harder-to-undo-cleanly act than merely
# surfacing a possible duplicate for a human to read.
CONSOLIDATE_MAX_PER_WRAP = 3
CONSOLIDATE_MIN_CONFIDENCE = 0.85

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

    Conservative I/O rule: reads all three usage-metric kinds
    (`collect.read(kind=KIND_L3_FETCH | KIND_WAKEUP_SURFACE | KIND_PAGE_READ)`)
    inside one gate — if ANY is unreadable, returns `[]` — decay is skipped
    entirely for this call, never partially.
    """
    try:
        fetch_entries = collect.read(kind=collect.KIND_L3_FETCH)
        surface_entries = collect.read(kind=collect.KIND_WAKEUP_SURFACE)
        read_entries = collect.read(kind=collect.KIND_PAGE_READ)
    except OSError:
        return []

    last_touch_by_page: dict[str, datetime] = {}

    def _touch(page: str | None, ts_raw: str | None) -> None:
        if not page:
            return
        entry_time = _parse_ts(ts_raw)
        if entry_time is None:
            return
        if page not in last_touch_by_page or entry_time > last_touch_by_page[page]:
            last_touch_by_page[page] = entry_time

    for entry in fetch_entries:
        _touch(entry.get("page"), entry.get("ts"))
    for entry in surface_entries:
        ts_raw = entry.get("ts")
        for page in entry.get("pages") or []:
            _touch(page, ts_raw)
    for entry in read_entries:
        _touch(entry.get("page"), entry.get("ts"))

    root = ren_paths.wiki_root()
    salient = _salient_pages(now)

    candidates: list[tuple[datetime, str]] = []
    for rel in _data_plane_pages(root):
        if archive.is_archived(rel) or rel in salient:
            continue

        write_ts = _last_write_ts(rel)
        if write_ts is None or now - write_ts <= timedelta(days=DECAY_WINDOW_DAYS):
            continue

        touch_ts = last_touch_by_page.get(rel)
        if touch_ts is not None and now - touch_ts <= timedelta(days=DECAY_WINDOW_DAYS):
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


def _ineligible_for_consolidation(rel: str, content: str) -> bool:
    """True if `rel` (with its already-read `content`) must never be
    touched by consolidation: `global/` (instruction plane), quarantined
    (unreviewed llm-auto data), or `foreign` trust (ingested from outside
    the session — never mechanically merged)."""
    if rel == "global" or rel.startswith("global/"):
        return True
    if quarantine.is_quarantined(content):
        return True
    prov = read_frontmatter_provenance(content)
    if prov is not None and prov.get("trust") == "foreign":
        return True
    return False


def consolidate_duplicates(findings: list[dict], session: str) -> list[dict]:
    """Auto-merge up to `CONSOLIDATE_MAX_PER_WRAP` judge-confirmed duplicate
    pairs from `findings` (wrap's `semantic_findings` shape — see
    `skills.wrap.lib._judge_semantic_findings`).

    For each `verdict == "duplicate"` finding at confidence >=
    `CONSOLIDATE_MIN_CONFIDENCE` where NEITHER page is `global/`,
    quarantined, or `foreign` trust: the older page (by frontmatter `ren_ts`)
    archives via `archive.archive_page(reason="consolidated")`, and the
    newer page gets an UPDATE (through `write_apply.apply_write`, same
    single write door `archive_page` itself uses, TOCTOU-guarded with
    `expect_token` exactly like `archive_page` threads it) appending a
    one-line `Merged from [[<old rel>]] (<date>).` under its body, journaled
    with `journal_extra={"merged_from": old_rel}`.

    Conservative, fail-closed per pair, never raises:
      - a page missing `ren_ts` (never written through the provenance door)
        makes the pair un-orderable — skipped rather than guessed.
      - already-archived pages are skipped.
      - `locks.LostUpdate`/`OSError`/`ValueError` from either write (a
        concurrent write racing the sweep, most plausibly) skips just that
        pair — the rest of the batch still runs, same isolation discipline
        as `run_decay`.

    Returns the merges that actually landed, plus any partial failures
    (older page archived, newer-page UPDATE then raised) surfaced distinctly
    rather than dropped:
      `[{"status": "merged", "archived": <old rel>, "archive_page":
      <archive rel>, "merged_into": <new rel>, "write_id": <UPDATE write_id>}
      | {"status": "partial", "archived": <old rel>, "archive_page":
      <archive rel>, "update_failed": <new rel>, "error": <str>}]`.
    """
    root = ren_paths.wiki_root()
    moves: list[dict] = []

    for finding in findings:
        if len(moves) >= CONSOLIDATE_MAX_PER_WRAP:
            break

        if finding.get("verdict") != "duplicate":
            continue
        if finding.get("confidence", 0) < CONSOLIDATE_MIN_CONFIDENCE:
            continue

        page = finding.get("page")
        other = finding.get("with")
        if not page or not other:
            continue
        if archive.is_archived(page) or archive.is_archived(other):
            continue

        page_abs = ren_paths.safe_join(root, page)
        other_abs = ren_paths.safe_join(root, other)
        try:
            # Read content and capture its content_token in the same breath,
            # mirroring archive.archive_page's own read+token pairing — the
            # token must reflect exactly the state the write is built from,
            # not a fresh read taken after the archive_page round-trip below
            # (see task-18-review.md CRITICAL finding).
            page_content = page_abs.read_text(encoding="utf-8")
            page_token = locks.content_token(page_abs)
            other_content = other_abs.read_text(encoding="utf-8")
            other_token = locks.content_token(other_abs)
        except OSError:
            continue

        if _ineligible_for_consolidation(page, page_content) or _ineligible_for_consolidation(
            other, other_content
        ):
            continue

        page_prov = read_frontmatter_provenance(page_content)
        other_prov = read_frontmatter_provenance(other_content)
        page_ts = _parse_ts(page_prov.get("ts") if page_prov else None)
        other_ts = _parse_ts(other_prov.get("ts") if other_prov else None)
        if page_ts is None or other_ts is None:
            continue

        if page_ts <= other_ts:
            older_rel, newer_rel, newer_content, expect_token = page, other, other_content, other_token
        else:
            older_rel, newer_rel, newer_content, expect_token = other, page, page_content, page_token

        try:
            archive_move = archive.archive_page(older_rel, session, reason="consolidated")
        except (locks.LostUpdate, ValueError, OSError):
            continue

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        merged_body = newer_content.rstrip("\n") + f"\nMerged from [[{older_rel}]] ({date}).\n"

        prov = new_provenance("routine", session, "UPDATE", newer_rel)
        try:
            write_apply.apply_write(
                newer_rel,
                merged_body,
                prov,
                expect_token=expect_token,
                journal_extra={"merged_from": older_rel},
            )
        except (locks.LostUpdate, OSError) as exc:
            # The older page is already archived (irreversible without a
            # manual undo) but the newer-page UPDATE failed — a half-done
            # merge. Surface it distinctly rather than silently dropping the
            # pair (see task-18-review.md Important finding); "status" is
            # new so callers checking "merged_into"/"write_id" on normal
            # entries are unaffected.
            moves.append(
                {
                    "status": "partial",
                    "archived": older_rel,
                    "archive_page": archive_move["archive_page"],
                    "update_failed": newer_rel,
                    "error": str(exc),
                }
            )
            continue

        moves.append(
            {
                "status": "merged",
                "archived": older_rel,
                "archive_page": archive_move["archive_page"],
                "merged_into": newer_rel,
                "write_id": prov.write_id,
            }
        )

    return moves


__all__ = [
    "DECAY_WINDOW_DAYS",
    "DECAY_MAX_PER_WRAP",
    "CONSOLIDATE_MAX_PER_WRAP",
    "CONSOLIDATE_MIN_CONFIDENCE",
    "decay_candidates",
    "run_decay",
    "consolidate_duplicates",
]
