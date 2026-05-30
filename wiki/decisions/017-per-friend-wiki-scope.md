---
title: "ADR-017: Per-Friend Wiki Scope — Local, Not Shared (Framework Provides Skeleton, Not Content)"
status: superseded
superseded-by: "ADR-031 (2026-05-30): solo-first pivot — Activity Feed / multi-user layer removed from the shipped framework"
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [llm-wiki-pattern, simon-scrapes-agentic-os, team-coordination-survey]
affects-components: [memory, wiki, install, distribution, sharing, backwards-compatibility]
relates-to: [002-token-efficiency-stack, 004-wiki-design-hierarchical, 014-project-sub-wiki-taxonomy, 015-onboarding, 018-agent-mail-messaging, 019-framework-distribution, 027-schema-versioning]
---

# ADR-017: Per-Friend Wiki Scope — Local, Not Shared

> ⚠️ **SUPERSEDED by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** The solo-first pivot removed the Activity Feed / multi-user sharing layer from the shipped framework. This ADR describes the pre-pivot per-friend *sharing* posture; the local-wiki principle survives, but the cross-friend framing no longer reflects the shipped framework. Preserved for history (and in the `baseline-v1.0-full-wiki` tag).

## Context

The earlier ADRs (002, 004, 014, 015) were filed under an implicit assumption — never stated explicitly — that the wiki might be a shared team artifact. The 2026-05-28 framing amendments corrected that across all five files. This ADR makes the per-friend wiki scope EXPLICIT as a load-bearing decision, so future contributors and future ADRs can build on solid ground.

A second clarification surfaced during the same discussion: **the wiki we've been building at `/home/hsozer/Dev/startup-framework/wiki/` is OUR (framework developers') design artifact — not what ships in the plugin.** When a friend installs the framework, they get a fresh wiki SKELETON (structure + templates), not our content. Our 16 ADRs + 25 research pages stay in the framework's development repo; they're how WE designed the framework, not what users inherit.

Without this ADR, future contributors might:
- Assume friends share a wiki and design new features around shared state
- Ship our development wiki inside the plugin (contaminating users with our design history)
- Try to build sharing infrastructure that conflicts with the local-only design

## Decision

### Core: the wiki is per-friend-local

Every wiki the framework helps a friend create or maintain is:

1. **Local to that friend's machine.** Lives on their disk; the framework writes to no other location by default.
2. **Private by default.** No automatic sync, no automatic upload, no automatic sharing.
3. **Owned by the friend.** They can do whatever they want with it (push to private GitHub, sync across their devices, share excerpts manually). Framework provides tooling, not policy.

The framework does NOT:
- Auto-share a friend's wiki with other friends
- Send wiki content over any network without explicit user action
- Assume any shared state across the friend group

### Critical distinction: framework dev wiki ≠ plugin's wiki

**Two separate wikis exist in the framework's lifecycle:**

| Layer | Purpose | Lives in | Ships in plugin? |
|---|---|---|---|
| **Framework's development wiki** | Our (framework developers') design history — ADRs, research, decisions, log of how we built it | `/home/hsozer/Dev/startup-framework/wiki/` (this repo) | **NO** — stays in our dev repo |
| **Plugin's wiki skeleton template** | Empty structure + page format templates that get instantiated on user install | Inside plugin source (when we build it, likely `plugin/skills/wiki-bootstrap/templates/`) | **YES** — ships as part of the plugin |
| **Friend's installed wiki** | The friend's actual personal wiki, populated through their own use | On the friend's machine post-install (e.g., `~/.<framework>/wiki/` or `~/.claude/<framework>/wiki/` — exact path settled in implementation phase) | N/A — created on install |

The plugin's `/sf:install` runs, the friend's wiki gets created from the skeleton, and from that moment forward the friend's wiki grows independently. Our design history stays in our dev repo; friends' wikis grow from empty per-friend.

This means: **none of our 16 ADRs + 25 research pages are inherited by users.** They are ours, not theirs. Each friend builds their own design history (if they want one) through their own work.

### Self-sync across one friend's own devices is allowed (and supported with guidance)

A friend with multiple devices (e.g., the user's CLAUDE.md notes desktop + MacBook Air) can self-sync their own wiki via:
- Private git remote (e.g., GitHub private repo)
- Syncthing or similar local sync
- iCloud / Dropbox / etc. on the wiki directory

Framework provides:
- Documentation in onboarding (ADR-015) describing the self-sync pattern with `git remote` as the recommended default
- No automatic syncing or auto-commit — the friend manages their own remote

Framework does NOT provide:
- Built-in sync daemons (per ADR-003 no-daemon rule)
- Automatic push hooks
- A managed sync service

### Friend-to-friend sharing is user-DIY and out of framework v1 scope

Friends can manually share wiki content with each other if they want — copy a markdown file, send it via Agent Mail (ADR-018), commit to a shared "studio decisions" repo on GitHub. Framework provides:
- Plain markdown format (easy to copy/paste/email)
- Git-friendly structure (easy to fork/merge)
- Optional Agent Mail messaging layer (per ADR-018) for cross-Claude communication

Framework does NOT provide (in v1):
- Aggregator services
- Master dashboards across friends' wikis
- Cross-friend wiki indexing
- Shared knowledge databases

### Future v2+ aggregation directions (documented, not committed)

The user surfaced two possible future aggregation patterns worth documenting:

**Direction A: Aggregator dashboard**
- Each friend opts to push their wiki to a private GitHub repo
- A separate aggregator service (Vercel-hosted, read-only) ingests all consented friend wikis
- Produces a unified "studio dashboard" view — what everyone's working on, decisions across the group, patterns in common
- Read-only; each friend's source-of-truth wiki stays on their machine

**Direction B: Shared knowledge database**
- A small shared knowledge store (e.g., Supabase-backed, already in user's global MCP)
- Friends explicitly push selected files to the shared store ("share this decision with the group")
- Friends explicitly pull from it ("get the latest shared patterns")
- Write/read is opt-in per file, per direction

Both are V2+ ideas. Each fundamentally preserves "wiki is local; sharing is explicit." Neither is committed for v1. **Decision**: v1 ships local-only; aggregator/shared-DB are filed as future directions to consider when the friend group asks for them.

### Backwards compatibility requirement (the new principle)

Plugin updates MUST NOT break existing wikis from earlier framework versions. The user stated this as: "if the framework is not broken, it's not an issue. It might shape with the user preferences. If it breaks, we will need to update. So it should support backwards, and put fixes while moving forward."

Concretely:

1. **Wiki schema changes are versioned.** Each wiki page's frontmatter includes a `framework_version` or `schema_version` field. New framework versions know how to read older schemas.

2. **Breaking changes require migration.** When the framework version bumps in a way that changes wiki schema, `/sf:install` (or a separate `/sf:migrate-wiki` command) walks the friend's existing wiki and migrates pages to the new schema. Old pages stay readable; new fields added with sensible defaults.

3. **Deprecation period.** A field marked deprecated in framework version N stays readable through versions N+1 and N+2; only removed in N+3 (or later). Friends have time to migrate.

4. **No silent overwrites.** Migrations show diffs and require user approval (mirrors `/revise-claude-md`'s pattern).

5. **Schema versioning ADR (forthcoming, ADR-027)** owns the detailed mechanics. This ADR commits to the principle: forward motion, backwards-compatible reads, explicit migrations for breakage.

## Consequences

**Easier:**
- The mental model is dead simple: "your wiki, your machine, your business"
- No multi-author conflict resolution to design
- No shared infrastructure to maintain
- Privacy is automatic (local = private)
- Friends switch jobs, leave the group, change preferences — none of it affects the others' wikis
- Backwards compatibility forces deliberate framework versioning — good discipline

**Harder:**
- Cross-friend knowledge sharing is manual (until v2 aggregator/DB if we ever build them) — friends have to talk to share
- Each friend reinvents their own wiki conventions over time (drift from the framework's defaults is allowed and not policed at v1)
- The framework can't easily learn from aggregated friend usage (privacy preserved, but we lose feedback signal)
- Self-sync friction for users with multiple devices (one-time setup; framework provides guidance)

**Now impossible:**
- A friend's wiki accidentally being readable by another friend without their action
- The framework imposing knowledge from our design history onto users (they start fresh)
- Hidden shared state that surprises someone later

**Sunset review trigger conditions:**
- Friend group asks for aggregation features (Direction A or B becomes a real ADR)
- Sharing friction creates pain that DIY mechanisms can't solve
- Backwards-compatibility commitments become a meaningful constraint on framework evolution

## Alternatives considered

### A) Shared wiki across the friend group

**Considered shape**: One wiki repo all friends contribute to via git; multi-author conventions for `log.md`; file-reservation tooling.

**Why rejected**: This was the framing we initially had and corrected on 2026-05-28. The friend group works asynchronously, on different projects, with their own context. Shared state forces coordination that doesn't reflect how the friend group actually operates. Per the user: "The wiki is the memory layer for the machine itself only so you don't forget important context."

### B) Per-friend wiki, but ship our development wiki as starting content

**Considered shape**: Each friend's wiki gets initialized with our 16 ADRs + 25 research pages on install, so they have rich context immediately.

**Why rejected**: Per user clarification — the framework's development wiki is OUR design history, not user-facing content. Shipping it would (a) bias each friend's wiki with our biases, (b) clutter their memory with information they didn't choose, (c) confuse "I wrote this" vs. "the framework gave me this." Friends should grow their own wiki.

### C) Per-friend local, with optional aggregator built into v1

**Considered shape**: Ship the local-only design but include a Vercel aggregator or Supabase-backed shared DB in v1 onboarding as a conditional feature.

**Why rejected for v1**: Premature. Friend group isn't using the framework yet; we don't know if aggregation actually solves a real problem. Adding infrastructure speculatively violates v1 scope. Documented as Direction A / Direction B for v2+; revisit when the friend group asks.

### D) Hybrid — framework dev wiki ships as a "reference library" inside the plugin (not auto-loaded)

**Considered shape**: Ship our research pages as plugin-bundled reference docs that friends can browse but aren't part of their personal wiki.

**Why rejected**: Adds size and confusion. If friends want to read our design rationale, they can read our public docs (when we publish them) or the framework's git repo directly. Doesn't need to ship inside the plugin.

## References

- `wiki/research/llm-wiki-pattern.md` — Karpathy's per-user wiki pattern; explicitly individual scope
- `wiki/research/simon-scrapes-agentic-os.md` — Agentic OS as a personal context-management layer
- `wiki/research/team-coordination-survey.md` — the team-coord framing correction; Agent Mail is messaging not shared state
- ADR-002 (Token-Efficiency Stack) — memory architecture map corrected with this scope
- ADR-004 (Hierarchical Wiki) — corrected per this scope
- ADR-014 (Project Sub-Wiki Taxonomy) — corrected per this scope
- ADR-015 (Onboarding) — corrected per this scope (identity is single file, no shared people/)
- ADR-018 (forthcoming) — Agent Mail inter-Claude messaging (the right place for friend-to-friend communication)
- ADR-019 (forthcoming) — Framework distribution and updates (covers v1 plugin distribution + backwards-compat mechanics)
- ADR-027 (forthcoming) — Schema versioning (detailed mechanics for backwards compatibility this ADR commits to in principle)
