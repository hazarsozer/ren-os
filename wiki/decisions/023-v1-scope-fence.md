---
title: "ADR-023: V1 Scope Fence — What's IN, What's OUT, What's V2+"
status: accepted
amended-by:
  - "ADR-031 (2026-05-30, solo-first pivot): the Activity Feed is no longer a built-in v1 feature — it is a deferred layer (preserved in git history + the baseline-v1.0-full-wiki tag). AMENDED, not superseded — the rest of the v1 fence stands."
date: 2026-05-28
sunset-review: 2026-08-28
references-pages: all
affects-components: all
relates-to: all-prior-adrs
note: This is a consolidation ADR. It re-states (with cross-references) the boundary already established by ADRs 001-022 + their amendments, into one explicit list. No new decisions; this is the fence in one place.
---

# ADR-023: V1 Scope Fence — What's IN, What's OUT, What's V2+

> 📝 **Amended by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** Solo-first: the Activity Feed moves from "IN for v1" to a deferred layer. The rest of the fence stands.

## Context

After 22 prior ADRs, the v1 boundary is implicit in dozens of scope decisions scattered across them. New contributors (or future-us) might miss what's deliberately deferred vs. what's accidentally missing. This ADR consolidates the boundary into a single explicit list.

This ADR makes no new decisions. Everything below is already settled in prior ADRs; this is a map.

## Decision: the explicit scope fence

### IN v1 (the framework ships these)

**Required-install plugins** (per ADR-006 + amendments):
- Superpowers (obra/superpowers, MIT) — development methodology
- Skill Creator (anthropics/skills, Apache-2.0) — skill authoring + Layer 1 self-improvement
- claude-mem (thedotmack/claude-mem, Apache-2.0) — cross-session memory
- Context Mode (mksglu/context-mode, ELv2) — within-session token efficiency
- context7 (upstash/context7) — version-aware documentation lookup
- claude-md-management (Anthropic) — CLAUDE.md quality + session learning capture

**Conditional-install plugins** (asked at onboarding):
- Frontend Design (Anthropic) — if friend group builds UIs

**Documented, not bundled** (friends install on demand):
- Ralph / Ralph Wiggum (Anthropic) — autonomous loop pattern

**Framework's own built-in components**:
- Wake-up hook (ADR-008) — SessionStart, conversation-layer injection, cwd-aware loading of master index + project index + log tail + session pointer
- Consolidate skill / `/sf:wrap` (ADR-009) — high-signal-threshold wiki promotion
- Activity Feed (ADR-018) — built-in shared GitHub repo + per-friend log files + SessionStart and `/sf:wrap` hook extensions
- Identity-interview / `/sf:interview` (ADR-022) — AI-driven onboarding
- Two-layer self-improvement (ADR-012) — `/sf:improve-skill` Karpathy-loop on top of Skill Creator's description optimizer
- Onboarding / `/sf:install` (ADR-015) — 7-stage flow including activity feed setup + OTel option
- Doctor / `/sf:doctor` (ADR-010 + ADR-015) — environment + plugin verification + update notification
- Project bootstrap / `/sf:bootstrap-project` (ADR-014 + ADR-015) — creates per-project sub-wiki skeleton
- Update mechanism / `/sf:update` (ADR-019) — opt-in version bump with migrations
- Catch-up / `/sf:catch-up` (ADR-020) — Activity-Feed-history summarizer for joiners
- Note / Recall / Skip-feed companions (`/sf:note`, `/sf:recall`, `/sf:disable-feed`)

**Wiki structure** (per ADR-004 + ADR-014 + ADR-017):
- Per-friend local wiki
- Hierarchical: master + project sub-wikis under `wiki/projects/<project>/`
- Page format conventions: YAML frontmatter + markdown body, log.md chronological invariant, index.md catalog
- Project sub-wiki taxonomy: PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, CONTEXT.md

**Distribution + updates** (per ADR-019):
- Private GitHub marketplace repo (Hazar's GitHub or friend-group org)
- Standard `/plugin marketplace add` + `/plugin install` UX
- Semver + monthly stable releases
- Update notifications via `/sf:doctor` + Activity Feed
- Backwards-compatibility commitment with schema migrations (mechanics in ADR-027)

**Observability** (per ADR-015 amendment + ADR-021):
- Native Claude Code OpenTelemetry support documented in onboarding (optional Stage 6 step)
- No new framework-level plugin; friends point at any OTLP backend they choose

**Curation principles** (per ADR-006 + ADR-007):
- Six required plugins, deliberate set; not kitchen-sink
- Provider-vetting (identity + governance + history + incentives + maintenance) as adoption criterion

### OUT of v1 (explicit non-goals)

The following are NOT in v1. Each was considered, discussed, and explicitly deferred or rejected:

**Architecture-level outs:**
- ❌ Shared wiki across friends — per ADR-017, wikis are per-friend-local
- ❌ Multi-author wiki conventions — moot per ADR-017 (no multi-author scenario in v1)
- ❌ Skill sharing between friends — not bundled; manual file transfer if needed
- ❌ Daemons at the framework layer — per ADR-003 (plugins may have their own; we don't)
- ❌ Coordinator process for hook ordering — per ADR-003 and ADR-010

**Plugin-level outs:**
- ❌ ECC (Everything Claude Code) — per ADR-006 amendment, studied for inspiration, didn't adopt
- ❌ GSD Redux — per ADR-006, overlaps Superpowers
- ❌ MCP Agent Mail — per ADR-018, our Activity Feed (built-in) replaces it
- ❌ Mercury/Proton MCP — per team-coordination survey, commercial SaaS not aligned with privacy
- ❌ Mem0 / Letta / Zep / LangMem — per ADR-002 + memory-architecture-alternatives, wrong scope
- ❌ lean-ctx — per ADR-002 amendment, kept as alternative-documented but not adopted
- ❌ qmd at v1 — per ADR-005, v2 upgrade path when index.md scales out
- ❌ Aikido / ECC AgentShield / framework-level secret scanning — per ADR-021, format constraint handles privacy; recommended only as optional per-project add-ons
- ❌ Mercury or other commercial SaaS for team coord — per ADR-018, GitHub-repo-based approach instead

**Feature-level outs:**
- ❌ Scheduled / autonomous workflows beyond Ralph — Ralph documented but not bundled
- ❌ Anchor-tag manifests for large codebases — per ADR-006 + Ben Fellows research, useful at scale, not v1
- ❌ Automated harness optimization (Meta-Harness style) — raw traces preserved (per ADR-002) to enable it later; no implementation in v1
- ❌ Master wiki aggregator (Vercel dashboard) — per ADR-017 Direction A, v2+ idea
- ❌ Shared knowledge DB (Supabase-backed) — per ADR-017 Direction B, v2+ idea
- ❌ Diff-review default for `/sf:wrap` — per ADR-021, terse format constraint does the work
- ❌ Mechanical phase-toggling for Superpowers skills — per ADR-022, soft signal not mechanical
- ❌ Internationalization (i18n) — English-only in v1; per ADR-022 open question

**Tech-stack outs:**
- ❌ Non-GitHub distribution — per ADR-019, marketplace + Activity Feed both on GitHub
- ❌ Auto-update on session start — per ADR-019, opt-in via `/sf:update`
- ❌ Daily release cadence — per ADR-019, monthly stable

### V2+ (deferred, logged for future)

These are documented in their source ADRs as future directions:

**Aggregation / multi-friend** (per ADR-017):
- Master wiki aggregator dashboard (Vercel-hosted, reads from friends' GitHub-published wikis)
- Shared knowledge database (Supabase-backed, explicit push/pull)

**Memory layer evolution**:
- qmd adoption when wiki scales past 200 entries (ADR-005 triggers)
- lean-ctx swap if ELv2 license becomes a friction point (ADR-002 sunset triggers)
- claude-mem alternative if unmaintained (ADR-002 sunset triggers)

**Skills + utilities**:
- `/sf:audit-stack` — ecosystem-level provider/plugin auditing (per ADR-007 alternative D)
- `/sf:wrap-checkpoint` — mid-Ralph-loop wraps (per ADR-010 + ADR-018)
- `/sf:lint-skills` — formal JSON-Schema validation for skill files (per ADR-011 alternative B)
- `/sf:scrub-feed <commit>` — coordinated Activity Feed deletion (per ADR-021 open question)
- Anchor-tag skill if a friend's codebase grows past need-threshold (per ADR-006 Ben Fellows reference)
- Skills sharing channel (built into Activity Feed or a dedicated mechanism)

**Scaling / governance**:
- Differentiated roles (maintainer / member / observer) if friend group grows
- Friend-group-bot automating GitHub collaborator invites (per ADR-020 open question)
- i18n for non-English friends

**Harness engineering exploration**:
- Automated harness optimization (Meta-Harness style; raw traces are preserved per ADR-002)
- Knowledge graph + temporal validity layer (Zep-adjacent; per memory-architecture-alternatives v3 idea)

### What this ADR does NOT do

- Does not enumerate every decision (those are in their source ADRs)
- Does not freeze v1 (we can amend if discussion changes)
- Does not promise v2+ items will ship (those are *if-needed* directions, not commitments)
- Does not constrain user (friends can install whatever else they want; this is the FRAMEWORK's scope, not the friend's machine)

## Consequences

**Easier:**
- New contributors / future-us can read this ADR and understand v1 scope in 5 minutes
- Scope creep is now visible — if someone proposes a new feature, check if it's in OUT or V2+; if so, requires explicit ADR amendment to add
- The "what's the framework for, anyway?" question has a clear answer
- Writing the design doc (next step in the brainstorming flow) becomes substantially easier since the scope is consolidated

**Harder:**
- This ADR must be kept in sync with the underlying ADRs (it's a cache; can go stale)
- Every amendment to any prior ADR potentially requires updating this one too
- Risk of becoming the "real" source of truth (it shouldn't — the source ADRs are; this is a map)

**Now impossible:**
- Quietly slipping a feature into v1 without crossing this fence

**Sunset review trigger conditions:**
- The fence becomes stale (count of "OUT" items that have since shipped, or "IN" items that have been removed)
- v2 work begins → this ADR is forked into a v2 scope fence
- A new contributor reads this and is misled → cross-references need fixing

## Alternatives considered

### A) No consolidation ADR; trust people to read all 22

**Considered shape**: Each ADR's scope decisions stand alone; no synthesis.

**Why rejected**: At 22+ ADRs (and growing) it's unrealistic to expect anyone to grep through them all to figure out scope. The consolidation ADR is small effort + big readability win.

### B) Make the consolidation ADR the primary source of truth

**Considered shape**: This ADR becomes the canonical decisions document; the others are details.

**Why rejected**: That inverts the right model. The source ADRs have full rationale, alternatives, and trade-offs. This ADR is a map. Maps without territories rot.

### C) Hide deferred-to-v2 items

**Considered shape**: Only list IN + OUT; don't enumerate v2+ ideas (those are speculation).

**Why rejected per user direction in earlier discussions**: documenting v2+ ideas honors the work of considering them and gives future-us a clean re-entry point. Hiding speculation hurts later when "did we ever think about X?" arises.

## References

This ADR consolidates from all prior ADRs (001-022) and their amendments. Cross-reference the source ADRs for full rationale on any specific decision.

- ADR-001 through ADR-022 — source decisions
- All amendments dated 2026-05-28
- All research pages (`wiki/research/`) — evidence base
