---
title: Agentic OS Framework (Simon Scrapes)
type: research
source: raw/transcripts/simon-scrapes-agentic-os
ingested: 2026-05-28
tags: [agentic-os, memory, skills, hooks, hierarchical-context, claude-code, planning, workflows]
status: ingested
attribution: Simon Scrapes (YouTube), video "Creating Your Own Agentic OS is Easy (Insanely Powerful)"
duration: ~24 min
---

# Agentic OS Framework (Simon Scrapes)

## TL;DR

A 9-part architecture for building a personal "Agentic OS" — a context-management layer that turns generic LLM tools into specialized, repeatable, scheduled workflows. Core thesis: the difference between a frustrating LLM experience and a productive one isn't model choice or prompting skill — it's the structure underneath. An Agentic OS is **"just clever context management"** implemented as folders, files, and hooks.

## The nine pillars

1. **Static context (you & your business)** — identity files, brand voice
2. **Improved memory** — six-level hierarchy from CLAUDE.md to cross-tool sharing
3. **Repeatable processes via skills** — modular, progressive-disclosure
4. **Multi-step workflows on a schedule** — chain skills, human-in-loop, autonomous runs
5. **Planning that matches the project** — three levels of planning depth
6. **Managing projects & clients** — hierarchical CLAUDE.md inheritance
7. **Output consolidation** — predictable file structure for outputs
8. **Access anywhere** — VPS hosting + messaging access (Telegram/Discord)
9. (Implicit ninth — meta-architecture & portability across tools)

## Key concepts worth absorbing

### Static vs. dynamic context (a clean mental split)

- **Static** — identity (user.md), agent personality (soul.md / personality.md), business/brand voice. Doesn't change often.
- **Dynamic** — ongoing projects, decisions, learnings. Maintained via the memory system.

This split is useful for the framework: static stuff lives in CLAUDE.md and identity files (loaded every session); dynamic stuff lives in the wiki (loaded on demand).

### Six levels of memory (Simon's hierarchy)

| Level | Mechanism | Tool example | When to use |
|---|---|---|---|
| L1 | CLAUDE.md / static rules | built-in | Rules that never change |
| L2 | SessionStart hook (force-inject context) | built-in hooks | Project context that MUST load every session |
| L3 | Semantic search | `mem search`, `claude mem` | Recall across many notes/sessions |
| L4 | Verbatim recall | `me palace` | When exact phrasing matters (client work) |
| L5 | Knowledge bases | various | Specific RAG use cases |
| L6 | Cross-tool shared memory | OpenClaw, MCP-based | Multiple LLMs/devices share memory |

**Simon's 80/20 recommendation**: L1 + L2 + L3 combined. L4–L6 are bolt-ons for specific needs.

### Hooks > CLAUDE.md for reliability (a load-bearing insight)

> "A hook deterministically says push this data into the conversation window. Whether it likes it or not, it's going in. Whereas a claude.md file might tell it to read another file for context, but Claude doesn't actually have to listen."

Implication: anything that MUST happen at session start belongs in a SessionStart hook, not as an instruction in CLAUDE.md. Instructions are advisory; hooks are deterministic.

### Progressive disclosure for skills

Skills load in stages to keep context lean:
1. **Always**: name + description (cheap, ~tens of tokens)
2. **On match**: full `SKILL.md` (target <200 lines)
3. **On demand**: examples, supporting references (loaded by the skill itself when needed in a specific step)

Claude's known-reliable recall window is ~200 lines — that's the bar for the SKILL.md body length.

### Self-learning skills via `learnings.md`

Pattern: every skill asks for feedback after use → feedback goes to `learnings.md` → next time the skill runs, it reads `learnings.md` first. Skills compound over time, like the wiki itself.

### Hierarchical CLAUDE.md inheritance

Claude Code's native feature: nested CLAUDE.md files inherit from parent. Simon's structure:
- Root: master methodology
- Per client/project: own CLAUDE.md that overrides or extends parent
- Shared skills installed at root, accessible from any client subfolder

**This maps directly onto our master + project sub-wiki design** — we get hierarchy mostly for free from Claude Code itself.

### Skills as chainable modular components ("skill systems")

A skill = one step. A "skill system" = a chain of skills. Simon's examples:
- Topic research → script writing → video creation → posting
- A transcription skill reused across multiple content-creation pipelines
- Human-in-the-loop steps can be inserted between skills
- Scheduled tasks orchestrate the chain

### Three levels of planning

Match planning depth to task complexity:
- **L1**: Built-in plan mode (`Shift+Tab+Tab` in Claude) — simple tasks
- **L2**: PRD-style plans — half-day to multi-day projects, broken into ticked-off files
- **L3**: GSD (Get Stuff Done) framework — break complex projects into phases, plan/execute/verify each. Designed to combat **context rot** (his term for the degradation of recall as the conversation window fills up).

### Output consolidation

Per-project + per-skill folder structure so outputs don't end up scattered across the filesystem or terminal. Example shape:
```
projects/<client>/
  skills/<skill-name>/<date-run-id>/output.md
  briefs/<project-name>/
    plan.md
    outputs/
```

### Access anywhere

V2+ concern: host the system on a VPS or Claude Cloud, message it via Telegram or Discord through Anthropic's **channels** feature. Decouples the OS from a single laptop. Simon admits his own community doesn't actually run this yet.

## How this informs the framework

### Directly adopt
- **Static vs dynamic context split** — clean mental model for our memory layer. Static stuff (identity, team preferences, stack defaults) lives in CLAUDE.md / identity files; dynamic stuff (decisions, project state, learnings) lives in the wiki.
- **Hooks > CLAUDE.md instructions** — confirms our SessionStart hook approach. Reinforces that wake-up logic belongs in a hook, not as advisory CLAUDE.md prose.
- **Progressive disclosure for skills** — adopt the 3-stage loading pattern. <200 line SKILL.md target. Every skill in the curated set follows this.
- **Hierarchical CLAUDE.md inheritance** — Claude Code's native feature already implements the hierarchical scoping we wanted. Master + project sub-wikis become natural.

### Consider adopting (open design decisions)
- **Self-learning skills via `learnings.md`** — interesting pattern; consider for high-value skills (e.g., the `consolidate` skill itself could benefit). Trade: more file churn, more places where signal-vs-noise discipline matters.
- **Output consolidation conventions** — we haven't designed this. Decide whether the framework prescribes a `projects/.../outputs/` structure or stays agnostic.
- **Three planning levels** — only relevant if the framework is also a development framework. If we stay strictly meta-tooling/memory, this is out of scope for v1.

### Tensions / divergences from our current design

| Our current decision | Simon's view | Tension |
|---|---|---|
| No vector search at v1; index-driven recall | L3 semantic search is part of 80/20 | Need to evaluate whether `index.md` is genuinely enough at our scale, or whether `claude-mem` style L3 should be in v1 |
| Memory layer is the headline novel feature | Memory is one of nine equal pillars | Are we overweighting memory at the expense of breadth (planning, scheduling, output consolidation)? |
| Onboarding = polished install UX | Onboarding includes an AI-interview to fill identity files | We hadn't designed the content of onboarding, only the install mechanism. Should add identity bootstrap. |
| Token efficiency is north star | Token efficiency is one concern among many | Are we under-investing in workflow/scheduling because of memory-centric framing? |

## Open questions raised by this source

1. **Should we reconsider vector search for v1?** Simon's L3 recommendation conflicts with our current "no daemon, files only" stance. Evaluate: at the friend group's projected scale, does `index.md`-driven recall genuinely match L3 quality, or do we silently degrade? Worth a focused experiment.
2. **Identity-bootstrap as part of onboarding?** When a friend installs the framework, should it walk them through an AI-driven interview to populate their `user.md` / preferences / role? This is a new onboarding requirement we hadn't surfaced.
3. **Self-learning skills — opt-in or default?** If `learnings.md` becomes default, the wiki gains a third type of evolving document (alongside index/log). Adds value but also complexity.
4. **Output consolidation — prescribed or agnostic?** Friend group projects may want different output structures. Decision pending.
5. **Are scheduled / autonomous workflows in v1 scope?** Simon emphasizes "skills on a schedule" as a key pillar. Our scope so far is curation + memory + onboarding. Workflows could be a v2.
6. **Should we adopt the "static context" identity-file pattern wholesale (user.md, soul.md, brand context.md), or design our own version?** Simon's structure is opinionated; ours could be slimmer.

## Quotes worth preserving

> "An Agentic OS is just clever context management."

> "A hook deterministically says push this data into the conversation window. Whether it likes it or not, it's going in."

> "Out of the box memory is pretty poor. So the more context and knowledge you push into a conversation window, the worse the recall will become. And that is effectively called context rot."

> "The most important thing for your agentic operating system is keeping your skills short and modular."

> "This architecture is completely portable. The tools are going to keep changing, but the underlying structure and the foundations are going to stay true."

## External references mentioned (for follow-up research)

- **`mem search`** — semantic search memory tool (verify URL/repo)
- **`claude-mem`** — semantic search memory tool (verify URL/repo)
- **`me palace`** — verbatim recall tool (likely "Pi Palace"? — verify)
- **OpenClaw** — alternative LLM tool with cross-tool memory
- **Hermes** — another LLM tool with channels feature
- **Anthropic channels** — Telegram/Discord access feature
- **GSD (Get Stuff Done) framework** — planning pattern
- **Anthropic's skill creator skill** — for building new skills
- **Aentic Academy** — Simon's commercial offering (out-of-scope for us, but namesake of the "Agentic OS" terminology popularized here)

## Reference

- Raw source: `raw/transcripts/simon-scrapes-agentic-os`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Simon Scrapes, YouTube video "Creating Your Own Agentic OS is Easy (Insanely Powerful)"
- Transcript length: ~34KB, video duration ~24 minutes
