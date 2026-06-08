---
title: "Memory 2.0 & Auto Dream (Nate Herk, 2026)"
type: research
source: "raw/transcripts/ — multiple Nate Herk 2026 videos"
ingested: 2026-06-08
tags: [aios, memory, auto-dream, context, consolidation, claude-code]
status: ingested
attribution: "Nate Herk | AI Automation (YouTube), 2026 videos"
related: [llm-wiki-pattern, claude-mem, nate-herk-ai-os, memory-architecture-alternatives]
---

# Memory 2.0 & Auto Dream (Nate Herk, 2026)

## TL;DR

Claude Code shipped **Auto Dream** — a background sub-agent that runs on a schedule or session-count threshold to consolidate, prune, and compact memory `.md` files without touching code. Layered on top of the existing Auto Memory write/inject system, it establishes a three-tier memory architecture: active session → auto-recorded memory files → background consolidation. Nate also surfaces the **three-layer CC memory model** (user-level, extracted, team-sync) from a source-code leak, and separately demonstrates practical workarounds for cross-session memory continuity before native persistent memory ships. For the startup-framework, the critical question is: does Auto Dream replace our governed in-wiki consolidate pass, or does it operate on a different surface? The answer is both — different surfaces — and the framework should govern its own wiki while letting Auto Dream handle the smaller `.md` memory files.

## New Claude Code primitives

**[NEW] Auto Dream** — A background sub-agent (trigger: time interval, e.g. every 12 hours, OR session-count threshold, e.g. every 300 sessions) that consolidates, prunes, and refreshes Claude's memory `.md` files. Activated via `/memory` menu with a global toggle and per-project file selection. Manual trigger: `/dream` or natural language. Status visible in the CC status line as "dreaming." Operates in three phases: gather session info → read current memory files → run a consolidation/pruning prompt → write back. Touches only `.md` memory files, never code.
- Why it matters to us: it is the platform's answer to memory rot — the same problem our sf-wrap/sf-note/sf-recall trio partially solves for sessions. But it runs on `.md` memory files, not our full project wiki. We must decide which surface Auto Dream owns and which the framework governs.

**[NEW] /memory slash command (UI menu)** — A built-in CC command that opens a memory management panel showing: auto dream on/off toggle, last-ran timestamp, view/edit/restore memory file changes, and a per-file diff of what was added or removed.
- Why it matters to us: gives the founder direct visibility into what Auto Dream changed, which is the minimal transparency needed before trusting an opaque background process with memory files. The diff view is the control surface.

**[NEW] Persistent Memory across sessions (managed agents, early access)** — Memory that survives across managed agent sessions at the agent level, not just the session level. Distinct from Auto Dream; applies to cloud-hosted agents, not local CC sessions.
- Why it matters to us: when this ships broadly it changes what we need to manually manage in sf-wrap/sf-recall. Track its GA date.

**[NEW] Three-layer CC memory model (source code)** — Source confirms three memory layers: user-level (explicit writes), extracted memories (autonomous CC extractions), and team memory synchronization (cross-session/cross-agent state sharing). The extracted layer in particular is opaque — the founder likely has auto-extracted memories they did not author.
- Why it matters to us: the recall skill should surface which layer a memory lives in. Pruning auto-extracted noise from the extracted layer is a distinct maintenance action from pruning user-authored notes.

**[NEW] Session-count trigger type** — Auto Dream can fire every N sessions (e.g., every 300 sessions) as an alternative to wall-clock intervals. This is also a general trigger concept applicable to any cadence task.
- Why it matters to us: for a solo founder with irregular work cadence, session-count triggers are more semantically correct than wall-clock crons for maintenance tasks (memory compaction, wiki lint).

## Techniques worth adopting

**Three-layer memory architecture.** Layer 1 = active coding session. Layer 2 = auto memory (records decisions, patterns, project/user context into `.md` files). Layer 3 = auto dream (background consolidation sub-agent). The framework has layers 1 and 2 via sf-wrap/sf-note/sf-recall. Layer 3 is missing entirely. This is directly implementable now without waiting for native Auto Dream to roll out broadly: a skill that spawns a sub-agent, applies the dream-prompt pattern, and writes back to memory files.

**Dream prompt pattern.** Nate's inferred dream prompt: "You are performing a dream — a reflective pass over your memory files. Synthesize what you have learned recently into durable, well-organized memories so future sessions can orient quickly. Keep under a line limit; it is an index, not a dump. Link to memory files with one-line descriptions; do not copy full memory into it." This is directly adoptable as the framework's own memory-compaction prompt for the governed in-wiki consolidate pass.

**"Index not a dump" constraint.** The dream prompt enforces a hard line-count ceiling and forbids copying full memory inline — the output must be pointers with one-line descriptions. The framework's MEMORY.md and session notes currently trend toward appending full context. Enforcing this in sf-note and sf-wrap output prompts keeps memory lean from the start and reduces the compaction burden later.

**Frankensteined persistent memory via session logs.** Before native persistent memory ships: have the agent write structured logs of what it did each session and point subsequent sessions at those logs via system-prompt injection. The framework already has the structural pieces (wrap/note/recall); formalizing an append-only log format and injecting it at SessionStart via the wake-up hook closes the gap for cloud-hosted or managed agents.

**Background sub-agent for memory ops.** Auto Dream launches a sub-agent, not the main thread, so consolidation work is non-blocking. The CC status line shows "dreaming" — the main session is not interrupted. Adopt this pattern for any framework memory-maintenance skill: spawn a sub-agent, write back the result, surface a one-line status, do not block the session.

**Session-count trigger for cadence tasks.** Track a session counter in the project memory file. Fire heavier maintenance tasks (full memory compaction, wiki sync, permission re-audit) every N sessions rather than on every SessionStart. Prevents startup bloat as project age grows.

## How this informs the framework

### Pillar 1 — Governable wiki = SSOT: do NOT cede to opaque native Auto Dream

KEEP. The governed in-wiki consolidate pass (a planned CADENCE primitive) is the framework's answer to memory rot on the full project wiki, and it must remain under explicit founder control. Auto Dream operates on `.md` memory files (small, CC-managed), not on the structured wiki pages that contain decisions, research, and roadmap state. These are different surfaces.

The risk of conflating them: Auto Dream consolidating the project wiki without the founder's review could silently overwrite decisions, prune cross-links, or corrupt the log.md chronological invariant. The positioning spec at `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md` is explicit that the wiki is the governable SSOT — "control the truth, leverage the muscle." Auto Dream is muscle; the wiki is truth.

Verdict: ADOPT Auto Dream for the small CC memory files (MEMORY.md, extracted memories). KEEP the governed in-wiki consolidate pass for everything under `wiki/`. Do not route wiki pages through Auto Dream.

### Pillar 4 — Governed in-wiki consolidate pass as the controllable answer to Auto Dream

ADOPT + BUILD. The dream-prompt pattern (index not a dump; synthesize, prune, link; keep under a line limit) is exactly the prompt the framework's consolidate pass should use. The three-phase sub-agent pattern (gather → read → consolidate → write back) is directly implementable with existing CC primitives.

The session-count trigger concept (fire compaction every N sessions, not every session) solves the SessionStart bloat problem as projects age — add a session counter to the project memory file and gate the full compaction pass behind it.

REBUILD: The existing sf-wrap/sf-note/sf-recall approach handles session-scoped memory. It needs a layer 3: a governed consolidation skill that runs asynchronously, uses the dream-prompt pattern, and writes back to the wiki (not just session files) under explicit founder approval (view the diff before accepting, analogous to the `/memory` UI's diff view).

Cross-links: [[claude-mem]] covers the existing memory file conventions this would build on. [[memory-architecture-alternatives]] covers the design space. [[llm-wiki-pattern]] is the underlying wiki-as-SSOT argument.

## Tensions / open questions

1. **Auto Dream scope boundary.** Does Auto Dream have any mechanism to be told "do not touch these files"? If Auto Dream can be scoped to only the CC-managed MEMORY.md and excluded from wiki/, the two systems coexist cleanly. If not, the framework must document "do not enable Auto Dream for your wiki directory" as an explicit safety instruction.

2. **Diff review requirement.** The `/memory` UI shows a diff before/after each Dream run. Should the framework require founder review of every Auto Dream diff before it is accepted, similar to how sf-wrap requires explicit session commit? Or is auto-accept appropriate for the small CC memory files?

3. **Session counter implementation.** Tracking session count in a memory file is straightforward but introduces a new write dependency at SessionStart. Is this a hook responsibility or a skill responsibility? What happens if the count file is corrupted or missing?

4. **Layer 3 triggers for the in-wiki consolidate pass.** Time-based (weekly) vs. session-count-based (every N sessions) vs. size-based (when any wiki section exceeds a line-count threshold) — or a combination. The right answer likely depends on how frequently the founder actually works in the project.

5. **Extracted-memory visibility gap.** The source-confirmed three-layer model includes an "extracted memories" tier that CC populates autonomously. The framework has no tooling to surface, audit, or prune this layer. It is an invisible accumulation surface that could affect sf-recall results without the founder knowing.

## Quotes worth preserving

> "it basically takes all of this different information that goes into your memory.md file. When it does its Auto Dream, it merges them, it prunes them, it refreshes them, and it compacts things and then all of the different memory files are a lot cleaner"

> "I basically just get to reset and it feels like I didn't reset because I already have all that context."

> "The architecture is clearly built to support decomposition, splitting work across multiple agents that can run in parallel. There are even concepts in the source for background tasks, work that continues while you're focused on something else."

## Source videos

- `nate-herk-claude-code-just-dropped-memory-20` — primary source; Auto Dream and /memory command
- `nate-herk-i-tested-claudes-new-managed-agents-what-you` — Frankensteined persistent memory, session logs workaround
- `nate-herk-claude-code-source-code-just-leaked-8-things` — three-layer memory model (user/extracted/team-sync), Daemon mode
- `nate-herk-how-to-manage-your-claude-limits-better-than` — session-chaining pattern, 120k threshold discipline
- `nate-herk-the-one-habit-that-doubles-your-claude-code-s` — session handoff skill, CLAUDE.md mid-session edit safety
- `nate-herk-18-claude-code-token-hacks-in-18-minutes` — self-evolving applied-learning footer as lightweight persistent memory
- `nate-herk-andrej-karpathy-just-10xd-everyones-claude-co` — hot.md recency cache, wiki lint as cadence primitive

## Reference

Positioning spec: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
