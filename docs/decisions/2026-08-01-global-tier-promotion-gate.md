# Decision — global-tier writes are promotion-gated by construction (issue #18)

- **Date:** 2026-08-01
- **Status:** accepted
- **Scope:** `lib/governance/tiers.py`, `lib/suggestions/gate.py`,
  `lib/memory/lifecycle.py`, `skills/bootstrap-project`, `skills/ingest-project`,
  `skills/wiki-health`
- **Supersedes nothing.** Tightens the v2.2 two-plane pivot (spec §10) — it
  does not revisit it.

> This repo has no numbered ADR series (the numbered `wiki/decisions/NNN-*.md`
> series lives in the pre-rebrand dev repo). Decision records here follow the
> dated-filename convention already used by `docs/audits/`.

## Context

The README's memory-hierarchy diagram draws the global tier — `decisions/` ·
`patterns/` · `research/` · identity — as reachable only by "promotion (gated,
never automatic)". The code disagreed: `lib.governance.tiers` classified only
`global/` as the instruction plane, so every root-level global-tier directory
was data plane. A `producer="ingest", writer="llm-auto"` proposal targeting
`decisions/<anything>.md` auto-applied like any session note.

This is not hypothetical. Dogfooding the Flux ingest (2026-07-31) the live
session wrote a project-specific `decisions/flux-stack.md`; nothing in the
queue, the tier model, or `/ren:doctor` pushed back. The page was relocated to
`projects/flux/stack.md` after founder review.

Two encodings of the same "is this instruction plane?" question already existed
alongside the tier model (`lib.suggestions.gate.is_critical_page`,
`lib.memory.lifecycle._data_plane_pages`), each re-spelling the `global/`
prefix by hand — three places to fix, three places to drift.

## Founder doctrine (the rule being encoded)

**Global-tier `decisions/` and `patterns/` are ONLY for practices general
enough to apply across projects. Project-specific decisions live under
`projects/<slug>/` and reach the global tier only via the promotion
producer.**

## Decision

1. **The instruction plane is the whole global tier.**
   `lib.governance.tiers.INSTRUCTION_PLANE_PREFIXES = ("global/",
   "decisions/", "patterns/", "research/")` is the single canonical encoding,
   with `is_instruction_plane_page(page)` as the only predicate. `tier_of`
   returns `diff_approved` for any memory write to those prefixes, for every
   writer and every producer.

2. **Gate by page prefix, not by producer.** The producer is deliberately NOT
   added to `Action`. Prefix-only is strictly stronger and needs no new field:
   the only legitimate global-tier writer, `lib.memory.promotion
   .promote_to_global`, already uses plain `propose()` (never
   `propose_and_apply`) and reaches the page through
   `approve_and_apply` — a human. Making the prefix itself
   `diff_approved` means every *other* producer inherits the gate
   automatically, including future ones, with no allowlist to keep current.

3. **Hold, don't downgrade.** A non-promotion write to the instruction plane
   holds pending (`propose_and_apply` returns `(entry, None)`; provenance is
   `None`; the page is untouched) — the exact mechanism already used for
   `global/` and for contradiction holds. Pending instruction-plane entries
   are already surfaced at wake-up and reviewable via `/ren:suggestions`; no
   new machinery was built, per the issue's "downgrade to a promotion
   suggestion" suggestion being explicitly optional. `apply_auto` and
   `resolve_and_apply` re-check the tier independently, so neither is a
   backdoor.

4. **One source of truth.** `gate.is_critical_page` and
   `lifecycle._data_plane_pages` now delegate to
   `is_instruction_plane_page`; `tests/lib/governance/test_tiers.py`
   asserts the encodings agree, so a future prefix change cannot drift.
   A side effect worth naming: decay no longer considers global-tier pages
   at all — they are durable by construction and only a human puts them
   there.

5. **`producer="promotion"` now means global-tier promotion, only.**
   `skills/bootstrap-project` used it for a data-plane L2 map
   (`projects/<slug>/map.md`); it now uses `producer="ingest"` with
   `writer="human"` (trust class is unchanged — `writer == "human"` wins, so
   it stays `user`).

6. **Doctrine gets an auditor, not just a wall.** `skills/wiki-health`'s
   `sweep()` gains `single_project_global_pages`: global-tier pages whose body
   names exactly one project (explicit `projects/<slug>` reference, or a bare
   word matching a known slug from `.ren/projects.json` plus the `projects/`
   directory names). Zero projects named (genuinely general) or two-plus (a
   real cross-project comparison) is not a finding. It gets its own report
   section, "none" when clean. The gate stops *new* violations; this finds the
   ones already on disk, including hand-authored ones the queue never saw.

## Consequences

- Any producer that wants a page in `decisions/`·`patterns/`·`research/` now
  gets a pending entry and a human question instead of a silent write. That is
  the intended friction.
- `skills/ingest-project`'s hold message was widened — it previously claimed a
  conflict was flagged whenever `write_id is None`, which would now misreport a
  governance hold.
- Pages the friend authors directly in Obsidian are unaffected (the queue only
  governs framework writes) — that is exactly why the wiki-health check exists.

## Migration: none needed

`migrations/queue-governance-2-to-3` set the precedent for a migration when
governance changes: that one *released* entries a stricter old policy had
parked, so leaving them pending would have silently swallowed writes.

This change is the opposite direction — strictly *fewer* auto-applies from here
on. It cannot invalidate an existing queue entry:

- Already-`applied` entries stay applied; the tier model is not consulted for
  them, and no page content is rewritten. Historically auto-applied global-tier
  pages remain exactly as they are (and now show up in the wiki-health check if
  they name one project).
- Already-`pending` entries stay pending and become *harder* to release, never
  easier — `auto_apply_eligible` is the same function the migration reuses, and
  it can only return `False` where it used to return `True`. A pending
  global-tier entry now needs `approve_and_apply`, which was always available.

There is therefore no state on disk that a migration would have to touch, and
no re-run of `queue-governance-2-to-3` is required.
