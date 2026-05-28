---
title: "ADR-015: Onboarding — Identity Bootstrap + Version Pinning + /sf:doctor + /sf:bootstrap-project"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [simon-scrapes-agentic-os, claude-mem, context-mode, superpowers, skill-creator, frontend-design, context7, anthropic-marketplace-catalog, observability-tools-survey]
amendments:
  - "2026-05-28: added context7 + claude-md-management to Stage 2 required-install; added Upstash API key to Stage 1 env check; added native OpenTelemetry as optional Stage 6 step (answers Token Budgets gap-ADR)"
  - "2026-05-28: scope correction — identity bootstrap writes to `wiki/identity.md` (single file, per-friend wiki), NOT to `wiki/people/<friend-handle>.md` (the previous wording implied a shared people-directory which doesn't exist in our actual per-friend wiki model). Added MCP Agent Mail as optional Stage 3 install for friends who want inter-Claude messaging."
  - "2026-05-28: replaced Stage 3 MCP Agent Mail conditional install with REQUIRED Activity Feed setup (per ADR-018) — shared private GitHub repo URL, gh CLI auth verification, local clone, first-friend bootstrap pattern. Added `gh` CLI dependency to Stage 1 environment check."
  - "2026-05-28: added `claude auth status` check to Stage 1 (per official-docs-validation pass against Claude Code CLI reference). Claude Code itself must be logged into the friend's Anthropic account, distinct from the API key check."
affects-components: [install, onboarding, friend-group-rollout, docs]
relates-to: [006-curated-stack, 010-hook-ordering, 013-slash-command-namespacing, 014-project-sub-wiki-taxonomy, 016-framework-license]
---

# ADR-015: Onboarding — Identity Bootstrap + Version Pinning + /sf:doctor + /sf:bootstrap-project

## Context

The user's brainstorming opener set the goal: "easily deployable when we propose to our friends." Onboarding is the third pillar of the v1 framework (alongside curation and memory). It's the user-facing surface — where the success or failure of the proposal moment is decided.

The research surfaced multiple onboarding requirements that need a single coherent flow:

1. **Identity bootstrap** (Simon Scrapes Agentic OS): each friend's `user.md` / identity file should be populated via an AI-driven interview, not blank or boilerplate. 70% completeness within 10 minutes is the bar Simon set.

2. **Plugin install + verification** (ADR-006 stack + ADR-010 hook coordination): the four required plugins (Superpowers + Skill Creator + claude-mem + Context Mode) need to be installed and verified to be working together. A `/sf:doctor` slash command was promised in ADR-010.

3. **Project bootstrap** (ADR-014): the `/sf:bootstrap-project <name>` command needs to exist so a friend can spin up a new project sub-wiki without manual file creation.

4. **Phase-based skill toggling** (ADR-006): Superpowers' build-phase skills (TDD, sub-agent dev, worktrees, finishing) should be off by default while the friend group is in pre-product ideation; toggle on when they commit to shipping a product.

5. **Conditional plugin install** (ADR-006): Frontend Design is install-if-UI-work. The onboarding asks.

6. **Version pinning vs. floating** (ADR-006): each plugin's version needs a strategy.

7. **License diversity** (ADR-002 / ADR-006): friends should know what they're agreeing to (Apache-2.0 + MIT + ELv2 license mix).

8. **Wiki bootstrap** (ADR-004): the master wiki needs `index.md` + `log.md` if a friend installs onto a clean machine.

9. **`ANTHROPIC_API_KEY` setup** (ADR-006 Skill Creator caveat): Layer 1 description optimizer requires it. Friend group has subscriptions but each needs an API key alongside.

The risk if onboarding isn't designed: the friend group hits friction at install, gets confused about which plugin owns what, ends up with inconsistent setups across members, and the framework's "deployable" promise breaks.

## Decision

**One unified onboarding flow** that combines all the above into a sequence a friend runs once when they install the framework.

### The install flow

The framework ships with one entry point: **`/sf:install`** (the inverse of `/sf:doctor`).

When invoked on a fresh machine, `/sf:install` runs through these stages:

#### Stage 1: Environment check
- Verify Claude Code version ≥ minimum required (1.0.33+ per Context Mode)
- Verify Node.js ≥ 22.5 (per Context Mode requirement)
- Verify git is available
- **(added 2026-05-28 via ADR-018 amendment)** Verify `gh` (GitHub CLI) is available and authenticated; prompt `gh auth login` if not (needed for Activity Feed shared repo access)
- **(added 2026-05-28 via official-docs-validation pass)** Verify `claude auth status` — Claude Code itself must be logged into the friend's Anthropic account. Prompt `claude auth login` if not authenticated (different from API key; this is the Claude subscription auth)
- If `ANTHROPIC_API_KEY` not set in env: prompt user to set it (with instructions); save to user's secret store
- **(added 2026-05-28)** If `UPSTASH_CONTEXT7_API_KEY` (or whatever context7 ends up naming its env var) not set: prompt user to set it (OAuth flow generates the key); save to user's secret store
- Show summary: "Environment ready" or "Missing: [list]; fix and re-run"

#### Stage 2: Plugin install (required)
Install in order (per ADR-010 hook ordering preferences):
1. Context Mode: `/plugin marketplace add mksglu/context-mode` → `/plugin install context-mode@context-mode`
2. claude-mem: `/plugin marketplace add thedotmack/claude-mem` → `/plugin install claude-mem`
3. Superpowers: `/plugin install superpowers@claude-plugins-official` (Anthropic marketplace, already registered)
4. Skill Creator: `/plugin marketplace add anthropics/skills` → `/plugin install skill-creator@anthropic-agent-skills`
5. **(added 2026-05-28)** context7: `/plugin install context7@claude-plugins-official` — Upstash API key from Stage 1
6. **(added 2026-05-28)** claude-md-management: `/plugin install claude-md-management@claude-plugins-official`

After each install: brief confirmation. After all: "All required plugins installed."

#### Stage 3: Activity Feed setup + conditional plugins
**Required (per ADR-018, amended 2026-05-28 — replaces earlier MCP Agent Mail conditional):**
- Ask: "What's the GitHub repo URL for your friend group's Activity Feed?" (e.g., `your-group/activity-feed`)
- If repo doesn't exist yet: guide friend through `gh repo create <name> --private` + add other friends as collaborators (out-of-band step)
- Clone the repo to a known local path (e.g., `~/<framework-dir>/activity-feed/`)
- Verify push access by committing a placeholder `identities/<handle>.md` from the identity-bootstrap output
- Confirm setup

**Conditional plugin installs:**
- Ask: "Will your friend group build user-facing UIs (web/mobile apps)?" → install Frontend Design or skip
- Ask: "Want to enable the Ralph autonomous loop pattern?" → defer; document that `/plugin install ralph-loop@claude-plugins-official` is the command when needed
- ~~Ask about MCP Agent Mail~~ — removed 2026-05-28; the Activity Feed above is the framework's built-in equivalent (simpler, file-based, no separate plugin)

Show summary: "Activity Feed connected + conditional plugins handled."

#### Stage 4: Identity bootstrap (AI-driven interview)
This is the **Simon-Scrapes-inspired identity interview**:

Invoke the `identity-interview` skill (a framework skill, shipped per ADR-011's schema). The skill asks ~15 questions one at a time:
- Who are you? (role, background, expertise)
- How do you prefer to communicate? (terse / verbose; with/without emoji; with/without explanations)
- What's your tech stack baseline? (languages, frameworks, package managers)
- What are your strong opinions? (testing approach, refactoring tolerance, deployment preferences)
- What are NON-goals you want to avoid? (over-engineering, premature abstractions, etc.)
- What's the friend group's current phase? (ideation / building / shipping)
- (etc.)

Output (corrected 2026-05-28): writes `wiki/identity.md` — a single file holding THIS friend's identity for THIS friend's local wiki. There is no shared `people/` directory because the wiki is local per friend (per ADR-004 amendment). If MCP Agent Mail is installed (per ADR-018), `wiki/peers/<friend-handle>.md` can hold notes about the friend's peer Claudes for message-passing context — but that's separate from the friend's own identity.

Phase-based skill toggling (per ADR-006) happens here: the "current phase" answer enables or skips Superpowers' build-phase skills.

Target completion: 10 minutes, 70% complete. Friend can fill in details later.

#### Stage 5: Wiki bootstrap
If `wiki/` doesn't exist (fresh install):
- Create `wiki/` with `research/`, `decisions/`, `alternatives/`, `patterns/`, `people/`, `projects/`
- Create master `index.md` (template with empty section headers)
- Create master `log.md` with init entry

If `wiki/` exists (re-install): skip; warn user it already exists.

#### Stage 6: Configuration verification (`/sf:doctor`)
Run the same checks `/sf:doctor` does standalone:
- All required plugins installed and at expected versions
- Hooks registered (wake-up SessionStart should be detected)
- `ANTHROPIC_API_KEY` accessible
- **(added 2026-05-28)** Upstash API key accessible (for context7)
- Wiki structure present
- License compatibility documented (write `LICENSES.md` summarizing the stack's license mix)

**(added 2026-05-28) Optional sub-step: Native OpenTelemetry**

Ask: "Want token usage / session traces / cost observability? Claude Code has native OpenTelemetry support — set `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_HEADERS` to point at any OTLP backend (Honeycomb, Datadog, Grafana, Langfuse, Dash0, or a self-hosted OTel Collector). Skip if you don't want telemetry exported."

If yes → guide through env var setup; default = skip.

This answers what would otherwise be the "token budgets" gap-ADR (per observability-tools-survey research): native OTel + chosen backend's alert features = budget mechanism. No new framework code needed for budget tracking.

Output: green checkmarks or red flags with remediation.

#### Stage 7: First-session walkthrough
The skill walks the friend through:
- What `/sf:wake-up`, `/sf:wrap`, `/sf:note`, `/sf:recall` do (the daily commands)
- **(added 2026-05-28)** When to use `/sf:wrap` (wiki-layer team knowledge) vs `/revise-claude-md` (project CLAUDE.md hygiene) — both serve different layers per ADR-009 amendment
- How to invoke `/sf:improve-skill` when they author a custom skill
- How `/sf:bootstrap-project <name>` works (when ready to start a project)
- Where the wiki lives and how it's updated
- **(added 2026-05-28)** `/plugin marketplace` as a discovery surface for per-project domain plugins (e.g., AWS / Vercel / Supabase / Resend) — friends pick when they commit to a project, not at install

Then: hands off control. Friend is ready.

### Version pinning strategy

**Pin specific versions for v1.** The framework's `install.json` (or equivalent registry) lists exact versions:

```json
{
  "context-mode": "^x.y.z",
  "claude-mem": "^x.y.z",
  "superpowers": "5.1.0",
  "skill-creator": "^x.y.z"
}
```

Use caret (`^`) for compatible minor/patch updates; pin major versions exactly. The framework's own version bumps follow when plugin majors change (with migration notes).

**Don't auto-update plugins.** Friends pull our framework updates manually (or via a configured update mechanism); plugin updates piggyback on those. Predictability over recency.

### `/sf:bootstrap-project <name>` command

When a friend (or the group) commits to a new project:

```
/sf:bootstrap-project sidecar-v2
```

Creates `wiki/projects/sidecar-v2/` with the full taxonomy from ADR-014:
- PROJECT.md (template with placeholders)
- REQUIREMENTS.md (empty Functional/Non-functional/Out-of-scope)
- ROADMAP.md (Phase 1: TBD)
- STATE.md (empty Active Work / Open Threads)
- CONTEXT.md ("Just bootstrapped; first session pending")
- index.md (empty section headers)
- log.md (init entry)
- research/, decisions/, patterns/ (empty directories with .gitkeep)

Then prompts the user: "Open the PROJECT.md and fill in the purpose, or invoke Superpowers' brainstorming skill to interview you about the project."

### `/sf:doctor` command (standalone)

Independent of install, friends can run `/sf:doctor` anytime to verify their setup. Same checks as Stage 6 of install. Output: green/red status with specific remediation.

### License documentation (`LICENSES.md`)

Auto-generated during install (Stage 6). Lists each plugin's license + license summary + link to its repo. The friend can review what they're agreeing to:

```markdown
# Stack Licenses

## Required plugins
- **Superpowers** (MIT) — fully permissive
- **Skill Creator** (Apache-2.0) — permissive with patent grant
- **claude-mem** (Apache-2.0) — permissive with patent grant
- **Context Mode** (ELv2) — **NOT permissive for SaaS** (fine for personal/team use)

## Conditional
- **Frontend Design** (Anthropic, license TBD — verify on install)

## Framework itself
- (See ADR-016)
```

Friends are explicitly informed that **Context Mode's ELv2 restricts SaaS use** so if they ever distribute their work as a hosted service, that plugin needs replacement or commercial license.

## Consequences

**Easier:**
- **Install becomes one command.** `/sf:install` handles everything; no friend follows a multi-page README.
- **First session works immediately.** Identity bootstrap means the friend's first session doesn't waste tokens re-explaining who they are.
- **Verification is self-service.** `/sf:doctor` lets friends diagnose problems without our help.
- **Phase-appropriate workflows.** Build-phase skills don't appear until the group is ready for them.

**Harder:**
- **The install skill is non-trivial to author.** It orchestrates plugin marketplace adds, plugin installs, conditional questions, identity interview, wiki creation, and verification. This is the largest single skill in the framework.
- **State of the install needs handling on partial failures.** If Stage 2 plugin install fails midway, the skill needs to recover gracefully. Mitigation: idempotent stages; re-running `/sf:install` resumes from the last successful checkpoint.
- **The identity interview has to be GOOD.** A bad interview produces shallow `user.md` files. Mitigation: ship a high-quality identity-interview skill with binary-assertion evals (per ADR-011) so it can self-improve over time.

**Now impossible:**
- "Just clone the repo and you're done." Onboarding is a skill-driven flow, not a passive checkout.
- Silent license disagreements — friends explicitly see and acknowledge the stack's license mix.

**Sunset review trigger conditions:**
- Friend group reports specific friction points during install → revise stages
- A plugin's install mechanism changes → adapt
- Anthropic adds a marketplace bundle/profile feature that obviates parts of this → simplify
- The identity interview produces consistently shallow `user.md` files → improve via ADR-012's L2 loop

## Alternatives considered

### A) README-only onboarding

**Considered shape**: Document the install steps in a README; let friends follow them manually.

**Why rejected**: High friction. Friends skip steps, get inconsistent setups, drift from the configuration's design. The whole framework is about reducing friction; a manual README contradicts that.

### B) Shell script installer (`bash install.sh`)

**Considered shape**: A traditional shell script that automates the install.

**Why rejected**: Doesn't compose with Claude Code's plugin system; can't drive the identity interview (which is best done conversationally inside Claude); breaks the "everything is a skill" pattern.

### C) Skip identity bootstrap; let friends edit user.md manually

**Considered shape**: Bootstrap creates an empty `user.md` template; friend fills it in (or doesn't).

**Why rejected**: Friends who don't fill it in get generic responses. The Simon Scrapes Agentic OS source explicitly identifies this as the failure mode that AI-driven interviews fix. 10 minutes of interview > "I'll fill it in later" (they won't).

### D) Per-friend customization with no shared baseline

**Considered shape**: Each friend installs whatever subset of plugins they want; no shared default.

**Why rejected**: Defeats the friend-group thesis. Inconsistent setups make collaboration friction. The whole framework is "this is OUR setup." Shared baseline + per-friend identity is the right balance.

### E) Floating versions (always-latest)

**Considered shape**: Don't pin versions; always install the latest.

**Why rejected**: Breakage risk. A plugin's v2 might break our integration. The friend group's experience should be predictable; we update plugin versions deliberately, not reactively.

## References

- `wiki/research/simon-scrapes-agentic-os.md` — identity-interview pattern; AI interviews user instead of expecting blank-template fill
- `wiki/research/claude-mem.md` — install path for cross-session memory
- `wiki/research/context-mode.md` — install path + Node 22.5 requirement
- `wiki/research/superpowers.md` — install path + per-harness independence
- `wiki/research/skill-creator.md` — install + ANTHROPIC_API_KEY requirement
- `wiki/research/frontend-design.md` — conditional install rationale
- ADR-006 (Curated Stack) — the plugin set this onboarding installs
- ADR-010 (Hook Ordering Coordination) — `/sf:doctor` was promised here
- ADR-013 (Slash Command Namespacing) — `/sf:install`, `/sf:doctor`, `/sf:bootstrap-project` follow the prefix convention
- ADR-014 (Project Sub-Wiki Taxonomy) — bootstrap-project creates the sub-wiki this ADR defined
- ADR-016 (Framework License) — referenced from `LICENSES.md` summary
