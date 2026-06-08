# Nate Herk Ingest + Positioning Pivot — Design Spec

> **Status:** Approved design (2026-06-08). Brainstormed via `superpowers:brainstorming`. This spec is the authoritative record of (a) the research ingest and (b) the positioning pivot it surfaced. **Sequencing decision = option (i):** the immediate deliverable is the *research synthesis + wiki pages* (below); the actual framework **rebuild** (cadence/code-map/self-improvement) is deferred to a future `superpowers:writing-plans` session that takes THIS spec as its input.

---

## 1. Provenance & method

- **Source:** Nate Herk's YouTube "Video Database" (Google Sheet, 97 videos across Q1+Q2 2026). Triaged to **33 on-target** (Claude-Code-as-OS / skills / agents / cadence / memory / economics); ~60 off-topic (n8n, sales, image/video, voice, trading) excluded.
- **Already-ingested (skipped):** `nate-herk-best-6-skills`, `nate-herk-ai-os`, `nate-herk-give-me-10-mins` (pre-existing in `raw/transcripts/`). Net **32 new** transcripts fetched.
- **Comparators (design pressure-test):** 2 Ben AI videos ("5 Skills to Build an AI Operating System", "Stop Using Claude Without an Agentic OS").
- **Engine lesson (reusable):** MarkItDown's YouTube path is **blocked on this machine** (returns the localized page footer, no transcript) — YouTube empty-responds the transcript endpoint. **`yt-dlp` auto-captions work** and is the engine. VTT → cleaned prose via a ~20-line stripper (drop timing/tags, de-dupe rolling captions). MarkItDown remains useful for non-YouTube docs/PDFs.
- **Extraction:** 32 Sonnet workers (one per transcript) against a fixed rubric → 67 distinct new-CC-features flagged, 164 candidate angles, signal 13 high / 11 med / 8 low. Condensed digest at `/tmp/nate-digest.json`; aggregated signal map captured in-session.
- **Workflow footgun (reusable):** pass workflow data as an **embedded `const`**, not via `args` (arrives stringified → `.map` throws) and not via a "loader agent" (silently returns empty). Both failed before the embedded-const run succeeded.

## 2. The strategic finding

Between the framework's design (~late May 2026) and now, **Claude Code shipped native primitives that absorb several framework capabilities** — concentrated on the framework's self-identified weakest layers (Cadence, multi-agent). The framework was largely defined by gaps the platform has now partly filled.

**Redundancy map (framework piece → native CC, postdating our research):**

| Framework component | Native CC now |
|---|---|
| Cadence ("just a SessionStart hook") | Routines / Cloud Routines (cron/API/GitHub triggers, machine-off, env-vault, network tiers), CronCreate/List/Delete, `/loop`, `/goal`, Channels |
| Memory (wrap/note/recall, "index not a dump") | Memory 2.0 + **Auto Dream** (background consolidation — *our exact philosophy*, now first-party) |
| improve-skill (experimental, Karpathy) | official **skill-creator** plugin (eval/benchmark/trigger-tune) + **Outcomes** |
| doctor --permissions ("keys ≠ instructions") | **Auto Permission Mode** (classifier-gated) |
| Planning | **Ultra Plan** (cloud Opus multi-agent) |
| Multi-agent (sub-agent fan-out) | **Agent Teams** (TeamCreate/SendMessage/A2A, plan-approval), **Dynamic Workflows**, **Managed Agents** (Credential Vault, Outcomes) |

This is **not a threat to retreat from — it's a platform to ride.** The pivot below reorients the framework from *building primitives* to *being the governable knowledge layer + the opinionated glue over native primitives.*

## 3. Thesis

> An **open-source second-brain OS for Claude Code**: a governable, compounding **wiki as the single source of truth**, plus thin opinionated **glue** that makes CC's native muscle (Routines, Teams, Memory) *report home*. **Ship the engine — the user brings the brain.**

The moat is not "we have a wiki." It is **"a transparent, governable, compounding source of truth — vs. CC's opaque auto-memory you can't fully steer."**

## 4. The six pillars

1. **Governable wiki = single source of truth.** Transparent plain-markdown the user owns and can override. Weighted *above* the glue (~65/35). The differentiator against CC's opaque native memory.
2. **Open-source the engine, the brain stays personal.** Ship the skeleton/system, never the content (makes ADR-017 the public stance). Inherently personal because a second brain gets more tailored with use.
3. **Control the truth, leverage the muscle.** Knowledge stays local/canonical in the wiki; *execution* (scheduling, multi-agent) rides native CC primitives — **but every run writes its durable result back to the wiki.** Control where it's canonical; leverage where it's transient.
   - **Write-back mechanism (refinement, from Ben AI pressure-test):** splits by execution locus. **Local** execution (cron/`/loop`/`/goal`) → direct file write. **Cloud** routines (machine off) → **git-based write-back** (the routine holds the wiki repo, commits results, the user pulls). Do **NOT** adopt Ben's "expose the wiki as an MCP server" approach — it violates the no-daemon rule (ADR-003) and needs the machine on. Git write-back reuses existing backup plumbing (ADR-026).
4. **Compounding model.** Three tiers:
   - **Hot capture** — `log.md` (chronological events) **+** a *new* lightweight instincts/learnings capture ("what worked, what to avoid, don't-repeat"), routed **hierarchically** (project-specific → project sub-wiki; global → global wiki). Cheap, liberal, append.
   - **Curated canonical** — the wiki proper; high-signal *promotions* from the hot tier. Deliberate.
   - **Governed in-wiki consolidate pass** — an LLM sweep that prunes contradictions, merges dupes, converts relative→absolute dates, promotes project→global. **This is our controllable answer to CC's opaque Auto Dream** — same benefit, we own it. May run **lightweight per routine-run** (opportunistic dedup/link-fix, per Ben) as well as a heavier scheduled sweep.
   - Instincts capture adopts ECC's *idea* (file-based, reviewable), **not** its machinery; project-scoped by default to avoid cross-project contamination; capture stays **separate** from skill-evolution.
5. **Self-improving capabilities.** Skills/agents/CLAUDE.md co-evolve with the project. Requires a **dependency-map** ("which artifacts reference which code") living in the wiki. Governance = **bike-method graduation**: auto-detect staleness + *propose* a diff (gated) first; an artifact *earns* auto-apply-on-branch after proving reliable over N runs. Automates the noticing, gates the applying.
6. **Code-map context layer.** **Adopt, don't hand-roll** a symbol→line-range markdown digest (ctags/tree-sitter/lean-ctx/Context Mode; an `update-codemaps` skill exists) so the agent reads compressed info and pulls only needed line ranges — token economy ("context gets worse hierarchically"). **Doubles as the dependency-map** for Pillar 5. Has a **staleness risk** → needs a refresh trigger + verify discipline (a digest that lies about line numbers is worse than none).
   - **Wiki navigation maps (from Ben AI):** the same navigation principle applies to the *wiki itself* — generate a **per-subfolder `CLAUDE.md`** map (Karpathy-attributed) so each section self-describes how to navigate it, not just one root map.

## 5. Prune / keep / rebuild map

| Framework piece | Verdict | Why |
|---|---|---|
| Wiki + wake-up injection | **KEEP + deepen** | the moat; native memory ≠ a curated studio brain |
| wrap / note / recall | **KEEP, reposition** as the curation/promotion layer above the hot tier | |
| Memory consolidation | **BUILD governed in-wiki pass**; do *not* cede to native Auto Dream | control the truth |
| Cadence | **REBUILD as glue** over native Routines/Cron/`/loop`/`/goal` + write-back | leverage the muscle |
| Multi-agent | **ADOPT native** Teams/Dynamic Workflows; add an orchestration decision-tree + per-sub-agent model-routing (Haiku workers, 3–5 cap) | leverage |
| improve-skill | **KEEP + extend** to artifact self-improvement (dep-map, bike-method); consider wrapping skill-creator's eval engine rather than hand-rolling | |
| doctor | **EXTEND** — token-economics + safety audits (auto-mode posture, network tiers, skill-size lint, stable-ID-rehydration flag, MCP-vs-CLI) **+ a wiki health-score** (dead links, stale files, token-heavy CLAUDE.md) | |
| Code-map + instincts capture | **NEW** (adopt-don't-build / governable, hierarchical) | token economy + compounding |
| Skill schema (ADR-011) | **ADD a lightweight/alias tier** — "a skill can be one prompt you don't want to retype" — alongside the full schema | reduce onboarding friction (Nate + Ben) |
| Onboarding (`sf-interview`/install) | **BROADEN** the guided init ritual — Ben's 12-section population (you/company/market/ICP/team + brain-dump) beyond identity-only | day-1 populated brain |
| Planning | **OPTIONAL** — adopt Ultra Plan as glue | |

## 6. Deferred / out of scope (named, not built)

- **Dashboard / visualization layer** — Ben's whole thesis; we deliberately omit it (terminal-native + Nate's "does it move the metric?" skepticism). The wiki is just a folder **Obsidian can open** as an optional overlay — zero conflict, note it.
- **Team-sharing, voice intake** — out of scope for solo-first (ADR-031). The "wiki-as-MCP" idea is the named future extension path if multi-user ever returns.
- **The actual rebuild** (cadence/code-map/self-improvement features) — deferred to a future `writing-plans` session (sequencing option i).

## 7. Positioning & rename implications

- The **rename** should signal the positioning: a *second-brain OS for Claude Code*, engine-you-bring-the-brain. Feeds the open-source goal. (Repo/displayName can be descriptive; the command namespace should stay short — see the v1.0 namespace defect.)
- **Pitch gifts** surfaced by the comparators: *"headless = free local execution"* (CC-native advantage vs. API-cost dashboards) and *"model-agnostic"* (it's just markdown + skill files; portable per ADR-024).
- The pivot **re-scopes Track B (v1.0 remediation):** several "fixes" become "prune/reposition." That re-scope happens in the deferred rebuild plan, not here.

## 8. This session's deliverable (the synthesis)

Write to `wiki/research/` (the framework's own dev-wiki), matching the `nate-herk-ai-os.md` schema, cross-linked into the existing corpus ([[nate-herk-ai-os]], [[simon-scrapes-agentic-os]], [[ralph]], [[py-harness-engineering]], etc.):

1. **5 thematic research pages** (Sonnet writers):
   - `nate-herk-cadence-automation.md` — Routines/Cron/`/loop`/`/goal`/Channels/deploy (the weakest-layer payoff)
   - `nate-herk-multi-agent-2026.md` — Agent Teams/A2A, Dynamic Workflows, Managed Agents, Agent View, orchestration decision-tree
   - `nate-herk-memory-2.0.md` — Memory 2.0, Auto Dream, `/memory`, three-layer memory, hot.md
   - `nate-herk-economics-and-permissions.md` — model routing, stable-IDs, CLI-over-MCP, task budgets, Auto Mode, network tiers
   - `nate-herk-skills-self-improvement.md` — skill-creator/eval/benchmark/trigger-tune, Outcomes, skill front-matter, WAT taxonomy, lightweight skill tier
2. **`new-angles-for-the-os.md`** — the synthesis: the redundancy map + the positioning pivot (this spec, distilled) + prioritized angles mapped to the pillars. The artifact that feeds the future rebuild plan + the rename.
3. **`index.md` + `log.md`** updates (Opus): add the 6 pages; append a dated ingest milestone.

Writers run on **Sonnet** (per maintainer instruction); Opus reviews every page + writes index/log.

## 9. Risks / open questions

- **Code-map staleness** — the digest must stay in sync with code; needs a refresh trigger + a "trust-but-verify" read discipline.
- **Self-improvement governance** — bike-method gating must hold; auto-apply only after earned trust, always on a reviewable branch.
- **No-daemon tension** — write-back must stay git-based for cloud routines (no local MCP daemon).
- **Scope** — the pivot is the framework's *next evolution*; this spec captures it but the build is explicitly deferred so the immediate research-filing goal isn't blocked.

## 10. Source index

- Transcripts: `raw/transcripts/nate-herk-*` (32 new) + `5-skills-to-build-an-ai-operating-system-like-the-1-ful`, `stop-using-claude-without-an-agentic-os` (Ben AI).
- Digest: `/tmp/nate-digest.json`; manifest: `/tmp/nate-manifest.json`; selection: `/tmp/nate-selection.json`.
- Prior corpus this builds on: `wiki/research/` (27 pages incl. the 3 prior Nate pages + simon-scrapes-*, caleb, jack-roberts, ralph, llm-wiki-pattern, py-harness-engineering).
