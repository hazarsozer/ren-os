---
title: Context Mode (mksglu) — Within-Session Token Efficiency Plugin
type: research
source_url: https://github.com/mksglu/context-mode
source_fetched: 2026-05-28
license: ELv2 (Elastic License v2)
ingested: 2026-05-28
tags: [token-efficiency, tool-sandboxing, session-restore, sqlite, mcp, hooks, claude-code, foreground-research]
status: ingested
related: [nate-herk-best-6-skills, nate-herk-give-me-10-mins, claude-mem]
---

# Context Mode (mksglu)

## TL;DR

Solves the "other half" of the context problem that claude-mem doesn't address: **within-session tool-output bloat**. Sandboxes tool calls in subprocesses so raw output never enters the conversation. 315 KB → 5.4 KB (98% reduction). Per-project SQLite + FTS5 for session continuity across compaction events. 11 MCP tools, 5 lifecycle hooks. **License: ELv2** — important to flag for adoption decisions. **Subprocess isolation, not a daemon** — distinguishes it architecturally from claude-mem.

## Why this matters

Context Mode and claude-mem are complementary, not competing:
- **claude-mem**: cross-session memory (knowledge survives across sessions)
- **Context Mode**: within-session memory (raw output stays out of context)

Both came up in Nate Herk's "best 6 skills" + were specifically called out as solving different halves of the same problem. Together they cover the token-efficiency story end-to-end.

## Problem statement

Tool output bloats the context window:
- A Playwright snapshot: 56 KB
- 20 GitHub issues: 59 KB
- Access logs: 45 KB
- After 30 minutes of real work: **40% of your context is just garbage**

Once the context fills and Claude compacts, you also lose track of what files you edited, what tasks were in progress, what your last prompt was.

## How it works — four mechanisms

1. **Sandboxing**: Tool calls (Bash, Read, WebFetch, Playwright, etc.) execute in sandboxed subprocesses. Raw output stays in the subprocess; only a compact summary returns to the context window. **315 KB → 5.4 KB (98% reduction).**

2. **Session persistence (SQLite + FTS5)**: Every file edit, git operation, task, error, and user decision tracked in a per-project SQLite DB with FTS5. On compaction, events are indexed (not dumped back) and retrieved via BM25 search.

3. **Code-first analysis**: Instead of reading 50 files to count functions, agents write scripts that return only results. Shifts work to the subprocess.

4. **Routing enforcement**: PreToolUse hook can block dangerous commands before execution.

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  Claude Code session                                       │
│   │                                                         │
│   ├── PreToolUse hook   → blocks dangerous commands         │
│   ├── PostToolUse hook  → captures structured events       │
│   ├── PreCompact hook   → builds resume snapshot           │
│   ├── SessionStart hook → restores state from snapshot     │
│   └── UserPromptSubmit  → captures decisions/corrections   │
│   ↓                                                         │
│   ctx_execute / ctx_execute_file / ctx_batch_execute       │
│       ↓                                                     │
│   ┌────────────────────────────────┐                      │
│   │ Sandboxed subprocess            │                      │
│   │   (Node.js or Bun)              │                      │
│   │   - Tool actually runs here     │                      │
│   │   - Raw output stays here       │                      │
│   │   - Compact summary returned    │                      │
│   └────────────────────────────────┘                      │
│       ↓                                                     │
│   ┌─────────────────────────────────────────┐             │
│   │ Per-project SQLite                       │             │
│   │   - FTS5 indexed event tables            │             │
│   │   - session_resume snapshot table        │             │
│   │   - file_edits, git_ops, tasks, errors  │             │
│   └─────────────────────────────────────────┘             │
└───────────────────────────────────────────────────────────┘
```

**No long-running daemon.** Subprocess-only isolation. Distinguishes it from claude-mem (which runs a Bun worker on port 37777).

## MCP tools (11 total)

| Category | Tools |
|---|---|
| Sandbox execution | `ctx_execute`, `ctx_execute_file`, `ctx_batch_execute` |
| Knowledge base | `ctx_index`, `ctx_search`, `ctx_fetch_and_index` |
| Utilities | `ctx_stats`, `ctx_doctor`, `ctx_upgrade`, `ctx_purge`, `ctx_insight` |

## Slash commands (Claude Code)

| Command | Function |
|---|---|
| `/context-mode:ctx-stats` | Context savings breakdown, tokens, savings ratio |
| `/context-mode:ctx-doctor` | Runtime diagnostics, hooks, FTS5, plugin registration |
| `/context-mode:ctx-upgrade` | Pull latest, rebuild, migrate cache, fix hooks |
| `/context-mode:ctx-purge` | Permanently delete indexed content |
| `/context-mode:ctx-insight` | Local web UI analytics dashboard (90 metrics) |

## Install path

For Claude Code v1.0.33+:
```
/plugin marketplace add mksglu/context-mode
/plugin install context-mode@context-mode
```

SessionStart hook auto-injects routing. No file written to the project. Verify with `/context-mode:ctx-doctor`.

## System files

- `~/.context-mode/` (or `~/.claude/context-mode`, `~/.codex/context-mode` — platform-specific)
- `sessions/` subdir — session event databases
- `content/` subdir — indexed web pages, markdown, cached fetches
- Per-project: `.claude/`, `.cursor/`, `.github/hooks/` (platform-specific)
- **No port consumed** (subprocess-only)
- `CONTEXT_MODE_DIR` env var to override location

## License: ELv2 (Elastic License v2) — IMPORTANT FLAG

ELv2 is **not fully permissive**. Key restrictions:
- Personal/team use within an organization: **fine**
- Internal development tooling: **fine**
- Offering as a hosted/managed SaaS service: **prohibited**
- Forking to offer a competing managed offering: **prohibited**

For our friend-group framework (internal tool, not a SaaS product): **adoption is unencumbered.** But:
- Document the licensing implication in our `decisions/` ADR
- If we ever commercialize the framework as a service, Context Mode would need replacement or a commercial license

This is different from claude-mem (Apache-2.0, fully permissive). Honesty matters here.

## Platform support and limitations

| Platform | Status |
|---|---|
| Claude Code (v1.0.33+) | Full support, all hooks + slash commands |
| Codex | Mostly supported; `PreCompact` runtime-gated on builds that emit the event |
| Cursor | `SessionStart` hook rejected by Cursor's validator → no session-restore-after-compaction |
| Gemini CLI, Windsurf, OpenClaw, others | Varied support |
| Antigravity, Zed | No hook support → routing relies on manually-copied instruction files (~60% compliance) |

**Other limitations**:
- Node < 22.5 on Linux unsupported
- Aggressive brevity prompts can degrade coding benchmark scores (flagged in README)

## How this informs the framework

### Adopt alongside claude-mem (the two solve different problems)

| Concern | Tool |
|---|---|
| Within-session tool-output bloat | **Context Mode** |
| Cross-session knowledge continuity | **claude-mem** |
| Team-level deliberate synthesis | **Our wiki** |

Three-layer memory stack. All complementary.

### Hook overlap is a real concern

Both Context Mode AND claude-mem register `SessionStart` and `PostToolUse` hooks. Plus our framework's wake-up + consolidate hooks would also touch lifecycle.

**Open question**: in what order do they fire? Does Claude Code chain multiple plugins' hooks? Do we need to test this combination explicitly before recommending both?

Action item: when we write the design doc, document the assumed hook ordering and the test plan to verify it.

### License diversity in our stack

Our recommended stack will likely include:
- Apache-2.0 (claude-mem, frontend-design)
- ELv2 (Context Mode)
- Possibly MIT (Superpowers — TBD)
- Possibly something else (GSD — TBD)

The framework's own license can stay permissive (MIT or Apache). The license diversity of dependencies should be documented in a `LICENSES.md` so friends installing the framework know what they're agreeing to.

### Slash command pattern as a model

Context Mode's slash commands (`/context-mode:ctx-stats`, etc.) follow a `/<plugin>:<command>` namespacing pattern that we should adopt in our own framework's slash commands (`/sf:wake-up`, `/sf:consolidate`, etc.) for clarity in a multi-plugin environment.

### Subprocess isolation as an architectural pattern

Context Mode demonstrates that you can achieve significant token efficiency WITHOUT a long-running daemon (claude-mem's approach). Subprocesses + per-project SQLite is sufficient.

**Implication**: where we have a choice in our own minor capabilities, prefer subprocess-only over daemon. Aligns with our "lightweight harness" thesis.

### The "ctx_index / ctx_search / ctx_fetch_and_index" knowledge base tools

Context Mode includes general-purpose indexed knowledge base MCP tools. This OVERLAPS with what our wiki provides. Need to be careful: are we using these too, or do we keep the wiki separate as the team-knowledge layer?

Likely answer: **separate concerns.** Context Mode's knowledge base is per-developer, per-project, ephemeral (cached web fetches). Our wiki is team-level, durable, deliberate. They don't overlap in scope even though both involve "indexed knowledge."

## Tensions / open questions

1. **Hook ordering with claude-mem + our own hooks** — must verify in actual setup. Both plugins + ours = 3 plugins touching SessionStart and PostToolUse. Need a test plan.
2. **ELv2 license implications** — fine for personal/team use, restricts SaaS distribution. Document this explicitly.
3. **Cursor compatibility gap** — if a friend later switches to Cursor, they lose session-restore after compaction. Mention in onboarding.
4. **Aggressive-brevity prompt risk** — README flags that pushing brevity too hard can degrade reasoning. We need to be careful that our framework's token-efficiency push doesn't fall into this trap.
5. **Slash command namespace clash** — Context Mode uses `/context-mode:`. Our framework will need its own namespace. Pick a short one (e.g., `/sf:`) and document it.
6. **`ctx_insight` 90-metric dashboard** — could be the token dashboard we'd otherwise recommend (Nate Herk's). Investigate whether it's sufficient.
7. **Per-project vs. global storage** — Context Mode uses per-project SQLite; claude-mem uses global. Behavior across multiple projects might differ in non-obvious ways.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Nate Herk Best 6 Skills | Verified Nate's claim (315 KB → 5.4 KB) — checks out per README |
| Nate Herk Prompt Caching | Context Mode's session-restore mechanism is how you get past 30-min sessions falling apart (Nate's specific claim) |
| claude-mem | Both use SQLite + FTS5; both touch SessionStart + PostToolUse hooks; together they cover within-session + cross-session token efficiency |
| Prompt Engineering Harness | Implements harness components #2 (context management) and #8 (lifecycle hooks) at the within-session layer |
| Caleb Agent Harness | The PreCompact + SessionStart restore pattern is exactly Caleb's "loops with fresh clean context" applied at the compaction event |

## Followups (for foreground research continuation)

- Test claude-mem + Context Mode coexistence in a Claude Code session (or find existing community report)
- Read Context Mode hook source to verify ordering behavior
- Look at `ctx_insight` dashboard to see if it replaces the need for Nate's separate token dashboard

## Reference

- GitHub: https://github.com/mksglu/context-mode
- Author: mksglu (handle)
- Fetched: 2026-05-28
- License: ELv2 (Elastic License v2) — NOT fully permissive
- Requires: Claude Code v1.0.33+, Node 22.5+ on Linux (or Bun)
