---
title: "ADR-037: Compounding Memory Model (Instincts Hot Tier)"
status: accepted
date: 2026-06-28
sunset-review: 2027-06-28
references-pages: [nate-herk-ai-os, simon-scrapes-agentic-os]
affects-components: [memory, wiki, note, recall, wrap, schema, page-types]
relates-to: [009-consolidate-via-wrap, 014-project-sub-wiki-taxonomy, 027-schema-versioning, 031-solo-first-pivot, 012-two-layer-self-improvement, 003-no-daemon-rule]
---

# ADR-037: Compounding Memory Model (Instincts Hot Tier)

> C3 roadmap slice (Pillar 4, "Compounding model"). Decomposed: this ADR governs **C3a** (the hot-capture
> tier). Primary source: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
> §"Compounding model"; design spec `docs/superpowers/specs/2026-06-28-c3a-instincts-design.md`.

## Context

RenOS's compounding/memory pillar was the last unbuilt one. The wake-up hook (ADR-008) reads the wiki at
session start; `/ren:wrap` (ADR-009) writes the high-signal subset at session end. But `wrap` is
deliberately **high-threshold** — "most sessions produce ZERO wiki edits." That discipline keeps the
curated wiki clean, but it leaves **no cheap home for the steady stream of small, durable lessons** ("that
worked," "don't do that again," "avoid X") that are too minor to promote yet too valuable to lose. Today
they evaporate, or land in ephemeral session-notes that `wrap` may or may not promote.

The positioning spec names the fix: a **three-tier compounding model** —
1. **Hot capture** — cheap, liberal, append: a lightweight typed `instincts` artifact, routed hierarchically.
2. **Curated canonical** — the wiki proper; high-signal *promotions* from the hot tier.
3. **Governed consolidate sweep** — an LLM pass that dedups, merges, promotes project→global, fixes dates.
   "Our controllable answer to CC's opaque Auto-Dream."

Two guardrails constrain any build here: consolidation stays **manual** (ADR-009 — never a Stop hook;
Ralph/claude-mem collision + quality-over-autonomy), and there are **no speculative autonomy subsystems**
(ADR-031 — the deterministic classifier stays conservative; any LLM sweep is proposal-diff-gated).

## Decision

### 1. Adopt the three-tier model; ship **tier 1 only** (C3a)

The model is the three tiers above. C3a builds the **hot tier**; the governed sweep (tier 3 — promotion +
dedup) is **C3b**, a separate deliberate slice. Tier 2 (curated wiki) already exists.

### 2. New `instincts` page-type — durable, hierarchical, append-only

One append-only `instincts.md` per wiki level (mirroring `log.md`):
- **Project:** `wiki/projects/<project>/instincts.md`
- **Global:** `wiki/instincts.md` (master root)

Frontmatter `type: instincts`, `schema_version: 1`, `scope: project|global`. Body is typed entries —
`- **[<kind>]** YYYY-MM-DD — text`, `kind ∈ {worked, avoid, dont-repeat}`. Registered in
`skills/wiki-migration/schemas.json` (**amends ADR-027**); added to the sub-wiki + master taxonomy
(**amends ADR-014**).

### 3. Capture via `/ren:note --instinct` — explicit + cheap (amends ADR-009)

The hot tier is the new **bottom layer** of the compounding model, below the manual `/wrap` consolidate.
Capture extends `/ren:note` (`--instinct <kind>`, optional `--global`) — it is **explicit and cheap**, NOT
inferred and NOT a Stop hook. This is consistent with ADR-009's manual posture: the hot tier makes
*capture* liberal without making *consolidation* automatic. Plain `/ren:note` is unchanged.

### 4. Hierarchical routing — project-default, `--global` opt-in

An instinct lands in the current project's sub-wiki by default; `--global` (or no resolvable project)
routes to the master wiki. This prevents cross-project contamination — a project-specific quirk surfacing
everywhere — for free in the common case.

### 5. Read via `/ren:recall --instincts`

`recall` already searches all of `wiki/**`, so instincts are searchable by default; `--instincts` narrows
to `type: instincts` pages. Read-only, unchanged contract.

### 6. Page-type batch (ADR-027 "decide together")

Per ADR-027's decide-page-types-together rule, the shapes of the parked batch-mates are decided now:
- **`instincts`** — built (this slice).
- **`experiment-log` (B1)** — forward-declared in the registry (shape: `{change, score_before,
  score_after, disposition, iteration, ts}`); **no writer** yet (future B1 slice).
- **`verification_strategy` (C2)** — recorded as the planned **`routine-spec` v2** additive field
  (`verification_strategy: visual|test-run|lint|llm-judge|manual` + optional `tools:`); the v1→v2 bump +
  `/ren:routine-init` elicitation + doctor flag is the deferred C2 build, not migrated here.

### 7. Boundary — what C3a does NOT do (→ C3b)

No governed LLM consolidate/dedup/**promote** sweep (hot→curated); no `wrap` change; no wake-up
auto-surfacing; no inferred capture. The sweep (C3b) will be **proposal-diff-gated, never a Stop hook**
(ADR-031 + ADR-009).

## Consequences

**Easier:**
- A cheap, durable home for small lessons that `wrap`'s high threshold would otherwise drop.
- Hierarchy keeps project quirks out of the global pool by default.
- Read path is free (recall already greps the wiki); `--instincts` just focuses it.
- The risky autonomy (the sweep) is isolated to its own future slice, reviewable on its own terms.

**Harder:**
- Two memory-capture verbs now exist (`/ren:note` plain vs `--instinct`); onboarding must teach the split.
- Without the C3b promotion sweep, instincts accumulate in the hot tier and don't yet flow up to the
  curated wiki automatically — they're captured + recallable, but promotion is manual until C3b.
- A new page-type is an N+3 commitment (ADR-027). Mitigated: the shape is minimal (typed append-only bullets).

## Alternatives rejected

- **Auto-capture via a Stop hook.** Rejected — ADR-009's Ralph/claude-mem collision + the manual posture.
  Capture is explicit.
- **LLM-inferred capture in `/wrap`.** Rejected — leans on the conservative deterministic classifier
  ADR-031 keeps experimental; contradicts the "cheap, liberal, append" framing; blurs into the C3b sweep.
- **Single global instinct pool.** Rejected — cross-project contamination is the exact failure the
  hierarchy avoids.
- **Build the full three-tier loop in one slice.** Rejected — bundles the ADR-031-sensitive autonomy
  (the sweep) into the memory layer in one large, less-reviewable change. Decomposed like C5a/b/c.
- **New dedicated `/ren:instinct` command.** Considered; rejected for now — minimal surface, and `note` is
  already the "worth remembering" companion. Revisit if the shared verb proves confusing.

## References

- `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md` §"Compounding model" — the three-tier framing
- `docs/superpowers/specs/2026-06-28-c3a-instincts-design.md` — C3a design spec
- ADR-009 (Consolidate via /wrap) — manual posture; this ADR adds the hot tier below it
- ADR-014 (Project Sub-Wiki Taxonomy) — gains `instincts.md`
- ADR-027 (Schema Versioning) — registry gains `instincts` + `experiment-log`; records `routine-spec` v2 plan
- ADR-031 (Solo-First Pivot) — no speculative autonomy; the C3b sweep is proposal-diff-gated
- ADR-012 (Two-Layer Self-Improvement) — the skill-quality compounding layer, orthogonal to this memory layer
- ADR-003 (No-Daemon Rule) — capture + sweep are explicit, bounded, user-initiated

---

## Amendment — 2026-06-28: C3b governed promotion sweep (`/ren:consolidate`)

C3b ships **tier 3** — the governed sweep — as the new `skills/consolidate/` skill, **promotion-first**
(design spec `docs/superpowers/specs/2026-06-28-c3b-consolidate-design.md`).

- **`/ren:consolidate` — manual, interactive-only, EXPERIMENTAL.** Reads the hot-tier `instincts.md`; the LLM
  *proposes* which durable instincts graduate into curated pages (`patterns/`/`decisions/`/lessons), and shows
  **every change as a diff for approval** before applying. No autonomous mode; never a Stop hook (ADR-009);
  LLM-proposes / human-approves every diff (ADR-031).
- **Reuses wrap's proven pattern.** Promotions apply atomically (all-or-nothing with `git restore`/`git clean`
  rollback) via a faithful copy of wrap's apply primitive — skill libs can't cross-import (the `lib`
  package-name collision documented in the C5c codemap work), so the primitive is duplicated + separately tested.
- **Idempotent via in-place marking.** A promoted instinct's source line gains a `_(promoted <date> → <page>)_`
  marker; the sweep skips marked entries, so re-runs never re-promote, and the marker traces each promotion.
- **Still deferred:** mechanical housekeeping (dedup, dead-link repair, date-normalize, contradiction-prune);
  the project↔global instinct axis; per-routine-run lightweight sweeps (a future cadence integration);
  autonomous mode. `/ren:wrap` is unchanged.

This completes the compounding loop: **capture (C3a) → promote (C3b)**. The wiki now compounds upward, under
human control at every diff.

---

## Amendment — 2026-06-28: C3c first housekeeping sweep — dead-link repair (`/ren:consolidate --fix-links`)

C3c ships the first **mechanical housekeeping** sweep named in §7's deferred list, as a `--fix-links` mode on
`/ren:consolidate` (design spec `docs/superpowers/specs/2026-06-28-c3c-link-repair-design.md`) — **extending the
skill** rather than adding one, reusing the C3b diff-gate + atomic-apply spine in-package.

- **Dead-link repair, wiki-wide.** Scans `wiki/**` for dead `[[wikilinks]]` and `](file.md)` links; detection is
  a faithful Python port of doctor's read-only `check-wiki-health.sh` (doctor *detects*, consolidate now *repairs*).
- **Deterministic + conservative proposer.** Wikilinks fuzzy-match the slug pool (cutoff 0.8); mdlinks relocate
  on an unambiguous basename match. It **never removes a link or invents a target** — no-confidence links are
  reported for manual fixing, never guessed. The human still approves every diff (ADR-031); manual, never a Stop
  hook (ADR-009).
- **Gate-per-repair, apply-per-file, naturally idempotent.** Approved fixes for a page coalesce into one
  `link-fix` diff (atomic apply); a repaired link resolves, so re-scans skip it — no marker needed (unlike promotion).
- **Still deferred:** dedup, date-normalize, contradiction-prune; the project↔global instinct axis.

The governed sweep now covers both **promotion** (C3b) and **link-health housekeeping** (C3c), each diff-gated.
