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

- **2026-06-11 — RenOS rebrand DONE** (`cbfc04c`). Named the product: **RenOS** (from 仁 *rén*,
  humaneness — the human core the user brings; the OS is the engine over native muscle). Curated
  `/sf:`→`/ren:` sweep (plugin `name: sf→ren`, displayName `RenOS`, repo/marketplace `ren-os`) on the
  shipped surface; frozen history + the `~/.startup-framework/` data root left intact; 454+ tests green,
  `plugin validate --strict` ✔. **ADR-033** supersedes ADR-013. This **completes F1's rename intent** —
  done before the first re-publish, so `/ren:` is the only public command surface users ever see.

- **2026-06-11 — A1 DONE.** Filed **ADR-034: Cadence as Glue over Native Primitives** (net-new — the
  framework had zero cadence ADRs). Binds the cadence architecture: no framework scheduler/daemon
  (ADR-003); the `/loop`/Cron/`/goal`/Cloud-Routines ladder + decision matrix; git pull-model write-back
  for cloud routines (ADR-026); the `ren-routine-init` + failure-footer + `routine-spec`-page-type glue
  surface; plan-aware permission safety. **Unblocks C4** (the cadence build). The instincts/hot page-type
  (Pillar 4) is deferred to C3's task 1.

- **2026-06-12 — C4 DONE.** Cadence-as-glue capability shipped on `feat/c4-cadence-as-glue`:
  `routine-spec` page-type registered in `schemas.json` + conformance harness; `/ren:routine-init`
  scaffolds a lean Cloud-Routine repo (CLAUDE.md + ROUTINE_PROMPT.md with failure footer + single-pass
  + env-var-sourcing conventions baked in, state.md, run-log.md) and writes the conformant
  `routine-spec` wiki page; `/ren:cadence` routes across /loop · Cron · /goal · Cloud Routines via the
  ADR-034 decision matrix; `/ren:recall --routine` reads a routine's state.md/run-log.md for
  cross-run memory; `/ren:doctor` gained a ROUTINES section (network-tier + quota headroom, via
  `check-routines.sh`); the wake-up hook surfaces a "Live automations" block listing `routine-spec`
  pages. No daemon (ADR-003); pull-model write-back (ADR-026).
  Plan: `docs/superpowers/plans/2026-06-11-c4-cadence-as-glue.md`.

- **2026-06-12 — C1 DONE.** Project-ingest (brownfield onboarding) shipped on `feat/c1-project-ingest`:
  `ingest-project` skill — read-only Python scanner (`scripts/scan.py`), extraction-spec + page-mapping
  references, SKILL.md orchestration procedure, eval suite + 2 fixtures. ADR-032 filed. Wire-up:
  README, CHANGELOG, wiki/index.md, wiki/log.md, roadmap all updated. 27 scanner tests green;
  `claude plugin validate --strict` ✔; CI-parity schema gate ✔. No new page-types — reuses ADR-014's
  existing `project-*` taxonomy (already registered in schemas.json). Plan: `docs/superpowers/plans/2026-05-31-project-ingest.md`.

- **2026-06-18 — C5a DONE.** Eval backend wired for `/ren:improve-skill` on `feat/c5a-self-improvement-loop`:
  `run_evals()` scores binary assertions via own LLM-judge; `--eval-runs N` flag (default 1, majority-binarized
  when N>1); exits cleanly via `requires_configured_backend` when backend unavailable. **ADR-036** filed
  (bike-method/earned-autonomy): interactive default; `--autonomous` requires `--max-iterations` +
  `--max-budget-usd`; EXPERIMENTAL until ≥3 logged clean supervised runs. SKILL.md banner reworded;
  `learnings.md` updated (spike findings + supervised-run log placeholder); README/CHANGELOG/wiki wire-up.
  **C5b (loop completion) followed; C5c (dep/call-graph + auto-refresh) followed.** Gate: pytest green; `plugin validate --strict` ✔; schema CI ✔.

- **2026-06-21 — C5c DONE.** Dependency-map + auto-refresh shipped on `feat/c5c-dep-graph`:
  `lib/codemap/deps.py` (stdlib-ast module-import graph; resolves absolute + relative imports; never raises);
  `CodeMap.dependencies` + `depends_on()`/`dependents_of()` queries; sidecar persistence (backward-compatible);
  `core.load_fresh()` on-demand auto-refresh (no daemon, per ADR-008); `/ren:code-map --deps` renders
  the dep graph; `skills/improve-skill/lib/impact.py` (`dependency_footprint` → `ImpactReport`).
  **Symbol-level call-graph deferred** — lean-ctx's graph DB is class-only with no usable edges
  (finding recorded in `lib/codemap/SPIKE_FINDINGS.md`); a true function→function call-graph exceeds
  the adopted tooling. Module-import graph delivers the Pillar-5 dep-map need.
  **C5 chain complete: C5a ✅ C5b ✅ C5c ✅.** Gate: codemap 28 tests, improve-skill 175+1skip;
  `claude plugin validate --strict` ✔. Plan: `docs/superpowers/plans/2026-06-21-c5c-dep-graph.md`.

- **2026-06-17 — C2 DONE.** Code-map context layer shipped on `feat/c2-code-map`: `lib/codemap/`
  (engine-agnostic core: models, adapter_leanctx, digest, staleness, sources) + `/ren:code-map`
  skill. lean-ctx adopted as CLI engine (per-file `read -m signatures`) — the spike confirmed no
  `lean-ctx map --format json` subcommand exists; per-file text parsing via deterministic regex is
  the only viable path. Regenerable cache under `${CLAUDE_PLUGIN_DATA}/code-maps/`; staleness
  detection with per-file content hashes + STALE banner; load-on-demand only (ADR-008 — never in
  wake-up injection). Ingest Stage-6 seeds the code-map when lean-ctx is available (graceful-degrade
  otherwise). `/ren:doctor` gained a CODE-MAP check. ADR-035 filed; ADR-002/008 amended. Wire-up:
  README, CHANGELOG, wiki/index.md, wiki/log.md, roadmap all updated. Gate: pytest suites green,
  schema CI-parity ✔, `claude plugin validate --strict` ✔. Auto/cadence refresh + the dependency-graph
  (call-graph layer) deferred to C5. Plan: `docs/superpowers/plans/2026-06-17-c2-code-map.md`.

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
| **A1** | Cross-cutting ADR pass | architecture | new (ADR writes) | F1 | new **cadence** ADR; new **git-write-back** ADR; amend **014/027** (page-types) | ✅ **DONE 2026-06-11** — **ADR-034** (cadence-as-glue folds in write-back + `routine-spec`); instincts page-type → C3 task 1 |
| **C1** | Project Ingest | P1 (moat) | Plan A (ready) | F1 | **032** (already in Plan A) | ✅ **DONE 2026-06-12** — `ingest-project` skill + ADR-032 + full wire-up; plan `docs/superpowers/plans/2026-05-31-project-ingest.md` |
| **C2** | Code-map context layer | P6 | new — built into C1's `scan.py` | C1 | amend **008** (token budget) | ✅ **DONE 2026-06-17** — `lib/codemap/` + `/ren:code-map` + lean-ctx adopt + ADR-035 + ADR-002/008 amend + doctor check + ingest seeding; plan `docs/superpowers/plans/2026-06-17-c2-code-map.md` |
| **C3** | Compounding model | P4 | new — repositions `sf-wrap/note/recall` | F1 (+ A1) | amend **009** (scheduled vs manual), **014**, **027** | 🟡 **C3a+C3b+C3c DONE 2026-06-28** — instincts hot tier (capture `/ren:note --instinct` + read `/ren:recall --instincts` + `instincts` page-type, project-default/`--global`), the governed promotion sweep (`/ren:consolidate`: LLM-proposes/human-approves diff-gated hot→curated promotion, atomic + idempotent-via-marking), **and the dead-link repair housekeeping sweep (`/ren:consolidate --fix-links`: deterministic conservative link-fix, gate-per-repair/apply-per-file, naturally idempotent)**. **ADR-037** (+amends 009/014/027); `experiment-log` forward-declared, `routine-spec` v2 `verification_strategy` recorded. **Housekeeping remainder (dedup/date-normalize/contradiction-prune) + project↔global axis PENDING.** Specs `2026-06-28-c3a-instincts-design.md`, `2026-06-28-c3b-consolidate-design.md`, `2026-06-28-c3c-link-repair-design.md` |
| **C4** | Cadence-as-glue | P3 (headline) | new skills | A1 | new **cadence** ADR; new **write-back** ADR | ✅ **DONE 2026-06-12** — `routine-spec` page-type + `/ren:routine-init` + `/ren:cadence` + recall/doctor/wake-up extensions; plan `docs/superpowers/plans/2026-06-11-c4-cadence-as-glue.md` |
| **C5a** | Self-improvement — eval backend + earned autonomy | P5 | extend `sf-improve-skill` | C2 | new **ADR-036** (bike-method/earned-autonomy) | ✅ **DONE 2026-06-18** — eval backend wired; `--eval-runs N`; ADR-036 earned-autonomy gate; SKILL banner + learnings + wire-up |
| **C5b** | Self-improvement — loop completion (skill-loading fix + eval-run variance) | P5 | extend `sf-improve-skill` | C5a | — | ✅ **DONE (code) 2026-06-19** — eval sandbox runs skill-runs from the plugin-active worktree root (real skills load); `--eval-runs N` judges each run's own output; unit-tested + reviewed (172 passing). **Live supervised proof DEFERRED** (run 1 of ≥3 toward ADR-036; nested-`claude` sandbox-blocked in-session). Plan: `docs/superpowers/plans/2026-06-19-c5b-loop-completion.md` |
| **C5c** | Self-improvement — dep/call-graph + auto-refresh | P6 | extend `sf-improve-skill` + `lib/codemap/` | C5b, C2 | — | ✅ **DONE 2026-06-21** — dependency-map (module import graph via ast) + `load_fresh` auto-refresh + `/ren:code-map --deps` + improve-skill impact surface; symbol call-graph deferred (lean-ctx graph DB is class-only, no usable edges); plan `docs/superpowers/plans/2026-06-21-c5c-dep-graph.md` |
| **H1** | Doctor extensions | glue | extend `sf-doctor` | F1 | — | ✅ **DONE 2026-06-21** — `/ren:doctor` +CONTEXT & TOKEN ECONOMICS +WIKI HEALTH (7→9 sections); plan `docs/superpowers/plans/2026-06-21-h1-doctor-extensions.md` |
| **H2** | Multi-agent glue + lightweight-skill tier + broadened onboarding | P2/glue | extend `sf-interview/install` + `CLAUDE.md` | A1 | amend **011** (lightweight tier) | 🟡 **PARTS 1+2 DONE 2026-06-27** — `tier: lightweight` carve-out (ADR-011 amendment; not self-improvable + doctor-lint exempt) + `agent-orchestration.md` reference (decomposition tree + model-routing) via `/ren:cadence`. **Part 3 (broadened onboarding) DEFERRED** (onboarding-designer/UX). |

---

## Critical path to "ready soon"

```
F1 ──► A1 ──► C4                  (foundation → shared ADRs → the headline cadence capability)
  └──► C1 ──► C2 ──► C5a ──► C5b ──► C5c ✅  (populated brain → code-map → self-improvement backend → loop completion → dep/call-graph)
       C3, H1 ✅, H2  = depth build-out, scheduled after the path clears
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

## Naming decisions — ✅ RESOLVED 2026-06-11 (RenOS)

- **Product = RenOS** (from 仁 *rén*, humaneness), **namespace = `ren`** (`/ren:wrap`, `/ren:doctor`, …),
  **displayName `RenOS`**, **repo + marketplace = `ren-os`** (install `ren@ren-os`). Brand story in the
  README header + ADR-033.
- **Rebrand executed** (`cbfc04c`): curated `/sf:`→`/ren:` sweep on the shipped surface; frozen history +
  the `~/.startup-framework/` data root left intact; 454+ tests green, `plugin validate --strict` ✔.
  ADR-033 supersedes ADR-013. **Completes F1's rename intent.**
- **Outward follow-ups (maintainer):** rename the GitHub repo `sf-marketplace → ren-os` (GitHub adds
  redirects); the F1 Phase 5 re-publish then ships RenOS as the first public surface.

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
