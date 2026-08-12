# Producer link duties (#54) — design

**Date:** 2026-08-12 · **Issue:** [#54](https://github.com/hazarsozer/ren-os/issues/54) · **Target version:** 0.7.0 (with #53 merged, #55 next)

## Problem

Producers write pages but never link them: L1 session pages are sinks, the
chronological log carries no links, and durable data-plane pages depend on a
session author remembering to add a pointer. Post-#53 the pointer grammar is
Obsidian-native, but connectivity is still optional. This spec makes it a
property of the wrap write path — mechanical, not instructional.

## Decisions already made (with Hazar)

- L1 reachability: the project map gains an auto-maintained `## Sessions`
  section (not a per-project `l1/index.md`, not log-only).
- Enforcement: auto-pointer + warn (wrap links new durable pages itself and
  warns when it can't) — not warn-only, not a hard write gate.
- `raw/` and `archive/` stay unlinked by design; `l1/` must be reachable.

## The four duties (all in `skills/wrap/lib`)

### D1 — L1 "Touched pages" section

Before writing the L1 page, `wrap_session` appends to the narrative:

```
## Touched pages
- [<page title or slug>](<wiki-relative-path>)
```

one line per distinct page in `applied` (plus overview.md / open-work.md when
this wrap created or updated them). Links render via
`"- [" + title + "](" + path + ")"` — plain markdown links, NOT decision-map
pointer lines (no write_id parenthetical; these are narrative links, and
`remember`/sweeps must not mistake them for pointers — which they won't,
since L1 pages are not `type: l2-map`). Title = the target page's first `# `
heading if cheaply readable, else the filename stem. Empty `applied` and no
maintained pages → no section at all.

### D2 — log.md session entry (new writer)

Wrap currently never writes `log.md`. Add an append, through the queue
(producer `"wrap"`, registered in `_PRODUCERS`; op UPDATE on `log.md`),
following the page's documented entry grammar:

```
## [YYYY-MM-DD] session | <project or "global"> — [session-<id>](projects/<slug>/l1/session-<id>.md)
```

Appended after the last entry (chronological, append-only invariant). The
link target is exactly the L1 path `wrap_session` just wrote. A wiki whose
`log.md` is missing → skip with a wrap-screen warning, never create the file
(bootstrap owns skeleton pages).

### D3 — map `## Sessions` section

After the L1 write, wrap appends to `projects/<slug>/map.md`:

```
## Sessions
- [session-<id>](projects/<slug>/l1/session-<id>.md)
```

creating the section (before `## Log` if present, else at end of body) when
absent, capped at the 10 most recent lines (trim oldest-first on overflow —
older sessions stay reachable via log.md). Plain markdown links, same
rationale as D1. Map writes go through the queue (UPDATE, producer `"wrap"`),
must preserve frontmatter and any quarantine banner byte-for-byte, and only
ever insert/trim within the `## Sessions` section.

`skills/remember/lib`'s `_sections` currently drops unknown headers — add
`## Sessions` to its known-headers tuple and render it in prose as a short
"recent sessions" line (count + most recent), not a dump.

### D4 — auto-pointer for new durable pages + master-index spine

For each entry in `applied` whose op was ADD and whose page lives under
`projects/<slug>/` (excluding `l1/`, `raw/`, `archive/`, `map.md` itself,
`overview.md`, `open-work.md`): if the project map's body does not already
reference that path anywhere, append to the map's `## Decision map`:

```
- [<topic>](<path>) (<write_id>)
```

via `lib.pointer.render_pointer_line(topic, path, write_id)` — write_id from
the applied queue entry; topic = the page's first `# ` heading, else the
filename stem. Spine: the same pass idempotently ensures the master
`index.md` `## Decision map` contains a pointer to
`projects/<slug>/map.md` (topic = `<slug>`, write_id = the map's current
`ren_write_id` if readable, else `unstamped`).

Pages that cannot be linked (no project in scope, map missing) are collected
and surfaced on the wrap screen as warnings, alongside D2's skip warning.

## Write mechanics (all duties)

- Every wiki write goes through `lib.memory.queue.propose_and_apply`
  (producer `"wrap"`), journaled and revertible — never a direct file write.
- All decision-map pointer lines through `lib.pointer.render_pointer_line`;
  D1/D3 narrative links are plain markdown by design (documented in code).
- Section edits are append/trim-within-section only: frontmatter, quarantine
  banners, and all other sections pass through untouched.

## Error handling

Each duty is isolated exactly like wrap's existing sweeps (`decayed`,
`consolidated`): any exception degrades to a wrap-screen warning entry,
never a failed session close-out. `wrap_session`'s result dict gains
`"links": {"l1_touched": int, "log_entry": bool, "sessions_entry": bool,
"auto_pointers": [pages], "warnings": [strings]}` — always present, zeroed
on total failure.

## Testing

- Unit per duty: D1 section content/absence; D2 grammar + append position +
  missing-log skip; D3 create/append/cap/trim + banner & frontmatter
  preservation + remember rendering; D4 pointer added, dedup (already-linked
  path → no write), exclusion list respected, spine idempotence.
- Integration: full `wrap_session` on a temp wiki (skeleton-stamped) →
  L1 has Touched pages, log.md gained a linked entry, map gained Sessions +
  a pointer for the new durable page, index.md links the map; a SECOND
  wrap_session run adds a second session line but duplicates neither the
  pointer nor the spine line.
- All existing wrap tests stay green; `links` key present in every result.

## Out of scope

- #55 orphan detection; backfilling existing orphan pages (post-release
  `/ren:wiki-health` repair work).
- Any change to pin/ingest/retrospective producers (wrap is where pages are
  born in practice; others already pointer their writes or write no pages).
- log.md backfill for past sessions.
