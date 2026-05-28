---
title: "Awesome-Claude-Skills Survey (ComposioHQ Curated List)"
type: research
source_url: https://github.com/ComposioHQ/awesome-claude-skills
source_fetched: 2026-05-28
ingested: 2026-05-28
tags: [ecosystem-survey, awesome-list, skills-survey, foreground-research, novel-approaches]
status: ingested
related: [ecc-everything-claude-code, nate-herk-best-6-skills, context-mode, claude-mem]
note: |
  Meta-survey of the awesome-claude-skills curated list maintained by ComposioHQ
  (~1000+ skills/plugins indexed). Identifies novel approaches and ecosystem
  patterns we missed in the practitioner-recommendation phase. Points at specific
  follow-up research targets.
---

# Awesome-Claude-Skills Survey (ComposioHQ Curated List)

## TL;DR

The ComposioHQ awesome-claude-skills list catalogs 1000+ skills/plugins across 10 categories. **Surfaces several novel approaches we hadn't yet researched** that are worth follow-up investigation: lean-ctx (Context Mode adjacent), Mercury/Proton MCP (team collaboration — addresses our identified gap), Chrome Relay (browser automation pattern), recursive-research (deep-research-with-checkpointing), great_cto + Septim Agents Pack (alternative agent orchestration). The list itself is partly Composio's marketing surface for their 78-integrations product — provider-vetting note: commercial entity, transparent about it.

## How the list is organized

10 primary categories:
1. Document Processing (PDF, DOCX, XLSX, PPTX)
2. Development & Code Tools
3. Data & Analysis
4. Business & Marketing
5. Communication & Writing
6. Creative & Media
7. Productivity & Organization
8. Collaboration & Project Management
9. Security & Systems
10. App Automation via Composio (78 pre-built SaaS workflows)

Plus a new **Assistive Technology** category for neurodivergent needs.

## Novel approaches worth investigating (not in our research yet)

### 1. lean-ctx — within-session token efficiency competitor

> "Session caching, AST-aware compression, and 90+ shell patterns" for token reduction.

Possible alternative or complement to Context Mode (per ADR-002). Worth a follow-up research page if/when we revisit the within-session efficiency stack. The "AST-aware compression" angle is technically interesting — Context Mode sandboxes but doesn't seem to do AST-level chunking.

### 2. Mercury / Proton MCP — addresses our team-collaboration gap

> "Message agent teammates, manage threads, create tasks, schedule automations across coordinated agent teams."

**This directly addresses the multi-author / team-collaboration gap we flagged for pre-design-doc filing.** The friend group dimension of our framework needs SOMETHING for cross-developer coordination; Mercury/Proton MCP is a candidate solution we should evaluate before designing our own.

### 3. Chrome Relay — clever browser automation

> "Drives the user's already-open Chrome session — cookies, SSO, extensions, localhost — via local CLI."

Bypasses the friction of fresh Playwright instances. Useful for projects with authenticated workflows. Not a v1 framework concern but worth knowing about.

### 4. OpenWeb — agent-native web access

> "Agent-native way to access any website" by calling underlying APIs with auth (cookies, JWT, CSRF, signing) auto-resolved.

A bridge tool for "agent wants to interact with a website that doesn't have a public API." Niche but interesting.

### 5. recursive-research — multi-step deep research with checkpointing

> "Multi-step research up to PhD level with disk checkpointing across context compaction."

This is the **deep-research-with-state-preservation pattern** we'd want for our own framework's research process. Currently we do research synchronously in conversation; recursive-research is a more disciplined pattern. Worth following up.

### 6. great_cto — meta-skill orchestrating 7 specialized subagents

> "Orchestrates 7 specialized subagents (tech-lead, senior-dev, qa-engineer, security-officer) across the full SDLC pipeline with 13 compliance frameworks."

Different agent orchestration philosophy than Superpowers' subagent-driven-development (which is more generic) or ECC's cascade orchestration. Worth understanding the design pattern.

### 7. Septim Agents Pack — named sub-agents

> "10 named sub-agents (Atlas, Luca, Canon, etc.) for coordinated team workflows."

Naming sub-agents is a stylistic / mental-model choice. Worth knowing the pattern exists; we don't need to adopt it for our framework.

### 8. LangSmith Fetch — first AI observability skill

> "First AI observability skill for debugging LangChain/LangGraph traces."

Per ADR-002 we don't use LangChain. Observability skills generally are an interesting category we don't address.

## Skill bundles / starter packs

- **Brand Build Skills** (59-skill library, brand → design → content → SEO → dev → ops)
- **Septim Agents Pack** (10 named sub-agents)
- **Google Workspace Skills** (Gmail, Calendar, Chat, Docs, Sheets, Slides, Drive)
- **solo-skills** (7 bilingual EN+中文 skills for indie founders)

The bundle pattern is interesting — bundling related skills for a specific use case. Our framework's `core` install profile (per ADR-006) is a form of bundle, but smaller-surface than these.

## Team-collaboration features (relevant to our gap)

This is where the awesome list surfaces direct value for our friend-group dimension:

- **Mercury / Proton MCP** — agent-to-agent messaging, thread management, task creation, scheduled automations
- **git-pushing, review-implementing, test-fixing** — collaborative engineering workflow skills (likely small individual skills)
- **Composio's 78 SaaS integrations** — Slack, Teams, Discord, GitHub, Jira, Linear, Asana, Monday, Notion. Distributed team coordination via real-time action propagation.

Our framework currently has no answer for any of these. **Worth deciding** at design-doc time whether to:
- Recommend Mercury/Proton MCP as part of the curated stack for team coordination
- Defer team-coordination tools to per-friend choice
- Build our own minimal team-coordination skill

## Provider-vetting note (per ADR-007)

ComposioHQ is a **commercial entity** (Composio.dev). The awesome-list is partly a curation service and partly a marketing surface for their 78-integration product. This is transparent (visible in the list categorization) and doesn't disqualify the list — just means we should:
- Trust the curation as a useful index, not as a neutral arbiter
- Cross-check any specific tool we adopt from the list against its actual maintainers
- Note Composio's commercial layer if friends ever consider Composio's own paid integrations

Per ADR-007 criteria: provider identity known + governance legible + clean history + transparent incentives + active maintenance → trust the list as a discovery surface.

## How this informs the framework

### Direct follow-up research targets (priority order)

1. **Mercury / Proton MCP** — addresses team-collaboration gap; high priority
2. **lean-ctx** — Context Mode alternative or complement; medium priority
3. **recursive-research** — deep-research pattern with disk checkpointing; useful for our framework's own research methodology (v2)
4. **great_cto** — alternative agent orchestration pattern; medium priority (we already have Superpowers + ECC options)

The rest (Chrome Relay, OpenWeb, LangSmith Fetch, Septim Agents Pack) are useful to know about but lower priority for v1.

### Scope check: ecosystem is bigger than we knew

The list catalogs 1000+ skills/plugins. Another source mentioned `quemsah/awesome-claude-plugins` indexed **15,134 plugin repositories by May 1, 2026**. The Claude Code ecosystem at this point is massive. Implication for our framework:
- **Curation is more valuable, not less** — picking carefully out of 15K is harder than picking out of 100
- **Comprehensive ingestion is impractical** — we have to be smart about which subset to evaluate deeply
- **The "discovery layer" itself is something the framework could help with** — speculative v2 idea: a `/sf:discover <use-case>` command that queries an awesome list and recommends candidates

### Categories where ecosystem gaps actually exist

Reviewing the 10 categories: most are well-served. Genuine gaps where our framework could add unique value:
- **Friend-group / team-level shared knowledge** (our wiki layer) — no equivalent in the awesome list
- **Identity-bootstrap onboarding** for groups — no equivalent
- **Project sub-wiki taxonomy** integrated with session lifecycle — no equivalent

Our framework's value-add isn't in the skill domain (ECC + this list cover that comprehensively); it's in the **integration + team layer**.

## Tensions / open questions

1. **Should we recommend Mercury/Proton MCP** as part of the curated stack? Need to research it specifically before deciding.
2. **lean-ctx vs Context Mode** — should we evaluate head-to-head, or trust Nate Herk's earlier recommendation of Context Mode and not revisit?
3. **The awesome-list itself as a v2 discovery surface** — should our framework include a `/sf:discover` skill that helps friends navigate the ecosystem?
4. **Bundle vs. single-skill thinking** — Brand Build Skills demonstrates that bundles can be 59 skills for one workflow. Our framework's `core` is much smaller. Should we consider bundling specifically for the friend group's likely use cases (e.g., a "founder bundle" with brand-voice + market-research + landing-page-copy)?

## Connections to prior research

| Prior source | Connection |
|---|---|
| ECC | ECC's `core` profile is one approach to curation; awesome-list bundles are another |
| Simon Scrapes Skill Systems | The bundle pattern is what skill systems aggregate into |
| Nate Herk Best 6 Skills | His curation was 6; this list is 1000+. Different scales of curation. |
| ADR-006 (Curated Stack) | This survey may surface alternative plugins worth adding/swapping |
| ADR-015 (Onboarding) | Onboarding could include opt-in browsing of the awesome list |

## Followups (logged for next research)

- **Deep ingest of Mercury/Proton MCP** (team collaboration — directly addresses identified gap)
- **lean-ctx evaluation** (Context Mode comparison)
- **recursive-research pattern** (research methodology for our own framework)
- **Check `quemsah/awesome-claude-plugins`** (15K+ plugins indexed — even broader)
- **Check `travisvn/awesome-claude-skills`** (alternative curation)

## Reference

- ComposioHQ awesome list: https://github.com/ComposioHQ/awesome-claude-skills
- Alternative lists: travisvn/awesome-claude-skills, BehiSecc/awesome-claude-skills, GetBindu/awesome-claude-code-and-skills, jqueryscript/awesome-claude-code, quemsah/awesome-claude-plugins
- Web directories: awesome-skills.com, awesomeclaude.ai/awesome-claude-skills, chat2anyllm.github.io/awesome-claude-skills
- ComposioHQ commercial layer: https://composio.dev (78 SaaS integrations)
- Fetched: 2026-05-28
- Scope of curation: 1000+ entries across 10 categories
