---
title: "ADR-006: Curated Stack — Which Plugins + Which Superpowers Skills"
status: accepted
date: 2026-05-28
sunset-review: 2026-08-28
references-pages: [superpowers, gsd-redux, skill-creator, frontend-design, claude-mem, context-mode, nate-herk-best-6-skills, simon-scrapes-claude-skills-upgrade, ecc-everything-claude-code, context7, anthropic-marketplace-catalog, team-coordination-survey]
amendments:
  - "2026-05-28: reworded ECC framing (studied for inspiration, didn't adopt); added context7 + claude-md-management as required; documented MCP Agent Mail as deferred / known alternative"
  - "2026-05-28: removed MCP Agent Mail from stack table entirely (per ADR-018, we build a simpler built-in Activity Feed instead, not MCP Agent Mail)"
affects-components: [install, onboarding, plugin-config, docs]
relates-to: [002-token-efficiency-stack, 003-no-daemon-rule, 011-skill-schema, 012-self-improvement, 015-onboarding]
---

# ADR-006: Curated Stack — Which Plugins + Which Superpowers Skills

## Context

ADR-002 named Context Mode + claude-mem as the token-efficiency stack but left "the full curated set" un-named. The user's #1 stated pain (token bloat from bad tools) is rooted in opinion-less "kitchen sink" plugin collections like ECC (Everything Claude Code). The whole pitch of the configuration is **curation** — choosing exactly the plugins that earn their slots and rejecting the rest.

The research surfaced a clear set of candidates from two practitioner curation passes (Nate Herk's "Best 6 Skills" after 400 hours, Simon Scrapes' Agentic OS 9-pillar framework, and the foreground research follow-ups). The shape of the consensus stack is:

- Skill authoring: Skill Creator (Anthropic official)
- Development methodology: Superpowers OR GSD Redux (overlap — pick one)
- Token efficiency: Context Mode + claude-mem (settled by ADR-002)
- Frontend quality: Frontend Design (Anthropic official, conditional)

Plus one set of decisions that ADR-002 didn't reach: **which Superpowers skills are active by default in our configuration vs. left optional.**

This ADR closes the curation question completely.

## Decision

**Plugin stack (v1, ordered by install priority):**

| # | Plugin | License | Purpose | Status |
|---|---|---|---|---|
| 1 | **Superpowers** (obra/superpowers) | MIT | Development methodology + foundational skills | **Required** — auto-install |
| 2 | **Skill Creator** (anthropics/skills) | Apache-2.0 | Authoring + improving custom skills | **Required** — auto-install |
| 3 | **claude-mem** (thedotmack/claude-mem) | Apache-2.0 | Cross-session memory | **Required** — auto-install |
| 4 | **Context Mode** (mksglu/context-mode) | ELv2 | Within-session token efficiency | **Required** — auto-install |
| 5 | **context7** (upstash/context7) — *added 2026-05-28* | TBD permissive | Version-specific documentation lookup | **Required** — auto-install (Upstash API key needed) |
| 6 | **claude-md-management** (anthropics) — *added 2026-05-28* | TBD permissive | CLAUDE.md quality audit + session-learning capture | **Required** — auto-install |
| 7 | **Frontend Design** (anthropics/claude-code plugins) | TBD permissive | Distinctive UI aesthetics | **Conditional** — install if friend group will build user-facing UIs |
| 8 | **Ralph / Ralph Wiggum** (anthropics/claude-code plugins) | TBD permissive | Autonomous loop pattern | **Documented, not bundled** — recommend in docs; install on demand |
| ~~9~~ | ~~**MCP Agent Mail** (Dicklesworthstone)~~ — *removed 2026-05-28* | — | — | **REMOVED**: per ADR-018, we built a simpler Activity Feed feature directly into the framework (shared private GitHub repo + per-friend log files). MCP Agent Mail's full machinery turned out to be overengineered for our use case ("automated session reports", not messaging or file reservations). |
| (built-in) | **Activity Feed** — *added 2026-05-28 per ADR-018* | (framework's own MIT) | Cross-friend session reports via shared private GitHub repo | **Built-in framework feature** (not a separate plugin). Setup happens in `/sf:install` Stage 3 (required). |

**Why these and not others:**

- **Superpowers wins over GSD Redux**: equivalent methodologies (both spec-driven, sub-agent-delegated, MIT). Superpowers is in Anthropic's official marketplace, has 150K+ stars, is already on the user's machine, and powered this very brainstorming session. GSD Redux's persistent-artifact taxonomy is borrowed into our project sub-wikis (ADR-014) without taking the whole plugin.
- **context7 (added 2026-05-28)**: solves the library-staleness problem (Claude's training cutoff vs current library versions). Anthropic-marketplace plugin by Upstash. Auto-activating skill + docs-researcher sub-agent on cheaper Claude 3.5 Sonnet (token-efficient). Adds a one-time Upstash API key setup step.
- **claude-md-management (added 2026-05-28)**: Anthropic-verified, 205K installs. `claude-md-improver` audits CLAUDE.md quality; `/revise-claude-md` captures session learnings into CLAUDE.md (the system-prompt-cached layer per ADR-008). Complements `/sf:wrap` at a different layer — `/sf:wrap` writes to the wiki, `/revise-claude-md` writes to CLAUDE.md. Both run; neither replaces the other.
- **Frontend Design is conditional**: relevant when projects produce user-facing UIs; irrelevant for backend / data / agent-only work. Onboarding asks; doesn't auto-install.
- **Ralph is documented, not bundled**: the pattern is valuable for autonomous overnight runs but doesn't belong in every developer's install. Plus its Stop hook would compete with claude-mem's lifecycle hooks (per ADR-010's coordination concerns). Install when needed.
- **MCP Agent Mail is removed (added 2026-05-28 amendment, then removed in second 2026-05-28 amendment per ADR-018)**: The user's clarification on the actual coordination need ("automated reports about session activity, not messaging or file reservations") made MCP Agent Mail overengineered. We built a simpler Activity Feed directly into the framework instead (see ADR-018 + the new entry in the stack table above). MCP Agent Mail stays in the research base (`wiki/research/team-coordination-survey.md`) as historical evidence of what we considered.

**Explicitly rejected (with reasoning):**

- **GSD Redux**: overlaps Superpowers; one is enough; pick the one we're already running.
- **ECC (Everything Claude Code) — reworded 2026-05-28**: we **studied ECC carefully** for insights and inspiration on their logical choices and how they solved adjacent problems. Their file-based instincts memory model aligned with our wiki philosophy; their `minimal/core/full` install profile demonstrated curation discipline; their AgentShield security testing offered a v2 idea. **We are not adopting ECC** because (a) our framework targets a friend group's specific team-knowledge layer that ECC doesn't address, (b) ECC's 246 skills + 14 MCP servers + 61 agents are far larger surface area than our group needs at v1, (c) a single-maintainer commercial-tier project carries different sustainability profile than the smaller, focused tools we adopt. ECC remains a known good option in the broader ecosystem; we built smaller-scoped and team-focused instead.
- **Generic kitchen-sink collections**: violate the curation thesis — they bring along tools the friend group will never use, eating context and rate limits. (ECC's `full` profile would be in this category; the previous wording incorrectly treated all of ECC as kitchen-sink, which the ecosystem survey corrected.)
- **Memory alternatives** (Mem0, Letta, Zep, LangMem): rejected per ADR-002 and `wiki/research/memory-architecture-alternatives.md`.

**Superpowers skills active by default vs. optional:**

The user's friend group is in **pre-product / ideation phase**, not feature-shipping. Some Superpowers skills are universally useful; others are heavyweight for the current phase.

**Active by default:**

| Skill | Why default |
|---|---|
| `brainstorming` | Universal — used for every new feature/project decision (we're using it now) |
| `writing-plans` | Universal — converts brainstorm output into actionable plans |
| `executing-plans` | Universal — drives planned work |
| `systematic-debugging` | Universal — needed when things break |
| `requesting-code-review` | Universal — quality gate on any commit |
| `verification-before-completion` | Universal — "this works" verification |

**Active when the friend group reaches the build-phase:**

| Skill | When activate |
|---|---|
| `test-driven-development` | When the group commits to shipping a product (TDD discipline is good for production, friction for ideation) |
| `subagent-driven-development` | When parallelizable work emerges (multiple features at once, refactors with isolation) |
| `using-git-worktrees` | When parallel branches matter (more than one in-flight feature) |
| `finishing-a-development-branch` | When branch-based workflows are in use |

**Onboarding flow handles this gradient** (ADR-015): asks "what phase are you in?" and toggles the second tier on/off.

## Consequences

**Easier:**
- One-command install scope is fully specified — no debate about what "the stack" includes
- The user's pitch to friends has a clean answer: "Six plugins, four required, two conditional, here's why each one earned its slot."
- The configuration's slash command namespace stays manageable — we know what we'll see
- Hook ordering questions (ADR-010) have a concrete plugin set to coordinate

**Harder:**
- We commit to maintenance of the full stack — if Anthropic deprecates Skill Creator, or thedotmack abandons claude-mem, we owe a migration plan
- License diversity in the stack (MIT + Apache-2.0 + ELv2) requires documentation in `LICENSES.md`
- We track six external projects' versions; pinning vs. floating becomes a sub-decision (ADR-015 will address)

**Now impossible:**
- Quietly adding plugins without an ADR amendment
- Claiming "kitchen-sink" parity — we're explicitly NOT trying to ship more

**Sunset review trigger conditions** (more aggressive than other ADRs because the stack moves fast):

- Any plugin in the stack becomes unmaintained (>3 months no commits) → revisit
- A new plugin emerges that displaces something in the stack → revisit
- Friend group reports specific skills they need that aren't covered → add or note as gap
- v2 of any plugin breaks our integration → migration plan or alternative

## Alternatives considered

### A) Adopt both Superpowers AND GSD Redux

**Considered shape**: Ship both for choice and flexibility.

**Why rejected**: Substantial overlap creates confusion about which methodology applies when. Competing slash command namespaces (`/gsd-*` vs. Superpowers'). Doubling install size without doubling value. Pick one.

### B) Don't bundle methodology at all — let friends pick

**Considered shape**: Ship only Skill Creator + claude-mem + Context Mode; let friends choose their own dev methodology.

**Why rejected**: Underspecifies what the framework is. A friend group with no shared methodology will diverge in working styles. Having a default is part of the curation value proposition. (Friends can still swap Superpowers out if they prefer something else — it's MIT, easy to replace.)

### C) Bundle everything Anthropic ships in claude-plugins-official

**Considered shape**: Auto-install the entire `anthropics/claude-plugins-official` marketplace.

**Why rejected**: Includes things irrelevant to our friend group (e.g., specialized skills for use cases they don't have). Kitchen-sink trap. Curate.

### D) Bundle additional community skills (e.g., the rest of Nate Herk's 100+ skills)

**Considered shape**: Survey the broader community plugins and bundle anything that scored well in our research.

**Why rejected**: Diminishing returns. Each additional plugin adds context cost + maintenance burden. The 6 we picked cover the user's stated pain (token efficiency + cross-session memory + skill authoring + dev methodology + optional UI quality + autonomous loops). More than that is creeping toward what we explicitly reject.

### E) Skip Frontend Design entirely

**Considered shape**: Don't include Frontend Design even conditionally — friends can install it themselves when needed.

**Why rejected**: Conditional inclusion (asked at onboarding) costs nothing if the friend declines, and saves them a step if they accept. Cheap convenience.

## References

- `wiki/research/superpowers.md` — full architecture; explains the Active-by-default skill selection
- `wiki/research/gsd-redux.md` — comparison showing overlap with Superpowers + trust note about open-gsd fork
- `wiki/research/skill-creator.md` — foundational; backed by Apache-2.0 + 256K installs
- `wiki/research/frontend-design.md` — conditional inclusion rationale
- `wiki/research/claude-mem.md` — adopted for cross-session memory
- `wiki/research/context-mode.md` — adopted for within-session efficiency
- `wiki/research/ralph.md` — documented-not-bundled rationale (Stop hook collision with claude-mem)
- `wiki/research/nate-herk-best-6-skills.md` — practitioner curation overlap signal
- `wiki/research/simon-scrapes-claude-skills-upgrade.md` — skill systems thesis (small + focused + reusable) underpins the curation discipline
- ADR-002 (Token-Efficiency Stack) — settled Context Mode + claude-mem
- ADR-003 (No-Daemon Rule) — context for why we can adopt plugin-internal daemons without violating our rule
- ADR-007 (Provider-Vetting Principle) — meme-coin lesson behind our exclusion of legacy gsd-build
- ADR-010 (Hook Ordering Coordination) — the operational reason Ralph is documented-not-bundled
- ADR-014 (Project Sub-Wiki Taxonomy) — where GSD's persistent-artifact pattern survives even though we don't adopt GSD itself
- ADR-015 (Onboarding) — handles the conditional install + phase-based skill toggling
