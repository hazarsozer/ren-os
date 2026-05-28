---
title: Anchor Tags for Large Codebases (Ben Fellows)
type: research
source: raw/transcripts/ben-fellows-anchor-tags
ingested: 2026-05-28
tags: [codebase-navigation, anchor-tags, manifest, large-codebases, determinism, agentic-development]
status: ingested
attribution: Agentic Development — Ben Fellows (YouTube), video "Agentic development wasn't working for my large codebase. Then I implemented anchor tags"
duration: ~10 min
related: [llm-wiki-pattern, prompt-engineering-agent-harness]
note: |
  More tangential to our immediate framework scope (this is about code legibility for
  AI at scale, not Claude Code memory/skills/harness). Useful for the manifest pattern
  and the "boring > bespoke" principle. Most directly relevant when framework users
  later build real codebases of meaningful size.
---

# Anchor Tags for Large Codebases (Ben Fellows)

## TL;DR

A pattern for making large codebases legible to AI agents: sprinkle structured metadata ("anchor tags") throughout the code, plus a single manifest catalog. AI queries the manifest first, derives custom searches, then greps deterministically. Solves planning inaccuracy, orphan code, and validation drift in big codebases. Ben's example: 35,000 anchor tags across 1,300 services.

## The pattern

### Two-layer architecture
1. **Anchor tags** — metadata directly in code (surface name, role, related tags)
2. **Manifest** — single catalog of every anchor tag surface in the codebase

### The flow
```
User asks for change
     │
     ▼
AI reads manifest first  →  decides what context it needs
     │
     ▼
Writes custom queries against the manifest
     │
     ▼
Greps the code using those queries
     │
     ▼
Has theoretically-complete relevant context for planning
```

## Why this works

### What it provides
1. **Context and linking across code at scale** — AI is great at small-scale connection but loses the thread on big codebases
2. **Deterministic, queryable source of truth** — beats AI's lossy grepping

### What it solves
- **Planning misses things** — even running 5 research agents in parallel still leaves gaps. Manifest closes those gaps.
- **Orphan code** — refactor moves on but old code remains. With anchor tags, "deprecate feature X" becomes "remove all code with anchor tag X" → verifiable.
- **Validation drift** — tests can be linked to anchor tags, giving a more honest test-pyramid view.

## Anti-patterns Ben names

- **Bespoke / unique tags** — defeats the purpose. Use BORING, repeatable tags.
- **Tagging every method** — overkill. Rule of thumb: not every line, not nothing — logical grouping.
- **No enforcement** — without policy-as-code rules, the tag system rots. Rules like: "X lines without an anchor tag is a problem," "tags must be added to the manifest."

> "Make the tag system boring. It doesn't work if every anchor tag is a completely different bespoke set of tags."

Heuristic Ben uses: 10–15 similar tags grouped logically, but not more than 25 identical (which would mean over-tagging).

## The core principle

> "AI did not understand the whole repo. The repo becomes more legible — and that's a rule of it."

## How this informs the framework

### Limited direct relevance to v1

This pattern is about CODE legibility for AI at scale. Our framework's primary scope is meta-tooling: memory, skills, hooks, onboarding. Most friend-group projects won't have 35,000-anchor-tag codebases for years (if ever).

### But three principles ARE transferable

1. **The manifest pattern**: Ben's manifest is what our `index.md` is for the wiki. Same primitive applied to different content. Validates our index-first retrieval approach — already established but reinforced.

2. **"Boring > bespoke" for schemas**: Apply this to wiki page formats, skill frontmatter, decision ADRs. Consistent schemas enable tooling. We should codify this as a wiki convention.

3. **Policy-as-code for metadata enforcement**: We don't need full policy enforcement at v1, but our wiki lint pass should at minimum enforce: every page has correct frontmatter, every research page has a Reference section, every decision has an Open-Questions section. Light-touch lint > nothing.

### When the framework should recommend anchor tags

When a friend-group project's codebase reaches scale (~thousands of files, multiple services), the framework's onboarding should mention anchor tags as an option. Could become a future skill: `anchor-tag-manifest` — generates and maintains a manifest of anchor tags across a project.

### Validation pattern worth borrowing

Ben's "deprecate feature" workflow:
- DON'T prompt "make the anchor tag go away"
- DO prompt "we're deprecating this feature. Look for this anchor tag and remove all related code."

This separation — describing INTENT, letting the agent use METADATA for traceability — is a useful prompt design pattern. Could apply to our wiki: when deprecating a decision, the prompt to the LLM specifies intent + the tag/reference to verify cleanup.

## Tensions / open questions

1. **Is `index.md` enough or do we need anchor-tag-style metadata on pages?** Probably enough at our scale. Revisit when wiki passes ~500 pages.
2. **Should the framework provide a "boring > bespoke" lint rule for wiki pages?** Probably yes, as part of wiki-maintainer agent's lint pass.
3. **Future codebase skill**: at what scale should we recommend anchor tags to friend-group project codebases? Threshold unclear — Ben's example is at extreme scale.

## Quotes worth preserving

> "AI did not understand the whole repo. The repo becomes more legible — and that's a rule of it."

> "Make the tag system boring."

> "What you're doing is you're basically introducing determinism along with the system."

> "This as a planning and verification tool, particularly when your codebase reaches a certain threshold, has absolutely been critical for our continued success."

## Convergence with prior sources

| Source | What this transcript shares |
|---|---|
| Karpathy LLM Wiki | Manifest = index.md. Both bet on deterministic queryable catalogs over pure AI search. |
| Prompt Engineering Harness | Anchor-tag manifest is essentially what the system-prompt-assembly pipeline does for CLAUDE.md files — walk + collect a deterministic structure. |
| Simon Skill Systems | The "single source of truth" principle for orchestration applies whether it's anchor tags or wiki indexes. |

## External references mentioned

- **Policy-as-code systems** — used to enforce anchor-tag rules. (No specific tool named; likely OPA/Rego or similar.)
- Ben's own codebase — 35,000 anchor tags, 1,300 services (private/commercial)

## Reference

- Raw source: `raw/transcripts/ben-fellows-anchor-tags`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Ben Fellows, YouTube channel "Agentic Development"
- Transcript length: ~12KB, video duration ~10 minutes
