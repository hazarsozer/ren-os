---
title: Startup Framework — Design Document
date: 2026-05-28
authors: Hazar + Claude (Sonnet 4.6)
status: draft
target-readers: friend-group members + future framework contributors
version-of-design: 1.0
---

# Startup Framework — Design Document

A meta-harness configuration for Claude Code, tailored for a small friend group building startup ideas together. Token-efficient, opinionated, and lightweight — installed once via the Claude Code plugin marketplace, then mostly invisible while it works.

This document synthesizes 27 Architectural Decision Records and 25 research pages into one comprehensive narrative. Each section cites the underlying ADRs for anyone who wants to drill into rationale.

---

## 1. Why this exists

A friend group decides to build a startup together. They've all used Claude Code individually. Each has their own preferences, their own pain points, their own muscle memory. Without coordination:

- They re-explain themselves to Claude every session ("I prefer Python with uv; I'm impatient with verbose responses; we're an early-stage team not a production shop")
- Generic plugins ship a kitchen sink of tools — most of which the friend group will never use, but they all eat tokens and rate limits
- Knowledge from one friend's hard-won debugging stays locked in their head
- They can't see what other friends are working on without DMing each other constantly
- Updates to their tooling are friction; rolling out a change to everyone is a Slack thread, not a deploy

The framework solves this by being **the friend group's curated Claude Code configuration**: a small set of carefully-chosen plugins + a personal knowledge wiki that grows with each friend's work + a lightweight cross-friend activity feed + an onboarding flow that takes a new member from zero-to-productive in ten minutes.

**North star: token efficiency.** Every design decision is checked against this. We exist because off-the-shelf tools waste tokens; we'll fail if we add more waste.

---

## 2. What it is

The framework is a **meta-harness configuration** on top of Claude Code.

- **Claude Code** itself is "the harness" — Anthropic's CLI tool that ships with hooks, skills, plugin marketplaces, agent management. (ADR-001 establishes this terminology distinction; we are NOT a "framework" in the LangChain sense.)
- **Our framework** sits on top, providing opinionated structure: which plugins to install, how their lifecycles coordinate, what the wiki looks like, how friends share context, how the whole thing evolves over time.

In concrete terms, what a friend gets when they install:

- **Six required plugins**: Superpowers (methodology) + Skill Creator (skill authoring) + claude-mem (cross-session memory) + Context Mode (within-session efficiency) + context7 (version-aware docs) + claude-md-management (CLAUDE.md hygiene)
- **One conditional plugin**: Frontend Design (asked at onboarding; UI projects only)
- **One documented-not-bundled plugin**: Ralph (autonomous-loop pattern; install on demand)
- **The framework's own built-in features**: wake-up hook, `/sf:wrap` consolidate, Activity Feed, identity interview, self-improvement loops, `/sf:install`, `/sf:doctor`, project bootstrap, update mechanism, and more — all coordinated for the friend group's specific workflow

The friend installs it via Claude Code's standard plugin marketplace pattern (`/plugin marketplace add ... && /plugin install ...`), runs `/sf:install`, and is ready in about ten minutes.

(See ADR-006 for the full curated stack rationale; ADR-023 for the explicit V1 scope fence.)

---

## 3. Architecture

### 3.1 The four-repo distinction

The framework's lifecycle involves four distinct git repos with different access patterns. Confusion about which is which can derail contributors; settling this early matters.

| Repo | Purpose | Access | Owner |
|---|---|---|---|
| **Framework dev wiki** (this repo, `~/Dev/startup-framework/`) | Our design history — ADRs, research, decisions. How WE built the framework. | Maintainers only | Hazar + future maintainers |
| **Framework marketplace repo** | Distribution surface — plugin source + `marketplace.json` + CHANGELOG. Where friends install FROM. | Read-collaborators (all friends) | Maintainers write |
| **Activity Feed repo** | Cross-friend session reports (per-friend `<handle>.log.md` files + identities). | Write-collaborators (all friends) | The friend group |
| **Friend's installed wiki** | Each friend's personal memory layer on their own machine. | Local-only to that friend | That friend |

The framework's development wiki is OUR record of how we built the framework. **It does not ship inside the plugin.** When a friend installs, they get an empty wiki skeleton (structure + page templates only); they grow their own wiki from there.

(ADR-017 + ADR-019 establish this; ADR-020 covers what happens when friends join/leave.)

### 3.2 Memory architecture (the four-layer stack)

The framework's memory model spans four layers, each per-friend-local:

```
Layer                         Tool                    Scope
──────────────────────────────────────────────────────────────
Within-session efficiency     Context Mode            Tool output sandboxed; raw output → 5KB compact summary
Cross-session continuity      claude-mem              Compressed observations across sessions
Personal deliberate synthesis Our wiki                Friend's hand-curated knowledge: decisions, patterns, lessons
Wiki search at scale (v2)     qmd (deferred)          Hybrid BM25+vector+LLM-rerank when wiki >200 pages
──────────────────────────────────────────────────────────────
(optional) Inter-Claude       Activity Feed (built-in) Cross-friend session reports via shared GitHub repo
messaging
```

The first three are active in V1 on every friend's machine. qmd is a v2 upgrade path the v1 architecture preserves (per ADR-005). Activity Feed is the only cross-friend layer — and it's deliberately terse (couple sentences per session-end entry, only project + task + files; no code, no decisions, no commentary).

**Critical for token efficiency** (per ADR-008): the wake-up hook injects wiki context into the **conversation layer**, NEVER the system prompt. This preserves Claude Code's prompt-cache prefix (Anthropic monitors cache hit rate at SEV level; we honor that). Cached tokens cost 10% of normal input; breaking the cache via system-prompt modification is expensive.

(ADR-002 for the stack; ADR-004 + ADR-014 for the wiki structure; ADR-008 + ADR-009 for the lifecycle hooks.)

### 3.3 The wiki structure

Each friend's wiki is **hierarchical**: one master wiki containing studio-level knowledge + one project sub-wiki per active project.

```
~/.claude/startup-framework/wiki/         (path settled in implementation; exact name TBD)
├── identity.md                             # Per friend, populated by /sf:interview
├── research/                               # Friend's ingested external sources
├── decisions/                              # Friend's own ADRs
├── alternatives/                           # Rejected options + reasoning
├── patterns/                               # Reusable patterns
├── projects/                               # Per-project sub-wikis
│   ├── <project-name>/
│   │   ├── PROJECT.md                       # What + why (rare updates)
│   │   ├── REQUIREMENTS.md                  # What must be true (per-milestone)
│   │   ├── ROADMAP.md                       # Phases + milestones
│   │   ├── STATE.md                         # Right-now snapshot (per signal session)
│   │   ├── CONTEXT.md                       # Active work focus (per session — wake-up's session-pointer home)
│   │   ├── index.md
│   │   ├── log.md
│   │   ├── research/
│   │   ├── decisions/
│   │   └── patterns/
├── index.md                                # Master catalog
└── log.md                                  # Master chronological event log
```

The wiki follows Karpathy's LLM Wiki pattern (ingest, query, lint operations; index.md + log.md as load-bearing artifacts) — confirmed by Karpathy's actual practice where his CLAUDE.md is just behavioral guidelines and the wiki is a separate artifact.

Page format (per ADR-011 + ADR-004): YAML frontmatter (`title`, `type`, `date`, `tags`, `framework_version`, `schema_version`, plus type-specific fields) + markdown body. The frontmatter is machine-readable; the body is human + AI-friendly narrative.

### 3.4 The daily loop

The framework's value shows up at session boundaries. Here's what happens:

**At session start** (SessionStart hook, per ADR-008 + ADR-018):

1. Wake-up hook reads `pwd` to determine context (which project, if any)
2. Loads master `wiki/index.md` (small)
3. If in a project directory, loads project sub-wiki's `index.md`, `CONTEXT.md` (the session pointer from last `/sf:wrap`), and last ~10 `log.md` entries
4. Loads master `log.md` tail
5. Pulls the Activity Feed shared repo + reads other friends' recent `<handle>.log.md` entries
6. Composes a single context-injection message in the **conversation layer**
7. Posts a new entry in own `<handle>.log.md` (Activity Feed): `## [<time>] start | <handle> | working in <dir>`
8. Pushes the Activity Feed update to GitHub

Total context loaded: ~3–5K tokens of relevant material. Never the whole wiki.

**During the session**: friend works. Hooks from claude-mem (capturing observations) and Context Mode (sandboxing tool outputs) run silently. Skills from Superpowers activate as the work matches their descriptions.

**At session end** (when the friend chooses, per ADR-009): friend runs `/sf:wrap`.

1. `/sf:wrap` reads the session log (Claude Code's record + any `/sf:note <text>` pins the friend captured during the session)
2. Decides what (if any) is high-signal enough to promote to the wiki — most sessions produce ZERO wiki edits; that's the discipline
3. Updates affected pages (STATE.md / CONTEXT.md / etc.) with diffs shown for approval
4. Composes a terse Activity Feed entry: "Worked on `<project>` — `<1-2 sentence task brief>`. Touched: `<file list>`."
5. Commits and pushes the Activity Feed entry

Companion commands during sessions: `/sf:note <text>` (pin for `/sf:wrap` to consider), `/sf:recall <query>` (mid-session wiki query without loading more), `/sf:catch-up [project]` (skim Activity Feed history when joining a project mid-flight).

For sensitive sessions the friend doesn't want shared: `/sf:wrap --skip-feed` (wiki updates only; nothing pushed to Activity Feed) or `SF_SKIP_FEED=1` environment variable.

### 3.5 Skills, agents, and self-improvement

Every framework-shipped skill follows this structure (per ADR-011):

```
skills/<skill-name>/
├── SKILL.md                    # Instructions, target <200 lines (progressive disclosure)
├── references/                  # Context loaded on demand
├── eval/eval.json               # Binary-assertion tests (Skill Creator compatible)
└── learnings.md                 # Optional, per-skill feedback log
```

SKILL.md frontmatter includes an **execution contract** (Tsinghua NLH-inspired): `required_outputs`, `budgets` (tokens/turns/files/duration), `permissions` (read/write/execute), `completion_conditions`, `output_paths`. This makes skill behavior predictable and verifiable.

**Self-improvement is two layers** (per ADR-012):

- **Layer 1 (activation)**: Skill Creator's existing description optimizer — 60% train / 40% test split, 3 runs per query, up to 5 iterations. Already shipped by Anthropic; we adopt it.
- **Layer 2 (body quality)**: New framework skill `/sf:improve-skill <name>` — Karpathy auto-research loop applied to SKILL.md body. Run iteratively: read skill, run binary assertions in eval/eval.json, propose one change, re-run, keep or revert via git. Available in interactive mode (default; user approves each change) or `--autonomous --max-iterations N` mode for overnight runs.

Native Claude Code safety primitives we layer on top of our `--max-iterations`: `--max-turns` (CC-native turn limit per session), `--max-budget-usd` (CC-native budget cap), `--bare` (skip plugin overhead in inner sub-runs).

This is the most strongly-supported design decision across our research — four independent sources (Karpathy auto-research, Simon Scrapes two-layer, PY's "self-evolution was the only consistently-helpful ablation module," Skill Creator's existing implementation) all point at this pattern.

(ADR-011 for the schema; ADR-012 for the two-layer mechanics.)

### 3.6 Distribution and updates

The framework distributes via a **private GitHub repo configured as a Claude Code plugin marketplace** (per ADR-019).

Install (per ADR-015 + ADR-019):

```
/plugin marketplace add <our-org>/<framework-marketplace-repo>
/plugin install startup-framework@<...>
/sf:install
```

**Versioning**: semantic versioning (MAJOR.MINOR.PATCH), **stable monthly release cadence**. PATCH = bug fixes only, no schema changes. MINOR = additive schema (new optional fields with defaults). MAJOR = breaking changes with required migration.

**Updates**: opt-in via `/sf:update`. Never automatic. `/sf:doctor` reports when a new version is available. Migrations (per ADR-027): hybrid scripted-for-mechanical + LLM-driven-for-semantic; snapshot before migration; diff shown for user approval; latest 3 snapshots retained for rollback.

**Backwards compatibility** (per ADR-017's commitment): schemas supported through N+3 versions before becoming read-only; the framework reads older formats and offers migration paths.

### 3.7 Activity Feed (cross-friend visibility without shared state)

The Activity Feed is the framework's only cross-friend layer. It's a **shared private GitHub repo** with per-friend log files:

```
friend-group/activity-feed/      (shared private GitHub repo)
├── hazar.log.md
├── friend-b.log.md
├── friend-c.log.md
├── identities/
│   ├── hazar.md                  # Public-facing identity per friend
│   └── friend-b.md
└── README.md
```

Per-friend log files prevent write conflicts when multiple friends end sessions simultaneously. Entries follow the wiki/log.md chronological-invariant format (`## [YYYY-MM-DD HH:MM] start|end | <handle> | <description>`).

The terse format is the **primary privacy mechanism** (per ADR-021). Session-end entries are couple-sentence summaries of project + task + files touched, never code or detailed reasoning. The format constraint prevents most accidental leakage.

For sensitive sessions: `/sf:wrap --skip-feed`. For preventing the start-of-session entry from posting: `SF_SKIP_FEED=1` environment variable.

(ADR-018 for the design; ADR-021 for privacy mechanics.)

---

## 4. Curated stack

The framework explicitly curates which plugins ship. Every plugin earns its slot.

### 4.1 Required at install (six plugins)

| Plugin | License | Why |
|---|---|---|
| Superpowers (obra) | MIT | The development methodology layer. 7-phase workflow (brainstorm → worktree → plan → TDD → subagent → review → finish). Already in Anthropic's official marketplace, 150K+ stars. Powered this entire brainstorming session. |
| Skill Creator (Anthropic) | Apache-2.0 | Skill authoring + Layer 1 description optimizer (the foundation of our two-layer self-improvement, per ADR-012). |
| claude-mem (thedotmack) | Apache-2.0 | Cross-session memory: SQLite + ChromaDB + 3-layer progressive disclosure retrieval. 46K-89K stars; two independent practitioner recommendations. |
| Context Mode (mksglu) | ELv2 | Within-session token efficiency: sandboxes tool output (315 KB → 5.4 KB compression). License caveat: ELv2 restricts SaaS distribution; fine for personal/team use, document if commercializing. |
| context7 (Upstash) | TBD permissive | Version-aware documentation lookup. Solves the "Claude wrote code against an outdated library version" failure mode. Auto-activating with cheap sub-agent on Claude 3.5 Sonnet for docs research. |
| claude-md-management (Anthropic) | TBD permissive | CLAUDE.md quality audit + `/revise-claude-md` (captures session learnings into project CLAUDE.md). Complements `/sf:wrap` at a different layer (CLAUDE.md vs. wiki). 205K installs. |

### 4.2 Conditional (one plugin, asked at onboarding)

- **Frontend Design** (Anthropic): for friend groups building user-facing UIs. Auto-activates for frontend work. Rejects generic AI aesthetics; teaches distinctive typography + color choices.

### 4.3 Documented-not-bundled (one plugin)

- **Ralph / Ralph Wiggum** (Anthropic): the canonical lightweight autonomous-loop pattern. Stop-hook-based session loop. Documented in framework docs; install on-demand if a friend needs overnight autonomous task loops. Not bundled because its Stop hook would compete with claude-mem's lifecycle hooks.

### 4.4 What we explicitly reject

(Per ADR-006 + ADR-023 + ADR-007's provider-vetting principle):

- **ECC (Everything Claude Code)**: studied carefully for inspiration; not adopted because our target scope is smaller and team-focused. Single-maintainer + commercial tier brings sustainability considerations beyond what our friend group needs.
- **GSD Redux**: overlaps Superpowers methodologically; one is enough; chose the one we're already running.
- **MCP Agent Mail**: ADR-018 builds simpler Activity Feed directly; full Agent Mail machinery (FastMCP HTTP server, FTS5 indexing, file reservations) was overkill.
- **Mercury / Proton commercial SaaS**: data leaves friend group's machines; not aligned with privacy.
- **Mem0 / Letta / Zep / LangMem**: framework-agnostic memory systems for custom agent frameworks; wrong scope for our Claude-Code-specific use case.
- **lean-ctx**: kept as documented alternative; not adopted because newer + memory-layer overlap with claude-mem.
- **Framework-level secret scanning** (Aikido / AgentShield): per ADR-021, the Activity Feed's terse format constraint handles privacy; comprehensive scanning is a per-project plugin choice friends make.

### 4.5 Curation principles

Two principles guide every adoption decision (per ADR-006 + ADR-007):

1. **Tool fit**: does it solve a real problem? Does it integrate cleanly with the rest of the stack? Is its license compatible?
2. **Provider trust**: is the maintainer identity known? Is governance legible? Clean history? Aligned incentives? Active maintenance?

The second axis exists because of a documented industry incident: a memory-related plugin (gsd-build/get-shit-done) was abandoned by its governance after a "meme-coin rug-pull" tied to the maintainer. Popularity ≠ safety; provider-vetting is its own check.

If a provider in our adopted stack ever turns adversarial: 2-week response timeline to file a follow-up ADR + migration plan.

---

## 5. Onboarding

A friend installs once. The friend's experience matters as much as anything else in the framework.

### 5.1 The `/sf:install` 7-stage flow

1. **Environment check** — Claude Code 1.0.33+, Node 22.5+, git, `gh` CLI, `claude auth login`, `gh auth status`, `ANTHROPIC_API_KEY`, Upstash key for context7
2. **Required plugin install** — Context Mode → claude-mem → Superpowers → Skill Creator → context7 → claude-md-management (in this order per ADR-010 hook coordination)
3. **Activity Feed + conditional plugins** — shared private GitHub repo URL → clone → identities setup; ask about Frontend Design (UI work); ask about Ralph (documented, not auto-installed)
4. **Identity bootstrap** — `/sf:interview` runs ~17-18 questions across 5 sections (About you / Working style / Tech preferences / Opinions+non-goals / Contribution). Multiple-choice + open-ended mix; writes `wiki/identity.md` locally + public summary to `<activity-feed>/identities/<handle>.md`
5. **Wiki bootstrap** — create master wiki skeleton (research/decisions/alternatives/patterns/projects directories + index.md + log.md) IF doesn't exist; optionally set up remote for backup
6. **`/sf:doctor` verification** — confirms everything works, all keys accessible, hooks registered. Optional sub-step: enable native Claude Code OpenTelemetry (set `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_HEADERS` env vars) for token + session observability
7. **First-session walkthrough** — daily commands tour: `/sf:wake-up`, `/sf:wrap`, `/sf:note`, `/sf:recall`, `/sf:improve-skill`, `/sf:bootstrap-project`, `/sf:catch-up`, `/sf:backup`, `/revise-claude-md` (from claude-md-management — complements `/sf:wrap`)

Target completion: 10 minutes. Friend ready to work.

### 5.2 Joining an existing group

When Friend X joins later (per ADR-020):

- Out-of-band: existing maintainer adds Friend X as collaborator on marketplace repo (read) + Activity Feed repo (write)
- Friend X runs the install commands
- Their `/sf:install` Stage 3 detects an EXISTING Activity Feed (not bootstrap); clones it; adds own `<handle>.log.md` + `identities/<handle>.md`
- Their wiki starts EMPTY (per ADR-017 per-friend-wiki principle — no group history to inherit)
- They catch up via Activity Feed history (`/sf:catch-up` skill summarizes recent activity)

This is dramatically simpler than the original framing (where shared wiki state would have required complex coordination). The friend group's per-friend-wiki design makes joining mechanically the same as first-install.

### 5.3 Leaving the group

When Friend Y leaves (per ADR-020):

- Out-of-band: maintainer removes Friend Y as collaborator on both repos
- `<friend-y-handle>.log.md` stays in the Activity Feed as historical record (other friends can still see what they had been working on)
- `identities/<friend-y-handle>.md` optionally archived to `identities/archived/`
- Friend Y's local install still works on their machine (they own the software); their `/sf:wrap` push fails (no access); optional `/sf:install --remove-activity-feed` to clean up locally

Bus-factor note: GitHub repos should have ≥2 admins (so removing one doesn't kill the group's ability to add new joiners).

---

## 6. The daily loop, in practice

This is the experience a friend actually has, once installed.

### 6.1 Starting a session

Friend opens Claude Code in a project directory:

```
$ cd ~/Dev/sidecar/
$ claude
```

SessionStart hook fires. The framework runs through these steps before the friend's prompt:

- Master wiki index loads
- Sidecar project's sub-wiki: `index.md` + `CONTEXT.md` + recent `log.md`
- Activity Feed pulls latest; reads other friends' recent entries
- Hazar's `<handle>.log.md` gets a new entry: `## [16:30] start | hazar | working in Dev/sidecar/`
- All this is composed into a conversation-layer message friend sees:

```
## Framework wake-up context

### Master wiki index
[brief catalog of master pages]

### Project: sidecar
[brief project index]

[last 10 log.md entries]

### Session pointer (from your last /sf:wrap)
You were working on JWT auth middleware. Open thread: write tests for the 
expired-token edge case. CONTEXT.md last updated 2 days ago.

### Recent friend activity
- Friend B: yesterday — finished landing page copy on Sidecar, touched 
  src/pages/index.tsx + tests
- Friend C: 3 days ago — debugged Restore's onboarding flow

### Recent master log
[last 5 entries]
```

Friend sees what they were doing + what others have been doing. Ready to work.

### 6.2 During the session

Friend asks Claude to "implement the expired-token tests we discussed yesterday."

Behind the scenes:
- Context Mode sandboxes tool outputs (Playwright snapshots, file reads, shell commands) — keeps the conversation context lean
- claude-mem captures the work as compressed observations for cross-session recall
- Superpowers' skills (TDD, code-review, brainstorming) activate based on the conversation
- context7 fetches current Next.js / React docs as relevant
- claude-md-management's `claude-md-improver` skill quietly audits CLAUDE.md if friend updates it

Friend can interject:
- `/sf:note "Important: the JWT secret must rotate weekly per security review"` — pins something for `/sf:wrap` to consider
- `/sf:recall "what did we decide about the auth-flow refresh-token approach?"` — queries the wiki without loading more pages

### 6.3 Ending the session

Friend runs `/sf:wrap`:

1. Reads the session log (CC's record + any `/sf:note` pins)
2. Applies high-signal threshold: was there a real decision, pattern, or lesson? If not, NO wiki edits — most sessions are routine
3. If signal exists: updates relevant wiki pages with diffs shown for approval (similar to `/revise-claude-md`'s pattern)
4. Writes terse Activity Feed entry:
   ```
   ## [18:45] end | hazar | session complete
   
   Worked on Dev/sidecar/ — wrote JWT expired-token tests and fixed off-by-one 
   in token validation. Touched: tests/test_auth.py, api/auth.py.
   ```
5. Git commits + pushes Activity Feed entry
6. Updates `CONTEXT.md` with the session pointer for next time
7. Returns a brief summary

Session ends. Claude Code exits. Next session, the loop closes — wake-up reads the session pointer; friend picks up where they left off.

### 6.4 Skill self-improvement

When friend authors a custom skill (using Skill Creator), they get a `SKILL.md` + references + eval.json scaffolding. Over time, the skill drifts from optimal as Claude evolves or use patterns shift.

Friend runs `/sf:improve-skill <skill-name>`:

- Interactive mode: reads SKILL.md + eval/eval.json, proposes one change at a time, friend approves, framework applies, runs tests, keeps or reverts based on score
- Autonomous mode (`--autonomous --max-iterations 10 --max-turns 50 --max-budget-usd 5.00`): runs overnight, never asks the human, bounded by all four safety primitives

This is the Karpathy auto-research pattern. Binary assertions in eval.json are the scoring primitive. Git is the memory; revert via `git reset`.

(See ADR-012 for the design + safety primitives.)

### 6.5 Cross-friend visibility

Friend opens session next morning. Wake-up shows:

```
### Recent friend activity
- Friend B: 2 hours ago — finished landing page conversion tests on Sidecar
- Friend C: yesterday — bootstrapped new project: era-test-app
```

Friend can ping Friend B on WhatsApp ("How'd the conversion tests go?") or just continue their own work knowing Friend B is mid-flight on the related area. No surprise PRs colliding.

For joining a new project mid-flight, friend runs `/sf:catch-up sidecar` and gets a summary of the past month's Sidecar activity from across the friend group.

---

## 7. Evolution

The framework evolves; friends shouldn't bear the cost.

### 7.1 Versioning + release cadence

Per ADR-019:

- Semantic versioning: MAJOR.MINOR.PATCH
- **Monthly stable releases.** Friends pin to specific versions; opt-in updates via `/sf:update`.
- Pre-release `-rc.N` versions for breaking changes: maintainer (Hazar) dogfoods for ~1 week before promoting to stable.

### 7.2 Backwards compatibility commitment

Per ADR-017 + ADR-027:

- Wiki page schemas evolve per page type (independently versioned)
- Schema version N readable through versions N+1, N+2, N+3 (deprecation window)
- Migrations: scripted for mechanical changes, LLM-driven for semantic; always shown as diff before applying; pre-migration snapshot retained
- `/sf:doctor` surfaces schema drift; `/sf:update` runs migrations

Concretely: if v1.3 introduces a new `phase` field in identity.md, friends running v1.0 wikis see a diff offered when they `/sf:update`: "Migration: identity.md 1 → 2. Adds new field: phase. Default: ideation. Approve? [a/s/e/r]" — they approve, the file gets the new field, framework moves on. No friend left behind.

### 7.3 Update notification

`/sf:doctor` queries the marketplace repo for the latest version. If friend is behind:

```
⚠️  Framework update available: v1.3.0 (you have v1.2.1)
    Run /sf:update to install. See CHANGELOG for what's new.
```

Plus: the maintainer posts a `release` entry in their own Activity Feed `<handle>.log.md` when a version ships. Friends' next session-start wake-up surfaces it.

### 7.4 Plugin updates

External plugins (Superpowers, claude-mem, etc.) update via Claude Code's standard `/plugin update`. The framework's version pinning per ADR-006 / ADR-015 means we control when plugins move — not auto-update on every restart.

If a plugin in our stack becomes unmaintained or has a security incident, ADR-007's 2-week response timeline kicks in: investigate, decide (replace / fork / accept risk), document.

---

## 8. V1 scope: what's in, what's out, what's deferred

(Consolidated from ADR-023; this is the explicit fence.)

### 8.1 IN v1

The framework ships:

- 6 required plugins + 1 conditional + 1 documented-not-bundled (per §4)
- Built-in features: wake-up hook (`/sf:wake-up`), consolidate (`/sf:wrap`), Activity Feed, identity-interview (`/sf:interview`), self-improvement (`/sf:improve-skill`), onboarding (`/sf:install`), doctor (`/sf:doctor`), project bootstrap (`/sf:bootstrap-project`), update mechanism (`/sf:update`), catch-up (`/sf:catch-up`), backup (`/sf:backup`), companion commands (`/sf:note`, `/sf:recall`, `/sf:disable-feed`)
- Per-friend hierarchical wiki + per-project sub-wikis
- GitHub-based distribution (private marketplace repo + Activity Feed repo)
- Native Claude Code OpenTelemetry support (optional onboarding step)
- Backwards-compatibility commitment with schema migrations
- Provider-vetting curation principle

### 8.2 OUT of v1

Explicit non-goals, deferred to V2+ or never:

- Shared wiki across friends (wikis are per-friend-local; cross-friend communication is the Activity Feed only)
- MCP Agent Mail, Mercury/Proton, framework-level secret scanning, anchor-tag manifests, automated harness optimization
- ECC, GSD Redux, Mem0/Letta/Zep/LangMem, lean-ctx as adopted plugins (each documented elsewhere)
- Daemons at the framework's own layer (plugins may have their own; we don't)
- Diff-review default for `/sf:wrap` (terse format constraint handles it)
- Auto-update; daily release cadence
- Cross-LLM portability beyond what's free (Claude-Code-only in v1; content is portable markdown)
- Internationalization

### 8.3 Deferred (V2+ candidates, documented but not committed)

- Master wiki aggregator (Vercel dashboard reading from friends' GitHub-published wikis) — ADR-017 Direction A
- Shared knowledge database (Supabase-backed; explicit push/pull) — ADR-017 Direction B
- qmd as wiki search at scale (ADR-005 triggers)
- `/sf:audit-stack`, `/sf:wrap-checkpoint`, `/sf:lint-skills`, `/sf:tidy`, `/sf:scrub-feed`, `/sf:rollback`
- Skill sharing mechanism between friends
- Differentiated roles, friend-group-bot for automating collaborator invites
- Knowledge-graph layer + automated harness optimization

---

## 9. Key design principles

What the framework is built around (extracted from the ADRs):

**Token efficiency as north star** — every design decision checked against this. We exist because off-the-shelf tools waste tokens.

**Per-friend local, share by action** — friend's wiki stays on their machine. Cross-friend communication is the Activity Feed, deliberately terse, opt-out per session. Nothing leaks without action.

**Curation > kitchen-sink** — every plugin earns its slot. Generic plugins like ECC are rejected for our specific use case (smaller scope, team-focused). The framework's value is what it leaves out.

**Files + Claude Code configurations, no daemons at our layer** — plugins we recommend may have their own daemons (claude-mem's worker on port 37777); the framework itself adds zero. Auditable + cross-platform + cheap to rewrite when models evolve.

**Backwards-compatibility commitment** — friends shouldn't lose work because the framework moved. Schema-versioned migrations, deprecation windows, snapshots before any breaking change.

**Provider vetting** — curation extends to maintainers, not just tools. The meme-coin rug-pull incident showed popularity ≠ safety; we vet identity + governance + history + incentives + maintenance signal.

**Lightweight harness thesis** — Ralph's documented successes ($50K contract for $297) prove lightweight works. PY's research: "mature harness work looks less like building structure up and more like pruning it down." We're skeptical of complexity; we cut where we can.

**Format constraint as privacy** — the terse Activity Feed entries (couple sentences, only project + task + files) prevent most accidental leakage. Per ADR-021: trust the format, not safety nets like diff-review-by-default.

**Discipline narrowing > expensive broadening** — PY's empirical finding: self-evolution (acceptance-gated attempt loops) is the only consistently-helpful module. The Karpathy loop's "one change per iteration; revert if score drops" is the operational form. Adopted in `/sf:improve-skill`.

---

## 10. What's next

This design doc closes the brainstorming phase. The next phase is **writing-plans**: synthesize this design into an actionable implementation plan with file paths, task ordering, and milestones.

After that: **build via TDD** (per Superpowers' methodology). Each component gets eval.json binary assertions; we author tests first, implement to pass, refactor.

Then: **dogfood**. Hazar installs his own framework end-to-end. Friends try it on his guidance. Feedback drives v1.1.

Then: **ship to friends**. Add them as marketplace collaborators. Walk them through `/sf:install`. Observe what surprises them.

Then: **let the wiki grow**. The framework becomes whatever the friend group's accumulated wisdom shapes it into.

The framework is small enough to throw away. PY's harness research showed Manus rewrote their harness 5× in 6 months — assumptions expire as models improve. We commit to that pattern: when Claude evolves past a feature we built, we cut the feature.

---

## Appendices

### A. Cross-reference: design section → ADRs

| §  | Topic | ADRs |
|---|---|---|
| 2 | What it is | 001, 006, 023 |
| 3.1 | Four-repo distinction | 017, 019, 020 |
| 3.2 | Memory architecture | 002, 004, 005 |
| 3.3 | Wiki structure | 004, 011, 014, 017 |
| 3.4 | Daily loop | 008, 009, 010, 018, 021 |
| 3.5 | Skills + self-improvement | 011, 012, 022 |
| 3.6 | Distribution + updates | 019, 027 |
| 3.7 | Activity Feed | 018, 021 |
| 4 | Curated stack | 006, 007, 023 |
| 5 | Onboarding | 015, 020, 022, 025 |
| 6 | Daily loop | 008, 009, 018 |
| 7 | Evolution | 017, 019, 026, 027 |
| 8 | V1 scope | 023 |
| 9 | Design principles | all |

### B. Cross-reference: ADR → underlying research

The framework's 27 ADRs are grounded in 25 research pages (transcripts + plugin surveys + ecosystem comparisons). See `wiki/research/` for the evidence base.

Key sources:
- **Karpathy LLM Wiki pattern**: ADR-004, ADR-017
- **PY harness engineering research**: ADR-006, ADR-012 (self-evolution as only consistently-helpful module)
- **Simon Scrapes Agentic OS series**: ADR-002, ADR-008, ADR-009, ADR-011, ADR-012, ADR-022
- **Caleb harness loops primitive**: ADR-008, ADR-009
- **Prompt Engineering 9-component reference**: ADR-001, ADR-008, ADR-010
- **Nate Herk's curated stack**: ADR-002, ADR-006
- **ECC research (course-correction ingest)**: ADR-006 amendment, ADR-007
- **Anthropic marketplace catalog**: ADR-006, ADR-015, ADR-019
- **Cross-validation: Claude Code official docs**: confirmed ADR-008's cache constraint, ADR-019's marketplace pattern, ADR-012's safety primitives

### C. Open implementation-phase questions

Aggregated from the ADRs (not blockers for the design; settled during writing-plans + implementation):

- Wiki path convention: `~/.claude/startup-framework/wiki/` vs. `~/.startup-framework/wiki/` (lean toward the former, per CC conventions)
- `AskUserQuestion`'s 4-option cap on multi-select: some `/sf:interview` questions need pagination
- Tarball backup retention policy (latest N? rolling?)
- `/sf:doctor` nag thresholds (warning vs. strong nag for missing backup remote)
- LLM-driven migration verification semantics (what if assertions pass for SOME pages but not others?)
- Hook-ordering verification: claude-mem + Context Mode + our hooks running together — exact ordering in practice
- Where the framework's repo lives initially (Hazar's GitHub or dedicated friend-group org)
- Friend-group-bot for automating GitHub collaborator invites (v2 idea, flagged)

### D. The framework, in one paragraph

If you read nothing else: the framework is a private Claude Code plugin a friend group installs once. It curates 6 plugins for token efficiency + cross-session memory + skill quality. It adds a personal wiki that grows with the friend's work, an opt-in cross-friend activity feed for visibility on parallel work, and a self-improvement loop for the custom skills the friend group authors. It's lightweight (no daemons), backwards-compatible (schema migrations on update), privacy-first (per-friend local wikis; terse activity feed entries), and small enough to throw away when models evolve past it. It assumes Claude Code; it doesn't assume Cursor or Gemini. It's MIT-licensed. It ships monthly stable releases. It's `/sf:install` from a private GitHub marketplace.

The goal: the friend group spends more time building startup ideas, less time fighting their tools.
