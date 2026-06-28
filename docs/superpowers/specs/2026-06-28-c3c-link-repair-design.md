# C3c — Dead-Link Repair Sweep (`/ren:consolidate --fix-links`, Compounding Memory Housekeeping) — Design Spec

> **Status:** Approved design (2026-06-28). Brainstormed via `superpowers:brainstorming`; scope
> (dead-link repair only) + invocation (extend `/ren:consolidate`) locked with the maintainer via
> AskUserQuestion (§2). The contract for the TDD build.
>
> **Roadmap slice:** C3 (Pillar 4, "Compounding model") — the deferred mechanical-housekeeping half.
> **C3a** (hot tier, `c102f3a`) and **C3b** (governed promotion sweep, `457f3ea`) shipped 2026-06-28.
> This is **C3c**, the first housekeeping sweep: dead-link repair. date-normalize / dedup /
> contradiction-prune and the project↔global axis remain deferred (§6).
> **Amends:** ADR-037 (Compounding Memory Model) — §7 already lists "dead-link repair (builds on H1
> WIKI-HEALTH detection)" as deferred housekeeping; this slice records shipping it.
> **Constrained by:** ADR-009 (manual, never a Stop hook), ADR-031 (proposer suggests / human approves
> every diff — EXPERIMENTAL bike-method), ADR-003 (no daemon).

---

## 1. Purpose

H1's `check-wiki-health.sh` already **detects** dead links (read-only) — broken `[[wikilinks]]` and broken
`](file.md)` links — and surfaces them in `/ren:doctor`. But detection without repair just nags: the human
still hand-fixes every link. C3c closes that loop with a **manual, diff-gated repair sweep** that proposes a
fix for each dead link and applies the approved ones atomically.

It is the narrowest of the four deferred housekeeping sweeps, and the one the roadmap ledger names
explicitly ("dedup/link-fix"). It reuses C3b's diff-gate + atomic-apply spine **directly** (same skill, same
`lib` package — no copy), so the new surface is small: a detector port + a deterministic repair proposer.

**Dead-link repair only.** date-normalize, dedup, contradiction-prune, and the project↔global axis are
deferred (§6) — same decompose discipline that kept C3a/C3b/C5a-c small.

## 2. Locked decisions (maintainer, 2026-06-28)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **Sweep scope** | **Dead-link repair only.** | Smallest coherent housekeeping slice; reuses H1's detection algorithm; deterministic core (lowest Goodhart risk). date-normalize/dedup/contradiction-prune deferred. |
| 2 | **Invocation** | **Extend `/ren:consolidate`** with a `--fix-links` mode (default = promotion, unchanged). | Reuses the gate→apply spine in-package (no re-copy). Broadens consolidate's identity from "promote instincts" to "governed, diff-gated wiki sweeps." |
| 3 | **Repair proposal** | **Deterministic + conservative.** Fuzzy-match (`difflib`, cutoff 0.8) for wikilinks; basename relocation for mdlinks; **never auto-remove**. No confident candidate → report for manual fix, no diff. | Most dead links (typos/renames/moves) get a confident fix; genuinely-missing targets are surfaced, not guessed. LLM disambiguation is optional prompt-layer only. |
| 4 | **Apply granularity** | **Gate per-repair, apply per-file.** All approved fixes for one page compose into ONE `PromotionDiff(kind="link-fix")`. | apply.py applies diffs in order against the working tree; N same-file diffs each computed against the original text would fail on the 2nd apply. One-diff-per-file sidesteps that and keeps atomicity. |
| 5 | **Idempotency** | **Natural — no marker.** | A fixed link is no longer dead; re-runs don't re-touch it. Unlike promotion (which needed `_(promoted …)_`), no in-place annotation is required. |

## 3. Architecture — extend `skills/consolidate/`

No new skill. New `lib/links.py` + two new `types.py` dataclasses; the diff builders and `apply_diff_entries`
are reused in-package. The bash `check-wiki-health.sh` is **unchanged** (it stays doctor's read-only detector);
`links.py` is a faithful Python port of its detection algorithm, separately unit-tested.

| Unit | Path | Status | Responsibility |
|------|------|--------|----------------|
| **skill contract** | `skills/consolidate/SKILL.md` | EDIT | Add the `--fix-links` mode (default = promotion). Broaden `write:` to `~/.startup-framework/wiki/**`. Pipeline + failure-mode rows for the new mode. |
| **types** | `skills/consolidate/lib/types.py` | EDIT | Add `DeadLink(source_relpath, form, raw_target, alias, raw_line)` and `LinkRepair(dead, new_target, new_line, rationale)`. Reuse `PromotionDiff` (kind=`"link-fix"`). |
| **detect** | `skills/consolidate/lib/links.py` → `find_dead_links(pages)` | NEW | Port the wikilink + mdlink detection from `check-wiki-health.sh`; return structured `DeadLink[]` (slug index built from `pages`). |
| **propose** | `… → propose_link_repair(dead, slug_index, basename_index)` | NEW | Deterministic, conservative repair → `LinkRepair` or `None`. |
| **compose** | `… → build_link_repair_diffs(page_relpath, page_text, repairs)` | NEW | Apply all approved `LinkRepair` line-rewrites to one page's text → ONE `PromotionDiff(kind="link-fix")`. Reuses `_unified_diff`. |
| **apply** | `lib/apply.py → apply_diff_entries` | REUSE | Already takes `PromotionDiff[]`; reads only `.unified_diff`/`.target_file`. No change. |

The repair judgment is **deterministic in the lib** (fuzzy-match); the LLM/prompt layer only orchestrates
(scan → propose → gate → apply) and may disambiguate ambiguous cases. The lib is pure + tested.

## 4. The repair pipeline (`--fix-links`)

1. **Scan (read-only, wiki-wide):** glob `wiki/**/*.md`, read all into `pages: {relpath: text}`.
   `find_dead_links(pages)` → `DeadLink[]`. Empty → print "no dead links — wiki is link-healthy" and stop.
2. **Propose (deterministic):** build `slug_index` (basename-without-ext → relpath, first wins, mirroring
   the bash detector) and `basename_index` (basename.md → [relpaths]). For each `DeadLink`,
   `propose_link_repair` → a `LinkRepair` (confident fix) or `None` (→ manual-attention list).
3. **Gate (interactive-only):** show each `LinkRepair` as `source_relpath: [[old]] → [[new]]` with the
   `Y / N / E[dit] / A[ll-yes]` flow. **Always prompt.** Rejected repairs are dropped.
4. **Compose per-file:** group approved repairs by `source_relpath`; `build_link_repair_diffs` →
   one `PromotionDiff(kind="link-fix")` per affected page.
5. **Apply atomically + close out:** `apply_diff_entries(diffs, wiki_root=…, cwd=…)` — all-or-nothing with
   `git restore`/`git clean` rollback. On success append one `log.md` line (`fixed N dead links across M pages`)
   and print a summary including the K un-repairable links (manual-attention report — never dropped silently).

## 5. Idempotency — natural (no marker)

Repair rewrites the link to a resolvable target, so on the next sweep `find_dead_links` no longer reports it.
No `_(promoted …)_`-style marker is needed (that was promotion-specific). Re-running a clean wiki is a no-op
that prints "no dead links".

## 6. Non-goals (deferred)

- **date-normalize** — normalizing non-ISO dates. Low value (schema already mandates ISO `YYYY-MM-DD`); a
  later sweep only if real drift appears. Would add a sibling `--fix-dates` mode.
- **dedup / contradiction-prune** — LLM-semantic, high false-positive risk (the ADR-031 "Auto-Dream"
  territory). Each is its own future slice if ever; not bundled here.
- **Project↔global instinct axis** — promoting a project instinct into the global pool. Same gated mechanism;
  still deferred (C3b non-goal carried forward).
- **Link CREATION** — the sweep never creates a missing target page or removes a link; it only re-points a
  dead link to an existing page. Missing-target links go to the manual-attention report.
- **Autonomous mode** — none. Interactive-only, EXPERIMENTAL (ADR-009/031). Same posture as C3b.
- **Touching doctor's detector** — `check-wiki-health.sh` stays read-only; `links.py` is an independent port.

## 7. Governance — ADR-037 amendment

Append a 2026-06-28 amendment to ADR-037 recording: C3c ships the **first housekeeping sweep** —
**dead-link repair** — as `/ren:consolidate --fix-links`. Deterministic conservative proposer (fuzzy-match /
basename relocation, never auto-remove), gate-per-repair / apply-per-file, naturally idempotent (no marker),
reusing C3b's atomic-apply spine in-package. date-normalize / dedup / contradiction-prune and the
project↔global axis remain deferred. Manual / never-a-Stop-hook (ADR-009), proposer-suggests / human-approves
every diff (ADR-031).

## 8. Testing (TDD) + slice

Run `skills/consolidate/lib/tests/` as its own pytest call (basename-collision discipline). New
`tests/test_links.py`:

- **`find_dead_links`:** detects dead `[[wikilink]]` (slug not in index) and dead `](file.md)` (path doesn't
  resolve); ignores live links; ignores `http(s)`; detects multiple per page; returns structured records with
  `form`, `raw_target`, `alias`, `raw_line`, `source_relpath`.
- **`propose_link_repair`:** confident wikilink fuzzy-match → rewrite (respects the 0.8 cutoff: close typo
  matches, far misses → `None`); `|alias` preserved; mdlink basename relocation → corrected relative path;
  ambiguous/zero basename match → `None` (manual report).
- **`build_link_repair_diffs`:** a single fix applies cleanly via `git apply --check`; **multiple fixes in one
  page compose into ONE valid diff** (the same-file hazard) preserving all other content; correct repo-relative
  `target_file`.
- **idempotency:** a page whose links were all repaired reports zero dead links on re-scan.
- **apply integration:** a `kind="link-fix"` `PromotionDiff` applies + rolls back via the existing
  `apply_diff_entries` (reuse — light integration check against a tmp git repo).

**Slice:** `feat/c3c-link-repair` off `feat/project-ingest`; `--no-ff` merge. Touches `skills/consolidate/`
(SKILL.md + `lib/{types,links}.py` + `lib/tests/test_links.py`), ADR-037 amendment, CHANGELOG `[Unreleased]`,
roadmap C3 row (→ housekeeping: dead-link DONE; date-normalize/dedup/contradiction + project↔global pending),
`wiki/log.md`. **No `schemas.json` change** (no new page-type; consolidate stays a `skill`).
