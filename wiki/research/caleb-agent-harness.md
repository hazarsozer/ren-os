---
title: Agent Harness Explained — The Loops Primitive (Caleb)
type: research
source: raw/transcripts/caleb-agent-harness
ingested: 2026-05-28
tags: [harness-engineering, loops, context-summarization, ralph, agent-architecture, claude-code]
status: ingested
attribution: Caleb Writes Code (YouTube), video "Agent Harness explained in 8 min"
duration: ~8 min
related: [py-harness-engineering, simon-scrapes-self-improving-skills, llm-wiki-pattern]
---

# Agent Harness Explained — The Loops Primitive (Caleb)

## TL;DR

Practical narrative of harness engineering's emergence — complements PY's research-grounded view with the developer-facing story. Three eras: prompt engineering (4K-token ChatGPT era) → context engineering (Cursor/Windsurf/Klein/Roo/Aider era with tool calling + MCP + RAG) → harness engineering (early 2026). The single most important harness primitive Caleb identifies: **looping the agent with a fresh clean context at each iteration, under strict start/finish rules.** Context summarization — the current default fallback when context fills — is explicitly warned against as the broken thing harness engineering replaces.

## The three-era evolution

| Era | Year | Core technique | What broke |
|---|---|---|---|
| Prompt engineering | 2022+ | Crafting better prompts in 4K-token windows | Couldn't do anything substantial; "do more with less" pressure |
| Context engineering | ~2023–2025 | Tool calling, MCP, RAG | Long-running tasks (12hr+) filled context → summarization → tasks declared finished when half-broken |
| Harness engineering | Early 2026+ | Loops with fresh context per iteration, hierarchical sub-agents, swarms | (current frontier) |

Players Caleb names as context-engineering-era tools: **Cursor, Windsurf, Klein, Roo, Aider**.

## Why context engineering hit a wall

Long tasks (e.g., "clone an entire website") exposed the failure mode:
- Context window fills up mid-task
- Auto-summarization compresses old context to make room
- **The agent's ability to summarize is the bottleneck**
- Common pathologies:
  - Mid-task summarization assumes the task is already finished
  - Features assumed completed when not verified
  - Tasks oversimplified through compression
- "Elastic self-managing context" *appears* to enable long-range tasks but doesn't actually work well

Caleb's framing:
> "Effectively the agent was bound by its own ability to properly summarize its previous work. And that's why you see tasks that are either half completed or not even attempted at all."

This is the empirical case AGAINST summary-based memory. **Strong external support for the wiki-based persistent-memory approach** — the wiki replaces summarization with compiled, durable knowledge.

## The loops primitive (the central insight)

> "One of the most critical changes that happened with the rise of harness engineering was the idea of loops. By stepping away one layer above context engineering and essentially looping the agent in a loop where at each iteration they have a **fresh clean set of context** but under a strict rule of how the agent should start and finish its task."

Two ingredients per iteration:
1. **Fresh, clean context** (not compressed from prior iterations)
2. **Strict start/finish rules** (deterministic boundaries — what the agent must produce, what counts as done)

This generalizes beyond Karpathy's auto-research loop: it's the **architectural pattern of running an agent in a sterilized environment, repeatedly**.

## Ralph as the worked example

Caleb cites **Ralph** as the canonical lightweight harness:
- First step: create a production requirement document → outlined into a JSON file
- Then enters a loop: implement feature after feature until completion
- Each iteration: fresh prompt + fresh context, drawing the next task from the JSON
- Notable: the repository is small. Architecture is simple.

Same pattern in **Anthropic's own demonstration of harnessing** — a similarly small, lightweight repo.

**Implication for us**: harness engineering done well is LIGHTWEIGHT. We don't need to build a heavyweight framework to do this right. Validates our "no daemon, files + hooks" Approach A+ direction.

## How the layers relate (Caleb's hierarchy)

```
┌─────────────────────────────────────────────┐
│ Harness engineering (the ENVIRONMENT)        │
│  - Loops with fresh context per iteration    │
│  - Strict start/finish rules                 │
│  - Hierarchical sub-agents / swarms           │
├─────────────────────────────────────────────┤
│ Context engineering (LEVERAGED, not replaced)│
│  - Tool calling, MCP, RAG                    │
│  - Smart loading of relevant context         │
├─────────────────────────────────────────────┤
│ Prompt engineering (smaller component now)   │
│  - System prompts, personas                  │
│  - Reminds the agent who it is               │
└─────────────────────────────────────────────┘
```

> "So prompt engineering is still used but a much smaller component in comparison to the system as a whole. Harness engineering effectively leverages both prompt and context engineering. It's a shift away from relying on these two approaches, but a paradigm change on the environment."

## How this informs the framework

### Direct validation of our wiki memory choice

Caleb's specific warning against context summarization is the strongest external case yet for our wiki-based memory model. The wiki is the alternative to summarization: knowledge is **compiled persistently** instead of being **re-derived through lossy compression** at each context-fill event.

### The loops primitive maps directly onto our session model

Our framework's session cycle is already a loops-with-fresh-context pattern:

| Caleb's loop | Our framework's session loop |
|---|---|
| Fresh context per iteration | Each new Claude Code session starts fresh |
| Strict start rules | `SessionStart` hook + `wake-up` skill load only relevant wiki slice |
| Strict finish rules | `Stop` hook + `consolidate` skill harvest learnings into wiki |
| Task drawn from a document | Project log + session pointer drive what's next |

**This is the architectural reframe**: we're not just "building a Claude Code plugin." We're building a **harness that runs Claude Code in disciplined iterations**, with the wiki as the durable layer between iterations.

### The requirements-document-to-loop pattern (Ralph-style)

For complex multi-step tasks within a single session, Ralph's pattern is worth absorbing:
1. Generate a requirements / plan document upfront
2. Outline it into machine-readable structure (JSON / structured markdown)
3. Loop through tasks, fresh context per task
4. Test + document each step

This could become a skill in our curated set — call it `/loop-on-plan` or similar — that takes a plan file and executes it task-by-task with consolidate between.

### Lightweight validates Approach A+

> "[Ralph's] entire architecture is... so small. Same thing for Anthropic's simple demonstration of harnessing... lightweight and simple environment."

External evidence that effective harnesses are SMALL. Our decision to avoid daemons / vector stores at v1 is consistent with this. **"Build a beast" is the failure mode; "build something readable on a coffee break" is the target.**

### Layered architecture honest naming

Our framework is doing all three:
- **Prompt engineering** lives in CLAUDE.md and the identity files (the smaller component)
- **Context engineering** lives in the wiki + wake-up hook (deciding what to load when)
- **Harness engineering** is the overall structure: loops, fresh contexts, consolidation, sub-agent delegation

The framework's design doc should name these explicitly to make the layering legible.

## Tensions / open questions

1. **Should we ship a `/loop-on-plan` skill** that implements Ralph's requirements-document → JSON → loop pattern? Probably yes, but as v1 or v2?
2. **Hierarchical sub-agents vs. swarms** — Caleb mentions both as harness approaches. We've leaned toward sub-agents (PY's "delegate to child agents"). Are swarms (parallel agents with independent contexts) a separate primitive worth supporting?
3. **Cursor/Windsurf moved the harness inside the app** — Caleb notes "many coding agents now have already adopted this harnessing layer directly inside the application." The question this raises for us: how much of harness engineering should be *in the framework* vs. *in Claude Code itself*? Some functionality is moving into the host. Our framework should focus on what isn't.
4. **The "fresh context per iteration" ideal vs. continuity needs** — sometimes you DO want continuity across iterations (mid-feature work, ongoing debugging). When do you reset vs. carry over? The wake-up's "session pointer" is our bridge — worth thinking through.
5. **Anthropic's reference harness repo** — Caleb mentions Anthropic published a simple demonstration. We should track this down and ingest it as a reference implementation (search for "anthropic agent skills harness" / "anthropic claude skills demo").

## Convergence with other sources

| Source | What Caleb adds |
|---|---|
| PY Harness Engineering | Practical narrative + tool names; PY had abstract research, Caleb names Ralph, Cursor, Windsurf, Klein, Roo, Aider |
| Karpathy LLM Wiki | Caleb's anti-summarization argument is the strongest external case for the wiki replacing context summarization |
| Simon Self-Improving Skills | The Karpathy loop is one instance of Caleb's "loops with fresh context per iteration" pattern |
| Simon Skill Systems | Skill systems implement the orchestration layer Caleb calls "the environment" |

**The accumulated picture**: our framework is a **lightweight harness** that uses the **LLM Wiki pattern** for persistent memory (replacing the broken summarization fallback), runs in **loops with fresh contexts per session** (Caleb's primitive), composes **small focused skills into skill systems** (Simon), and uses **self-improvement with binary assertions** for skill quality (Simon + PY). Five sources, one coherent architecture emerging.

## Quotes worth preserving

> "Effectively the agent was bound by its own ability to properly summarize its previous work."

> "One of the most critical changes that happened with the rise of harness engineering was the idea of loops."

> "At each iteration they have a fresh clean set of context but under a strict rule of how the agent should start and finish its task."

> "Harness engineering effectively leverages both prompt and context engineering. It's a shift away from relying on these two approaches, but a paradigm change on the environment that puts the agent into series of steps."

## External references mentioned

- **Ralph** — the canonical lightweight harness example ("took over the internet given how effective it was, more importantly just how simple the architecture was underneath"). Track down repo.
- **Anthropic's simple demonstration of harnessing** — referenced as a reference small repo. Worth finding.
- **Klein** — open-source coding agent, prompt engineering still visible in system prompt
- **Cursor, Windsurf, Roo, Aider** — context-engineering-era coding agents (early players)
- **Cursor cloud agents** — referenced in sponsor segment; runs in cloud, integrates with Slack, supports automation triggers

## Reference

- Raw source: `raw/transcripts/caleb-agent-harness`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Caleb Writes Code, YouTube video "Agent Harness explained in 8 min"
- Transcript length: ~10KB, short-form video (~8 minutes)
