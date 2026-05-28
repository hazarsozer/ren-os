---
title: Memory Architecture Alternatives — Mem0 / Letta / Zep / LangMem (Comparison)
type: research
sources:
  - https://github.com/mem0ai/mem0
  - https://github.com/letta-ai/letta
  - https://github.com/getzep/zep
  - https://github.com/langchain-ai/langmem
source_fetched: 2026-05-28
ingested: 2026-05-28
tags: [memory, alternatives, mem0, letta, memgpt, zep, langmem, comparison, foreground-research]
status: ingested
related: [claude-mem, llm-wiki-pattern, simon-scrapes-agentic-os]
note: |
  Comparison page covering the major framework-agnostic memory systems we considered
  but did NOT adopt. Useful evidence for the memory-architecture ADR. Captured in a
  single page since each alone wouldn't change the framework's design.
---

# Memory Architecture Alternatives — A Comparison

## TL;DR

The major framework-agnostic memory systems (Mem0, Letta/MemGPT, Zep, LangMem) all target a different problem than ours. They're designed to add memory to **custom agent frameworks** (LangChain, CrewAI, AutoGen, etc.). Our framework targets **Claude Code specifically**, where claude-mem is the Claude-Code-native option with auto-capture via lifecycle hooks. **None of these alternatives displaces claude-mem for our use case.** This page exists to honestly document what we considered and why we picked claude-mem.

## The four alternatives

### Mem0 — "Memory layer you bolt onto your agent framework"

- **Architecture**: Framework-agnostic library — drops into LangChain, CrewAI, AutoGen, or custom loops
- **Specialty**: User preferences + personalization. Core data model is "what this specific user prefers / how they work / what they've asked before"
- **Best for**: Consumer apps where "remember the user" is the feature
- **Trade**: You provide the agent loop; Mem0 just adds memory primitives

### Letta (formerly MemGPT) — "Agent runtime with memory paging"

- **Architecture**: Full agent runtime (not just memory). OS-inspired model: in-context memory + external storage + explicit paging operations between them
- **Pluggable backends**: MongoDB, Weaviate, Mem0, Zep (interestingly — Letta can use Mem0 as its storage layer)
- **Best for**: Autonomous agents needing long-horizon coherence ("yesterday we tried X and it failed")
- **Trade**: Slower per-retrieval but more semantically appropriate context. You commit to Letta as your agent platform, not just a library

### Zep — "Temporal Knowledge Graph for evolving facts"

- **Architecture**: Knowledge-graph-backed memory using a Temporal Knowledge Graph. Tracks entity relationships and how facts evolve over time.
- **Requires**: Neo4j as the graph database
- **Best for**: Agents tracking evolving facts and complex entity relationships (e.g., a CRM agent that needs to know "Sarah used to work at Acme but is now at BetaCo and reports to Mike")
- **Trade**: Significant infrastructure overhead (Neo4j) for power most apps don't need

### LangMem — "Memory for LangChain ecosystem"

- **Architecture**: LangChain-native memory library
- **Best for**: Teams already deep in LangChain that want memory without adopting a separate framework
- **Trade**: LangChain lock-in (which our user explicitly does NOT want — per the framework's stack preferences in CLAUDE.md)

## How they compare on dimensions that matter to us

| Dimension | Mem0 | Letta | Zep | LangMem | **claude-mem** |
|---|---|---|---|---|---|
| Claude Code native | No | No | No | No | **YES** |
| Auto-capture via lifecycle hooks | No | No | No | No | **YES** |
| Requires custom agent loop | Yes | Yes (Letta IS the loop) | Yes | Yes (LangChain) | No |
| Infrastructure overhead | Low | High | Very high (Neo4j) | Medium | Low (SQLite + ChromaDB) |
| Best for "remember the developer's project history" | OK | Good but heavy | Overkill | OK (in LangChain) | **Excellent** |
| License | Apache-2.0 (mostly) | Apache-2.0 | Apache-2.0 (Zep CE) | MIT | Apache-2.0 |
| Active development | Yes | Yes | Yes | Yes | Yes |

## Why claude-mem wins for our framework

1. **Claude Code is our harness, period.** Memory tools designed for "any framework" are over-general for our specific case.
2. **Auto-capture via lifecycle hooks is exactly what we want** — the developer doesn't think about memory; it happens. The framework-agnostic tools require explicit calls.
3. **Two independent practitioner recommendations** (Simon Scrapes + Nate Herk) for claude-mem in a Claude Code context. None of the alternatives have this signal for our specific use case.
4. **Simplest install** — `/plugin install`. Letta + Zep require running services. Mem0 requires manual integration.
5. **The friend group's mental model** matches claude-mem better — they think in terms of "Claude Code sessions," not "agent frameworks."

## When we'd reconsider

If the friend group later builds **a custom agent product** (not a developer tool but a deployed AI service):
- **Mem0**: drop-in addition for personalization features
- **Letta**: if the product is a long-running autonomous agent
- **Zep**: if the product needs entity-relationship modeling (CRM, social, etc.)
- **LangMem**: only if for some reason the project locked into LangChain (our user prefers raw APIs over LangChain per CLAUDE.md — unlikely)

But none of these displace claude-mem for the developer-tooling use case.

## How this informs the framework

### Confirms claude-mem as the memory layer for v1

Honest evaluation: claude-mem is the right tool for our shape of problem. The alternatives target adjacent problems.

### Document this comparison in the memory-architecture ADR

When we write `wiki/decisions/001-memory-architecture.md`, this comparison goes in as "Alternatives considered" — proves we did due diligence and explains why claude-mem won.

### Mem0 might come back later

If our friend group ever builds a personalization-heavy consumer app, Mem0 is the right tool to bolt onto whatever agent framework that app uses. **Different layer of the stack, different decision.**

### Letta + Zep are out-of-scope for the developer-tooling use case

These are agent-product infrastructure, not developer-tooling memory. Out of scope for now.

### Knowledge graphs as a future v3 idea

Zep's temporal knowledge graph IS an interesting pattern for the wiki itself. Our current wiki is a graph of markdown pages with manual links. A future v3 could potentially auto-extract entities and relationships into a knowledge graph layer ON TOP of the wiki. Speculative — not for v1 or v2.

## Open questions

1. **Friend-group product memory choice** — if they pick a product idea later that needs production memory, revisit this comparison in that project's context (not the framework's).
2. **Could claude-mem + Mem0 coexist?** Letta's pluggable architecture suggests Mem0 can be a storage backend for other systems. Claude-mem doesn't expose its storage to other tools — so probably no direct interop. Worth investigating only if needed.
3. **Hybrid memory architectures** — some 2026 articles mention "dual-layer architectures" combining vector and graph memory. Could a future v3 of our framework combine claude-mem (vector) with a Zep-style graph layer? Speculative.

## Connections to prior research

| Prior source | Connection |
|---|---|
| claude-mem | Direct alternative we picked over these |
| Simon Scrapes Agentic OS | His 6-level memory hierarchy listed multiple of these (mem search ≈ Mem0 family, knowledge bases ≈ Letta/Zep) |
| Karpathy LLM Wiki | His thesis — wiki + synthesis > raw retrieval — is the layer above ALL of these tools |

## Reference

- Mem0: https://github.com/mem0ai/mem0
- Letta (MemGPT): https://github.com/letta-ai/letta
- Zep: https://github.com/getzep/zep
- LangMem: https://github.com/langchain-ai/langmem
- Comparative analyses:
  - https://vectorize.io/articles/mem0-vs-letta
  - https://tokenmix.ai/blog/ai-agent-memory-mem0-vs-letta-vs-memgpt-2026
  - https://agentmarketcap.ai/blog/2026/04/10/agent-memory-vendor-landscape-2026-letta-zep-mem0-langmem
- Fetched: 2026-05-28
