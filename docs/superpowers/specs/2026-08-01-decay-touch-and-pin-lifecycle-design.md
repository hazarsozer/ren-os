# Decay touch signals (#24) + pin lifecycle (#25) — design

Date: 2026-08-01
Issues: [#24](https://github.com/hazarsozer/ren-os/issues/24), [#25](https://github.com/hazarsozer/ren-os/issues/25)
Decided with Hazar in a live session; approved before implementation.

## #24 — wake-up surfacing no longer counts as a decay usage touch

### Problem

`decay_candidates` (`lib/memory/lifecycle.py`) treats three signals as a
usage touch: L3 fetch, direct page read, and `KIND_WAKEUP_SURFACE`. The
first two are genuine demand; the third is the framework's own output — a
page that keeps ranking into "Possibly relevant now" refreshes its own
90-day clock every session, which keeps it live, which keeps it ranking.
A stale page can self-perpetuate indefinitely.

### Decision

Drop `KIND_WAKEUP_SURFACE` from the touch signals entirely:

- `decay_candidates` stops reading `collect.KIND_WAKEUP_SURFACE`; the
  conservative fail-closed I/O gate shrinks to the two remaining metrics
  (fetch + read — if either is unreadable, decay is still skipped
  entirely for that call).
- The surface-entries touch loop is deleted.
- Docstrings change from "three signals" to "two signals — mechanical
  evidence a human or session actually wanted the page; wake-up surfacing
  is the framework's own output and never counts as demand".
- Surfacing stays logged via `miss_log` for the miss metric — untouched.

Net effect: decay becomes slightly more aggressive — "injected 40 times,
never once read or fetched" now decays, which is the honest outcome (the
ranker being wrong about a page is not demand for it).

### Tests

- A page whose only touch is a wake-up surface entry IS a decay candidate.
- A page with a recent `KIND_PAGE_READ` or `KIND_L3_FETCH` is NOT.
- An unreadable fetch or read metric still skips decay entirely
  (fail-closed gate preserved for the two signals that remain).

## #25 — wrap closes the pin loop

### Problem

`/ren:pin` is the right verb for "next session, do X", but nothing closes
the loop: once X is done, the pin remains a live, human-trust page.
Salience lapses after 30 days, yet the page stays an extras candidate. The
only disposal today is the friend remembering `/ren:pin --wrong <page>`.

### Decision

Wrap-side cleanup gate + doc note. No TTL pin flavor, no new pin syntax,
no fired-once state (YAGNI — the wrap gate closes the loop with a human in
it; pins are rare enough to list them all).

Mechanical detection, human decision, queue-routed disposal:

1. **`live_pin_pages()`** (new, `skills/wrap/lib`): applied queue entries
   with `producer="pin"` whose page still exists on disk and is not
   archived; deduped by page, newest-first. Purely mechanical — no
   "plan-shaped" classification in code; judging whether a pin looks
   acted-on is model-work for the live session.
2. **Wrap screen**: `render_wrap_screen` gains a "Live pins" section
   listing each live pin page with a content preview. Omitted entirely
   when there are none (same no-bare-header rule as wake-up sections).
3. **`skills/wrap/SKILL.md`**: new step — at wrap, review the live pins;
   for any that look acted-on, ask the friend "delete / keep?". A
   confirmed delete goes through the queue as a normal DELETE proposal via
   the existing correction path (`skills.pin.lib.correct(page, None,
   session)` — `producer="pin"`, `writer="human"`). Nothing auto-deletes;
   no answer means keep.
4. **`skills/pin/SKILL.md`** doc note: a task-shaped pin should carry
   "…and delete this page" as its own last step (manual mitigation stays
   documented as belt-and-braces).

### Tests

- `live_pin_pages()` returns an applied pin whose page exists; excludes
  deleted-from-disk pages, archived pages, and non-pin producers; dedupes
  multiple entries for the same page.
- `render_wrap_screen` shows the "Live pins" section when pins are live
  and omits the header entirely when none are.
- A wrap-gated delete lands as a queue DELETE with `producer="pin"`,
  `writer="human"` (existing `correct` behavior — regression-covered).
