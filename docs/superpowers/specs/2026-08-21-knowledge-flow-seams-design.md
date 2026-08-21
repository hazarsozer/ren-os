# Knowledge-flow seams — page typing, finding retraction, merge transport

**Date:** 2026-08-21
**Status:** Approved design (brainstorm 2026-08-21, post-0.8.0)
**Decides:** GitHub #74 (write door stamps no `type:`), #73 (`accept()` has no
`place_durable_item` route), #75 (update-verdicts unreachable under the
`verdicts=` transport), #72 (scrub false positive on a trailing comma), plus
the `schemas.json` type-registry drift surfaced while scoping #74.

## 1. Evidence (why now)

0.8.0 shipped the knowledge flows end-to-end and they immediately started
being used — by the distiller, by `/ren:pin`, and on 2026-08-20 by a real
non-ren-os session (`d51255fa`, project hallm). Every seam between the new
producers and the pre-existing consumers leaked.

Measured on the live wiki, 2026-08-21:

- **49 pending suggestions, 100% of them wiki-health lint.** Breakdown:
  26 `missing-frontmatter-type`, 17 quarantine-release `structured_action`,
  3 `map-pointer-missing`, 2 `dangling-link`, 1 `hub-split-link-lists`.
- **The 26 are #74 compounding.** The 2026-08-19 ledger line predicted
  "~11 duplicate suggestions" on the next sweep. The 2026-08-20 sweep raised
  the count to 26. The rate is proportional to how much the system is used:
  every page the distiller, pin, or retrospective creates lands without
  `type:` and manufactures one more finding.
- **29 of 156 wiki pages carry no `type:`** — every one of them created by a
  producer that routes through the write door.
- **`expire_stale_pending()` is age-based only** (30 days, run at wrap).
  Nothing ever re-checks whether a finding still holds, so a finding fixed by
  other means sits pending for a month and then expires undecided.
- **`schemas.json` registers 8 page types; the wiki uses 13.** `l1`, `lesson`,
  `hub`, `licenses`, and `log-entry` appear on disk and in no registry.
- **All three of the 2026-08-19 wrap's durable-affirmed candidates died** to
  `merge llm call failed: 'NoneType' object is not callable` (#75).
- **#72 blocked the 0.7.9 release push once** and is still open.

The unifying diagnosis: 0.8.0's producers were built and wired, but the
consumers they hand off to — the frontmatter schema, the suggestions store,
the merge step — were never taught about them.

## 2. Part A — page typing (#74)

### 2.1 Where derivation happens

**`queue.propose()`, before `_normalize_body()` runs.** Not
`stamp_frontmatter()`.

This placement is the whole design. `_normalize_body()`'s docstring records
the invariant that makes it work:

> Only `stamp_frontmatter`'s own `ren_*` keys are noise here — they're added
> downstream of this comparison and never appear in a proposal's raw content.

A `type:` stamped in the door would land *downstream* of the duplicate
comparison: a re-proposal of byte-identical content (no `type:`) would be
compared against a stored page (with `type:`) and never normalize equal.
Every idempotent re-write would register as a real change, breaking:

- the distiller's noop-duplicate exclusion from `WRITE_CAP` (commit `5bb8d07`),
- `suggestions._apply()`'s `"content already on page"` branch,
- the re-accept safety that `accept()`'s docstring depends on.

Deriving at propose-time puts `type:` inside the comparison boundary — present
on both sides — so all three keep working untouched. `stamp_frontmatter()`
keeps owning `ren_*` and nothing else, and the ren-distiller agent contract
("no frontmatter — the write door stamps frontmatter") stays honest.

### 2.2 Single source of truth

New module `lib/memory/page_types.py`, exporting:

```python
def derive_type(page: str) -> str | None
```

Two consumers, one table, no drift:

1. `queue.propose()` — fills a missing `type:` on new content
2. `migrations/frontmatter-type-1/` — the backfill (§2.5)

The lint is **not** a third consumer: its `missing-frontmatter-type` rule
checks only that a `type:` is present, never what it should be. It becomes
one if a rule ever validates the value.

`skills/wrap/lib/_ensure_l1_type` already stamps `type: l1` on L1 narratives
before they reach the door. I1 means its value wins, and both agree on `l1`,
so the overlap is benign — noted here so a future reader knows which one is
authoritative if they ever diverge.

### 2.3 Two invariants

**I1 — never override an existing `type:`.** Derivation fills a *missing*
value only. This preserves root `index.md` at `l2-map` and
`projects/hallm/knowledge/lessons/lessons.md` at `project-knowledge` rather
than silently renaming pages out from under their author.

**I2 — an unmapped path gets no stamp and raises no error.** It stays untyped
and the lint's `missing-frontmatter-type` rule still fires on it as a genuine
judgment call. Without I2 the rule becomes dead code and a novel path shape
lands mistyped forever, invisibly.

### 2.4 The derivation table

Ordered; first match wins; applied only when content carries no `type:`.

| # | Path shape | `type:` |
|---|---|---|
| 1 | `projects/<slug>/{map,overview,schema,open-work,instructions}.md` — **direct children only**, i.e. exactly 3 path segments | `l2-map`, `overview`, `project-schema`, `open-work`, `project-instructions` |
| 2 | folder-note hub `<dir>/<dirname>.md` | `hub` |
| 3 | `**/lessons/*.md` (non-hub) | `lesson` |
| 4 | `**/l1/*.md`, including `archive/l1/` | `l1` |
| 5 | `projects/*/knowledge/**` | `project-knowledge` |
| 6 | root `identity.md` / `log.md` / `LICENSES.md` / `index.md` | `identity` / `log-entry` / `licenses` / `l2-map` |
| — | anything else | none — I2 applies |

**Rule 3 before rule 5 is the one contested cell.** A project-scoped lesson at
`projects/<slug>/knowledge/lessons/foo.md` matches both. Decision (Hazar,
2026-08-21): **kind wins** — a lesson is a lesson wherever it lives, scope is
already carried by the path and by project frontmatter, and it matches the
`type: lesson` hand-stamped during the 0.8.0 rescue. One query finds every
lesson, global or project-scoped. Rule 2 precedes rule 3 so a `lessons.md`
folder-note is a `hub`, not a `lesson`.

Verified mechanically against all 29 untyped pages: every one resolves,
producing `lesson` ×17, `project-knowledge` ×6, `l1` ×3, `hub` ×2,
`project-schema` ×1 (sum 29, nothing unresolved). No page falls through to I2
today — I2 exists for path shapes not yet invented.

The depth qualifier on rule 1 is load-bearing: a first pass at this table read
it as 2 segments and silently dropped `projects/hallm/schema.md` through to
I2. The implementation must pin that case in a test.

### 2.5 Backfill

`migrations/frontmatter-type-1/`, registered under `global_migrations` in
`schemas.json`. It calls `derive_type()` — never its own copy of the table.

It follows the `trust-backfill-1` / `folder-note-hubs-1` mold: **direct writes
plus its own journal, revertible via the pre-update whole-wiki snapshot** —
not the write queue. Stated explicitly because it reads like a doctrine
violation: the "never edit a governed page directly" rule binds *sessions*,
and tree-wide migrations have their own revert path. Inventing a
queue-routed second convention here would fragment migration revert.

Scope: the 29 untyped pages. I1 means it touches nothing already typed.

### 2.6 Registry reconciliation

`schemas.json` `page_types` gains `l1`, `lesson`, `hub`, `licenses`,
`log-entry`, each `{current: 1, migrations: []}` — 8 registered types to 13.

Once the door derives types mechanically, a derivation table and a registry
that disagree is a latent trap: `migration_chain()` is keyed by page type, so
a type the registry has never heard of can never be migrated later.

## 3. Part B — finding retraction

### 3.1 The problem it fixes

A lint finding is **verifiable**. Unlike a judgment call ("should this be
promoted?"), you can mechanically re-check whether `missing-frontmatter-type`
still holds on a page. Nothing currently does, so a finding resolved by any
other means stays pending until the 30-day expiry.

Without this, Part A clears 26 findings once and the class immediately starts
refilling. With it, the class is closed permanently.

### 3.2 Retraction must not be a decline

**`decide(sid, "declined")` is the wrong mechanism and would introduce a
worse bug than the one it fixes.** `decide()` appends to the decision ledger,
and `record()` refuses any fingerprint present in `ledger_fingerprints()`.
Declining a retracted finding would **permanently deafen the lint for that
page + rule**: strip `type:` off that page again later and no finding ever
fires again.

`expire_stale_pending()` is the correct model — it sets a status *without*
ledgering, precisely so the fingerprint stays free to re-fire.

### 3.3 `retract()`

New in `lib/suggestions/__init__.py`:

```python
def retract(sid: str, reason: str) -> dict
```

- sets `status = "resolved"`, plus `resolved_at` and `resolved_reason`
- appends **no ledger line** — the fingerprint may fire again if the defect
  returns
- `pending_suggestions()` filters it out for free (not `_PENDING`)
- `decide()` remains untouched and still rejects non-pending entries, so a
  resolved entry is immutable by the same rule as an expired one

`prune_decided()` extends to sweep `resolved` entry files on the existing
retention clock; otherwise they accumulate on disk forever.

### 3.4 The lint pass

`_retract_resolved_findings()` in `skills/wiki-health/lib/lint.py`: for each
pending suggestion whose fingerprint starts with `_LINT_FINGERPRINT_PREFIX`,
re-run `_lint_page()` against the page as it stands now and retract when that
`(page, rule)` pair no longer appears in the returned judgments. A page that
no longer exists retracts too.

Runs as part of `run_incremental_lint()`, before the sweep files new findings.

## 4. Part C — the `place_durable_item` route (#73)

`_route_unplaced()` builds a payload of `{action, item, session}` with **no
target page**. There is nothing to write *to*, so a handoff is the only
correct shape — this formalizes exactly the workaround run by hand in the
2026-08-19 acceptance session.

Added to `_apply()` alongside `orphan_page`:

```python
if action == "place_durable_item":
    # judgment finding — the live session places the item with the friend;
    # accepting records the review handoff, same convention as orphan_page.
    return {"sid": sid, "applied": False,
            "detail": {"item": payload.get("item"),
                       "session": payload.get("session")}}
```

`accept()` needs no change: an intentional non-write outcome that returns
(rather than raising) already counts as decided, so `decision_recorded`
becomes `true` and the suggestion stops re-offering forever.

## 5. Part D — merge under the `verdicts=` transport (#75)

### 5.1 Split validation from the call

`skills/wrap/lib/merge.py` grows:

```python
def validate_merged(current_text: str, merged_text: str) -> str
```

carrying the three checks that exist today — non-empty string, frontmatter
block byte-identical to the input's, and not byte-identical to the current
page. `merge_update()` keeps its signature and calls `validate_merged()`
after `llm_call`. **Callers holding a live callable see zero behavior change.**

### 5.2 `merges=`

`wrap_session()` gains `merges: list[str | None] | None = None` — index-keyed
1:1 with `durable_items`, length-validated exactly as `verdicts` is, with the
same `ValueError` on mismatch. `None` at an index means "no merge produced".

The `action == "update"` branch becomes a three-way:

| condition | outcome |
|---|---|
| `merges[i]` is not `None` | `validate_merged()` → write door on pass |
| else `llm_call` is not `None` | existing `merge_update()` path, unchanged |
| else | `_route_unplaced(fingerprint=f"wrap-unmerged:{session}:{i}")` |

`validate_merged()` failure and an `OSError` reading the target both route to
`_route_unplaced()` as well. **This is the actual die-loudly fix**: those
three cases currently land in `gated_out`, which is the same
die-silently class Part A of the 0.8.0 spec fixed for scope-`None` placement.
A distinct `wrap-unmerged:` fingerprint prefix keeps "couldn't place" and
"couldn't merge" separable in the store.

The existing `_target_trust(target) == "user"` → suggestion branch is
unaffected and still runs after a successful merge, from either source.

### 5.3 SKILL.md — phase 2

`skills/wrap/SKILL.md` documents the second dispatch:

1. Phase 1 classify → `verdicts[]` (unchanged)
2. Call `wrap.eligible_update_targets(session)` — already public and exported,
   no new plumbing
3. For each verdict with `action: "update"` whose `target_page` is in the
   eligible set, dispatch one batched merge subagent with the item text and
   the target page's current text; it returns the complete merged page
4. Assemble `merges[]` index-aligned with `durable_items`, `None` wherever no
   merge came back
5. `wrap_session(..., verdicts=[...], merges=[...])`

This keeps 0.8.0's auto-update capability alive under the transport the SKILL
actually drives, instead of retiring `action: "update"` in practice.

## 6. Part E — scrub false positive (#72)

`lib/memory/scrub.py:117` and its token/api_key twin at `:130`. The type-token negative
lookahead only accepts `[`, `|`, whitespace, a quote, or end-of-string after a
guard word:

```python
r"(?:[\[\|]|[\s'\"]|$)"
```

So in `secret: str,` the character after `str` is `,`, the lookahead does not
fire, and `[^\s'\"(]{4,}` matches `str,` — exactly 4 characters — scanning a
bare annotated parameter as a password pair.

Fix — extend the follow-set in **both** branches:

```python
r"(?:[\[\|,)\]]|[\s'\"]|$)"
```

covering `str,`, `str)` and `str]`. The `#29` exemption's intent is unchanged;
only its terminator set was incomplete.

**Verified before approval** against a 20-case matrix (current vs. proposed,
both branches): **7 false positives cleared, 0 regressions**, and all six true
positives — quoted values, a digits-only PIN, `none.of.your.business`, a real
`ghp_` token — still hit. Those 20 cases are the test table for task 6.

## 7. Sequencing

Worktree-isolated on `worktree-knowledge-flow-seams-train`. Test-first per
task (baseline at branch point: 3466 passed, 1 skipped).

1. `page_types.derive_type()` + `propose()` wiring + `schemas.json` registration
2. `migrations/frontmatter-type-1/`
3. `retract()` + `_retract_resolved_findings()`
4. `place_durable_item` route (#73)
5. `validate_merged()` + `merges=` + SKILL.md phase 2 (#75)
6. scrub follow-set (#72)

1 precedes 2 because the migration consumes the same table. 3 follows 2 so the
retraction pass has real findings to retract. 4, 5 and 6 are independent of
each other and of 1–3, and may land in any order.

## 8. Testing

Per task, test-first:

- **derive_type** — one case per table row; I1 (existing `type:` wins) and I2
  (unmapped path returns `None`, no raise); the rule-2-before-3 and
  rule-3-before-5 orderings pinned explicitly; and rule 1's depth qualifier
  pinned by `projects/<slug>/schema.md` → `project-schema` (3 segments) versus
  `projects/<slug>/knowledge/schema.md` → `project-knowledge` (4 segments).
- **propose() wiring** — the regression this design exists to prevent: propose
  identical content twice against a page the door typed, assert the second is
  `noop-duplicate`. Assert `stamp_frontmatter()` output still contains only
  `ren_*` keys.
- **migration** — fixture wiki with all six path shapes plus one already-typed
  page (untouched) and one unmapped page (untouched); verify + rollback.
- **retract()** — status transitions to `resolved`; **no ledger line appended**;
  the same fingerprint can be `record()`ed again afterwards (the §3.2 bug,
  pinned as a test); `prune_decided()` sweeps resolved files.
- **retraction pass** — a fixed page's finding retracts, an unfixed one stays
  pending, a deleted page's finding retracts.
- **#73** — `accept()` on a `place_durable_item` returns `applied: False` with
  `decision_recorded: True`; the suggestion leaves `pending_suggestions()`.
- **#75** — all three branches of the update three-way; `validate_merged()`
  rejection routes to suggestions rather than `gated_out`; `merges=` length
  mismatch raises; a live-`llm_call` caller's behavior is byte-identical to
  today.
- **#72** — `secret: str,` / `token: int)` / `password: str]` are clean;
  `secret: "hunter2xyz"` and `password: 1234` still hit.

## 9. Acceptance (run live, after the train lands)

- 29 untyped pages → 0
- a fresh distiller or pin write carries `type:` on its **first** write
- pending suggestions 49 → ~23, with the 26 lint findings in status
  `resolved` (not `declined`) and their fingerprints absent from the ledger
- one update-verdict auto-applies under the `verdicts=` path
- `accept()` on a `place_durable_item` returns `decision_recorded: true`
- `secret: str,` passes the pre-push scan
- full suite green; `/ren:doctor` no worse than its pre-train baseline

### Acceptance run — 2026-08-21 (measured)

Run against the live wiki after a successful `/ren:backup` (git push to
`renos-wiki`, the revert substrate). Every prediction above held.

| Criterion | Predicted | Measured |
|---|---|---|
| Untyped pages | 29 → 0 | **29 → 0** (156 pages, all typed) |
| Derivation split | lesson ×17, project-knowledge ×6, l1 ×3, hub ×2, project-schema ×1 | **exact match** |
| Findings retracted | 26 | **26** |
| Pending suggestions | 49 → ~23 | **49 → 23** |
| Retracted status | `resolved`, not `declined` | **26 `resolved`** |
| Fingerprints leaked to ledger | 0 | **0** |
| New findings filed by the sweep | 0 | **0** (`queued_suggestions: 0`) |
| Fresh write typed on FIRST write | yes | **yes** — `type: lesson`, 1 journal entry |
| Doctor | no worse than baseline | **17 ok, 4 skip, 4 info, 0 warn, 0 fail** |

Two results worth recording beyond the table:

**The §3.4 rule-set gate was load-bearing, and only the final whole-branch
review caught it.** The retraction pass originally treated "rule absent from
`_lint_page`'s judgments" as "finding resolved". But the lint *driver*
synthesizes `held:<cls>` and `blocked:<cls>` rule families into the same
`wiki-lint:` fingerprint namespace, and the live store also held findings for
rules `_lint_page` no longer emits (3 `map-pointer-missing`, 1
`hub-split-link-lists`). Un-gated, all four would have been retracted with a
reason asserting something never checked — landing this run at 19 pending and
reading as a *better* result than the 23 predicted. Retraction is now gated on
`_RECHECKABLE_RULES`; those four correctly survived, and the 2 `dangling-link`
findings survived because they genuinely still hold.

**The remaining 23 are a legible queue, not a wall**: 17 quarantine-release
decisions, 3 map-pointer-missing, 2 dangling-link, 1 hub-split-link-lists.
Draining them is the next session's work (§10).

**Ordering constraint discovered in review:** the backfill must run *before*
the next distill or wrap. Until a page is typed, a re-propose of unchanged
content no longer normalizes equal (the proposal carries `type:`, the page on
disk does not), costing one self-healing extra write per page and a distiller
`WRITE_CAP` slot. Satisfied here — the migration ran before any producer did.

## 10. Out of scope

- **Hub typing inconsistency.** Three pages disagree today: global
  `lessons/lessons.md` is `hub`, project `.../lessons/lessons.md` is
  `project-knowledge`, and root `index.md` is `l2-map` while the lint's
  `_is_hub_page()` counts it as a hub. I1 preserves all three. Normalizing
  them is a follow-up issue, filed at close-out — not this train's business.
- **Draining the 17 quarantine-release suggestions.** A review activity, not
  code. It becomes legible once retraction clears the 26, and belongs to the
  session *after* this train.
- **A `pin` page type.** `projects/*/knowledge/pins/*.md` derives to
  `project-knowledge` under rule 5. A dedicated type would need a registry
  entry and a consumer that reads it; nothing reads `type:` to make a
  decision today.
- **Making `type:` load-bearing.** This train makes it *correct and
  consistent*. Nothing yet dispatches on it.
- **The 0.8.0 measurement window and the #60 shrink question** (spec
  2026-08-18 §4.2) — unaffected by this train, still open.
