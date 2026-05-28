---
title: claude-mem (thedotmack) — Cross-Session Memory Plugin
type: research
source_url: https://github.com/thedotmack/claude-mem
source_fetched: 2026-05-28
license: Apache-2.0
version_at_capture: v6.5.0
ingested: 2026-05-28
tags: [memory, plugin, cross-session, sqlite, chromadb, hooks, mcp, claude-code, foreground-research]
status: ingested
related: [nate-herk-best-6-skills, simon-scrapes-agentic-os, llm-wiki-pattern]
---

# claude-mem (thedotmack)

## TL;DR

The most-recommended cross-session memory plugin for Claude Code. **Apache-2.0 licensed**, ~46–89K GitHub stars (depending on the snapshot — trended explosively Feb 2026). Architecture: 5 lifecycle hooks + worker service on port 37777 (Bun runtime) + SQLite (FTS5) + ChromaDB (hybrid vector/keyword) + local ONNX embeddings (all-MiniLM-L6-v2). Auto-captures session events, compresses via Claude's agent SDK, injects relevant context into future sessions via MCP tools with 3-layer progressive disclosure retrieval. Works across Claude Code, Cursor, Codex, Gemini, Windsurf, OpenClaw, Hermes, Copilot, OpenCode.

## Why this matters to the framework

Two independent practitioner recommendations (Simon Scrapes + Nate Herk). Direct prior art for the cross-session memory problem. **This is the plugin we likely adopt for individual-level memory, with our wiki layered on top for team-level synthesis.**

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code session                                         │
│   ↑                                                          │
│   │ MCP tools (4 tools, 3-layer disclosure: search→         │
│   │ timeline → full observation)                            │
│   ↓                                                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ claude-mem worker service (port 37777, Bun runtime)  │  │
│  │  - HTTP API                                           │  │
│  │  - Web viewer UI                                      │  │
│  │  - Lifecycle hooks: SessionStart, UserPromptSubmit,   │  │
│  │    PostToolUse, Stop, SessionEnd (+ pre-install hook) │  │
│  └─────────┬──────────────────────────────────────────────┘  │
│             │                                                  │
│             ▼                                                  │
│   ┌─────────────────────────────────┐                        │
│   │ SQLite (FTS5 full-text search)  │                        │
│   │   - sessions                     │                        │
│   │   - observations                 │                        │
│   │   - summaries                    │                        │
│   └─────────────────────────────────┘                        │
│             │                                                  │
│             ▼                                                  │
│   ┌─────────────────────────────────┐                        │
│   │ ChromaDB                          │                        │
│   │   - Vector embeddings (ONNX,      │                        │
│   │     all-MiniLM-L6-v2, local)      │                        │
│   │   - Hybrid keyword + semantic     │                        │
│   └─────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

**Key insight**: it IS a daemon (worker service on port 37777, Bun runtime). We said "no daemon for our framework" — but claude-mem's daemon is part of claude-mem itself, not part of our framework. We can use it as an external dependency without violating our design principle. **The wiki layer remains daemon-free.**

## How it operates

1. **Capture**: Lifecycle hooks intercept tool calls, prompt submissions, session events
2. **Compress**: Observations compressed via Claude's agent SDK (semantic summaries)
3. **Index**: Stored in SQLite (FTS5) + ChromaDB (vectors)
4. **Retrieve**: 3-layer progressive disclosure (search index → timeline → full observation)
5. **Inject**: Relevant context fed back into future sessions via MCP

## Install path

**Correct (Claude Code plugin marketplace)**:
```
/plugin marketplace add thedotmack/claude-mem
/plugin install claude-mem
```

Or via the auto-installer:
```
npx claude-mem install
```

**Incorrect** (won't work — only installs the SDK, no hooks):
```
npm install -g claude-mem
```

The README explicitly warns about this. Nate Herk's transcript flagged the same trap.

## Files & ports it creates

- `~/.claude-mem/settings.json` — config (auto-generated on first run)
- `~/.claude/plugins/marketplaces/thedotmack/` — plugin install location
- Port 37777 — worker service HTTP API (configurable)

## Configurable settings

- AI model used for summarization
- Worker port
- Data directory
- Log level
- Context injection settings (what gets pulled into new sessions)
- `CLAUDE_MEM_MODE` — multiple workflow modes; supports localization (e.g., `code--zh`, `code--ja`)

## Dependencies

- Node.js 18.0.0+
- Bun (auto-installed if missing)
- uv (for vector search components)

## Privacy: `<private>` tags

The plugin honors `<private>` tags to exclude content from storage. Useful pattern.

## License: Apache 2.0

Permissive license. Confirmed by README — Augment Code's blog post incorrectly labeled it AGPL; the actual repo is Apache-2.0. License chosen explicitly to enable commercial integration and forking.

> "Durable agentic memory should be easy to embed in developer tools, local agents, MCP servers, enterprise systems, robotics stacks, and production agent harnesses."

Implication for us: adoption is unencumbered.

## How this informs the framework

### Likely decision: adopt claude-mem at the individual layer

Two independent practitioner votes + Apache-2.0 license + battle-tested at 46K+ stars + active maintenance (v6.5.0) + multi-platform support (so it works for any tool a friend later uses, not just CC). The case to adopt is strong.

**Adoption pattern**:
- Each developer's individual Claude Code sessions use claude-mem for cross-session continuity (auto-captures their work, recalls relevant past observations)
- Our framework's wiki layer sits ON TOP, holding team-level synthesis (decisions, patterns, project knowledge) that claude-mem doesn't address

### Two-layer memory architecture (finalizing)

| Layer | Tool | Scope | What it holds |
|---|---|---|---|
| **Individual recall** | claude-mem | Per-developer, per-session | Compressed observations, file edits, tool calls, decisions made during sessions |
| **Team synthesis** | Our wiki | Friend group studio | ADRs, patterns, project sub-wikis, deliberate team knowledge |

These don't overlap. claude-mem is captured automatically; the wiki is curated deliberately. Both run together.

### Where claude-mem's daemon goes in our "no daemon" rule

Restating: **our framework adds no daemons of its own.** Plugins our framework recommends (claude-mem, Context Mode, etc.) may have their own daemons. That's the plugin's concern, not the framework's.

### Skill design alignment

claude-mem's 3-layer progressive disclosure retrieval (search → timeline → full detail) matches our wiki's index-first approach exactly. The pattern is converging across multiple sources.

### `<private>` tag pattern — adopt for the wiki

Useful primitive: explicit content exclusion via inline tags. Adopt for wiki pages where sections shouldn't be ingested into AI context (e.g., personal notes, secrets-adjacent content). Easy to implement: linter rule + wake-up hook respects the tag.

### Coexistence question still open

The README doesn't explicitly address how claude-mem behaves alongside other plugins that touch the same lifecycle hooks. If we also wire SessionStart for our wake-up skill, do they conflict? Need to verify by reading the actual hook implementations or testing.

## Tensions / open questions

1. **Hook ordering with our wake-up skill** — claude-mem uses SessionStart. If we also add SessionStart for wake-up, what's the order? Does claude-mem inject FIRST and we add on top? Need to verify against actual hook code.
2. **`CLAUDE_MEM_MODE` localization** — interesting that it supports per-language modes (`code--zh`, `code--ja`). Not relevant for us, but tells us about the project's scope and team.
3. **Port 37777 conflict** — if a friend runs other dev services on that port, will it clash? Configurable but document the default.
4. **What gets captured by default?** — "automatic operation" without hook-level granularity might capture more than we want. Need to evaluate whether claude-mem's defaults align with our token-efficiency goal or whether we need to tune `context injection settings`.
5. **Storage growth** — no mention of caps or pruning in the README. Long-running projects could accumulate large SQLite + ChromaDB stores. Need to investigate.
6. **AGPL vs. Apache confusion** — Augment Code's blog claimed AGPL; the README claims Apache-2.0. Confirmed Apache from the repo itself, but worth noting the inconsistency exists in third-party coverage.
7. **What does the worker service do exactly?** — HTTP API on port 37777 + web viewer. Need to look at the API surface to understand what we can/can't integrate with. (Could be useful for the framework to query.)

## Connections to prior research

| Prior source | What claude-mem confirms / differs |
|---|---|
| Simon Scrapes Agentic OS | His L3 "semantic search" recommendation maps directly to claude-mem (he mentioned it by name) |
| Nate Herk Best 6 Skills | Detailed practitioner recommendation; this fetch verifies the architectural claims |
| Karpathy LLM Wiki | claude-mem auto-generates folder-level CLAUDE.md files — an automated, compression-based variant of the wiki pattern. Differs from Karpathy in that summaries replace synthesis. Our wiki goes deeper on synthesis. |
| Prompt Engineering Harness | claude-mem implements the 9-component checklist's #6 (session persistence) and #8 (lifecycle hooks) layers |
| Caleb Agent Harness | claude-mem operationalizes "fresh context per iteration" by feeding curated past observations rather than relying on Claude Code's broken summarization |

## Followups (for foreground research continuation)

- **Read the actual hook source code** to understand exact capture behavior and ordering with other plugins
- **Look at the `mem-search` skill source** to see how the 3-layer disclosure is implemented (worth borrowing patterns)
- **Investigate storage growth / pruning behavior**
- **Test claude-mem alongside Context Mode** — both touch lifecycle hooks; do they coexist cleanly?

## Reference

- GitHub: https://github.com/thedotmack/claude-mem
- Author: thedotmack (handle); active maintainer
- Fetched: 2026-05-28
- Version at capture: v6.5.0
- License: Apache-2.0
- Star count at search time: 46–89K (recent rapid growth)
