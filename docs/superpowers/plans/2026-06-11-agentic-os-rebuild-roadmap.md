# Agentic OS Rebuild — Roadmap

> **Coordinating artifact** for the positioning-pivot rebuild. This is not a task list — it is the
> decomposition + sequencing that the individual `superpowers:writing-plans` implementation plans
> hang off. Each slice below produces working, testable software on its own.
>
> **Input spec (the why/what):** `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
> **Strategic index (the angles):** `wiki/research/new-angles-for-the-os.md`
> **Created:** 2026-06-11

---

## Status log

- **2026-06-11 — F1 DONE + merged.** Discovered (via worktree detection) that Plan B (v1.0
  remediation) was **already executed** — Phases 1–4, 36 reviewed commits — on the
  `fix/v1-remediation` worktree, and never merged. The earlier grounding mis-read un-ticked
  checkboxes on `feat/project-ingest` as "unstarted." Merged `fix/v1-remediation` →
  `feat/project-ingest` (`9555a2d`, conflict-free); **454 unit + 30 integration tests green**,
  `plugin validate --strict` ✔. F1's `/sf:` namespace fix + all correctness/security fixes are now on
  the dev branch. **Remaining F1 = Phase 5 only** (re-publish, human-gated, no version bump).
  **Lesson:** verify plan status across *all* branches/worktrees, never just checkbox state on the
  current branch — apply this to Plan A / C1 before executing it.

## Thesis (recap)

An **open-source second-brain OS for Claude Code**: a governable, compounding **wiki as the single
source of truth**, plus thin opinionated **glue** that makes CC's native muscle (Routines, Agent
Teams, Memory 2.0) *report home*. **Ship the engine — the user brings the brain.** The moat is not
"we have a wiki"; it is **transparent, governable, compounding truth vs. CC's opaque auto-memory
you cannot fully steer.**

The pivot reorients the framework from *building primitives* (which CC has now shipped natively) to
*being the governable knowledge layer + the opinionated glue over those primitives.*

---

## Why a roadmap, not one plan

The spec spans **nine independent subsystems**. The `writing-plans` scope check requires breaking
multi-subsystem specs into separate plans, one per subsystem, each independently shippable. This
roadmap is that decomposition. The actual code lands via the per-slice plans named in the table.

---

## Current baseline (grounded 2026-06-11)

- **12 shipped skills** (`sf-backup, sf-bootstrap-project, sf-doctor, sf-improve-skill, sf-insights,
  sf-install, sf-interview, sf-note, sf-recall, sf-update, sf-wrap` + `wiki-migration`), Python `lib/`
  + per-skill `lib/tests/` / `scripts/tests/` + `eval/eval.json` (ADR-011). Wake-up hook +
  `lib/sf_paths.py` are the shared infra.
- **Namespace defect (confirmed):** `plugin.json` `name` is `startup-framework`, so shipped commands
  are `/startup-framework:sf-wrap`, **not** the documented `/sf:wrap`. Resolved in F1.
- **Plan B — v1.0 remediation** (`docs/superpowers/plans/2026-05-31-v1-remediation.md`): **EXECUTED**
  (Phases 1–4) on `fix/v1-remediation`, **merged 2026-06-11** (`9555a2d`). The checkboxes in the plan
  file were never ticked — which is why the initial grounding wrongly reported "0/108, unstarted."
  Outcome report: `docs/superpowers/2026-05-31-v1-remediation-report.md`.
- **Plan A — project-ingest** (`docs/superpowers/plans/2026-05-31-project-ingest.md`): written,
  **0/64 executed**, **fully pivot-aligned** — its `scan.py` is the host for the code-map (C2) and
  dependency-map (C5). The pivot *enhances* it; nothing is wasted.
- **The rebuild is gated by ~7 ADR decisions**, not just code (see ADR map below). Most just *record*
  decisions the positioning spec already made; a few are genuinely open.

---

## The decomposition (the slices)

| ID | Slice | Pillar(s) | Source / target | Depends on | ADRs (file/amend) | Status |
|----|-------|-----------|-----------------|------------|-------------------|--------|
| **F1** | Foundation + rename | hygiene | Plan B (executed) + `2026-06-11-f1-foundation-rename.md` | — | resolve **013** (namespace=`sf`) | ✅ **DONE — merged 2026-06-11** (`9555a2d`); Phase 5 publish deferred |
| **A1** | Cross-cutting ADR pass | architecture | new (ADR writes) | F1 | new **cadence** ADR; new **git-write-back** ADR; amend **014/027** (page-types) | Not started |
| **C1** | Project Ingest | P1 (moat) | Plan A (ready) | F1 | **032** (already in Plan A) | ⚠️ **Verify true status across worktrees first** (per F1 lesson), then execute |
| **C2** | Code-map context layer | P6 | new — built into C1's `scan.py` | C1 | amend **008** (token budget) | Not started |
| **C3** | Compounding model | P4 | new — repositions `sf-wrap/note/recall` | F1 (+ A1) | amend **009** (scheduled vs manual), **014**, **027** | Not started |
| **C4** | Cadence-as-glue | P3 (headline) | new skills | A1 | new **cadence** ADR; new **write-back** ADR | Not started |
| **C5** | Self-improvement | P5 | extend `sf-improve-skill` | C2 (dep-map) | new **bike-method** ADR | Not started |
| **H1** | Doctor extensions | glue | extend `sf-doctor` | F1 | — | Not started |
| **H2** | Multi-agent glue + lightweight-skill tier + broadened onboarding | P2/glue | extend `sf-interview/install` + `CLAUDE.md` | A1 | amend **011** (lightweight tier) | Not started |

---

## Critical path to "ready soon"

```
F1 ──► A1 ──► C4              (foundation → shared ADRs → the headline cadence capability)
  └──► C1 ──► C2 ──► C5       (populated brain → code-map → self-improvement)
       C3, H1, H2  = depth build-out, scheduled after the path clears
```

- **F1 is the universal unblocker** — every new skill inherits the `sf` namespace; do it before
  authoring any C/H slice or you rename 18 skills later instead of 12.
- **C1 (ingest) can run in parallel with A1** — it carries its own ADR-032 and does not depend on the
  cadence/write-back ADRs.
- **C4 (cadence) is gated by A1** — it cannot ship faithfully until the cadence + git-write-back ADRs
  are filed (currently the framework has **zero** cadence ADRs; ADR-008 is SessionStart-only).
- **C2 → C5**: the code-map *is* the dependency-map; self-improvement's staleness detection reads it.

---

## ADR map (the decisions that gate the rebuild)

The grounding pass surfaced that the pivot touches the decision layer, not just code. Filing order:

| # | Decision | Gating ADR(s) | Where it's filed | Notes |
|---|----------|---------------|------------------|-------|
| 1 | **Namespace resolution** — fix to `/sf:` (set plugin `name: sf`) | ADR-013 | **F1** (Plan B Phase 4) | Already decided; F1 executes it. |
| 2 | **Cloud-routine git write-back boundary** — pull-model only, no listener/daemon | ADR-003 | **A1** (new ADR) | Records the spec's decision; states the no-daemon boundary explicitly. |
| 3 | **Cadence-as-glue** — Routines/`/loop`/`/goal`/Cron are native, framework adds spec + glue only | (none exists) | **A1** (new ADR) | Framework has no cadence ADR; this is the binding decision C4 needs. |
| 4 | **New wiki page-types** — `routine-spec`, hot/`instincts` capture | ADR-014, ADR-027 | **A1** (amend + `schemas.json` registry) | N+3 deprecation commitment; decide once, up front. |
| 5 | **Governed consolidate pass** — scheduled LLM sweep, narrowly scoped (dedup/link-fix), distinct from `/sf:wrap` | ADR-009 | **C3** task 1 (amend) | ADR-009 made consolidation manual on purpose; amendment must scope the autonomy. |
| 6 | **Code-map budget** — load-on-demand, NOT in the 3–5K wake-up injection | ADR-008 | **C2** task 1 (amend) | Plus a refresh-trigger + trust-but-verify discipline (a digest that lies is worse than none). |
| 7 | **Lightweight/alias skill tier** — "a skill can be one prompt you don't want to retype" | ADR-011 | **H2** task 1 (amend) | ADR-011 forbids shipping without `eval/eval.json`; the tier needs an explicit carve-out. |

**Rule:** cross-cutting decisions (1–4) are settled in F1/A1 so later plans are fast and faithful;
subsystem-local decisions (5–7) are task 1 of their own slice.

---

## Naming decisions

- **Command namespace = `sf`** → `/sf:wrap`, `/sf:doctor`, … **(settled, executed in F1 via Plan B
  Task 4.2).** Short, already documented everywhere, satisfies the spec's "namespace stays short."
- **`displayName` = "Startup Framework"** → **kept for now.** F1 repositions only the *description /
  keywords messaging* toward the second-brain-OS framing; it does **not** require a product name.
- **Product / brand rebrand** (a "second-brain OS" product name, repo rename) → **DEFERRED, open.**
  This is a branding call tied to the open-source launch, not a foundation blocker. Trigger a naming
  brainstorm whenever desired; until then the interim identity is "Startup Framework — a governable
  second-brain OS for Claude Code."

---

## Deferred / out of scope (named, not built)

- **Dashboard / visualization layer** — terminal-native by choice; the wiki is a folder Obsidian can
  open as an optional overlay. (Ben AI's whole thesis; deliberately omitted.)
- **Team-sharing, voice intake** — out of scope for solo-first (ADR-031). "Wiki-as-MCP" is the named
  future extension path if multi-user ever returns — and it is explicitly **rejected** for the
  rebuild (violates ADR-003 no-daemon).
- **Daemon / Coordinator mode** — if CC ships these internal feature flags publicly, C4 wires in
  immediately; design should be ready in advance.

---

## How to use this roadmap

1. Execute slices roughly along the critical path; each is a standalone `writing-plans` document.
2. Before authoring a C/H slice plan, confirm its gating ADR (table above) is filed.
3. When a slice ships, tick its **Status** here and append a `wiki/log.md` milestone.
4. F1 and C1 plans already exist and are ready — they need execution, not authoring.
