---
title: "ADR-001: Harness vs Framework Terminology"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [prompt-engineering-agent-harness, caleb-agent-harness, py-harness-engineering]
affects-components: [docs, naming, design-doc]
---

# ADR-001: Harness vs Framework Terminology

## Context

We've been calling this project a "framework" since the brainstorming session opened. The user's working name for the directory is `startup-framework/`, and the external pitch to the friend group will likely use the same term.

However, the research surfaced a **technical terminology distinction** that the LLM agent community has converged on (per the Prompt Engineering source and reinforced by Caleb and PY):

- **Harness** — a fixed architecture that turns a model into an agent. Ships a working agent. While-loop + tool registry + permissions wired together. Examples: Claude Code, Cursor, Codex, Windsurf.
- **Framework** — provides abstractions you wire together yourself (state graphs, chains, memory cans, retrievers). Examples: LangChain, LangGraph, AutoGen, CrewAI.

> *"A framework is built for a human to assemble an agent. A harness is built for the agent itself to do a task."*

By this taxonomy, **our project is technically neither a harness nor a framework**. It's a **meta-harness configuration**: an opinionated wiring + extension layer that sits ON TOP of Claude Code (which IS the harness), adding team-knowledge wiki + opinionated curation + lifecycle hooks + onboarding.

The terminology mismatch matters because:
1. Downstream ADRs need precise language ("the framework provides X" vs. "the harness provides X" mean different things now)
2. Public-facing docs that conflate the terms will confuse readers who know the distinction
3. If we accidentally call ourselves a "framework" in the LangChain sense, friends will expect us to provide abstractions to wire — which we don't

## Decision

**Internal language (this wiki, ADRs, design docs): we are a meta-harness configuration on top of Claude Code.**

**External language (user-facing docs, install commands, READMEs): "framework" remains acceptable** as long as it's not paired with implied LangChain-style abstractions. Default external phrasing: *"opinionated configuration for Claude Code"* or *"team agentic OS"* (matching Simon Scrapes' framing) rather than just "framework."

**Concrete renaming guide**:

| Where | Use |
|---|---|
| Internal ADRs, design docs, this wiki | "meta-harness configuration" or "the configuration" |
| External README, install instructions | "team agentic OS" or "opinionated Claude Code config" |
| Casual conversation / slack / user-facing | "framework" or "stack" (still OK informally) |
| Subject lines for ADRs that touch harness layers | Use "harness components" terminology (per Prompt Engineering's 9-component checklist) |

The directory name `startup-framework/` stays. Renaming the directory would break too many references; the directory name is a label, not a claim.

## Consequences

**Easier:**
- Downstream ADRs can be precise about what claude-mem provides vs. what our configuration provides vs. what Claude Code provides
- Public docs can use clear vocabulary without misleading users
- When evaluating future tools, we can ask "does this belong at the harness layer or at our configuration layer?" — a clearer question than "is this a framework feature?"

**Harder:**
- Some redundant language: "the configuration provides X by configuring Claude Code's harness" is wordier than "the framework provides X"
- Need to consistently apply the terminology — easy to slip into "framework" out of habit

**Now impossible:**
- Claiming we provide LangChain-style abstractions — we don't. This is a feature, not a bug. Curation + opinionation > flexibility for our use case.

## Alternatives considered

**A) Embrace "framework" fully and ignore the distinction.**
- Pro: Simpler external pitch; matches the user's instinct
- Con: Misleading to anyone familiar with the terminology; would create disappointment when friends expect LangChain-style wiring

**B) Call it a "plugin" since it deploys as a Claude Code plugin.**
- Pro: Accurate at the deployment layer
- Con: Understates the scope — we're more than a single plugin; we're an opinionated curation + integration of multiple plugins + a wiki layer + lifecycle hooks
- Con: Doesn't capture the team-knowledge layer that's the unique contribution

**C) Coin a new term ("agentic OS" per Simon Scrapes).**
- Pro: Matches the user's mental model
- Con: Less established than "harness"; risks marketing flavor
- Con: Doesn't help with the harness-component-level decisions in subsequent ADRs

**Decision rationale**: Option D (this ADR) — use both terms, scoped to context. Honors the technical distinction internally where precision matters; uses approachable language externally where users won't care about the harness/framework debate.

## References

- `wiki/research/prompt-engineering-agent-harness.md` — sharpest definition of harness vs. framework
- `wiki/research/caleb-agent-harness.md` — three-era evolution (prompt → context → harness engineering)
- `wiki/research/py-harness-engineering.md` — harness engineering as a formal discipline; "if you're not the model, you're the harness"
- `wiki/research/simon-scrapes-agentic-os.md` — "Agentic OS" as the user-facing framing alternative
