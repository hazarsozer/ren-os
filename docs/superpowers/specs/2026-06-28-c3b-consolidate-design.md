# C3b — Governed Promotion Sweep (`/ren:consolidate`, Compounding Memory Tier 3) — Design Spec

> **Status:** Approved design (2026-06-28). Brainstormed via `superpowers:brainstorming`; scope
> (promotion-first) + invocation (new `/ren:consolidate`) locked with the maintainer via AskUserQuestion
> (§2). Input to a `superpowers:writing-plans` pass and the contract for the TDD build.
>
> **Roadmap slice:** C3 (Pillar 4, "Compounding model") — decomposed. **C3a** (hot tier) shipped 2026-06-28
> (`c102f3a`). This is **C3b**, the governed sweep (tier 3). The mechanical housekeeping sweeps + project↔global
> axis are deferred (§6).
> **Amends:** ADR-037 (Compounding Memory Model) §7 already names C3b as the governed sweep; this slice records it.
> **Constrained by:** ADR-009 (consolidate is manual, never a Stop hook), ADR-031 (LLM proposes / human approves
> every diff — no auto-apply; EXPERIMENTAL bike-method), ADR-003 (no daemon).

---

## 1. Purpose

C3a gave instincts a cheap home (the hot tier), but without promotion they just accumulate — the loop
doesn't *compound upward*. C3b adds the missing link: a **manual, diff-gated sweep** that promotes durable
hot-tier instincts into the curated wiki (`patterns/`, `decisions/`, lessons). It is the positioning spec's
"governed consolidate pass — our controllable answer to CC's opaque Auto-Dream": same benefit, but every
change is a diff the human approves.

**Promotion-first.** This slice does ONLY hot→curated promotion. The mechanical housekeeping sweeps (dedup,
dead-link repair, date-normalize, contradiction-prune) and the project↔global axis are deferred (§6).

## 2. Locked decisions (maintainer, 2026-06-28)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **Sweep scope** | **Promotion-first** (hot→curated only). | Smallest coherent slice; delivers the compounding link (the pillar's purpose). Housekeeping deferred. |
| 2 | **Invocation** | **New `/ren:consolidate` skill** (separate from `/ren:wrap`). | Clean lifecycle split: wrap = per-session capture; consolidate = deliberate wiki-wide curation. Matches the 2026-06-21 ledger rec. |
| 3 | **Autonomy** | **Interactive-only, EXPERIMENTAL.** LLM proposes; human approves every diff. No `--autonomous` in V1. | ADR-031 bike-method; ADR-009 manual posture. The proposal is LLM judgment, the gate is human. |
| 4 | **Idempotency** | **In-place marking** of promoted instincts. | Re-runs never re-propose promoted entries; the marker is a traceable promotion link. (Alt considered: a `consolidated_through:` frontmatter watermark — less precise; rejected.) |
| 5 | **Apply primitive** | **Copy wrap's atomic apply pattern** into consolidate's lib. | Skill libs can't cross-import (the `lib` package-name collision documented in the C5c codemap work). Reuse the *pattern* + a faithful, separately-tested copy; the duplication is the cost of skill isolation. |

## 3. Architecture — new `skills/consolidate/`

A new skill, structured like `wrap`/`note`/`recall` (SKILL.md contract + `eval/eval.json` + `lib/`).

| Unit | Path | Status | Responsibility |
|------|------|--------|----------------|
| **skill contract** | `skills/consolidate/SKILL.md` | NEW | `/ren:consolidate` — manual, EXPERIMENTAL, interactive-only; the prompt orchestrates read → propose → gate → apply. |
| **types** | `skills/consolidate/lib/types.py` | NEW | `InstinctEntry` (kind, date, text, promoted: bool, raw_line), `PromotionDiff` (target_file, unified_diff, kind: page-edit\|marking, rationale). |
| **parse** | `skills/consolidate/lib/__init__.py` → `parse_instincts(text)` | NEW | Parse an `instincts.md` body into `InstinctEntry[]`; detect the `_(promoted …)_` marker. |
| **filter** | `… → unpromoted(entries)` | NEW | Drop already-promoted entries (idempotency). |
| **diff build** | `… → build_promotion_diffs(entry, target_path, target_current, promoted_on)` | NEW | Build the pair: (a) the curated-page diff (append-to-existing or create-new), (b) the in-place marking diff on the source line. Deterministic unified diffs (`git apply`-compatible). |
| **apply** | `… → apply_diff_entries(entries, *, wiki_root, cwd)` | NEW (copy) | Atomic apply: `git apply --check` all → apply → `git restore`+`git clean` rollback on any failure. Faithful copy of `wrap/lib/apply.py`, taking a `PromotionDiff[]` (no wrap-specific `context_md_rewrite`). |

The **what-to-promote judgment is LLM, prompt-layer** (SKILL.md), like wrap's LLM-classifier path is a
primitive — gated by human approval, not unit-tested for content. The lib is pure + deterministic + tested.

## 4. The promotion pipeline

1. **Read (read-only):** the hot tier — project `wiki/projects/<p>/instincts.md` + master `wiki/instincts.md`
   — and the curated pages for context. `parse_instincts` → `unpromoted` gives the candidate set.
2. **Propose (LLM):** for each durable/reusable/canonical-worthy instinct, propose a promotion → the right
   curated page-type (`patterns/`, `decisions/`, or a curated lessons note), reusing wrap's
   `references/wiki-page-mapping.md`. Bias conservative — most instincts don't promote. Most sweeps promote a few.
3. **Compose diff plan:** for each proposed promotion, `build_promotion_diffs` → the curated-page diff + the
   source-marking diff (the pair).
4. **Gate:** show each diff with wrap's `Y/N/E[dit]/A[ll]` flow (interactive-only).
5. **Apply atomically:** `apply_diff_entries` — all-or-nothing with rollback. Append one `log.md` line
   (`consolidated N instincts → M curated pages`). Print a summary.

## 5. Idempotency — in-place marking

A promoted instinct's source line is annotated in place (a gated diff):
`- **[worked]** 2026-06-28 — text  _(promoted 2026-06-28 → patterns/foo.md)_`
`parse_instincts` sets `promoted=True` for marked lines; `unpromoted` excludes them — so re-running the
sweep never re-proposes a promoted instinct, and the marker traces where it went.

## 6. Non-goals (deferred)

- **Mechanical housekeeping** — dedup, dead-link repair (builds on H1 WIKI-HEALTH detection), date-normalize,
  contradiction-prune. A later sweep slice.
- **Project↔global axis** — promoting a project instinct to the global pool. Same gated mechanism; deferred to keep this slice one operation.
- **Per-routine-run lightweight sweep** — a future cadence/C4 integration (a Cloud Routine invoking consolidate), not a daemon.
- **Autonomous mode** — none in V1 (interactive-only). Earned later per ADR-036 if ever.
- **No `/ren:wrap` change** — wrap still owns session→wiki; consolidate owns hot-tier→curated.

## 7. Governance — ADR-037 amendment

Append a 2026-06-28 amendment to ADR-037 recording: C3b ships the **governed promotion sweep** as
`/ren:consolidate` — interactive-only + EXPERIMENTAL, LLM-proposes/human-approves every diff (ADR-031),
manual/never-a-Stop-hook (ADR-009), in-place marking for idempotency. Housekeeping + project↔global + the
per-routine cadence integration remain deferred.

## 8. Testing (TDD) + slice

Run `skills/consolidate/lib/tests/` as its own pytest call (basename-collision discipline).

- **`parse_instincts`:** parses typed bullets (kind/date/text); detects the `_(promoted …)_` marker → `promoted=True`; ignores frontmatter/header; tolerates malformed lines.
- **`unpromoted`:** excludes promoted entries; keeps the rest.
- **`build_promotion_diffs`:** append-to-existing-page diff applies cleanly via `git apply --check`; create-new-page diff (`/dev/null` → new file) applies; the marking diff rewrites exactly the source line; both target the right paths.
- **idempotency:** an entry promoted once is `unpromoted=False` thereafter.
- **`apply_diff_entries` (copied):** atomic all-or-nothing; one bad diff → full rollback (re-test the copied primitive against a tmp git repo, mirroring `wrap/lib/tests/test_apply.py`).

**Slice:** `feat/c3b-consolidate` off `feat/project-ingest`; `--no-ff` merge. New `skills/consolidate/`
(SKILL.md + eval.json + lib + tests), ADR-037 amendment, `schemas.json` (the consolidate SKILL.md is a
`skill` page-type — no new page-type), CHANGELOG `[Unreleased]`, roadmap C3 row (→ C3a+C3b done; housekeeping
pending), `wiki/log.md`.
