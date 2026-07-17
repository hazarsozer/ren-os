"""
lib.instrument.miss_log — G12 mechanical wake-up miss log (Task 3.3, RenOS 0.2
Phase 3).

Spec §3.2 "Honest miss measurement": a fetch of active-project knowledge that
wake-up could have surfaced = a wake-up miss. The definition is mechanical and
the denominator is computable — no LLM self-report of "did I have this
already" involved. Two thin event-log wrappers plus a join:

  - `log_fetch` — call this wherever the framework does an on-demand L3 fetch
    (e.g. `/ren:recall`, a retrieval-eval query) to pull a page wake-up didn't
    already inject.
  - `log_surface` — call this from the wake-up hook with exactly the pages it
    injected for a session.
  - `log_read` — call this wherever a page is read directly (not via an L3
    fetch or wake-up injection), e.g. Task 5's read hook. Feeds decay
    protection (`lib.memory.lifecycle.decay_candidates`) as a third usage
    signal alongside fetches and wake-up surfacing.
  - `misses` — joins the two logs BY SESSION: a fetch is a miss iff its
    session has a recorded wakeup-surface AND the fetched page isn't in it.
    Fetches from a session with NO surface record are excluded from the
    denominator entirely — without knowing what wake-up actually surfaced for
    that session, "could it have surfaced this" is unanswerable, and an
    excluded fetch must never silently count as a hit.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib.instrument import collect


def log_fetch(page: str, query: str, session: str) -> None:
    """Record an on-demand L3 fetch (a page pulled that wake-up didn't inject).

    The query is user free-text and metrics JSONL is append-only, never pruned
    (Task 9.3 FIX 2, holistic-review HIGH finding): a secret pasted into a
    recall query must never land at rest in the metrics stream — same
    redaction pattern as the classifier-event preview.
    """
    from lib.memory import scrub  # local import: instrument stays importable without lib.memory

    if scrub.scan(str(query)):
        query = "<redacted: secret-shaped content>"
    collect.record(collect.KIND_L3_FETCH, {"page": page, "query": query, "session": session})


def log_surface(pages: list[str], session: str) -> None:
    """Record the exact set of pages wake-up surfaced for `session`."""
    collect.record(collect.KIND_WAKEUP_SURFACE, {"pages": list(pages), "session": session})


def log_read(page: str, session: str) -> None:
    """Record a direct read of `page` (mirrors `log_fetch`'s shape, minus the
    free-text query — there's nothing to scrub)."""
    collect.record(collect.KIND_PAGE_READ, {"page": page, "session": session})


@dataclass(frozen=True)
class MissReport:
    fetches: int      # total L3 fetches counted (only sessions with a surface record)
    misses: int        # of those, fetches of a page NOT in that session's surfaced set
    miss_rate: float   # misses / fetches, 0.0 when fetches == 0


def misses(since: str | None = None) -> MissReport:
    """Compute the mechanical miss rate over `collect`'s L3_FETCH/WAKEUP_SURFACE
    records, optionally restricted to `ts >= since`.

    A session may have multiple `log_surface` calls recorded (e.g. wake-up ran
    more than once); the surfaced set for a session is the UNION of every
    surface record's pages within the window, not just the most recent one.
    """
    fetch_entries = collect.read(kind=collect.KIND_L3_FETCH, since=since)
    surface_entries = collect.read(kind=collect.KIND_WAKEUP_SURFACE, since=since)

    surfaced_by_session: dict[str, set[str]] = {}
    for entry in surface_entries:
        session = entry.get("session")
        pages = entry.get("pages") or []
        surfaced_by_session.setdefault(session, set()).update(pages)

    fetch_count = 0
    miss_count = 0
    for entry in fetch_entries:
        session = entry.get("session")
        surfaced = surfaced_by_session.get(session)
        if surfaced is None:
            continue  # no surface record for this session -> excluded entirely
        fetch_count += 1
        if entry.get("page") not in surfaced:
            miss_count += 1

    miss_rate = (miss_count / fetch_count) if fetch_count else 0.0
    return MissReport(fetches=fetch_count, misses=miss_count, miss_rate=miss_rate)


__all__ = ["log_fetch", "log_surface", "log_read", "MissReport", "misses"]
