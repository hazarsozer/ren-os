---
title: "ECC — Everything Claude Code (affaan-m): The Plugin We Mistakenly Dismissed"
type: research
source_url: https://github.com/affaan-m/everything-claude-code
source_fetched: 2026-05-28
license: MIT (Pro tier separate)
ingested: 2026-05-28
tags: [ecc, plugin, kitchen-sink-rejected-but-not-really, harness-system, agents, skills, hooks, mcp, foreground-research, ecosystem-survey, course-correction]
status: ingested
related: [nate-herk-best-6-skills, superpowers, claude-mem, simon-scrapes-agentic-os]
priority: CRITICAL — forces ADR amendments
---

# ECC — Everything Claude Code (affaan-m)

## TL;DR

**ECC is dramatically more sophisticated than the "kitchen sink" rejection in ADR-006 implied.** Calling it "Everything Claude Code" undersold it; the actual project is a **harness-native operator system** with **246 skills + 61 agents + 76 commands + 29 rule sets + 14 MCP servers + 15+ hooks**, MIT-licensed, 182K+ stars, 170+ contributors, and a **curated three-tier install profile** (minimal / core / full). Its memory model is **file-based instincts with confidence scoring** — closer in philosophy to our wiki than to claude-mem's vector store. **This research forces us to reconsider ADR-006's rejection.** We may have been building something that ECC's `core` profile already substantially is.

## Crucial honest reflection

Our brainstorming opening framed the user's #1 pain as "token/rate bloat from bad tools" — explicitly citing "Everything Claude Code" as the example of what NOT to be. The user's stated curation thesis was "we want minimal, not maximal."

**We never actually looked at ECC before writing that.** The mental model was: ECC = kitchen-sink; our framework = curated alternative.

Ingesting ECC now: that mental model is partially wrong. ECC offers `minimal`, `core`, and `full` install profiles. `core` is the recommended default and it's not maximalist — it's "agents, skills, commands, rules, hooks-runtime." `full` is the kitchen-sink variant; the project explicitly archives retired commands to `legacy-command-shims/` for opt-in only.

This research page exists to:
1. Document ECC honestly
2. Identify where ECC overlaps with our framework
3. Identify where our framework is genuinely additive vs. duplicative
4. Drive ADR amendments where the evidence demands

## Architecture

### Component inventory

- **246 skills** organized by domain (Coding / Frameworks / Languages / Content / Operations)
- **61 narrow-specialist agents** (planner, code-reviewer, security-reviewer, language-specific reviewers, mle-reviewer, etc.)
- **76 legacy command shims** (archived for opt-in)
- **29 rule sets**: `common/` (universal) + 9 language dirs (TypeScript, Python, Go, PHP, Swift, Perl, C++, Rust, ArkTS)
- **14 MCP servers** (GitHub, Supabase, Vercel, Context7, Exa, Playwright, Sequential Thinking, Memory, others)
- **15+ hook event handlers** (SessionStart, PostToolUse, Stop-phase, Pre/PostShellExecution)
- **Multi-agent orchestration commands** (`/multi-plan`, `/multi-execute`, `/multi-backend`, `/multi-frontend`, `/multi-workflow`) using "cascade orchestration"
- **PM2 integration** for managing long-running services (dev servers, workers, DBs)
- **AgentShield**: 1282 security tests across 102 rules + optional `--opus` adversarial 3-agent pipeline

### Philosophy (in their own words)

> "The harness-native operator system for agentic work" — packaging production-ready workflows evolved over 10+ months of daily use building real products.

**Core principle**: **research-first development** — prioritize documentation lookup and evidence gathering before code generation.

### Memory model (close to ours, NOT claude-mem)

ECC has **no built-in vector store or database**. Instead:

- **SessionStart hooks** capture `~/.claude/instincts/` frontmatter + file listings (≤8000 chars default)
- **Stop hooks** parse session markdown, extract decision patterns, write `.instinct.md` files
- **`/instinct-import`, `/instinct-export`, `/evolve`** commands manage learning across projects
- **Skill Creator (their GitHub App)** auto-generates `SKILL.md` from git history

Their memory is **file-based + markdown-native**. They reject database-backed memory just like our wiki design does.

### Cross-harness portability

ECC treats Claude Code, Cursor, Codex, OpenCode, Zed as **interchangeable harnesses**. Instead of baking in Anthropic APIs, it uses each platform's native CLI/plugin interface. Works with custom gateways via `ANTHROPIC_BASE_URL`.

This is a feature we don't address. Our framework is Claude-Code-specific.

### Install profiles

| Profile | What's in |
|---|---|
| `minimal` | Rules + agents only; no hooks, no legacy shims |
| `core` (recommended) | Baseline: agents, skills, commands, rules, hooks-runtime |
| `full` | Everything including legacy command shims and all optional modules |

The plugin path installs commands/agents/skills/hooks automatically but **cannot distribute rules** (upstream Claude Code limitation). Users manually copy desired rule folders.

### Anti-patterns / curation principles (theirs)

- **No stacked installs** — plugin + manual installer simultaneously creates duplicates
- **No explicit hooks in plugin.json** — CC v2.1+ auto-loads `hooks/hooks.json`; declaring it causes duplicate detection errors (with regression test enforcing this)
- **No rule bundling via plugin** — rules require manual copying (CC limitation)
- **No hardcoded Anthropic endpoints**
- **Retired commands archived** — opt-in only

### License & commercial model

- **MIT** for the OSS portion ("forever" per their commit)
- **ECC Pro** is a hosted GitHub App at $19/seat/month for private repos
- **GitHub Sponsors** from $5/month fund the maintainer

## Comparison with our adopted stack

| Concern | ECC (`core` profile) | Our adopted stack |
|---|---|---|
| **Memory model** | File-based instincts + confidence scoring | Wiki (team) + claude-mem (individual) + Context Mode (within-session) |
| **Skills** | 246 across many domains | Superpowers' ~10 skills (universal) + Skill Creator (foundation) |
| **Agents** | 61 specialists | Whatever Superpowers + Anthropic ship |
| **Hooks** | 15+ event handlers | Wake-up SessionStart + reliance on claude-mem + Context Mode hooks |
| **MCP servers** | 14 included | Whatever the user installs (Supabase, Vercel, Resend, Canva already global) |
| **Rule sets** | 29 (common + 9 languages) | No explicit rule files; rules embedded in skills |
| **Multi-agent orchestration** | Cascade orchestration commands | Superpowers' subagent-driven-development |
| **Security** | AgentShield (1282 tests, 102 rules, opus adversarial mode) | None at framework layer |
| **Cross-harness** | Yes (CC, Cursor, Codex, OpenCode, Zed) | Claude Code only |
| **Maturity** | 182K stars, 170+ contributors, 1,994 commits | Pre-v1; our own design |
| **License** | MIT (Pro $19/seat/mo) | MIT (per ADR-016) |
| **Philosophy** | "research-first development" | Same: token efficiency + wiki-as-memory + curation |

## What this means for our framework

This is the **honesty moment**. Some uncomfortable observations:

### Observation 1: ECC's core philosophy substantially overlaps with ours

- File-based markdown memory (NOT vector DB) — same as our wiki
- Research-first development as principle — same as our framework
- Curation discipline (minimal / core / full profiles, retired commands archived) — exactly the discipline our ADR-006 advocates
- Lifecycle hooks for session memory — same architectural pattern as our wake-up + consolidate

We may have been describing a framework that exists already.

### Observation 2: ECC's `core` profile is NOT maximalist

The "Everything Claude Code" name is misleading. `core` is the recommended default. `full` is the kitchen-sink variant — explicitly an opt-in. Calling the project a "kitchen sink" in ADR-006 was inaccurate.

### Observation 3: ECC adds things we don't

- Cross-harness portability (works on Cursor, Codex, OpenCode, Zed)
- Language-specific reviewers (12 languages with paired reviewer + build-resolver agents)
- AgentShield security testing (1282 tests, 102 rules)
- PM2 integration for service management
- Multi-agent cascade orchestration commands

### Observation 4: Things our framework genuinely adds that ECC doesn't

- **Team-level wiki for the friend group** — ECC's instincts are per-developer; our wiki is for shared studio knowledge across the friend group
- **Project sub-wiki taxonomy** (PROJECT.md / STATE.md / CONTEXT.md per ADR-014) — ECC doesn't have a project-organization layer
- **Two specific external plugin choices** (claude-mem for cross-session, Context Mode for within-session) — ECC's memory is in-house instincts
- **Opinionated config + identity bootstrap onboarding** — ECC's onboarding is more "install and figure it out"
- **Friend-group specific tech stack assumptions** (Python+uv, Vercel, Supabase, etc.)

### Observation 5: The right framing might be "ECC + our additions"

Instead of building a parallel system, we could:
- **Recommend ECC's `core` profile** as part of our adopted stack
- **Add our team-wiki layer on top** (the genuine novel piece)
- **Add our opinionated onboarding** that wraps ECC's install + adds identity bootstrap + the wiki
- **Replace our framework's "Superpowers + Skill Creator" recommendation with "ECC `core`"** — gets all of Superpowers' patterns (TDD, planning, review) PLUS ECC's broader skill set

This would dramatically reduce our framework's scope. The question is: **is that the right call?**

## ADR amendment candidates

If we accept that ECC + our additions is the right framing, several existing ADRs need amendments:

1. **ADR-006 (Curated Stack)** — replace Superpowers + Skill Creator with ECC `core`, OR add ECC alongside Superpowers; clarify the relationship
2. **ADR-002 (Token-Efficiency Stack)** — possibly update if ECC's instinct memory is good enough for some use cases (still likely keep Context Mode + claude-mem for the specific within-session + cross-session problems they solve)
3. **ADR-011 (Skill Schema)** — ECC has its own SKILL.md conventions; verify compatibility
4. **ADR-012 (Two-Layer Self-Improvement)** — ECC's `/evolve` command may overlap with our Layer 2; investigate
5. **ADR-015 (Onboarding)** — ECC has its own onboarding flow (`configure-ecc` skill); our `/sf:install` may want to compose with theirs rather than replace
6. **ADR-007 (Provider-Vetting Principle)** — affaan-m is a single maintainer; the trust assessment was reasonable but should be explicit

If we DON'T accept that framing — we still operate as designed but with the honest documentation that ECC exists and we chose to build something more focused — that's a defensible position too, but the ADR-006 rationale needs rewording.

## Tensions / open questions

1. **Single-maintainer concern.** ECC is by affaan-m. The project is mature (1,994 commits, 170+ contributors) but the bus factor is real. claude-mem and Context Mode have similar concerns; ECC's larger surface area amplifies it.

2. **Pro tier as monetization vector.** affaan-m runs ECC Pro as a $19/seat/month SaaS for private repos. The core is MIT but the existence of Pro creates incentive alignment questions (per ADR-007's provider-vetting). Is core sustainable independent of Pro? Mostly yes (MIT forever commitment + sponsors fund work), but worth tracking.

3. **246 skills is a LOT.** Even on `core` profile, the skill set is broader than most teams need. Counterpoint: skill activation is on-demand (progressive disclosure); unused skills don't actively cost tokens.

4. **Cross-harness portability is value we don't need YET.** Friend group is Claude Code-only for now. But if any member ever switches to Cursor (mentioned in user's CLAUDE.md as installed but rarely used), ECC's portability would matter.

5. **Lifecycle hook collision** with claude-mem + Context Mode + Ralph. ECC has 15+ hooks; the coordination problem from ADR-010 gets harder.

6. **Skill Creator vs ECC's auto-generation.** Our adopted Skill Creator is Anthropic's tool that interviews you. ECC's "Skill Creator" is a GitHub App that auto-generates from git history. Different tools, possibly complementary.

7. **The friend-group differentiation.** ECC is for individual developers. Our framework is for a TEAM with shared knowledge. That's the genuine gap. But is the team-wiki layer enough to justify a separate framework, vs. layering on top of ECC?

## Recommendation pending discussion

I don't have a confident recommendation yet. The user needs to decide:

**Option A**: Adopt ECC `core` as the primary stack, keep our wiki + onboarding + identity bootstrap as the team layer. Treat our framework as a thin meta-configuration that composes ECC + claude-mem + Context Mode + our wiki.

**Option B**: Stay the course. Recommend Superpowers + Skill Creator + claude-mem + Context Mode + our wiki, as currently designed. Document ECC honestly in the wiki and explain we made a different choice (smaller surface area, friend-group focus). Reword ADR-006's rejection rationale.

**Option C**: Hybrid. Recommend Superpowers (already dogfooding) PLUS some subset of ECC's tools where they don't duplicate Superpowers (e.g., AgentShield for security, language-specific reviewers, PM2 integration). More work to define what's in vs. out but possibly best-of-both.

Each requires ADR amendments. The decision should be discussed before filing.

## Quotes worth preserving

> "The harness-native operator system for agentic work."

> "Production-ready workflows evolved over 10+ months of daily use building real products."

> "Research-first development."

> "OSS stays free." (MIT commitment forever)

## References

- GitHub: https://github.com/affaan-m/everything-claude-code
- Plugin Hub listing: https://www.claudepluginhub.com/plugins/affaan-m-everything-claude-code
- ECC v1.10.0 release thread: https://github.com/affaan-m/everything-claude-code/discussions/1272
- ECC Pro: https://github.com/apps/ecc-tools
- Author: affaan-m
- Fetched: 2026-05-28
- License: MIT (OSS) + commercial Pro tier ($19/seat/mo for private repos)
- Star count: 140K+ (one source says 182K — high recent growth)
