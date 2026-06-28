---
name: consolidate
description: |
  Use when the friend wants to PROMOTE accumulated hot-tier instincts into the
  curated wiki — the governed compounding sweep (C3b). Triggers on /ren:consolidate.
  Reads instincts.md, proposes which durable instincts graduate into curated pages
  (patterns/decisions/lessons), shows every change as a diff for approval, and applies
  atomically. Per ADR-009/031: manual, never a Stop hook; LLM proposes, human approves
  every diff. Companion to /ren:wrap (session consolidate) and /ren:note --instinct (capture).
version: 0.1.0
license: MIT

framework_version: "0.1.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "Zero-or-more promotion proposals, each shown as a diff PAIR (curated-page edit + source marking) for approval"
    - "Approved diffs applied atomically (all-or-nothing with rollback); a summary of N instincts promoted to M pages"
    - "On no unpromoted instincts: an explicit 'nothing to consolidate' message, no writes"
  budgets:
    turns: 12
    files_written: 20
    duration_seconds: 120
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
    write:
      - "~/.startup-framework/wiki/patterns/**"
      - "~/.startup-framework/wiki/decisions/**"
      - "~/.startup-framework/wiki/projects/**"
      - "~/.startup-framework/wiki/instincts.md"
      - "~/.startup-framework/wiki/log.md"
    execute: []
  completion_conditions:
    - "Every applied change was shown to the user and approved first"
    - "Promoted instincts carry an in-place `_(promoted …)_` marker (idempotency)"
    - "On any apply failure, the wiki was fully rolled back (no half-applied promotion)"
  output_paths:
    - "~/.startup-framework/wiki/patterns/"
    - "~/.startup-framework/wiki/decisions/"
    - "~/.startup-framework/wiki/instincts.md"

tags: [companion, compounding, promotion, wiki, lifecycle, experimental]
related_skills: [sf-wrap, sf-note, sf-recall]
references_required: []
references_on_demand: []
---

# sf-consolidate

> **⚠ EXPERIMENTAL (bike-method, ADR-031/036).** The promotion *proposal* is LLM judgment; the *gate* is
> human. Interactive-only — there is NO autonomous mode. Manual slash command, never a Stop hook (ADR-009).

Tier 3 of the compounding memory model (ADR-037). C3a gave instincts a cheap home (the hot tier); this skill
makes them **compound upward** — promoting durable instincts into the curated wiki, one approved diff at a
time. It is the controllable answer to opaque auto-memory: same benefit, but the human approves every change.

## When to use this skill

- Friend invokes `/ren:consolidate` (canonical trigger)
- Friend says: "promote my instincts", "consolidate the hot tier", "graduate these lessons", "compound the wiki"

## When NOT to use this skill

- Mid-session capture of a new instinct → `/ren:note --instinct <kind> <text>`
- End-of-session save → `/ren:wrap` (session → wiki; this skill is hot-tier → curated)
- Look something up → `/ren:recall`
- No unpromoted instincts exist → the skill reports "nothing to consolidate" and exits (no writes)

## The pipeline

### Step 1. Read the hot tier (read-only)
Load the project `wiki/projects/<active>/instincts.md` (resolve the active project as `/ren:wrap`/`/ren:recall`
do) and the master `wiki/instincts.md`. Parse with `lib.parse_instincts`; filter with `lib.unpromoted`. If
the candidate set is empty → print "nothing to consolidate" and stop. Load curated pages (`patterns/`,
`decisions/`, a curated lessons note) for context — lazily, only what you may write into.

### Step 2. Propose promotions (LLM judgment — bias conservative)
For each unpromoted instinct, decide whether it is durable / reusable / canonical-worthy enough to graduate,
and if so, to WHICH curated page-type (reuse `skills/wrap/references/wiki-page-mapping.md`):
- a reusable technique → a `patterns/` page (append, or create a new page)
- a real architectural/scope decision → a `decisions/` entry
- a non-obvious gotcha → a curated lessons note
**Most instincts do not promote.** Most sweeps promote a few. When in doubt, leave it in the hot tier.

### Step 3. Build the diff plan
For each proposed promotion call `lib.build_promotion_diffs(entry, target_relpath=…, target_current=…,
curated_addition=<your proposed curated wording>, instincts_relpath=…, instincts_current=…, promoted_on=<today>)`
→ the diff PAIR (the curated-page edit + the in-place source marking).

### Step 4. Gate — show every diff for approval
For each diff show: target path, the unified diff, and `Y / N / E[dit] / A[ll-yes]`. **Always prompt.** No
autonomous mode in V1. Drop any diff the user rejects (and its paired diff — never mark-without-promoting).

### Step 5. Apply atomically + close out
Apply the approved diffs via `lib.apply.apply_diff_entries(entries, wiki_root=…, cwd=…)` — all-or-nothing
with `git restore`/`git clean` rollback. On failure, surface the cause; the wiki is already rolled back.
On success, append one line to `wiki/log.md` (`consolidated N instincts → M curated pages`) and print:
```
/ren:consolidate complete.
  Promoted: <N> instincts → <M> curated pages
  Hot tier: <K> instincts left unpromoted
```

## Idempotency

A promoted instinct's source line is annotated in place: `… — text  _(promoted <date> → <page>)_`. Re-running
the sweep skips marked entries (`unpromoted` excludes them), so promotions never double-fire, and the marker
traces where each instinct went.

## What `/ren:consolidate` explicitly DOES NOT do (C3b scope)

- Run automatically / autonomously. Manual + interactive only (ADR-009/031).
- Mechanical housekeeping — dedup, dead-link repair, date-normalize, contradiction-prune. A later sweep slice.
- The project↔global instinct axis (promoting a project instinct into the global pool). Deferred.
- Touch `/ren:wrap`'s domain. Wrap owns session→wiki; this owns hot-tier→curated.
- Write any change the user didn't approve. Every diff is gated.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| No unpromoted instincts | Stop cleanly, no writes | "Nothing to consolidate — the hot tier is empty or all promoted." |
| User rejects a promotion | Drop both diffs of the pair | (that instinct stays in the hot tier) |
| A diff fails to apply | Full atomic rollback; surface cause | "Apply failed; wiki rolled back. Cause: <err>" |
| instincts.md missing | Treat as empty | "Nothing to consolidate." |

## References

- ADR-037 (Compounding Memory Model) — the three-tier model; this skill is tier 3 (the governed sweep)
- ADR-009 (Consolidate via /wrap) — manual posture, never a Stop hook
- ADR-031 (Solo-First) — LLM proposes / human approves; no speculative autonomy
- `docs/superpowers/specs/2026-06-28-c3b-consolidate-design.md` — C3b design spec
- `skills/wrap/references/wiki-page-mapping.md` — signal→page mapping reused for promotion targets
- `skills/wrap/lib/apply.py` — the atomic-apply pattern this skill's `lib/apply.py` mirrors
