---
title: "New Angles for the OS — Nate Herk Ingest Synthesis (2026-06)"
type: synthesis
ingested: 2026-06-08
tags: [synthesis, positioning, roadmap, aios, claude-code]
status: ingested
related: [nate-herk-cadence-automation, nate-herk-multi-agent-2026, nate-herk-memory-2.0, nate-herk-economics-and-permissions, nate-herk-skills-self-improvement, nate-herk-ai-os]
spec: docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md
---

# New Angles for the OS — Nate Herk Ingest Synthesis (2026-06)

## TL;DR

Between the framework's design (~late May 2026) and now, **Claude Code shipped native primitives that absorb several framework capabilities** — concentrated on Cadence (the framework's self-identified weakest layer) and multi-agent orchestration. The right response is not retreat: it is a positioning pivot to **a governable wiki as the single source of truth** + **thin opinionated glue** that makes CC's native muscle (Routines, Teams, Memory 2.0) report home.

The moat is not "we have a wiki." It is **transparent, governable, compounding truth vs. CC's opaque auto-memory you cannot fully steer.**

Full design rationale: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`

---

## The redundancy map

| Framework component | Native CC now |
|---|---|
| Cadence ("just a SessionStart hook") | Routines / Cloud Routines (cron/API/GitHub triggers, machine-off, env-vault, network tiers), CronCreate/List/Delete, `/loop`, `/goal`, Channels |
| Memory (wrap/note/recall, "index not a dump") | Memory 2.0 + Auto Dream (background consolidation — our exact philosophy, now first-party) |
| improve-skill (experimental, Karpathy) | Official skill-creator plugin (eval/benchmark/trigger-tune) + Outcomes (early access) |
| doctor --permissions ("keys ≠ instructions") | Auto Permission Mode (classifier-gated, team plan) |
| Planning | Ultra Plan (cloud Opus multi-agent, 3 exploration + 1 critique) |
| Multi-agent (sub-agent fan-out) | Agent Teams (TeamCreate/SendMessage/A2A, plan-approval), Dynamic Workflows, Managed Agents (Credential Vault, Outcomes) |

Platform advances are not a threat — they are leverage. The pivot reorients the framework from building primitives to being the **governable knowledge layer + opinionated glue over native primitives.**

---

## Positioning thesis + the six pillars

> **An open-source second-brain OS for Claude Code**: a governable, compounding **wiki as the single source of truth**, plus thin opinionated **glue** that makes CC's native muscle (Routines, Teams, Memory) report home. **Ship the engine — the user brings the brain.**

### Six pillars

1. **Governable wiki = single source of truth.** Transparent plain-markdown the user owns and can override (~65% of the framework's weight). The differentiator against CC's opaque native memory.

2. **Open-source the engine, the brain stays personal.** Ship the skeleton/system, never the content (ADR-017). A second brain gets more tailored with use — inherently personal.

3. **Control the truth, leverage the muscle.** Knowledge stays canonical in the wiki; *execution* rides native CC primitives — but every run writes its durable result back to the wiki. Local execution → direct file write. Cloud routines → git-based write-back (no daemon; reuses ADR-026 backup plumbing). Do NOT adopt wiki-as-MCP-server (violates ADR-003).

4. **Compounding model.** Three tiers: (a) **Hot capture** — `log.md` + new lightweight instincts/learnings capture, hierarchically routed (project-specific → sub-wiki; global → global wiki); (b) **Curated canonical** — high-signal promotions from the hot tier; (c) **Governed in-wiki consolidate pass** — an LLM sweep that prunes contradictions, merges dupes, promotes project→global. This is the controllable answer to CC's opaque Auto Dream — same benefit, we own it.

5. **Self-improving capabilities.** Skills/agents/CLAUDE.md co-evolve with the project. Requires a **dependency-map** living in the wiki. Governance = **bike-method graduation**: auto-detect staleness + *propose* a diff (gated); an artifact earns auto-apply-on-branch after proving reliable over N runs.

6. **Code-map context layer.** Adopt (don't hand-roll) a symbol→line-range markdown digest (ctags/tree-sitter/lean-ctx/Context Mode; `update-codemaps` skill exists). Doubles as the dependency-map for Pillar 5. Has a staleness risk — needs a refresh trigger + verify discipline. Apply the same navigation principle to the wiki itself: generate per-subfolder `CLAUDE.md` maps so each section self-describes (Karpathy-attributed pattern per Ben AI comparator).

---

## Prune / keep / rebuild

| Framework piece | Verdict | Why |
|---|---|---|
| Wiki + wake-up injection | **KEEP + deepen** | the moat; native memory ≠ a curated studio brain |
| wrap / note / recall | **KEEP, reposition** as the curation/promotion layer above the hot tier | |
| Memory consolidation | **BUILD governed in-wiki pass**; do not cede to native Auto Dream | control the truth |
| Cadence | **REBUILD as glue** over native Routines/Cron/`/loop`/`/goal` + write-back | leverage the muscle |
| Multi-agent | **ADOPT native** Teams/Dynamic Workflows; add an orchestration decision-tree + per-sub-agent model-routing (Haiku workers, 3–5 cap) | leverage |
| improve-skill | **KEEP + extend** to artifact self-improvement (dep-map, bike-method); consider wrapping skill-creator's eval engine | |
| doctor | **EXTEND** — token-economics + safety audits (auto-mode posture, network tiers, skill-size lint, stable-ID-rehydration flag, MCP-vs-CLI, ultra-mode detection) + a wiki health-score (dead links, stale files, token-heavy CLAUDE.md) | |
| Code-map + instincts capture | **NEW** (adopt-don't-build / governable, hierarchical) | token economy + compounding |
| Skill schema (ADR-011) | **ADD a lightweight/alias tier** — "a skill can be one prompt you don't want to retype" | reduce onboarding friction |
| Onboarding (`sf-interview`/install) | **BROADEN** the guided init ritual — Ben's 12-section population beyond identity-only | day-1 populated brain |
| Planning | **OPTIONAL** — adopt Ultra Plan as glue | |

---

## Prioritized new angles

Distilled from 164 candidates across 32 videos to the ~25 highest-leverage. Grouped by pillar/theme.

### Cadence — rebuild as glue over native primitives

| Angle | Source slug | Notes |
|---|---|---|
| **`sf-routine-scaffold` skill**: lean GitHub repo + cloud-env config + failure-notification footer template for a given routine type | `nate-herk-claude-code-finally-gave-us-scheduled-automat`, `nate-herk-build-sell-claude-code-operating-systems-2-ho` | Highest-value CADENCE primitive; closes the "no-machine" gap |
| **`/loop` + CronCreate/CronList/CronDelete** as in-session primitives; pair with auto-compact cron (every 5 min injects `/clear`) to prevent context rot in loops | `nate-herk-i-tested-3-ways-to-deploy-claude-agents-heres`, `nate-herk-32-claude-code-hacks-in-16-mins` | Self-terminating loop (kill after N iterations) must be the default |
| **`/goal` as CADENCE backbone** for convergence-style routines (loop-until-done, 24h+, objective metric as exit criterion) | `nate-herk-multi-agent-building-in-claude-code-somehow-g`, `nate-herk-claude-code-dynamic-workflows-clearly-explained` | Pairs with improve-skill; wraps well as `sf-goal` with measurable-exit-criteria template |
| **Cloud Routine write-back via git**: every routine run commits results/state to a branch; recall skill reads `state.md` at next run start | `nate-herk-claude-code-finally-gave-us-scheduled-automat` | Stateless-run memory trail; reuses ADR-026 git backup |
| **`/loop` vs desktop-scheduled-tasks distinction**: `/loop` = stateful, 3-day max; desktop tasks = stateless, persistent, cold-start each run | `nate-herk-32-claude-code-hacks-in-16-mins` | Both needed in the CADENCE model with explicit guidance |
| **Budget-capped headless CC subprocess**: `claude --budget $2 "<task>"` for cron-triggered runs | `nate-herk-unlock-the-next-evolution-of-claude-code-with` | Works today; no new API needed |
| **`sf:cadence-start` skill**: wraps CronCreate with context-rot guard + self-terminating loop baked in | `nate-herk-i-tested-3-ways-to-deploy-claude-agents-heres` | One call creates two crons: work cron + /clear cron |

### Multi-agent — adopt native, add decision-tree

| Angle | Source slug | Notes |
|---|---|---|
| **Three-tier orchestration hierarchy**: main thread → sub-agents (fan-out, read-heavy, Haiku) → agent teams (collaborative, bidirectional, expensive, Opus-main) | `nate-herk-32-claude-code-hacks-in-16-mins`, `nate-herk-how-to-build-claude-agent-teams-better-than-9` | Width(/workflow) vs depth(/goal) decision heuristic belongs here too |
| **Capability ladder** (quick ask → skill → sub-agent → agent team → /goal → dynamic workflow) as a routing heuristic in doctor/planning | `nate-herk-claude-code-dynamic-workflows-clearly-explained` | Prevents over-engineering; solo-founder decision rule |
| **Haiku workers + Opus synthesis split** for Dynamic Workflows: 41 Haiku scorers → 1 Opus synthesizer | `nate-herk-claude-code-dynamic-workflows-clearly-explained` | Saves ~3-5x tokens on batch/fan-out jobs |
| **Agent Teams patterns**: goal-paragraph + file-territory ownership + named SendMessage recipients + graceful shutdown + 3–5 agent cap | `nate-herk-how-to-build-claude-agent-teams-better-than-9` | Cap is the token-economics gate; plan-approval mode is the safety gate |
| **Plan-approval mode** as the default posture for any Agent Team | `nate-herk-how-to-build-claude-agent-teams-better-than-9` | Aligns with "instructions ≠ capabilities" doctrine |

### Memory — governed, not ceded

| Angle | Source slug | Notes |
|---|---|---|
| **`hot.md` recency cache** (~500 chars, in project root): wrap skill writes it at session-end; SessionStart hook loads it before index.md | `nate-herk-andrej-karpathy-just-10xd-everyones-claude-co`, `nate-herk-build-sell-claude-code-operating-systems-2-ho` | Low cost, high continuity value |
| **Governed in-wiki consolidation pass** (the controllable Auto Dream): LLM sweep every N sessions; "index not a dump" constraint; prune contradictions; promote project→global | `nate-herk-claude-code-just-dropped-memory-20` | Adopt the dream prompt pattern verbatim (Nate infers it in the source video) |
| **Session-count trigger alongside time-based hooks**: track cumulative session count in project memory; fire heavier maintenance (wiki sync, permission re-audit) every N sessions | `nate-herk-claude-code-just-dropped-memory-20` | Prevents startup bloat as project ages |
| **Session-handoff schema** (upgrade wrap output): decisions locked + what shipped + key files + running state + deferred questions + pick-up block | `nate-herk-the-one-habit-that-doubles-your-claude-code-s`, `nate-herk-how-to-manage-your-claude-limits-better-than` | More reliable than /compact for cross-session continuity |

### Economics + permissions — extend doctor

| Angle | Source slug | Notes |
|---|---|---|
| **Stable-ID registry**: hardcode MCP discovery IDs (list IDs, channel IDs, workspace slugs) in skill.md at authoring time; /doctor flags repeated MCP lookup calls | `nate-herk-master-95-of-claude-code-skills-in-28-minutes`, `nate-herk-build-sell-claude-code-operating-systems-2-ho` | High ROI per-skill; eliminates re-discovery overhead |
| **/context audit step in doctor**: flags MCP server count, CLAUDE.md line count, loaded skills count, baseline token burn before any message | `nate-herk-18-claude-code-token-hacks-in-18-minutes`, `nate-herk-32-claude-code-hacks-in-16-mins` | Makes the invisible visible; 51K pre-message baseline is typical |
| **Ultra-mode detection in doctor**: warn when `/effort → ultra` is active; it bypasses many permission confirmations | `nate-herk-claude-code-dynamic-workflows-clearly-explained` | Aligns with "scope the keys" safety model |
| **Network-access tier as a permissions-audit dimension**: routines on "full" are vulnerable to prompt-injection exfiltration; default should be "trusted" | `nate-herk-claude-code-finally-gave-us-scheduled-automat` | New security surface native to Routines |
| **Sub-agent model routing as a framework-level rule**: Haiku for exploration/summarization/3+-file tasks; Sonnet for orchestration; Opus only on failure — encode in CLAUDE.md + skill front-matter | `nate-herk-18-claude-code-token-hacks-in-18-minutes`, `nate-herk-how-to-manage-your-claude-limits-better-than` | 7–10x sub-agent cost multiplier makes this high-leverage |

### Skills + self-improvement

| Angle | Source slug | Notes |
|---|---|---|
| **Wrap skill-creator into the self-improvement loop**: delegate eval/benchmark/trigger-tune to the official plugin; reserve improve-skill as the feedback-ingestion front-end (approved outputs → eval corpus) | `nate-herk-claude-code-skills-just-got-even-better` | Avoids duplicating Anthropic's official tooling |
| **Two-tier skill taxonomy** (capability-uplift vs. encoded-preference): tag each skill in YAML front-matter; schedule evals only for capability-uplift; treat encoded-preference as long-lived | `nate-herk-claude-code-skills-just-got-even-better` | Determines maintenance strategy per skill |
| **Skill-size lint in doctor**: flag skills over 500 lines; enforce YAML front-matter completeness; operationalises progressive context-loading guarantee | `nate-herk-build-sell-claude-code-operating-systems-2-ho` | Prevents token bleed as skill library grows |
| **Disable-model-invocation as safety default** for sensitive skills (doctor, backup, improve-skill): force explicit slash-command-only invocation | `nate-herk-master-95-of-claude-code-skills-in-28-minutes` | Aligns with "instructions ≠ capabilities" model |
| **Skill eval corpus directory** (`.claude/skills/evals/<skill-name>/`): approved wrap/note outputs become eval fixtures automatically over time | `nate-herk-claude-code-skills-just-got-even-better` | Self-feeding corpus; no extra user effort |

### Wiki navigation + context layer

| Angle | Source slug | Notes |
|---|---|---|
| **Per-subfolder `CLAUDE.md` maps** in the wiki (Karpathy-attributed): each section self-describes how to navigate it | `nate-herk-andrej-karpathy-just-10xd-everyones-claude-co` (Ben AI comparator sourced) | Low cost; prevents agent crawling the entire wiki |
| **CLAUDE.md as routing index** (under 200 lines): route to external files by path; never inline large reference material | `nate-herk-18-claude-code-token-hacks-in-18-minutes`, `nate-herk-32-claude-code-hacks-in-16-mins` | Enforce from install as a convention |
| **`routine-spec` section in project wiki schema**: name, trigger type, linked repo, env vars, expected output, failure handler | `nate-herk-claude-code-finally-gave-us-scheduled-automat` | Keeps wiki (truth) and routines (execution) in sync |

---

## Deferred / out of scope

Named and parked — not built in this session, not forgotten:

- **Dashboard / visualization layer** — Ben's whole thesis; deliberately omitted (terminal-native + Nate's "does it move the metric?" skepticism). The wiki is just a folder Obsidian can open as an optional overlay — zero conflict.
- **Team-sharing, voice intake** — out of scope for solo-first (ADR-031). Wiki-as-MCP is the named future extension path if multi-user ever returns.
- **The actual rebuild** (cadence/code-map/self-improvement features) — deferred to a future `superpowers:writing-plans` session that takes the spec as input. This page is the strategic index that feeds that session.
- **Daemon mode / Coordinator mode** — internal CC feature flags surfaced in source-code leak (`nate-herk-claude-code-source-code-just-leaked-8-things`); when these ship publicly, CADENCE should wire in immediately. Design spec should be ready in advance.

---

## Rename / positioning gifts

- The **rename** should signal the positioning: a *second-brain OS for Claude Code*, engine-you-bring-the-brain. Feeds the open-source goal. (Command namespace stays short — see v1.0 namespace defect in memory.)
- **Pitch gifts** from the comparators: *"headless = free local execution"* (CC-native advantage vs. API-cost dashboards) and *"model-agnostic"* (it's just markdown + skill files; portable per ADR-024).
- The pivot **re-scopes Track B (v1.0 remediation)**: several "fixes" become "prune/reposition." That re-scope happens in the deferred rebuild plan, not here.

---

## Next step

The actual rebuild (cadence/code-map/self-improvement) is explicitly **deferred**. The immediate next step is a `superpowers:writing-plans` session that takes the design spec as its primary input and produces a sequenced implementation plan.

This synthesis page is the strategic index that feeds that planning session. Cross-references:
- [[nate-herk-cadence-automation]] — Routines, `/loop`, `/goal`, CronCreate, remote-control, Trigger.dev
- [[nate-herk-multi-agent-2026]] — Agent Teams, Dynamic Workflows, Managed Agents, orchestration decision-tree
- [[nate-herk-memory-2.0]] — Memory 2.0, Auto Dream, three-layer memory, `hot.md`
- [[nate-herk-economics-and-permissions]] — model routing, stable-IDs, CLI-over-MCP, Auto Mode, network tiers, token budgeting
- [[nate-herk-skills-self-improvement]] — skill-creator, eval/benchmark/trigger-tune, Outcomes, skill front-matter, WAT taxonomy
