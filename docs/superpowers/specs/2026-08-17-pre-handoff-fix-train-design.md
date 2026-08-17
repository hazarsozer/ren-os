# Pre-handoff fix-train — design

**Date:** 2026-08-17
**Issues:** #58 (remainder), #61, #32 → release 0.7.5; #40, #64, #37, #36 → release 0.7.6
**Motivation:** a friend is about to install the plugin fresh. Two trains,
safety first: 0.7.5 clears the data-loss and crash paths a new install can
hit; 0.7.6 clears first-impression polish. 0.7.5 ships before any 0.7.6
work starts, so the handoff is unblocked even if the second train slips.

## Decisions (Hazar, 2026-08-17)

- Clustering: two trains — 0.7.5 "safe hands" (#58 remainder, #61, #32),
  0.7.6 "first impressions" (#40, #64, #37, #36).
- #61: auto-uniquify the slug on collision. No holds — the auto tier stays
  autonomous; no silent loss — nothing is overwritten.
- #40: redirect the uv environment out of the versioned cache dir via
  `UV_PROJECT_ENVIRONMENT`; update GCs stale envs; doctor warns on `.venv`
  inside a cache dir.
- #58: refuse bootstrap on a populated wiki with no `--force` escape hatch
  (nothing legitimate needs one — `stamp_skeleton` already never
  overwrites); test isolation is the existing `REN_WIKI_ROOT` override,
  documented as the sanctioned test-run recipe.
- #64: wire both re-render triggers (update + revert); spec §3(b) of the
  2026-08-14 standing-instructions design stays as written.

---

## Release 1 — 0.7.5 "safe hands"

### #58 remainder — install bootstrap safety

The core clobber vector closed in 0.7.1 (`apply_write` refuses `op=ADD`
over an existing page; `stamp_skeleton` never overwrites). Three pieces
remain, all flow-level:

1. **Populated-wiki refusal.** Before stamping, the bootstrap stage
   detects non-skeleton content — real `log.md` entries beyond the
   bootstrap stamp, a non-placeholder `identity.md` — and refuses with an
   explanatory message that names what it found and points at
   `REN_WIKI_ROOT` for test drives. Detection lives in a helper next to
   `stamp_skeleton` (`lib/skeleton.py`) so bootstrap-project can reuse it
   later if needed.
2. **Idempotency.** A re-run on a half-bootstrapped wiki stamps only
   missing pages and reports "stamped N missing page(s), M already
   present" instead of erroring or re-ADDing.
3. **Test isolation.** Install's SKILL.md gains a test-run section
   documenting the `REN_WIKI_ROOT` scratch-dir recipe as the ONLY
   sanctioned way to exercise install against anything but the real wiki.

**Files:** `skills/install/lib/__init__.py`, `lib/skeleton.py`,
`skills/install/SKILL.md`.
**Tests:** re-run the 2026-08-12 incident repro (four-wave skeleton
re-ADD against a populated wiki) and assert `identity.md` and `log.md`
survive byte-identical; refusal message content; idempotent re-run
counts; `REN_WIKI_ROOT` recipe actually isolates.

### #61 — auto-uniquify on durable slug collision

`apply_auto` (`lib/memory/queue.py`) currently passes
`allow_existing_add=True` and never checks the target, so two different
durable items whose first ~8 significant words slugify identically
silently overwrite each other (revertible via `ren_supersedes`, but
nothing surfaces it).

New contract for `apply_auto` with `op=ADD` and an existing target page:

- **Same session** as the page's provenance → upsert, today's behavior.
  Wrap's L1 re-ADD across repeated same-session calls keeps working
  (covered by `tests/skills/wrap/test_wrap_flow.py`).
- **Identical normalized content** (the `_check_add_race` /
  `_normalize_body` comparison) → transition to `noop-duplicate`.
- **Different session AND different content** → a genuine collision:
  write to the first free `<slug>-N.md` (N from 2), rewriting the
  proposal's page path before apply; the journal entry records the
  collision (original target + chosen path).

The "deliberately NOT wired" NOTE at `lib/memory/queue.py:573` is
rewritten to describe this contract. The human `apply()` path keeps
`_check_add_race` unchanged — its hold semantics are correct for the
approve/apply time gap.

**Files:** `lib/memory/queue.py` (+ journal record shape if a field is
needed).
**Tests:** collision → both pages exist with correct content + journal
collision record; same-session upsert unchanged; identical-content
noop-duplicate; suffix skips occupied `-2`.

### #32 — `changelog_digest` str-path crash

`skills/update/lib/__init__.py:31` calls `.read_text()` on the argument;
the `except (OSError, ValueError)` does not catch the `AttributeError` a
str raises. Fix: coerce `Path(changelog_path)` at the top; docstring
notes str-or-Path. The digest is documented as "a courtesy, never a
gate" — it must not be able to crash the closing flow.

**Files:** `skills/update/lib/__init__.py`.
**Tests:** str path returns the same digest as Path; garbage str returns
`""`.

---

## Release 2 — 0.7.6 "first impressions"

### #40 — uv environment out of the cache dir

The versioned plugin cache dir is treated as an immutable installed
artifact, but `uv run` from it creates a `.venv` inside it.

1. Documented invocations (install/update/wiki-health SKILL.md,
   ren-wiki-lint agent) set
   `UV_PROJECT_ENVIRONMENT=~/.renos/.envs/<version>` — the env lands
   under the framework root, one per version, cache dir stays pristine.
2. `/ren:update` GCs `~/.renos/.envs/` entries whose version no longer
   has a cache dir.
3. Doctor gains a warn-level check: a `.venv` inside any versioned cache
   dir → warn + suggest removal (flags the existing stale ones).

**Files:** the four documented-invocation surfaces,
`skills/update/lib/`, `skills/doctor/lib/__init__.py`.
**Tests:** doctor check fires on a planted `.venv`; GC removes only
orphaned envs.

### #64 — CLAUDE.md re-render triggers (update + revert)

Spec §3(b) of `2026-08-14-project-standing-instructions-design.md` names
"/ren:update's existing re-render step" as a trigger, but update never
calls `write_project_claude_md`; `revert` of an applied instructions
write doesn't re-render either.

1. Update's re-render step calls `write_project_claude_md` for every
   registered project (same fail-closed-on-quarantine semantics as the
   apply-path render).
2. `revert` of a write targeting `projects/<slug>/instructions.md`
   re-renders that project's block.

**Files:** update flow, `lib/memory/` revert path,
`lib/adapter/claude_md.py` (owns `write_project_claude_md`).
**Tests:** update re-render refreshes a stale block; revert restores the
pre-apply block.

### #37 — unlinted-nudge count agrees with the watermark

Observed: nudge said 65, watermark seeded 66 moments later. Diagnose the
baseline mismatch between `_unlinted_count`
(`hooks/wake-up/wakeup/__init__.py:870`) and `run_incremental_lint`'s
seed, then make both read the same counter.
**Tests:** regression — nudge count equals the watermark delta on the
same journal fixture.

### #36 — doctor `agent_shadowing` wording

`skills/doctor/lib/__init__.py:804,813`: skip/warn messages say "user"
even for project `.claude/agents` collisions. Messages name the actual
directory. **Tests:** message content for both collision origins.

---

## Process

Each release follows the standard train: this spec → implementation plan
(writing-plans) → ren-planner briefs → one fresh subagent per task,
test-first → ren-reviewer final whole-branch review, clear every
CRITICAL/HIGH → merge → `bump_version.py` (the #65 lesson) → release.
0.7.5 merges and releases before any 0.7.6 task starts.

Out of scope: #62/#60/#55/#54 (wrap/wiki-graph design work), #49/#50
(calibration + noop-duplicate follow-ups), #38, #33/#31/#34/#29
(diagnostic noise on the dev setup), #11 (adoption-readiness review —
worth a read before handoff, but it is a review, not a fix).
