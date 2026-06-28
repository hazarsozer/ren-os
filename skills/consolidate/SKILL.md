---
name: consolidate
description: |
  Use when the friend wants a governed, diff-gated wiki sweep — either PROMOTE accumulated
  hot-tier instincts into the curated wiki (default, C3b) or REPAIR dead links across the
  wiki (--fix-links, C3c). Triggers on /ren:consolidate. Proposes each change, shows it as a
  diff for approval, and applies atomically. Per ADR-009/031: manual, never a Stop hook; the
  tool proposes, the human approves every diff. Companion to /ren:wrap (session consolidate)
  and /ren:note --instinct (capture).
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
      # Default (promotion) writes patterns/decisions/projects + the instincts.md marking.
      # --fix-links may rewrite a dead link in ANY page, so the sweep's write scope is the
      # whole wiki; log.md gets one summary line in either mode.
      - "~/.startup-framework/wiki/**"
    execute: []
  completion_conditions:
    - "Every applied change was shown to the user and approved first"
    - "Promoted instincts carry an in-place `_(promoted …)_` marker (idempotency)"
    - "On any apply failure, the batch's own changed files were rolled back (scoped — unrelated uncommitted wiki work is left untouched); no half-applied promotion"
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

**Two modes, one diff-gate spine:**
- **promote (default, no flag)** — graduate durable hot-tier instincts into curated pages (C3b).
- **`--fix-links` (C3c)** — repair dead `[[wikilinks]]` and `](file.md)` links across the wiki.

Both propose changes, gate every diff (`Y/N/E/A`), and apply atomically via the same primitive.

## When to use this skill

- Friend invokes `/ren:consolidate` (canonical trigger — promote mode)
- Friend says: "promote my instincts", "consolidate the hot tier", "graduate these lessons", "compound the wiki"
- Friend invokes `/ren:consolidate --fix-links` (dead-link repair mode, C3c)
- Friend says: "fix the dead links", "repair broken wikilinks", "the wiki has broken links"

## When NOT to use this skill

- Mid-session capture of a new instinct → `/ren:note --instinct <kind> <text>`
- End-of-session save → `/ren:wrap` (session → wiki; this skill is hot-tier → curated)
- Look something up → `/ren:recall`
- No unpromoted instincts exist → the skill reports "nothing to consolidate" and exits (no writes)

## Mode: promote instincts (default — no flag)

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
with `git restore`/`git clean` rollback **scoped to the files the batch changed** (a friend's unrelated
uncommitted wiki work is never reverted or deleted). On failure, surface the cause; those files are already rolled back.
On success, append one line to `wiki/log.md` (`consolidated N instincts → M curated pages`) and print:
```
/ren:consolidate complete.
  Promoted: <N> instincts → <M> curated pages
  Hot tier: <K> instincts left unpromoted
```

## Idempotency (promote mode)

A promoted instinct's source line is annotated in place: `… — text  _(promoted <date> → <page>)_`. Re-running
the sweep skips marked entries (`unpromoted` excludes them), so promotions never double-fire, and the marker
traces where each instinct went.

## Mode: `--fix-links` — dead-link repair (C3c)

> The first mechanical housekeeping sweep. Detection is a faithful port of doctor's read-only
> `check-wiki-health.sh`; repair is **deterministic + conservative** — it never removes a link or invents a
> target. Same gate + atomic apply as promote mode.

### Step 1. Scan (read-only, wiki-wide)
Glob `wiki/**/*.md` into `pages = {repo_relpath: text}` (keys relative to the git root, e.g.
`wiki/decisions/037.md`; glob order is irrelevant — the lib sorts internally for cross-machine determinism). `lib.find_dead_links(pages)` → dead `[[wikilinks]]` (slug not found) and `](file.md)`
links (don't resolve relative to the source; `http(s)` ignored). Empty → print "No dead links — the wiki is
link-healthy." and stop.

### Step 2. Propose repairs (deterministic — bias conservative)
Build `lib.build_slug_index(pages)` + `lib.build_basename_index(pages)`. For each dead link,
`lib.propose_link_repair(dead, slug_index, basename_index)`:
- dead wikilink → fuzzy-match the slug pool (cutoff 0.8); confident match → re-point, else **report** (no diff).
- dead mdlink → relocate on an unambiguous basename match (corrected relative path), else **report**.
Links with no confident candidate are collected for the manual-attention report — never guessed or removed.

### Step 3. Gate — show every fix
For each `LinkRepair` show `source_relpath: <old_literal> → <new_literal>` with `Y / N / E[dit] / A[ll-yes]`.
**Always prompt.** Dropped repairs leave the link as-is.

### Step 4. Compose per-file + apply atomically
Group approved repairs by page; `lib.build_link_repair_diffs(page_relpath, page_text, repairs)` → ONE
`PromotionDiff(kind="link-fix")` per page (multiple fixes coalesce — N same-file diffs would fail the 2nd
`git apply`). Apply via `lib.apply.apply_diff_entries(...)` — all-or-nothing with rollback. On success append
one `log.md` line (`fixed N dead links across M pages`) and print:
```
/ren:consolidate --fix-links complete.
  Fixed:  <N> dead links across <M> pages
  Manual: <K> links with no confident fix (listed above)
```

### Idempotency (natural)
A repaired link resolves, so the next scan no longer reports it — no marker needed (unlike promote mode).

## What `/ren:consolidate` explicitly DOES NOT do (C3b + C3c scope)

- Run automatically / autonomously. Manual + interactive only (ADR-009/031).
- Mechanical housekeeping beyond link repair — dedup, date-normalize, contradiction-prune. Later sweep slices.
- Create a missing target page or remove a link. `--fix-links` only re-points to an existing page; missing
  targets go to the manual-attention report.
- The project↔global instinct axis (promoting a project instinct into the global pool). Deferred.
- Touch `/ren:wrap`'s domain. Wrap owns session→wiki; this owns hot-tier→curated + wiki link health.
- Write any change the user didn't approve. Every diff is gated.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| No unpromoted instincts | Stop cleanly, no writes | "Nothing to consolidate — the hot tier is empty or all promoted." |
| User rejects a promotion | Drop both diffs of the pair | (that instinct stays in the hot tier) |
| A diff fails to apply | Atomic rollback scoped to the batch's changed files; surface cause | "Apply failed; the batch's changes were rolled back. Cause: <err>" |
| instincts.md missing | Treat as empty | "Nothing to consolidate." |
| No dead links (`--fix-links`) | Stop cleanly, no writes | "No dead links — the wiki is link-healthy." |
| A dead link has no confident fix | Skip it; collect for the report | "K link(s) need manual attention: …" |

## References

- ADR-037 (Compounding Memory Model) — the three-tier model; this skill is tier 3 (the governed sweep)
- ADR-009 (Consolidate via /wrap) — manual posture, never a Stop hook
- ADR-031 (Solo-First) — LLM proposes / human approves; no speculative autonomy
- `docs/superpowers/specs/2026-06-28-c3b-consolidate-design.md` — C3b design spec
- `docs/superpowers/specs/2026-06-28-c3c-link-repair-design.md` — C3c design spec (dead-link repair mode)
- `skills/wrap/references/wiki-page-mapping.md` — signal→page mapping reused for promotion targets
- `skills/wrap/lib/apply.py` — the atomic-apply pattern this skill's `lib/apply.py` mirrors
- `skills/doctor/scripts/check-wiki-health.sh` — the read-only dead-link DETECTOR that `lib/links.py` ports
