---
title: Best 6 Claude Code Skills (Nate Herk's Curated Stack)
type: research
source: raw/transcripts/nate-herk-best-6-skills
ingested: 2026-05-28
tags: [skills, plugins, curated-stack, claude-mem, context-mode, superpowers, gsd, ultrareview, skill-creator, frontend-design]
status: ingested
attribution: Nate Herk | AI Automation (YouTube), video "I Tried 100+ Claude Code Skills. These 6 Are The Best"
duration: ~14 min
related: [simon-scrapes-agentic-os, simon-scrapes-self-improving-skills, caleb-agent-harness, py-harness-engineering]
note: |
  This is the single most strategically important source so far. It surfaces a real
  question: how much of what we want to build is already shipped as community skills,
  and what does the framework add on top?
---

# Best 6 Claude Code Skills (Nate Herk's Curated Stack)

## TL;DR

Practitioner's curated list of the 6 most valuable Claude Code skills/plugins after 400 hours of use across multiple businesses. **The list is essentially what we said we wanted to build — already shipped as community plugins.** Two plugins (claude-mem, Context Mode) are direct prior art for our memory layer. One (Skill Creator) is Anthropic-official and already on our adopt list. Strategic implication: our framework's value proposition needs to clarify what it adds *on top of* this stack — likely the team-level layer (shared decisions, project sub-wikis, opinionated onboarding) plus a different memory thesis (wiki synthesis vs. compressed retrieval).

## The 6 skills (+ 1 bonus)

### 1. Skill Creator (Anthropic official)

- **What it does**: Describe a skill in plain English → Claude drafts, tests, iterates, packages
- **Why it matters**: Drops the barrier for non-engineers to build skills; same skill builds all other skills you'll ship
- **Install**: `/plugin install skill-creator` (recommended at user-global scope)
- **Already in our adopt list** (cited by Simon earlier)

### 2. Superpowers

- **What it does**: Forces Claude to work like a senior developer — plan first, work in isolated env, write tests first, two-stage review (spec match + code quality)
- **Why it matters**: Solves "rushed/sloppy code" failure mode. 150K+ GitHub stars (most popular community skill cited in our research).
- **Trade**: More expensive in tokens but fewer debug cycles
- **Install**: Single command (Nate puts in description)
- **Connection to our wiki**: Their two-stage review pattern echoes Tsinghua's evaluator/critic patterns. Different domain (code) but same shape.

### 3. GSD (Get Stuff Done)

- **What it does**: Spawns fresh sub-agents per task with clean context windows. Quality gates for scope reduction + security enforcement. Optional autonomous mode.
- **Why it matters**: Operationalizes the context-engineering layer per Caleb's harness model — fresh context per task. Mentioned by Simon in his Agentic OS source as a planning framework.
- **Trade**: Costs more tokens (sub-agent spawning) but saves hours of rework
- **Connection to our framework**: This is essentially the sub-agent delegation pattern (PY's "90% compute through child agents") packaged as a skill.

### 4. `/re` + `/ultrareview` (built into Claude Code, NOT external)

- **What it does**:
  - `/re` — local structured code review, bugs/edge-cases/design issues
  - `/ultrareview` — uploads branch to cloud sandbox, fleet of parallel reviewer agents (logic / security / performance / edge cases). Bugs must be **independently reproduced and verified** before listing.
- **Why it matters**: This is **Anthropic's official 3-agent GAN-inspired architecture** in action (planner + generator + evaluator from PY's research). It's free for first 3 runs (Pro/Max), then $5-20 per run.
- **Requires**: Claude Code 2.1.86+, signed-in account (API key alone won't work)
- **When to use**:
  - `/re` always (fast, cheap)
  - `/ultrareview` before risky merges (payments, auth, DB migrations, big refactors)

### 5. Context Mode

- **What it does**:
  - Sandboxes tool calls → only relevant output returns to context (raw garbage stays in subprocess)
  - 56KB Playwright snapshot → 299 bytes
  - 46KB access log → 155 bytes
  - 315KB total raw output → 5KB total returned to Claude
  - Tracks every meaningful event in local SQL database
  - On compaction: rebuilds session snapshot from DB and re-injects → "sessions that fell apart at 30 min now run 3 hours"
- **Why it matters**: Solves a problem we hadn't explicitly addressed — **within-session token bloat from tool call outputs**. Token efficiency we'd missed.
- **Architecture**: MCP server + hooks + routing instructions. Auto-installs all of it on plugin install.
- **Install**: 2 commands + restart Claude Code.

### 6. claude-mem (the elephant in the room)

- **What it does**:
  - Hooks into Claude's session lifecycle (start/stop)
  - Auto-captures file edits, decisions, bug fixes, commands
  - Uses Claude's own agent SDK to compress to semantic summaries
  - Stores in local SQLite with vector search
  - Auto-generates folder-level `CLAUDE.md` files (project docs write themselves)
  - **Three-layer retrieval**:
    1. Compact index of observations
    2. Timeline around relevant ones
    3. Full details only for the specific handoff needed
  - Claims 10× token savings on retrieval vs. dumping everything at session start
  - Web viewer for inspecting what Claude remembers
- **Why it matters**: **This is the closest existing prior art to our memory layer.** Mentioned by both Simon Scrapes AND Nate Herk as a recommended tool. Two independent practitioner recommendations.
- **Install warning**: There's a confusing npm install path that installs only the SDK. Stick to the plugin marketplace commands.

### Bonus Skill #7: Frontend Design (Anthropic official)

- Makes designs look less AI-generated; Anthropic's Cloud Design product has it baked in natively. Install globally for any UI work.

## Selling angle (not directly relevant for us, but illustrative)

Nate's pitch advice for selling AI services with these skills:
- Sell **outcomes**, not workflows ("save 10 hours/week", not "build AI workflow")
- Start with one skill, learn deeply, demo to business owners
- Build small specialized agents per industry

For us, the lesson is opposite-facing: **the value is in the outcomes the skill stack enables, not the skills themselves.** Our framework's pitch to the friend group is "this is the stack that makes us productive together," not "this is a fancy plugin."

## How this changes the framework's positioning

### The hard question this transcript raises

If we install Skill Creator + Superpowers + GSD + Context Mode + claude-mem + frontend-design + use built-in `/re` and `/ultrareview`, **we already have**:
- Skill authoring infrastructure (Skill Creator)
- Senior-developer workflow w/ TDD (Superpowers)
- Sub-agent delegation w/ context isolation (GSD)
- Code review automation (/re, /ultrareview)
- Within-session token efficiency (Context Mode)
- Cross-session memory (claude-mem)
- Frontend design quality (frontend-design)

That covers a LOT of what we said we wanted to build.

So what is *our* framework, exactly?

### The honest reframe

Our framework is **the team-level integration layer** sitting on top of this curated stack:

1. **Opinionated curation** — pick exactly this set (and explicitly reject ECC-style kitchen sinks), pin versions, install with one command for friends
2. **Team-shared knowledge that claude-mem doesn't capture** — decisions, patterns, lessons learned, project sub-wikis. claude-mem is single-user automatic capture; the wiki is team-curated synthesis.
3. **Project lifecycle integration** — CWD-aware wake-up, consolidate-to-wiki hooks, multi-project hierarchical organization
4. **Onboarding** — the polished install + identity-bootstrap + "here's how we work together" doc
5. **Self-improvement infrastructure** — the Karpathy-loop pattern applied to OUR custom skills (the ones that encode team-specific processes)

### Two memory layers, not one

This reshapes the memory thesis:

| Layer | Tool | Scope | Granularity |
|---|---|---|---|
| **Per-user session memory** | claude-mem | Individual developer's sessions | Auto-compressed event-level |
| **Team knowledge wiki** | Our framework | Friend-group studio | Curated synthesis-level |

These are complementary, not competing. claude-mem keeps a developer's individual context tight; the wiki carries team-level decisions across the group. **We should run BOTH.**

This actually resolves the L3-semantic-search tension we had earlier (Simon recommended vector search; we wanted file-only). Answer: **claude-mem provides the vector layer at the individual level; our wiki stays file-only at the team level.** Best of both worlds, no daemon to maintain ourselves.

### Strategic shift in framework scope

**Before this ingest**: framework = curated plugin doing curation + memory + onboarding.

**After this ingest**: framework = curated *meta-configuration* that wires together existing best-in-class skills (claude-mem, Context Mode, Superpowers, GSD, etc.) + adds a team-knowledge wiki layer on top + provides opinionated onboarding.

This is a much smaller, more honest, more defensible scope. We're not reinventing memory — we're **integrating the best existing memory tool (claude-mem) into a team workflow that none of the existing tools address**.

## Tensions / open questions

1. **Should we adopt claude-mem wholesale** as the user-level memory backend, with our wiki layered on top for team knowledge? Two independent recommendations make this strong. But we should evaluate claude-mem's actual code/architecture (next ingest target) before committing.
2. **Should Superpowers be in our recommended set?** Senior-dev workflow is high-value but opinionated. Friend group buy-in matters.
3. **GSD vs. our own sub-agent patterns** — GSD already does fresh-context-per-task delegation. Do we recommend GSD or build our own thin version that integrates with our wiki?
4. **Context Mode is non-trivial infrastructure** (MCP + hooks). Trusting an external plugin for within-session token efficiency is high-leverage but also high-trust. Worth evaluating their code.
5. **What's left for the FRAMEWORK to do?** With all these plugins installed, the framework's unique contribution is: the wiki layer + the install/config orchestration + the project lifecycle hooks (wake-up, consolidate) + the onboarding flow. Is that enough to call a "framework"?
6. **Pin versions or float?** Recommended plugins evolve. If we pin to specific versions, we get reproducibility but stale-ness. If we float, we get freshness but breakage risk.
7. **Skill stack as an ADR**: this set of decisions (which 6+ plugins ship by default, which configs, which we recommend installing globally vs. project-scoped) is now the most important upcoming `wiki/decisions/` entry.

## Convergence with prior sources

| Source | What this source confirms / extends |
|---|---|
| Simon Agentic OS | Confirms claude-mem (L3 semantic search recommendation). Confirms Skill Creator (mentioned). Confirms GSD (mentioned). |
| Simon Self-Improving Skills | Skill Creator is the foundation (confirmed). The framework's two-layer self-improvement pattern works on top of these tools. |
| Simon Skill Systems | Skill Creator + Superpowers + GSD ARE the kind of well-designed modular components Simon advocated for. Validates the composition thesis. |
| PY Harness Engineering | `/ultrareview` is Anthropic's official 3-agent GAN architecture. GSD operationalizes "90% compute through delegated child agents." |
| Caleb Agent Harness | Context Mode + GSD together implement Caleb's "loops with fresh clean context per iteration" pattern at the sub-agent and session level. |
| Karpathy LLM Wiki | claude-mem auto-generates `CLAUDE.md` files (auto-wiki pattern, but compressed not synthesized). Our wiki goes deeper on synthesis. |

**The picture, restated**: existing community plugins already cover most of the layers we identified. Our framework's actual unique contribution is the **wiki for team knowledge** + the **opinionated integration / onboarding** of these existing plugins. This is smaller scope than we thought, and that's good.

## Quotes worth preserving

> "Most people online are developing fancy skills for the sake of a cool video. But businesses don't actually want that. They want six types of skills. They're simple, they're boring, but they are effective."

> "[Superpowers] is one of the most popular community skills out there with over 150,000 stars on GitHub."

> "[claude-mem] auto-generates folder-level CLAUDE.md files and updates them as you work. So your project documentation literally writes itself while you code."

> "[Context Mode] sessions that used to fall apart around the 30-minute mark now run for three hours because you don't hit any slowdown."

## External references mentioned (HIGH PRIORITY for follow-up)

- **Skill Creator** — Anthropic official plugin
- **Superpowers** — community plugin, 150K+ GitHub stars. **Find the repo URL.**
- **GSD (Get Stuff Done)** — plugin. **Find the repo URL.**
- **`/re` and `/ultrareview`** — built into Claude Code 2.1.86+ (built-in, no install needed)
- **Context Mode** — plugin with `ctx-stats` subcommand. **Find the repo URL.**
- **claude-mem** — plugin with web viewer + SQLite + vector search + three-layer retrieval. **Find the repo URL. CRITICAL prior art.**
- **Frontend Design** — Anthropic official
- **Cloud Design** — Anthropic Labs product (browser-native version)

These should all be near the top of the foreground web research pass when we do it. claude-mem in particular needs deep evaluation.

## Reference

- Raw source: `raw/transcripts/nate-herk-best-6-skills`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Nate Herk | AI Automation, YouTube video "I Tried 100+ Claude Code Skills. These 6 Are The Best"
- Transcript length: ~22KB, video duration ~14 minutes
