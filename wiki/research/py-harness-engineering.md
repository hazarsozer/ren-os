---
title: Harness Engineering as a Discipline (PY)
type: research
source: raw/transcripts/py-harness-engineering
ingested: 2026-05-28
tags: [harness-engineering, agents, orchestration, ablation, research-papers, dspy, meta-harness, nlh]
status: ingested
attribution: 'PY (YouTube), video "Rethinking AI Agents: The Rise of Harness Engineering"'
duration: ~11 min
---

# Harness Engineering as a Discipline (PY)

## TL;DR

A research-grounded survey of harness engineering — the discipline of designing everything around a language model: orchestration, memory, verification, safety. Two March 2026 papers (Tsinghua NLH + Stanford Meta-Harness from Omar Khattab) formalize the field. **Headline finding: same model + different harness = 6× performance gap. The reusable asset isn't the model; it's the harness.** Direct implication for us: the framework we're building IS our team's harness for Claude Code. Everything here applies.

## Key concepts

### Agent = Model + Harness (Langchain's framing)

> "If you're not the model, you're the harness."

The harness is everything that isn't model weights:
- System prompts
- Tool definitions
- Orchestration logic
- Memory management
- Verification loops
- Safety guardrails

### The OS analogy

| Component | Maps to |
|---|---|
| Raw LLM | CPU — powerful but inert |
| Context window | RAM — fast but limited |
| External databases | Disk |
| Tool integrations | Device drivers |
| **Harness** | **Operating system** coordinating what the CPU sees and when |

The "Agentic OS" framing isn't a metaphor — it's a direct mapping.

### The 6× performance gap (Stanford finding)

Stanford researchers showed orchestration code drives MORE performance variation than the model itself. Langchain demonstrated the magnitude — modifying only harness infrastructure jumped their coding agent from outside the top 30 to **rank 5 on Terminal-Bench 2**. Same model. Different harness.

### Anthropic's five canonical patterns

Every production agent combines some mix of:
1. Prompt chaining
2. Routing
3. Parallelization
4. Orchestrator-workers
5. Evaluator-optimizer loops

### Two failure modes of naive harnesses

1. **One-shotting** — agent tries everything at once, exhausts context
2. **Premature completion** — a later session sees partial progress and declares victory

Anthropic's fix: 3-agent GAN architecture (planner + generator + evaluator). 20× more expensive ($200 vs $9), but the core thing actually works instead of being broken.

### Paper 1: Natural-Language Agent Harnesses (Tsinghua)

Three separable layers:
1. **Backend** — infrastructure, tools
2. **Runtime charter** — "universal physics": how contracts bind, how state persists, how child agents are managed
3. **NLH** (Natural-Language Harness) — task-specific control logic expressed in **structured natural language** (not Python, not YAML)

**Why the separation matters**: it enables controlled ablation experiments. Swap NLH while fixing charter → you're testing harness design. Swap charter while fixing NLH → you're testing runtime policy. Before this, harness logic was scattered — "two systems differing by one design choice" actually differed in prompts, tools, verification, and state simultaneously.

**Two underlying mechanisms**:
- **Execution contracts** — bounded agent calls with five elements: required outputs, budgets, permissions, completion conditions, output paths. *Function signatures for agents.*
- **File-backed state** — externalized memory to path-addressable files, survives truncation, restarts, delegation. *Validates the wiki pattern.*

### The ablation surprise — more structure isn't always better

Same pass rate (74–76% on SWE-Bench Verified with GPT-5), but the full harness burned 16.3M tokens / 642 tool calls / 32 minutes, while stripped down was 1.2M tokens / 51 calls / under 7 minutes. **Same destination, radically different paths.**

Module-by-module ablation:

| Module | Effect |
|---|---|
| Self-evolution (acceptance-gated attempt loop) | **+4.8 SWE, +2.7 OS World — only consistently helpful module** |
| Verifiers | -0.8, -8.4 — actively hurt |
| Multi-candidate search | -2.4, -5.6 — actively hurt |

**Headline**: discipline-narrowing beats expensive broadening. Self-evolution stays narrow until failure signals justify broadening.

### The migration that proved representation matters

Took **OS Symphony** (native code harness for desktop automation) and migrated its logic into NLH representation. *Same strategy, different representation:*

| Metric | Native code | NLH |
|---|---|---|
| Performance | 30.4% | **47.2%** |
| Runtime | 361 min | 141 min |
| LLM calls | 1,200 | **34** |

The representation itself drove the gain. Brittle GUI repair loops replaced with durable runtime state and artifact-backed completion.

### Two crystallized patterns from full results

1. **~90% of all compute flows through delegated child agents, not the parent.** The harness is an orchestration pattern, not a reasoning pattern. It decomposes, delegates, verifies.
2. **The only consistently-helpful module is the one that narrows the agent's own attempt loop.**

### Paper 2: Meta-Harness (Stanford, Omar Khattab)

Khattab — creator of DSPy — treats the harness itself as the optimization target. DSPy tunes prompts within a fixed pipeline; Meta-Harness rewrites the pipeline itself: structure, retrieval, memory, orchestration topology.

**The loop**:
- Agentic proposer (Claude Code with Opus 4.6) reads failed execution traces
- Diagnoses what broke
- Writes a complete new harness
- Scores + raw traces accumulate
- Evaluator tests each proposal

**Scale**: 10M tokens per iteration, 400× more feedback than any prior method, 82 files read per round.

**Raw traces are irreplaceable**: remove them, accuracy drops 50% → 34.6%. Replace with summaries → 34.9%. **The signal lives in the raw details.**

**Headline results**:
- Rank 2 with Opus, **Rank 1 with Haiku** — smaller model outranking larger ones through harness optimization alone
- 76.4% on Terminal-Bench 2 — only automatically optimized system in a field of hand-engineered entries
- 48.6% on 215-class text classification — 7.7 points above SOTA using **4× fewer tokens**
- **A harness optimized on one model transferred to five others, improving all of them**

### Convergence: prompt → context → harness engineering

> "Prompt engineering → context engineering → harness engineering. Three eras in four years, each one swallowing the last."

### Assumptions expire (Anthropic's dynamic)

Every harness component encodes an assumption about what the model can't do alone. Those assumptions expire as models improve.

- When Opus 4.6 stopped needing context resets, Anthropic dropped them entirely
- Manus rewrote their harness 5× in 6 months
- Vercel removed 80% of an agent's tools — and got better results

> "The harness space doesn't shrink as models improve. It moves. Mature harness work looks less like building structure up and more like pruning it down. A craft of subtraction as much as addition."

### Safety concern

> **1 in 4 community-contributed agent skills contains a vulnerability.**

Strong external support for our curate-don't-kitchen-sink thesis.

## How this informs the framework

### Confirms / strengthens our current design

- **We are doing harness engineering.** Name it explicitly. The framework is the team's harness for Claude Code.
- **Curation over kitchen-sink** is now validated by: Vercel's 80% tool-removal result, NLH ablations ("more structure isn't always better"), and the 1-in-4-skills-vulnerable statistic.
- **File-backed state** — path-addressable, survives truncation/restarts — exactly validates the wiki pattern.
- **Self-evolution is the only consistently-helpful module** — **this is now the third independent source pointing to self-improving skills** (after Simon Scrapes' `learnings.md` pattern). Strong signal.
- **Smaller model + better harness > bigger model** — token efficiency isn't penny-pinching, it's competitive advantage.
- **Hierarchical separation** — Tsinghua's backend/charter/NLH split mirrors our hierarchical CLAUDE.md / wiki / skills split.

### New adoption candidate: execution contracts for skills

Tsinghua's "execution contract" framing — bounded agent calls with five elements — is a pattern to bake into every skill in our framework:

| Element | What it specifies |
|---|---|
| Required outputs | What the skill must produce |
| Budgets | Tokens / turns / files / time bounds |
| Permissions | What it's allowed to read/write/execute |
| Completion conditions | How "done" is decided |
| Output paths | Where artifacts land (ties to output consolidation from Simon Scrapes) |

This becomes part of the SKILL.md frontmatter schema in our framework. Note how this also connects to Simon Scrapes' output-consolidation pattern — the same design need from two angles.

### New principle: design for rewrites

Manus rewrote 5× in 6 months. Anthropic dropped context resets when Opus 4.6 made them obsolete.

> **Plan for the framework to be rewritten frequently as Claude evolves. Don't over-abstract; don't gold-plate; keep components small and replaceable.**

Practical: every assumption gets dated and reviewed. The wiki's `decisions/` ADRs should include an "Assumption being made about Claude" field and a sunset-review date.

### New principle: raw traces over summaries

Khattab's finding (raw traces critical, summaries don't substitute) has direct implications:
- The `log.md` is **good** (chronological, raw entries)
- Resist over-aggressive compression in the consolidate skill
- Session logs should preserve enough rawness for future Meta-Harness-style optimization

## Tensions / open questions

1. **Should the framework include automated harness optimization (Meta-Harness style)?** Powerful but ambitious. Definitely out of v1. But the file structure should preserve the raw trace data needed to enable it later. `log.md` + `session.log.md` already support this — just don't compress them away.
2. **Verifiers were net-negative** in NLH ablations. We hadn't planned to ship verifier agents, but if we do later, be skeptical.
3. **Runtime charter / NLH split** — should our framework formalize a layered architecture (universal physics in framework CLAUDE.md, task-specific NLH in individual skills)? Worth considering as a design discipline.
4. **Skill execution contract schema** — does the framework prescribe SKILL.md frontmatter that captures the five contract elements, or leave skills loose?
5. **Skill-vulnerability review process** — 1 in 4 community skills is a real risk. What's our review process before adopting a third-party skill? This becomes a curation-layer design problem.

## Quotes worth preserving

> "If you're not the model, you're the harness."

> "Same model, same benchmark, six times the performance difference."

> "Discipline narrowing beats expensive broadening every time."

> "The reusable asset isn't the model, it's the harness."

> "The harness space doesn't shrink as models improve. It moves."

> "Mature harness work looks less like building structure up and more like pruning it down. A craft of subtraction as much as addition."

> "1 in 4 community-contributed agent skills contains a vulnerability."

## External references mentioned (for follow-up research)

- **DSPy** (Khattab, Stanford) — prompt optimization within fixed pipelines
- **Meta-Harness** (Khattab, Stanford) — March 2026 paper, automatic harness optimization
- **NLH / Natural-Language Agent Harnesses** (Tsinghua) — March 2026 paper
- **OS Symphony** — native code harness for desktop automation (used in NLH migration experiment)
- **Terminal-Bench 2** — coding agent benchmark
- **SWE-Bench Verified** — software engineering benchmark
- **OS World** — operating system task benchmark
- **DeepMind auto-harness** — compiles game rules into code harnesses, eliminates 10% of illegal moves across 145 games
- **AgentSpec** — safety constraints as DSL, prevents >90% unsafe executions
- **Anthropic 3-agent GAN architecture** — planner + generator + evaluator
- **Manus, Vercel** — companies whose harness evolution patterns were cited

## Reference

- Raw source: `raw/transcripts/py-harness-engineering`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: PY, YouTube video "Rethinking AI Agents: The Rise of Harness Engineering"
- Transcript length: ~11KB, short-form video (~11 minutes)
