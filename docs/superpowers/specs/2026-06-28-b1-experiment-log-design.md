# B1 — `experiment-log` Writer (`/ren:improve-skill` Audit Ledger) — Design Spec

> **Status:** Approved design (2026-06-28). Brainstormed via `superpowers:brainstorming`; scope (B1 solo,
> defer C2) + the design knots (project-scoped, SKILL-layer wiring, skip-if-no-project) resolved by the
> maintainer's standing "use your own reasoning" directive. The contract for the TDD build.
>
> **Roadmap slice:** B1 — the `experiment-log` page-type writer, forward-declared in C3a's ADR-027
> "decide-together" batch (ADR-037 §6). **C2** (`routine-spec` v2 `verification_strategy`) is the immediate
> next slice, deferred here (§6) — it is a different subsystem and the framework's *first* schema migration.
> **Amends (note only):** ADR-037 (page-type batch) + ADR-012 (two-layer self-improvement — the experiment
> ledger is the loop's compounding memory). **No new ADR, no schema version bump.**
> **Constrained by:** ADR-009 (wiki writes are explicit), ADR-036 (the loop is EXPERIMENTAL; this ledger is
> its supervised-run audit trail), ADR-027 (the page-type is already `current: 1`).

---

## 1. Purpose

The `/ren:improve-skill` Karpathy loop runs iterations, scores each, keeps or reverts, and squash-merges — but
nothing survives as a **readable, persistent record**. `improve_skill()` returns `history: IterationOutcome[]`
in memory and the git history holds the commits, but there is no durable ledger of *what was tried and what it
scored*. B1 adds that: each run appends its experiments to `wiki/projects/<name>/experiment-log.md`.

This is precisely the audit trail **ADR-036** wants — the loop stays EXPERIMENTAL until ≥3 logged supervised
clean runs earn autonomy; the experiment-log is where those runs become legible evidence. It is also the
self-improvement layer's slice of the compounding-memory theme (ADR-012): the loop's outcomes compound.

The `experiment-log` page-type was **forward-declared in C3a** (`schemas.json`, `current: 1`, shape
`{change, score_before, score_after, disposition: kept|reverted, iteration, ts}`) with **no writer**. B1 ships
the writer. **No schema version bump** — instances are written at the already-declared v1.

## 2. Locked decisions (maintainer standing directive, 2026-06-28)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **Scope** | **B1 solo.** C2 (`routine-spec` v2) is the next, separate slice. | Different subsystem; C2 is the first real schema migration → its own focused slice. Keeps the decompose discipline. |
| 2 | **Where the writer lives** | New `skills/improve-skill/lib/experiment_log.py` (sf-lifecycle domain, the page-type's owner). | Isolated module; the 224-test orchestrator is **not** modified. |
| 3 | **Wiring point** | **SKILL.md close-out step**, not `improve_skill()`. The prompt layer resolves `wiki_root` + active project and calls the writer with `result.history`. | Matches the note/recall "lib pure, SKILL resolves+calls" boundary; surgical (orchestrator untouched). |
| 4 | **Project scope** | **Project-scoped** (`wiki/projects/<name>/experiment-log.md`), active project resolved like `/ren:note`. **No resolvable project → skip with a notice.** | Schema-faithful to the declared path; the git history is still the record when skipped. Master-level ledger deferred (§6). |
| 5 | **Gating + idempotency** | **No gate; append-only** (like `log.md`/`instincts.md`). | It is an audit record of what the loop *did*, not proposed content needing approval. Re-runs append new sections — naturally idempotent. |

## 3. Architecture — new `skills/improve-skill/lib/experiment_log.py`

| Unit | Path | Status | Responsibility |
|------|------|--------|----------------|
| **types** | `skills/improve-skill/lib/types.py` | EDIT | Add `ExperimentEntry(iteration, change, score_before, score_after, disposition, ts)` (frozen). |
| **build** | `lib/experiment_log.py → build_experiment_entries(history, *, ts)` | NEW | Map `IterationOutcome[]` → `ExperimentEntry[]`: `change=proposed_change.summary`, `disposition="reverted" if status is REVERTED else "kept"`, scores/iteration passthrough, `ts` injected (the run date). |
| **render** | `… → render_run_section(entries, *, skill_name, baseline, final, disposition, ts)` | NEW | One dated markdown section per run (header carries skill_name, baseline→final, branch disposition; one bullet per entry). Pure string. |
| **append** | `… → append_experiment_log(path, section)` | NEW | I/O: append the section; create the file with `type: experiment-log` / `schema_version: 1` / `scope: project` frontmatter + a title when absent. Returns the path written. |
| **contract** | `skills/improve-skill/SKILL.md` | EDIT | A close-out step: resolve `wiki_root` + active project; on a resolvable project, call the writer with `result.history`; else print the skip notice. |

`improve_skill()` (the orchestrator) and its `IterationOutcome`/`ImproveSkillResult` types are **unchanged**.

## 4. The write pipeline (SKILL.md close-out)

1. **Run the loop** (unchanged): `improve_skill(...)` → `ImproveSkillResult` (with `history`).
2. **Resolve target** (prompt layer): `wiki_root` (SF_WIKI_ROOT → CLAUDE_PLUGIN_OPTION_WIKIROOT → framework
   wiki, as note/recall do) + the **active project slug**. No project → print
   "experiment-log skipped (no active project); the run's git history is the record." and stop.
3. **Build + render**: `build_experiment_entries(result.history, ts=<today>)` →
   `render_run_section(entries, skill_name=…, baseline=result.baseline_score, final=result.final_score,
   disposition=result.branch_disposition, ts=…)`.
4. **Append**: `append_experiment_log(wiki_root/"projects"/<slug>/"experiment-log.md", section)` — creates the
   file with frontmatter on first write, appends thereafter. Print a one-line confirmation.

## 5. Entry shape + rendering

`ExperimentEntry` mirrors the forward-declared shape exactly. A rendered run section:

```markdown
## 2026-06-28 — improve(consolidate): 50% → 100% (squash-merged)

- iter 1 — [kept]     0.500 → 0.750 — tighten the gate prompt
- iter 2 — [reverted] 0.750 → 0.625 — add a second worked-example
- iter 3 — [kept]     0.750 → 1.000 — clarify the failure-mode table
```

File header (created once):

```markdown
---
type: experiment-log
schema_version: 1
scope: project
---

# Experiment Log — <project>

Append-only record of `/ren:improve-skill` runs (ADR-012/036). One section per run.
```

## 6. Non-goals (deferred)

- **C2 — `routine-spec` v2 `verification_strategy`.** The immediate next slice: an additive v1→v2 field +
  `/ren:routine-init` elicitation + doctor flag — the framework's first real schema migration. Different
  subsystem (cadence); built separately.
- **Master-level `wiki/experiment-log.md`.** The declared path is project-scoped only; a global ledger
  (mirroring instincts' two-level routing) is a later extension if framework-skill dogfooding needs it.
- **Per-iteration timestamps.** `IterationOutcome` carries no per-iteration time; all of a run's entries share
  the run date. Sufficient for the ledger.
- **Any `improve_skill()` change** — no new orchestrator args, no in-loop write. The write is a close-out step.
- **Gating / dedup** — append-only audit log; not proposed content.

## 7. Governance — registry description + ADR notes (no version bump)

- **`schemas.json`:** update the `experiment-log` *description* (drop "NO writer yet"; record "writer shipped
  B1; the `/ren:improve-skill` close-out fills it"). **`current` stays 1; no migration** — instances are
  written at the declared v1, so `/ren:doctor` sees no drift.
- **ADR-037** gains a 2026-06-28 note: the forward-declared `experiment-log` now has its writer (B1).
- **ADR-012** gains a note: the loop's experiment ledger is its compounding memory.
- CHANGELOG `[Unreleased]`, roadmap (B1 row / C3-batch follow-on), `wiki/log.md`.

## 8. Testing (TDD) + slice

Run `skills/improve-skill/lib/tests/` as its own pytest call.

- **`build_experiment_entries`:** maps each `IterationStatus` correctly (`IMPROVED`/`NEUTRAL` → `kept`,
  `REVERTED` → `reverted`); passes through scores/iteration; `change` = the proposed-change summary; `ts`
  injected on every entry; empty history → empty tuple.
- **`render_run_section`:** dated header with `skill_name` + baseline→final + disposition; one bullet per
  entry; deterministic ordering (iteration order); pure (no I/O).
- **`append_experiment_log`:** first write creates the file with correct `type: experiment-log` frontmatter +
  title; second write appends (frontmatter not duplicated); the file parses back to the expected sections;
  exercised against a `tmp_path`.
- **round-trip:** `build → render → append` from a synthetic `history` yields a file whose entries match the
  inputs.

**Slice:** `feat/b1-experiment-log` off `feat/project-ingest`; `--no-ff` merge. Touches
`skills/improve-skill/{lib/experiment_log.py, lib/types.py, lib/tests/test_experiment_log.py, SKILL.md}`,
`skills/wiki-migration/schemas.json` (description only), ADR-037 + ADR-012 notes, CHANGELOG `[Unreleased]`,
roadmap, `wiki/log.md`. **No schema version bump.**
