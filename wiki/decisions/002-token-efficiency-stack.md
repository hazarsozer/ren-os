---
title: "ADR-002: Token-Efficiency Stack"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [claude-mem, context-mode, memory-architecture-alternatives, nate-herk-best-6-skills, nate-herk-give-me-10-mins, simon-scrapes-agentic-os, caleb-agent-harness, lean-ctx]
amendments:
  - "2026-05-28: added lean-ctx as Option E in Alternatives Considered + sunset-review triggers"
  - "2026-05-28: scope clarification — wiki is PER-FRIEND-MACHINE (personal deliberate synthesis), not a shared/team artifact. Inter-Claude messaging if any happens via Agent Mail (see ADR-018), not via shared wiki state."
affects-components: [memory, hooks, install, onboarding]
supersedes: none
---

# ADR-002: Token-Efficiency Stack

## Context

Our north-star design constraint, established in the brainstorming opening, is **token efficiency**. The user explicitly chose "token/rate bloat from bad tools" as the #1 pain point to fix.

The research surfaced two complementary token-efficiency problems and two specific tools that address them in the Claude Code ecosystem:

1. **Within-session token bloat** — raw tool output (Playwright snapshots, GitHub issues, access logs) dumps into the context window. Per Nate Herk's measurements, 30 minutes of real work fills ~40% of the context window with garbage. Anthropic's auto-compaction summarizes when full, but as Caleb's source documents, **summarization is the broken thing harness engineering replaces** — the agent's compression ability becomes the bottleneck, leading to tasks declared "done" when they aren't.

2. **Cross-session knowledge loss** — every new session re-explains the project. Per Nate Herk, this costs ~10 minutes and thousands of tokens per session start. Claude Code's built-in CLAUDE.md mechanism helps but is shallow.

We need to address both problems. Building either tool ourselves would be substantial scope — and **both already exist as community plugins with strong adoption signals** (Nate Herk's "Best 6 Skills" + Simon Scrapes' Agentic OS source both recommend the same tools).

The framework-agnostic memory alternatives (Mem0, Letta/MemGPT, Zep, LangMem) target a different problem: adding memory to custom agent frameworks. They're poor fits for our Claude-Code-native use case.

## Decision

The configuration's token-efficiency strategy is to **adopt two existing best-in-class plugins** rather than building memory infrastructure ourselves:

**Within-session efficiency: Context Mode (mksglu/context-mode)**
- Sandboxes tool calls in subprocesses; raw output never enters the conversation
- 315 KB raw → 5.4 KB returned to Claude (98% reduction documented in README)
- Per-project SQLite + FTS5 for session-restore across compaction events
- Subprocess-only isolation; **no daemon required**
- ELv2 license — fine for personal/team use; restricts SaaS distribution (document in `LICENSES.md`)

**Cross-session continuity: claude-mem (thedotmack/claude-mem)**
- 5 lifecycle hooks auto-capture tool usage, file edits, decisions across sessions
- SQLite (FTS5) + ChromaDB + local ONNX embeddings (all-MiniLM-L6-v2)
- 4 MCP tools with 3-layer progressive disclosure retrieval (search index → timeline → full observation)
- Runs a Bun worker on port 37777 (claude-mem's daemon, not ours)
- Apache-2.0 license
- ~46–89K GitHub stars, two independent practitioner recommendations

These plugins coexist with each other AND with the configuration's own wiki layer (covered in ADR-004). They occupy **different layers** of the memory architecture; they don't compete.

**Memory architecture map (corrected framing 2026-05-28):**

| Layer | Tool | Scope | What it holds |
|---|---|---|---|
| Within-session efficiency | Context Mode | Per-friend, per-project, per-session | Sandboxed tool output, compacted events |
| Cross-session continuity | claude-mem | Per-friend, across sessions | Compressed observations, file edits, decisions |
| **Personal deliberate synthesis** | Our wiki (see ADR-004) | **This friend's local machine** | Deliberate ADRs, patterns, lessons for THIS friend's work |
| Wiki search at scale (v2) | qmd (deferred, see ADR-005) | This friend's wiki when >200 pages | Hybrid BM25 + vector + LLM rerank |
| **(optional) Inter-Claude messages** | MCP Agent Mail (see ADR-018) | Friend-to-friend communication, **not shared state** | Per-friend inbox; ephemeral messages between friends' Claudes |

The first three are **all active in v1**. qmd is a v2 upgrade path that doesn't require architectural changes to add later (per ADR-005). The fifth (inter-Claude messaging) is opt-in per ADR-018 and is messaging-not-shared-state.

**Critical scope correction**: every layer above is **per-friend, on that friend's machine**. There is no shared wiki across the friend group. Friends communicate via Agent Mail messages (if they opt in), not by writing to each other's wikis.

## Consequences

**Easier:**
- We don't build memory infrastructure ourselves — substantial scope reduction
- Each layer is independently maintained by domain specialists (mksglu, thedotmack, us)
- Failure modes are isolated: if claude-mem misbehaves, Context Mode still works, and vice versa
- License diversity is contained per plugin

**Harder:**
- We take on a **license diversity burden** — Apache-2.0 (claude-mem) + ELv2 (Context Mode) need to be documented in stack `LICENSES.md` so friends know what they're agreeing to
- We take on a **dependency-trust burden** — each plugin needs to stay actively maintained; if either project rots, we have a transition decision
- We need to verify **hook coexistence** — both plugins touch SessionStart and PostToolUse hooks (see ADR-010 for hook ordering coordination)
- Context Mode requires Node 22.5+ on Linux; claude-mem requires Node 18+ and Bun (auto-installed). Friends installing the stack need a Node toolchain.

**Now impossible:**
- Replacing claude-mem with the configuration's own minimal alternative without significant rework — we're committing to the plugin's API surface
- Distributing the configuration as a hosted SaaS without replacing Context Mode (ELv2 restriction)

**Sunset review trigger conditions** (when to revisit this ADR):
- Either plugin becomes unmaintained or substantially regresses
- Claude Code's built-in memory becomes competitive enough to make claude-mem redundant
- A friend's product requires Mem0/Letta/Zep at the application layer (different decision, not this ADR)
- We get burned by hook collisions despite ADR-010's coordination
- **(amended 2026-05-28)** Context Mode's ELv2 license becomes a friction point (e.g., friend group commercializes the framework as a hosted service)
- **(amended 2026-05-28)** lean-ctx demonstrates stable production use across the friend group AND its knowledge-graph memory proves materially better than claude-mem's vector retrieval for our actual usage patterns
- **(amended 2026-05-28)** lean-ctx's built-in budget controls + token-tracking dashboard become valuable enough to displace Context Mode + Nate Herk's separate dashboard recommendation

## Alternatives considered (with reasoning for rejection)

### A) Build our own memory layer ourselves

**Considered shape**: Hooks + a small SQLite store + simple keyword retrieval, all in our configuration.

**Why rejected**: Reinventing what claude-mem already does well. Per the research, claude-mem has 46–89K stars, two independent practitioner recommendations, active maintenance, and an Apache-2.0 license. Building a worse version of it is a scope mistake.

### B) Adopt only claude-mem (skip Context Mode)

**Considered shape**: claude-mem alone for cross-session; live with within-session bloat.

**Why rejected**: claude-mem doesn't solve the within-session problem. After 30 minutes per Nate Herk's measurements, the context window is 40% garbage. Sessions falling apart at 30 minutes is a real friction we'd be ignoring.

### C) Adopt only Context Mode (skip claude-mem)

**Considered shape**: Context Mode for within-session; rely on Claude Code's native CLAUDE.md + auto-memory for cross-session.

**Why rejected**: Claude Code's native cross-session is shallow per the user's stated pain point. Building cross-session continuity on top of just Context Mode would be substantial work for a problem claude-mem already solves.

### D) Adopt Mem0 / Letta / Zep / LangMem instead of claude-mem

**Considered shape**: One of the framework-agnostic memory systems as the cross-session layer.

**Why rejected**: These target "add memory to your custom agent framework," not "auto-memory for Claude Code sessions." They require manual integration or a separate runtime (Letta) or significant infrastructure (Zep's Neo4j). claude-mem is Claude-Code-native and auto-captures via lifecycle hooks — the better fit by an order of magnitude. See `wiki/research/memory-architecture-alternatives.md` for the detailed comparison.

### E) Adopt qmd at v1 (now, not as a v2 upgrade)

**Considered shape**: Use qmd as the primary cross-session memory tool.

**Why rejected**: qmd is a wiki search engine, not a session-continuity tool. It targets the wiki layer specifically (covered in ADR-005). Not a substitute for claude-mem.

### F) Adopt lean-ctx instead of Context Mode (added 2026-05-28)

**Considered shape**: Use lean-ctx (yvgude, Apache-2.0 + MIT) as the within-session efficiency layer instead of Context Mode (mksglu, ELv2). lean-ctx is more comprehensive (62 MCP tools vs 11), uses tree-sitter AST compression across 21 languages, ships its own knowledge-graph memory layer with temporal validity, includes a browser dashboard with budget profiles + throttling, and is a single Rust binary.

**Why rejected for v1** (per ecosystem-survey discussion):
- Newer (4 months / 2.2K stars) than Context Mode at our scale of trust
- Larger MCP surface (62 tools) could affect prompt cache prefix (per ADR-008 constraint)
- lean-ctx's knowledge-graph memory layer collides architecturally with claude-mem's cross-session role + our wiki's team-knowledge role — three memory layers risk stepping on each other
- Context Mode's ELv2 SaaS restriction is theoretical at the friend-group level for v1; not an active blocker

**Future swap triggers**: see sunset-review conditions above (added in this same amendment). Architecturally, lean-ctx is a worthy swap candidate; its risks are about timing not direction.

## References

- `wiki/research/claude-mem.md` — detailed architecture of the adopted cross-session memory tool
- `wiki/research/context-mode.md` — detailed architecture of the adopted within-session efficiency tool
- `wiki/research/memory-architecture-alternatives.md` — comparison with Mem0 / Letta / Zep / LangMem
- `wiki/research/nate-herk-best-6-skills.md` — practitioner recommendations for both
- `wiki/research/nate-herk-give-me-10-mins.md` — operational details on prompt caching that interact with this stack
- `wiki/research/simon-scrapes-agentic-os.md` — 6-level memory hierarchy that maps to this stack's layers
- `wiki/research/caleb-agent-harness.md` — "summarization is broken" argument for replacing default compaction behavior
