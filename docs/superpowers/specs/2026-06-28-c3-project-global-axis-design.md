# C3 — project↔global instinct axis (`/ren:consolidate --to-global`)

**Date:** 2026-06-28
**Slice:** C3 (Compounding model, Pillar 4) — the project→global promotion axis
**Status:** design → build
**ADR:** amends ADR-037 (compounding memory model)
**Reuses:** C3b consolidate spine (`parse_instincts`, `unpromoted`, `apply_diff_entries`, marker idempotency)

## Context

ADR-037 §1 names the tier-3 governed sweep as one that "dedups, merges, **promotes project→global**, fixes
dates." C3b shipped hot→curated promotion; C3c shipped dead-link housekeeping. Both amendments explicitly list
**"the project↔global instinct axis"** as the remaining deferred piece. This slice ships it — the last C3
buildable axis (dedup / contradiction-prune stay deferred: high-risk LLM-semantic, ADR-031 "Auto-Dream").

Instincts are hierarchical (ADR-037 §2/§4): project-default (`wiki/projects/<slug>/instincts.md`), global opt-in
(`wiki/instincts.md`). Capture routes correctly, but a lesson first learned inside one project that proves
**cross-project-general** has no governed path *up* to the global pool. That is this slice.

## Decision

A new **`--to-global`** mode on `/ren:consolidate` (a mode, like `--fix-links` — not a new skill).

1. **Scope = the active project's instincts → the global pool.** Read `wiki/projects/<active>/instincts.md`
   (resolved via `lib.sf_paths`, same as the default promote mode). The LLM proposes which **unpromoted**
   project instincts are general enough to graduate to global (cross-project value); shows every promotion as a
   diff for approval. Manual, interactive-only, never a Stop hook (ADR-009); LLM-proposes / human-approves
   every diff (ADR-031).
2. **Promotion shape.** Each graduated instinct is **re-emitted into `wiki/instincts.md`** preserving its
   original `kind` + `date` + `text` (provenance — the bullet records when the lesson was learned, not when it
   was globalized), and its **source line is marked in place** `_(promoted <date> → wiki/instincts.md)_` so the
   sweep is idempotent (reuses C3b's `_MARKER` + `unpromoted()` filter).
3. **Two-diff coalesced plan (the C3c lesson).** K promotions → exactly **2 diffs**, applied atomically:
   - one **global page-edit**: append all K bullets to `wiki/instincts.md`; **create it** (with replicated
     `type: instincts / scope: global` frontmatter) if absent — the global pool is lazily created on first
     `--global` capture and may not exist yet.
   - one **project marking**: mark all K source lines in `wiki/projects/<active>/instincts.md` in a single diff.
   Building K separate same-file diffs would fail the 2nd `git apply` (the C3c finding); coalesce instead.
4. **New pure fn** `build_globalize_diffs(...)` in `consolidate/lib` (alongside `build_promotion_diffs`). Reuses
   `_mark_line`, `unified_diff`, `_create_file_diff`. The global-instincts header is **replicated** (~7 lines)
   from `note._instinct_template(scope=global)` — skill libs can't cross-import (the documented `lib`
   package-name collision); accepted duplication, per the `apply.py`-copies-`wrap` precedent.
5. **Apply** via the shared `apply_diff_entries` (all-or-nothing, scoped rollback — now files-scoped per the C3c
   hardening). Close out: append one `wiki/log.md` line `globalized N instincts → wiki/instincts.md`.

### Idempotency / constraints
- The marker makes re-runs no-ops (marked lines are skipped). **One promotion per instinct line** (curated OR
  global, not both) — the single-marker model from C3b. Acceptable V1 constraint; noted for users.
- **Direction is one-way** (project→global). Global→project demotion is out of scope.

## TDD plan (pure `build_globalize_diffs`, verified against real `git apply`)
- append into an existing global pool → one page-edit diff appends K bullets; applies cleanly.
- **create** the global pool when absent → diff creates `wiki/instincts.md` with valid `scope: global`
  frontmatter + the bullets; the result parses as a conformant instincts page.
- bullets preserve original kind/date/text (provenance), not today's date.
- one coalesced marking diff marks all K source lines; the pair applies atomically through `apply_diff_entries`.
- idempotent re-scan: after apply, the marked source lines are excluded by `unpromoted()` → re-run proposes nothing.

## Wire-up
- `consolidate/SKILL.md`: document the `--to-global` mode (Scan active-project instincts → LLM-select
  cross-project-general → gate-per-promotion → atomic 2-diff apply → log line); add to the failure table +
  completion conditions; permissions already cover `wiki/**`.
- ADR-037 amendment (project↔global axis ships; the C3 deferred list shrinks to dedup/contradiction-prune).
- CHANGELOG `[Unreleased]`, roadmap C3 row, `wiki/log.md` milestone.

## Out of scope (deferred, named)
- dedup / merge / contradiction-prune (high-risk LLM-semantic — ADR-031 Auto-Dream); date-normalize (YAGNI —
  schema enforces ISO). global→project demotion. multi-instinct-into-one global bullet merging.
