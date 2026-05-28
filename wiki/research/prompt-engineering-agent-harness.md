---
title: What Is an Agent Harness? — Nine Components Reference (Prompt Engineering)
type: research
source: raw/transcripts/prompt-engineering-agent-harness
ingested: 2026-05-28
tags: [harness-engineering, agents, architecture, hooks, permissions, system-prompts, while-loop, claude-code]
status: ingested
attribution: Prompt Engineering (YouTube channel), video "What is an Agent Harness? and how to build a great one!"
duration: ~20 min
related: [py-harness-engineering, caleb-agent-harness, simon-scrapes-agentic-os]
---

# What Is an Agent Harness? — Nine Components Reference (Prompt Engineering)

## TL;DR

The most structured, definition-grade source so far. Three-part contribution: (1) sharp definition of harness ("a fixed architecture that turns a model into an agent"), (2) **the crucial distinction between harnesses and frameworks** — they are NOT the same thing despite the conflated usage, (3) a 9-component checklist for what a complete harness contains. Includes a reference Python implementation. Surfaces a real technical constraint we need to design around: **prompt caching breaks if you dynamically prepend content to the system prompt**.

## The definition

> "A harness is a fixed architecture that turns a model into an agent."

- Model = engine
- Harness = car (the thing around the engine that makes it useful)
- A model alone is a one-shot text generator
- The harness gives it action, feedback, and persistence
- Codex / Cursor / Claude Code / Windsurf are all harnesses — and they've **converged on remarkably similar architectures**

## Harness vs. framework — the distinction we need to honor

| Property | Framework | Harness |
|---|---|---|
| Examples | LangChain, LangGraph, AutoGen, CrewAI | Codex, Cursor, Claude Code, Windsurf |
| What it provides | Abstractions (state graphs, chains, memory cans, retrievers) | A working agent (while loop + tool registry + permissions, wired together) |
| Assembly step? | YES — human must wire components together | NO — ships ready to run |
| Built for | The human architect | The agent itself |
| You provide | The configuration | The goal |
| Mental model | "Here are pieces, build something" | "Here's a worker, give it a task" |

> "A framework is built for a human to assemble an agent. A harness is built for the agent itself to a task."

**Why this matters to us**: we've been calling our project a "framework," but technically it's neither a framework NOR a harness — it's a **meta-harness configuration**: an opinionated wiring + extension layer on top of Claude Code (which IS the harness). The user's preferred name stays "framework," but internally we should be honest about the technical category.

## The nine components

### 1. The while loop

The foundation. Model reads system prompt → decides which tool → runs tool → feeds result back → loops. Continues until text-only response OR max-iteration cap.

This is the engine that runs everything else. Our framework doesn't add to this — Claude Code provides it.

### 2. Context management

Every turn the context grows. The harness must decide what to **keep verbatim**, what to **summarize**, what to **throw away**. Claude Code currently caps at ~200K tokens (1M for Opus 4.7) and triggers compaction at 80–90%. Recent messages stay full; older messages get summarized.

> "Compaction is very important — and it can have some real bad consequences if not done properly."

**Connection to our design**: this is the failure mode Caleb warned about. Our wiki layer is the answer: the durable knowledge survives compaction because it lives outside the conversation.

### 3. Tools, skills, and the registry

- **Tools** = universal primitives (read file, run bash, search code)
- **Skills** = team/workflow-specific knowledge encoded in markdown files
- **Registry** = what's available + permissions + dispatch

> "Tools are universal. Skills are specific to your team, your workflow."

**Connection to our framework**: curation is at the skill layer (team-specific), not the tool layer (universal). The framework's value is in the skills, not the tools.

### 4. Sub-agent management

When a task gets too big or too parallel for a single thread, the harness spawns sub-agents. Each sub-agent gets:
- Own session
- Restricted set of tools
- Focused system prompt

The pattern Prompt Engineering names: **"spawn, restrict, collect outputs."**

Connects to PY's research ("90% of compute through delegated child agents") and Simon's skill systems (orchestrator skill spawns component skills).

### 5. Built-in skills (the baseline)

Every harness ships with non-negotiable primitives:
- File operations (read/write/edit/search)
- Shell execution
- Code navigation

Plus higher-level vendor-specific skills:
- How to make a git commit
- How to open a pull request
- How to run tests

**Important architectural note**: "These primitives need to use pure standard libraries. You don't want to rely on framework dependencies."

### 6. Session persistence / memory

> "Modern harnesses do this pretty elegantly. Typically they use **append-only JSON files** or markdown files. Every message, every tool result, every compaction event gets one line."

The beauty: durability + resumability. **Anthropic separates session management from the harness itself** — Prompt Engineering noted this as a notable design pattern from a recent Anthropic talk.

**Connection to our wiki design**: our `log.md` and `session.log.md` follow exactly this append-only pattern. Externally validated.

### 7. System prompt assembly

> "This is the one that will surprise most people. The system prompt is **not a static string**. It's a pipeline that walks ancestor directories looking for CLAUDE.md / AGENTS.md and injects them into the system prompt."

**CRITICAL CONSTRAINT for our framework**:
> "Most third-party harnesses or even first-party harnesses have really strict prompt caching. **If you dynamically introduce components to the system prompt, that is going to break the caching.** Keep the static part first, dynamically load content second — otherwise you break prefix caching."

This is a real design constraint for our wake-up hook. The wiki context we load at session start must come AFTER the static system prompt sections (CLAUDE.md, identity files) to preserve cache hits.

### 8. Lifecycle hooks

> "This is the extensibility seam. Hooks let you inject custom logic before or after a tool runs without touching the harness itself."

- **Pre-tool hook** — fires before execution. Receives tool name + input. Can allow / deny / modify the call.
- **Post-tool hook** — fires after execution. Sees the output. Used for audit, logging, observability. **Cannot block.**

Protocol: typically JSON files with exit codes for allow/deny.

> "Hooks are how enterprises today adopt harnesses themselves."

Connects directly to our SessionStart and Stop hooks for wake-up + consolidate.

### 9. Permissions and safety

> "This is the layer that makes the difference between a useful tool and a dangerous one."

Hierarchy: read-only / workspace / full access. Each tool declares minimum permission needed. Harness enforces at dispatch time.

For bash specifically: **dynamic command classification** —
- `ls`, `cat`, `grep` → read-only
- `rm`, `sudo`, `shutdown` → full access (require approval)
- Everything else → workspace

Plus interactive approvals for destructive operations.

We don't add to this layer; Claude Code handles it.

## The Python reference implementation (concrete patterns)

**Append-only JSONL memory** (`append()` opens in append mode, writes event, immediately flushes — crash-safe; `replay()` reads back line by line; two runs share log without stepping on each other)

**Tool/skill registry** = dict mapping name to record (name + permissions + handler + description). Skills are just tools whose handler reads a markdown file at invocation time.

**Sub-agent archetypes** — three were demonstrated: `exploration`, `general`, `verification`. Each with own permission level, restricted tool list, focused system prompt.

**Prompt assembly** — static first, dynamic second (caching constraint).

**Permission classification** — static rules + dynamic shell classifier + interactive approval for destructive ops.

## How this informs the framework

### 1. Honor the harness/framework distinction

Internally, document that we're building a **meta-harness configuration**, not a framework in the LangChain sense. Externally we keep the user's preferred term ("framework").

The 9-component checklist is what a harness has. Our work is at components **2 (wiki replaces summarization), 3 (curated skills), 4 (sub-agent patterns via GSD recommendation), 6 (wiki + session log + pointer), 7 (CLAUDE.md hierarchy), 8 (wake-up + consolidate hooks)** — primarily layers built ON TOP of Claude Code's harness.

### 2. The prompt-caching constraint is real and important

> Keep static parts of the system prompt FIRST. Dynamic content from our wake-up hook must be appended at the END of the system prompt, never prepended.

This becomes a design rule for the wake-up skill. Add it to `wiki/decisions/` when we start filing ADRs.

### 3. The 9-component checklist as a design review tool

Every framework decision can be evaluated: which component does it touch? Does our change to that component conflict with what Claude Code already provides?

Adopt as `wiki/conventions/harness-component-checklist.md` (when we create that directory) for design reviews.

### 4. Anthropic's "session management separated from harness" insight

This is intriguing. We should track down their published material on this when we do the foreground web research. It might align with what we're doing (wiki separate from Claude Code's session state) or suggest a better pattern.

### 5. "Spawn, restrict, collect" sub-agent pattern

Adopt this exact phrasing for our framework documentation. It's the cleanest articulation of the sub-agent delegation pattern we've seen, and it operationalizes PY's "90% compute through child agents" finding.

## Tensions / open questions

1. **Prompt cache vs. dynamic context loading.** Our SessionStart hook design needs to be VERY careful — load wiki context at the END of the system prompt, never at the front. Need to test this works in Claude Code's actual prompt caching.
2. **Should we disable Claude Code's auto-compaction?** Component #2 (context management) does compaction by default, but Caleb's warnings + our wiki layer suggest compaction is the broken thing we're working around. Is there a config to disable it? If not, can our consolidate skill run BEFORE compaction triggers?
3. **Append-only JSONL vs. our markdown log.md.** Both are append-only. Prompt Engineering prefers JSON ("JSON seems to be the better choice"); Karpathy prefers markdown. Trade: JSON is machine-parseable, markdown is human-readable. We chose markdown — is that right? Consider for `session.log.md`.
4. **Sub-agent archetypes** — the three archetypes (exploration, general, verification) might be a useful primitive. Should our framework define a small set of archetypes and provide them as skills?
5. **"Anthropic separates session management from harness."** Need to track this down — could change our session-start design.
6. **Where do permissions live?** Component #9 is Claude Code's responsibility — but our skills with **execution contracts** (from Tsinghua) declare required permissions. The contract's `permissions` field is essentially a higher-level declaration that Claude Code can enforce.

## Convergences with prior sources

| Source | What this transcript adds |
|---|---|
| PY Harness Engineering | Component-level breakdown of what a harness IS, complementing PY's research findings about which components matter |
| Caleb Agent Harness | The 9 components are what comprise the "environment" Caleb described at the architectural level |
| Simon Agentic OS | Skills/registry + hooks layers map exactly; this is the technical underpinning of Simon's pillars 3 (skills) and 4 (workflows) |
| Simon Skill Systems | The "spawn, restrict, collect" pattern is the technical name for skill systems' delegation model |
| Karpathy LLM Wiki | The CLAUDE.md walking pipeline is what makes the wiki schema enforceable across Claude Code sessions |

**Sharper picture**: Claude Code is the harness. We're building an opinionated meta-layer that touches specific harness components — particularly 2 (context/memory via wiki), 3 (curated skills), 6 (persistence via wiki), 7 (CLAUDE.md hierarchy), 8 (lifecycle hooks). Components 1 (loop), 5 (built-in skills), 9 (permissions) are handled by Claude Code itself; we don't touch them.

## Quotes worth preserving

> "A harness is a fixed architecture that turns a model into an agent."

> "A framework is built for a human to assemble an agent. A harness is built for the agent itself to a task."

> "The system prompt is not a static string. It's a pipeline that walks ancestor directories looking for specific types of instructions."

> "If you dynamically introduce components to the system prompt, that is going to break the caching."

> "Hooks are how enterprises today adopt harnesses themselves."

> "Tools are universal. Skills are specific to your team, your workflow."

## External references mentioned

- **Codex, Cursor, Claude Code, Windsurf** — examples of harnesses
- **LangChain, LangGraph, AutoGen, CrewAI** — examples of frameworks (NOT harnesses)
- **Anthropic's session-management talk** — referenced as a talk where Anthropic discussed separating session management from the harness. Worth tracking down.
- The Python reference implementation built in the video — useful template if we ever want to fork/study a minimal harness

## Reference

- Raw source: `raw/transcripts/prompt-engineering-agent-harness`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Prompt Engineering (YouTube channel), video "What is an Agent Harness? and how to build a great one!"
- Transcript length: ~19KB, video duration ~20 minutes
