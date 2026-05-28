---
title: "context7 (Upstash) — Version-Specific Documentation Lookup MCP"
type: research
source_url: https://github.com/upstash/context7
plugin_marketplace: https://claude.com/plugins/context7
source_fetched: 2026-05-28
ingested: 2026-05-28
tags: [documentation, version-aware, mcp, anthropic-marketplace, ecosystem-survey, quick-ingest]
status: ingested
related: [anthropic-marketplace-catalog, awesome-claude-skills-survey, superpowers]
---

# context7 (Upstash) — Version-Specific Documentation Lookup

## TL;DR

MCP server by Upstash that delivers **up-to-date, version-specific documentation and code examples** directly into prompts. Ships in Anthropic's official Claude Code marketplace — one-command install. Includes a docs-researcher agent (runs on Claude 3.5 Sonnet) that keeps the main context lean. Strong candidate to **add to our curated stack (ADR-006 amendment)** — fills the "agent doesn't know the latest API" gap that hits every framework eventually.

## What it does

Pulls **up-to-date, version-specific documentation** from source (npm, PyPI, official docs, etc.) and places it into Claude Code's prompts. Eliminates the staleness problem where Claude's training cutoff doesn't include the current version of a library you're using.

Example use:
> "How do I set up Next.js 14 middleware?"

context7 fetches Next.js 14's current docs (not v12's that was in training data) and puts them in context.

## Architecture

Three components:

1. **MCP server** — handles documentation requests
2. **Skill** — auto-activates when conversation indicates external docs would help (no explicit "use context7" keyword needed)
3. **docs-researcher agent** — runs on Claude 3.5 Sonnet (cheaper than main session's model) for documentation retrieval, keeps main session context lean
4. **`/context7:docs` command** — manual interface for direct lookups (testing, quick checks)

## Install

For Claude Code:
```
/plugin install context7@claude-plugins-official
```

Or via the one-command installer:
```
# Authenticates via OAuth, generates API key, installs the skill
# Choose CLI + Skills or MCP mode
# --claude, --cursor, --opencode flag targets specific agent
```

## License & provider

- **Provider**: Upstash (known company, multiple OSS projects)
- **In Anthropic's official marketplace** (provider-vetting per ADR-007: positive)
- License: not extracted from search results; likely permissive given marketplace inclusion

## How this informs the framework

### Add to curated stack (ADR-006 amendment)

Strong candidate for inclusion in the curated stack:

- **Solves a real problem** every framework hits: model staleness around library versions
- **Anthropic-official** (in claude-plugins-official marketplace)
- **One-command install** — onboarding friction is zero
- **docs-researcher sub-agent pattern** — runs on a cheaper model, keeps main context lean (token-efficiency aligned)
- **Skill auto-activation** — no need for friends to remember to invoke it; works as background augmentation
- **Provider trust** is high (Upstash known + Anthropic marketplace)

The case to add context7 to the required-install plugins (alongside Superpowers + Skill Creator + claude-mem + Context Mode) is strong.

### Connects to our research-first principle

ECC's core principle is "research-first development." Several other research pages echo this. context7 implements the **looking-up-the-actual-docs** part of research-first behavior. Adopting it operationally enforces the principle.

### Slash-command consideration (ADR-013)

context7's `/context7:docs` follows the `/<plugin>:<command>` namespacing pattern we adopted for our own commands (`/sf:*`). No collision.

## Tensions / open questions

1. **API key required** — context7 needs an API key from Upstash. Onboarding (ADR-015) needs to handle this similar to ANTHROPIC_API_KEY for Skill Creator. Two API keys per friend = more setup friction. Mitigation: include in `/sf:install` Stage 1 (environment check) or Stage 3 (conditional install with explanation).
2. **Free tier exists** but limits unclear. Worth checking before recommending.
3. **Privacy** — documentation lookups go to Upstash. Should be fine (queries are typically generic; no proprietary code shared) but worth documenting.
4. **Sub-agent on cheaper model** — confirms harness research's "delegate to smaller models for sub-tasks" pattern. Worth noting.

## Connections to prior research

| Prior source | Connection |
|---|---|
| ECC | Their `core` profile includes documentation lookup; context7 is a more specialized version |
| Awesome-claude-skills survey | context7 appeared as community-managed entry in Anthropic marketplace |
| Anthropic Marketplace Catalog | context7 in the marketplace; surprise we hadn't covered it sooner |
| Superpowers | Doesn't include docs-lookup; context7 fills the gap |
| ADR-006 (Curated Stack) | Amendment candidate to add context7 |
| ADR-015 (Onboarding) | API key handling needs to extend to context7 |

## Followups

- Verify license + free tier limits before recommending
- Test that docs-researcher agent doesn't conflict with Superpowers' subagent-driven-development hook ordering (per ADR-010)

## Reference

- Repo: https://github.com/upstash/context7
- Plugin marketplace: https://claude.com/plugins/context7
- Claude Code-specific plugin path: https://github.com/upstash/context7/tree/master/plugins/claude/context7
- DeepWiki coverage: https://deepwiki.com/upstash/context7/9-claude-code-plugin
- Provider: Upstash
- Fetched: 2026-05-28
