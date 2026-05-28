---
title: Prompt Caching Mechanics for Claude Code (Nate Herk)
type: research
source: raw/transcripts/nate-herk-give-me-10-mins
ingested: 2026-05-28
tags: [prompt-caching, ttl, sessions, token-savings, claude-code, operational]
status: ingested
attribution: Nate Herk | AI Automation (YouTube), video "Give Me 10 Mins and I'll Save You Millions of Claude Tokens"
duration: ~10 min
related: [prompt-engineering-agent-harness, nate-herk-best-6-skills]
---

# Prompt Caching Mechanics for Claude Code (Nate Herk)

## TL;DR

Operational details on prompt caching that directly support the constraint surfaced by Prompt Engineering's source. Headline numbers: cached tokens cost **10% of normal input**; Nate saved 91M tokens in one day via cache hits. Three operational rules: don't pause >1hr (Claude subscription TTL), don't switch models mid-session, don't change the system prompt. Mid-session CLAUDE.md edits do NOT break cache (changes only apply on restart) — useful design implication for our wake-up hook.

## Key numbers

- **Cached token cost**: 10% of normal input
- **Cache TTL on Claude subscription**: **1 hour**
- **Cache TTL on API (default)**: 5 minutes (can be extended to 1 hour at extra cost)
- **Cache TTL for sub-agents (any plan)**: **5 minutes** ← important for our skill systems / sub-agent designs
- **Daily token savings (Nate's example)**: 91M cached out of session that paid as if ~9M new tokens

## The three cache layers (Thoric / Anthropic)

```
┌──────────────────────────────────────────────────┐
│ System layer (globally cached)                   │
│  - Base system instructions                      │
│  - Tool definitions (read, write, bash, grep…)   │
│  - Output style                                  │
├──────────────────────────────────────────────────┤
│ Project layer (cached per project)                │
│  - CLAUDE.md / memory                            │
│  - Project rules                                  │
├──────────────────────────────────────────────────┤
│ Conversation layer (grows each turn)             │
│  - User messages                                  │
│  - Model replies                                  │
└──────────────────────────────────────────────────┘
```

Caching uses **prefix matching**. Anything that breaks the prefix invalidates the cache from that point onward.

## What breaks the cache

| Action | Breaks cache? | Notes |
|---|---|---|
| Wait >1 hour | YES | TTL expires |
| `/clear` or `/compact` | YES (intentional) | Use deliberately when switching tasks |
| Switch model | YES | Each model has its own cache. `--model opus-plan` toggles between Opus (plan) and Sonnet (execute) → resets cache each toggle |
| Change system prompt | YES | All downstream cache invalidated |
| Edit CLAUDE.md mid-session | **NO** | Edits don't apply until restart — cache stays safe |
| Add a sub-agent call | Sub-agent has 5-min TTL of its own |

## Anthropic monitors this

> "We actually run alerts on our prompt cache hit rate and declare SEVs if they're too low." — Thoric, Anthropic

External validation that prompt caching is a hard, real, business-critical constraint — not a nice-to-have.

## Nate's three habits to save tokens

1. **Don't pause too long.** If >1 hour passes, start a fresh session — hand off if needed rather than resume in the same session.
2. **Switch tasks via `/clear` or `/compact`** (or his session-handoff skill — summarize → `/copy` → `/clear` → paste → continue).
3. **For Claude Chat (web), use projects for documents** instead of pasting them into the chat (project files cached differently / more optimized).

## How this informs the framework

### 1. Confirms the prompt-caching design constraint (with hard numbers)

The Prompt Engineering source identified the constraint qualitatively. This source quantifies it (10% cost for cached, 1-hour TTL, prefix matching, SEV-level monitoring at Anthropic). Our wake-up hook MUST preserve cache prefix integrity:

- **OK**: write to CLAUDE.md at the END of the static section, before session starts
- **OK**: SessionStart hook injects wiki context into the conversation layer (does not affect system/project layers)
- **BAD**: dynamically prepending content to the system prompt
- **BAD**: changing the CLAUDE.md frontmatter mid-session (well — it's actually OK because changes don't apply mid-session, but confusing as a pattern)

### 2. CLAUDE.md mid-session edits don't break cache — IMPORTANT design implication

We CAN write to CLAUDE.md during a session (e.g., as the consolidate skill updates project context for the next session). The change won't take effect until restart, but that's exactly when we want it to: NEXT session starts with the updated CLAUDE.md, and that's the natural cache boundary anyway.

This means **the consolidate skill can write project CLAUDE.md updates without worrying about breaking the current session's cache.**

### 3. Sub-agent TTL is 5 minutes — design around it

Sub-agents (per Claude Code's `Agent` tool) have only 5-minute cache TTLs regardless of subscription tier. Implications:

- Long-running orchestrated workflows that hop between sub-agents will pay full cache costs frequently
- Better to batch sub-agent work tightly than spread it over time
- If we ship a skill that orchestrates 5 sub-agents over 30 minutes, the later sub-agents will all see cache misses
- **The framework should document this trade-off** explicitly in any sub-agent-using skill systems we ship

### 4. Model-switching breaks cache — affects Opus/Sonnet split strategies

The `--model opus-plan` pattern (Opus during plan mode, Sonnet during execution) is popular for token savings, but **each toggle resets the cache**. Net: it depends on session shape whether you save or lose net tokens. Our framework's docs should be honest about this trade.

### 5. Session-handoff pattern (Nate's skill)

Nate's session-handoff skill summarizes session state, copies to clipboard, clears, pastes. This is essentially our `consolidate` skill in a different shape:

| Our framework | Nate's skill |
|---|---|
| Consolidate writes to wiki (durable, multi-session) | Session-handoff writes to clipboard (transient, single-paste) |
| Restored via wake-up hook (automatic) | Restored via paste (manual) |
| Synthesizes for long-term knowledge | Summarizes for immediate next session |

These aren't competing — they could coexist. The consolidate skill (durable wiki) does the long-term work; a session-handoff-style skill could handle the mid-task task-switch use case. Worth considering as a v2 addition.

### 6. Token dashboard

Nate ships a local GitHub repo that visualizes token usage. We don't need to build this — recommend it (or similar) as part of our curated stack. Useful for the team to see where tokens go.

## Tensions / open questions

1. **Should the framework's wake-up hook write to CLAUDE.md or inject into the conversation layer?** Both work; writing to CLAUDE.md means cache hits on next session start; injecting into conversation means immediate availability but at current-session cost. Probably: do both — CLAUDE.md gets a stable bootstrap, conversation layer gets dynamic wiki content.
2. **5-minute sub-agent TTL is a real constraint.** Skill systems with multiple sub-agents need to be designed compactly. Document this clearly when we write skill-system templates.
3. **Should we recommend a token dashboard?** Either Nate's repo or build our own thin one. Probably recommend an existing one; building one is out of scope.
4. **The Opus/Sonnet split trade** — should the framework default to a single-model strategy (no switching) for cache efficiency, with documentation that users who need to switch should know the cost?

## Quotes worth preserving

> "Cached tokens only cost you 10% of normal input."

> "We actually run alerts on our prompt cache hit rate and declare SEVs if they're too low." — Thoric, Anthropic

> "Switching with model means the next request reads the entire conversation history with no cache hits even though the context is identical."

## Convergence with prior sources

| Source | What this source adds |
|---|---|
| Prompt Engineering Harness | Quantifies and operationalizes the prompt-caching constraint that source surfaced qualitatively |
| Nate Herk Best 6 Skills | Same author; this is the operational complement to his strategic plugin list |
| Karpathy LLM Wiki | Caching mechanics validate the "stable bootstrap + dynamic loading" pattern — the wiki is naturally loaded into the conversation layer (where it doesn't break cache) |

## External references mentioned

- **Thoric** at Anthropic — quoted on SEV-level cache monitoring; wrote a detailed article on prompt caching (Nate links it in his description — track down for foreground research)
- **Nate's token dashboard** — GitHub repo, free, in his school community
- **Nate's session-handoff skill** — same source

## Reference

- Raw source: `raw/transcripts/nate-herk-give-me-10-mins`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Nate Herk | AI Automation, YouTube video "Give Me 10 Mins and I'll Save You Millions of Claude Tokens"
- Transcript length: ~16KB, video duration ~10 minutes
