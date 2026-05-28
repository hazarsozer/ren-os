---
title: "Anthropic Plugins Marketplace Catalog (Aerial View)"
type: research
source_url: https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json
source_fetched: 2026-05-28
ingested: 2026-05-28
tags: [anthropic-marketplace, ecosystem-survey, aerial-view, foreground-research]
status: ingested
related: [awesome-claude-skills-survey, ecc-everything-claude-code, superpowers, skill-creator, frontend-design]
note: |
  Meta-survey of the official Anthropic plugins marketplace (2721 lines, ~100+
  plugins). We extracted the first 73. Most are domain-specific (AWS/Azure/db/CRM);
  a few are framework-level and worth knowing about. Confirms our curated stack's
  scope is at a different layer than most marketplace entries.
---

# Anthropic Plugins Marketplace Catalog (Aerial View)

## TL;DR

Anthropic's official marketplace has **~100+ plugins** (marketplace.json is 2721 lines). We extracted 73 to scan the landscape. **Most plugins are domain-specific** (cloud providers, databases, CRMs, productivity tools) — not architecturally relevant to our framework's harness-level scope. **A few framework-relevant plugins** worth knowing: `claude-md-management`, `dash0` (token observability), `context7` (docs lookup), `code-review`. Confirms our framework's curation operates at a **different layer than most marketplace entries** — we're not competing with these plugins; we provide a curated subset + a team-knowledge layer.

## Scope

- **2721-line marketplace.json file** (113 KB)
- Schema: `https://anthropic.com/claude-code/marketplace.schema.json`
- Owner: Anthropic (support@anthropic.com)
- Total plugins: ~100+ (we extracted 73)
- Source distribution: ~30 Git subdir, ~35 URL, ~8 local path
- Some marked "community-managed" (atomic-agents, context7)

## Category distribution (from the 73 we extracted)

| Category | Count | Examples |
|---|---|---|
| Development | ~25 | agent-sdk-dev, aws-dev-toolkit, apollo-skills, appwrite, base44 |
| Database | ~15 | airtable, cockroachdb, clickhouse, convex, alloydb |
| Productivity | ~15 | asana, atlassian, box, claude-md-management |
| Deployment | 5 | azure, cloudflare, deploy-on-aws |
| Security | 5 | 42crunch, aikido, auth0, crowdstrike-falcon-foundry |
| Monitoring | 4 | amplitude, dash0, datadog |
| Design | 1 | adobe-for-creativity |
| Location | 1 | amazon-location-service |

## Plugins specifically relevant to our framework

These are architectural/framework-level (not pure domain plugins):

### 1. `claude-md-management` — CLAUDE.md maintenance + quality auditing

**Worth investigating.** Our framework manages CLAUDE.md per-project hierarchy (per ADR-014 + Claude Code's native inheritance). This plugin specifically focuses on CLAUDE.md hygiene. Potential overlap or complement.

### 2. `dash0` — OpenTelemetry-based AI observability

**Worth investigating.** Captures traces, token usage, monitoring data via OpenTelemetry. Could substitute for Nate Herk's separate token dashboard (referenced in ADR-015). Especially relevant given our token-efficiency north star.

### 3. `context7` — version-specific documentation lookup

**We should have known about this** earlier — Karpathy and others reference it tangentially. Provides AI agents with version-specific docs via Upstash. Almost mandatory for any framework that does dependency-aware coding.

### 4. `code-review` — automated PR review with specialized agents

Built-in `/re` and `/ultrareview` cover code review. This plugin layers in confidence scoring. Possibly overlapping/redundant with Anthropic's built-in review commands but worth tracking.

### 5. `code-modernization` — legacy codebase modernization

Less relevant for our friend group (new projects, not legacy modernization). Note its existence.

### 6. `commit-commands` — git commit/push/PR workflows

Likely overlaps with Superpowers' `using-git-worktrees` + `finishing-a-development-branch`. Choose one set; don't double up.

### 7. `agent-sdk-dev` — Claude Agent SDK development kit

For people authoring custom agents. Relevant if the friend group builds custom agent products (a v2 concern).

## Plugins we'd evaluate for friend-group projects (domain-specific)

When the friend group commits to a specific project, these become candidates:

- **Database layer**: depending on choice (cockroachdb, clickhouse, convex, alloydb, cloud-sql-postgresql, duckdb-skills)
- **Cloud**: depending on choice (aws-*, azure, cloudflare, deploy-on-aws)
- **Communication**: discord, atlassian (if Jira), asana
- **Security**: aikido (SAST), auth0 (authentication scaffolding)
- **Observability**: dash0 / datadog (per-project monitoring choice)

These are **per-project decisions**, not framework decisions. Document in our framework's onboarding as a discovery surface ("when you pick a project, here's how to find adjacent plugins").

## Conspicuously absent from our research

Plugins on the marketplace we haven't researched but are visible in the inventory:

- **Many language servers** (clangd-lsp, csharp-lsp) — for IDE-style language support; not our concern
- **AWS-heavy presence** (10+ AWS plugins) — Anthropic prioritizes AWS-related tooling
- **Carta financial trio** (carta-cap-table, carta-crm, carta-investors) — niche but well-supported
- **Crypto / web3 plugins** (circle-skills with USDC payments) — narrow domain

None of these would change our framework's architecture.

## How this informs the framework

### Confirms our framework's layer is correct

Most marketplace plugins are **vertical domain tools** (AWS, databases, CRMs). Our framework is **horizontal infrastructure** (memory, skills, hooks, wiki). These don't compete; they compose.

The friend group will install our framework + plus per-project domain plugins. Onboarding should educate friends about the marketplace as a discovery surface.

### Three plugins to actually evaluate further

Priority order if we want to refine the stack:

1. **dash0** — for token-efficiency observability (aligns with north star)
2. **context7** — for version-aware doc lookup (almost mandatory; mild surprise we hadn't covered it)
3. **claude-md-management** — for CLAUDE.md hygiene (overlaps with what we do natively)

These are smaller deep-dives than the 19 substantial research pages we already have. Worth doing if user wants completeness; can defer if not.

### Recommendation in onboarding (per ADR-015)

Update ADR-015 to include in the onboarding flow: a step that introduces friends to the Anthropic marketplace as a discovery surface for domain plugins they'll want when they commit to a project. Don't auto-install anything domain-specific; just teach `/plugin marketplace` and let friends choose.

## Tensions / open questions

1. **Did we miss anything critical** in the 28+ plugins we didn't extract from the 2721-line file? Probably not architectural; likely more domain coverage. Worth a future scan but not blocking.
2. **dash0 deserves a deeper look** — its OpenTelemetry approach to AI agent observability is specifically aligned with our token-efficiency goal. Could be a curated-stack addition.
3. **context7 might be a near-mandatory addition** — version-specific docs is something any production framework wants.
4. **Anthropic's bias toward AWS** (10+ AWS plugins, few GCP, fewer Azure) is worth noting if friend group uses non-AWS clouds.

## Connections to prior research

| Prior source | Connection |
|---|---|
| ECC | ECC has 14 MCP servers + 246 skills covering many of these domain concerns inside its own scope |
| Awesome-claude-skills survey | Composio list is broader (1000+); Anthropic marketplace is smaller (~100) but officially supported |
| Superpowers | Mostly orthogonal to most marketplace plugins; Superpowers is methodology, plugins are domain |
| Skill Creator | Both in Anthropic's marketplace; both Anthropic-official |
| Frontend Design | Same — Anthropic-official, in this marketplace |

## Followups (lower priority than pending decisions)

- Deep ingest of dash0 (observability for our token-efficiency north star)
- Quick ingest of context7 (likely add to curated stack)
- Quick ingest of claude-md-management (verify overlap or complement)
- Scan remaining ~28 plugins in marketplace.json that we didn't extract

## Reference

- Anthropic marketplace.json: https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json
- Plugin directory: https://github.com/anthropics/claude-plugins-official
- Schema: https://anthropic.com/claude-code/marketplace.schema.json
- Plugin marketplace directory: https://claudemarketplaces.com/
- Fetched: 2026-05-28
- Total plugins available: ~100+ (we extracted 73)
