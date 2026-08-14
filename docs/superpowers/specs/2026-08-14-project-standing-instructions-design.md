# Project-scoped standing instructions (#63)

**Date:** 2026-08-14
**Status:** Approved in brainstorm (Hazar), pending implementation
**Issue:** #63
**Train:** ships with the quarantine-exit fix-train (#52, #51, #46, archive-lint
rider). Those four are bounded fixes designed in chat; this spec covers #63 only.

## Problem

Per-project knowledge that should reach every session already has a home: wake-up
injects the active project's L2 map in full (ADR-008 conversation-layer
injection), and 0.7.3 #60 lets wrap UPDATE it. But a **rule that must bind
unconditionally** ("never touch X in this repo") has no project-scoped governed
home:

- Wake-up is a SessionStart hook. Subagents, other harnesses, and hook-failure
  sessions load CLAUDE.md but never see the wake-up payload.
- The promotion gate's standing-instructions target is global-only
  (`lib/memory/promotion.py: promote_to_global`).
- Writing rules straight into a project CLAUDE.md is ungoverned — no provenance,
  no trust stamp, no one-step revert, invisible to wiki-health's
  contradiction/staleness sweeps. That is the failure class of #58/#52.

## Decision summary

A governed wiki page per project, rendered into the project CLAUDE.md's existing
managed marker block. Content lives in the wiki with full provenance; CLAUDE.md
carries a splice the renderer owns. Entry is **manual-first** — `/ren:pin` and a
new `promote_to_project`, both human diff-approved; wrap's classifier is
untouched. Demand for automatic candidate detection is measured through the
suggestion accept/decline stream before any classifier change is considered
(same doctrine-first posture as the #60 distiller decision).

## 1. The page

- Path: `projects/<slug>/instructions.md`.
- New page type `project-instructions`, `schema_version: 1`, registered in
  `skills/wiki-migration/schemas.json` (`current: 1`, empty migration chain).
- Frontmatter follows the standard write-door stamp set (`type`, `project`,
  `schema_version`, `ren_*` provenance fields).
- **Instruction-plane.** The queue's instruction-plane predicate (today:
  `global/`, `decisions/`, `patterns/`, `research/`) grows
  `projects/<slug>/instructions.md`. Every write, from every producer, holds
  pending for human diff-approval per the 2026-08-01 promotion-gate decision
  (issue #18).
- Absent page = feature dormant. No migration, no backfill, no skeleton stamp at
  install/ingest — the page is born on first promotion.

## 2. Entry paths (manual-first)

- **`/ren:pin`:** when the friend asks for a standing rule scoped to the current
  project ("make this a standing rule for this repo"), pin proposes an
  ADD/UPDATE to `projects/<slug>/instructions.md`. The instruction-plane hold
  does the gating; pin itself stays the one-invocation, one-proposal producer it
  is today.
- **`promote_to_project(text, slug)`** in `lib/memory/promotion.py`, symmetric
  with `promote_to_global`: builds the proposal, routes it through the single
  write door, returns the held entry. Reachable from `/ren:suggestions` when a
  promotion suggestion is accepted.
- **Wrap:** no classifier change. Wrap's existing suggestion paths may surface
  "promote this to a project standing rule?" suggestions like any other
  promotion suggestion; acceptance flows through `promote_to_project`.

## 3. Render

- `lib/adapter/claude_md.py: render_project_block` gains a
  `## Standing instructions` section sourced from the page **body** (frontmatter
  stripped), inside the same single `<!-- ren:begin -->`/`<!-- ren:end -->`
  managed block. No second marker pair.
- **Re-render triggers:** (a) a write to `projects/<slug>/instructions.md` is
  applied through the queue — the apply path calls
  `write_project_claude_md(repo_root, slug)` for the mapped repo; (b)
  `/ren:update`'s existing re-render step. Projects with no repo mapping in
  `projects.json` skip (a) silently — doctor's drift check (section 5) is the
  backstop.
- **Budget:** the rendered section is capped at 3,000 characters,
  truncate-with-marker (same mechanism family as wake-up's budget truncation).
  The wiki page itself is uncapped; only the splice truncates.
- **Fail-closed:** a missing page, an unreadable page, or a page carrying the
  `ren-quarantine` banner renders **nothing** (section omitted entirely). A
  bannered instructions page is a governance anomaly — quarantined content must
  never become standing instructions.

## 4. No double-injection

Wake-up's extras channel excludes `projects/<slug>/instructions.md` (exact-path
predicate, alongside the existing exclusions). The page is already in every
session — including subagents — via CLAUDE.md; injecting it again would spend
wake-up budget on a duplicate. The L2 map and `knowledge/` injection behavior is
unchanged.

## 5. Doctor visibility

New warn-not-block check `check_standing_instructions_drift`: for every project
with both a repo mapping and an `instructions.md`, re-render the expected block
section and compare against what the repo's CLAUDE.md managed block actually
contains. Mismatch (stale splice, hand-edit inside markers, missed re-render)
→ `warn` naming the project. Remediation is a re-render, never automatic.

## 6. Testing (TDD, one failing test first per unit)

- Instruction-plane hold: a write to `projects/<slug>/instructions.md` from any
  producer lands `pending`, never auto-applies.
- `promote_to_project`: proposal shape, hold behavior, slug validation.
- Render: section present with page body; 3k cap with truncation marker;
  fail-closed on missing/banner/unreadable page; projects without the page
  render byte-identically to today.
- Apply-path re-render: applying an instructions write updates the mapped repo's
  CLAUDE.md block; unmapped project skips without error.
- Wake-up exclusion: instructions.md never appears in extras; map/knowledge
  injection unchanged (negative test).
- Doctor drift check: clean, stale-splice, and hand-edited-marker cases.
- End-to-end: pin → approve → CLAUDE.md block contains the rule.

## Out of scope

- Any wrap classifier change (measured-demand gate first).
- Retrofitting existing projects (pages appear on first use).
- Any change to the global CLAUDE.md block or `promote_to_global`.
- Cross-harness surfaces (AGENTS.md etc.) — `lib/portability` follow-up if ever.
