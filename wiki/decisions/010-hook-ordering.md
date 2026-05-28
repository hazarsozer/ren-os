---
title: "ADR-010: Hook Ordering Coordination — Multi-Plugin Lifecycle Coexistence"
status: accepted
date: 2026-05-28
sunset-review: 2026-08-28
references-pages: [claude-mem, context-mode, superpowers, ralph, prompt-engineering-agent-harness]
affects-components: [hooks, install, onboarding, plugin-coexistence, troubleshooting]
relates-to: [006-curated-stack, 008-wake-up-hook, 009-consolidate-via-wrap]
---

# ADR-010: Hook Ordering Coordination — Multi-Plugin Lifecycle Coexistence

## Context

ADR-006 commits us to a stack where multiple plugins touch Claude Code's lifecycle hooks:

| Plugin | SessionStart | UserPromptSubmit | PostToolUse | PreCompact | Stop / SessionEnd |
|---|---|---|---|---|---|
| **Our configuration** (ADR-008/009) | YES (wake-up) | — | — | — | NO (per ADR-009; uses /wrap) |
| **claude-mem** | YES | YES | YES | — | YES (SessionEnd) |
| **Context Mode** | YES | YES | YES | YES | — |
| **Superpowers** | (skill activation, not hooks) | — | — | — | — |
| **Ralph** (documented-not-bundled per ADR-006) | — | — | — | — | YES (Stop) |

Hook ordering matters because:

1. **Multiple plugins on the same hook compete for order.** Whichever runs first sees pristine state; whichever runs last sees state modified by the others.
2. **Order affects correctness.** E.g., does our wake-up's wiki context arrive in the conversation before or after claude-mem's auto-injected past observations? Either order is OK but they should be predictable.
3. **Failures cascade.** A misbehaving hook in one plugin can break the lifecycle for downstream hooks.
4. **Debug surface is broad.** When something breaks, the user needs to know which plugin's hook was responsible.

Claude Code's documentation on hook ordering at the time of this ADR is partial — we should design assuming ordering may not be globally configurable and our hooks must be robust to other plugins running before or after us.

## Decision

**This ADR defines the coordination strategy across plugins, not Claude Code's enforcement mechanism.** Our framework's own hooks are designed to coexist with claude-mem, Context Mode, and (when installed) Ralph.

### The order we PREFER (and design for, but don't strictly require)

For the **default v1 stack** (Superpowers + Skill Creator + claude-mem + Context Mode + our wake-up):

**SessionStart (preferred order):**
1. **Context Mode** — restores its session_resume snapshot first (this is its main value)
2. **claude-mem** — injects relevant past observations second (builds on restored state)
3. **Our wake-up** — injects wiki context last (sits on top of both)

Reasoning: Context Mode restores within-session continuity (compacted snapshots), claude-mem adds cross-session continuity, our wake-up adds team-level context. Most specific → most general layering.

**UserPromptSubmit (preferred order):**
1. **Context Mode** — captures user decision/correction first
2. **claude-mem** — captures for cross-session

(Our framework adds no hook here in v1.)

**PostToolUse (preferred order):**
1. **Context Mode** — sandboxes the tool output, captures structured event
2. **claude-mem** — observes the (now-summarized) event

Reasoning: Context Mode's whole job is to compress raw output BEFORE it ends up anywhere else. Running first means claude-mem doesn't end up storing 56KB Playwright dumps.

**PreCompact:**
- **Context Mode** — builds resume snapshot (only Context Mode uses this hook in our stack)

**Stop / SessionEnd:**
- **claude-mem** — runs its SessionEnd capture
- **Our framework** — does nothing (per ADR-009; /wrap is the user-invoked path)
- **Ralph** (if installed) — intercepts Stop and re-feeds the prompt. **If Ralph is running, claude-mem's SessionEnd may not fire** because the session doesn't actually end. This is a known limitation per ADR-006's "documented-not-bundled" status for Ralph.

### Our hook design rules (robustness)

Our SessionStart wake-up hook MUST:

1. **Be idempotent.** Running it twice in a row must be safe (no duplicate context injection).
2. **Be order-insensitive.** Whether it runs before or after claude-mem's SessionStart shouldn't change correctness — only the ergonomic of "which context shows up first."
3. **Fail gracefully.** If reading the wiki fails (file system error, malformed index), log to stderr and let the session start without wake-up rather than killing the session.
4. **Be deterministic.** Same cwd + same wiki state → same output. Important for testability.
5. **Not modify shared state outside its concern.** No writing to other plugins' SQLite databases, no touching their settings, no editing CLAUDE.md (per ADR-008).

### Coexistence with Ralph

Per ADR-006, Ralph is documented-not-bundled. When a user installs Ralph on demand:

- **Ralph's Stop hook becomes the active session-end behavior.** Session doesn't actually end; prompt re-feeds.
- **Our `/wrap` is unaffected.** It's a slash command, not a hook — fires when the user calls it, regardless of Ralph being installed.
- **claude-mem's SessionEnd capture may not run** during Ralph loops. claude-mem's PostToolUse + UserPromptSubmit hooks still capture during the loop; SessionEnd only fires when the loop terminates or `/cancel-ralph` is called.
- **Recommendation in the framework's docs**: when running long Ralph sessions, manually call `/wrap` at meaningful checkpoints to harvest learnings rather than relying on Ralph's terminal SessionEnd. Future v2 could provide a `/sf:wrap-checkpoint` that's lighter-weight than full /wrap.

### Verification at install time

The framework's install / `/sf:doctor` slash command (future addition, mentioned in onboarding ADR-015) should:

- Detect which other plugins are installed
- Warn if known-incompatible combinations exist (e.g., Ralph + heavy reliance on claude-mem's SessionEnd → mention the limitation)
- Confirm our wake-up hook is registered and not silently overridden

## Consequences

**Easier:**
- Default v1 stack has a documented, sensible hook order — most plugins use lifecycle hooks for orthogonal concerns and don't actually conflict
- Our hook is designed to be tolerant of other plugins' choices — minimizes "this only works if I'm first" fragility
- Ralph compatibility documented honestly (it works, with a known limitation around SessionEnd)

**Harder:**
- We don't fully control hook ordering — Claude Code may evolve its hook scheduling logic without our knowing
- Adding new plugins to the stack requires re-checking this ADR's order assumptions
- Users who customize their install (add a plugin not in our stack) may hit ordering surprises we haven't documented

**Now impossible:**
- Strict "everything must fire in this exact order or we break" designs — we explicitly chose robustness over precise ordering control

**Sunset review trigger conditions:**
- Claude Code adds hook-ordering controls (priority numbers, before/after declarations, etc.) → revisit to use them
- A plugin's hook breaks ours in a non-obvious way → escalate
- Friends report consistent confusion about why some context didn't appear at session start → may indicate hook order assumptions are wrong on their machines

## Alternatives considered

### A) Mandate strict ordering via Claude Code config

**Considered shape**: Investigate whether Claude Code has plugin priority or ordering directives, use them to lock the order.

**Why rejected**: As of the research date, Claude Code's hook ordering isn't fully documented as user-configurable. Designing around hypothetical mechanisms is fragile. Better to be robust to whatever order emerges.

### B) Replace our wake-up hook with a slash command (`/sf:wake-up`)

**Considered shape**: Mirror the consolidate decision (ADR-009). No SessionStart hook at all; user runs `/sf:wake-up` manually at the start of each session.

**Why rejected**: Loses the value of automatic context. ADR-008 explicitly considered and rejected this; the discipline of remembering manual wake-up is higher friction than `/wrap` because it has to happen at the START of every session before the user even knows what they're doing.

### C) Combine our wake-up with claude-mem's SessionStart somehow

**Considered shape**: Either get claude-mem to call our wake-up after its own injection, or piggyback on its hook with shared state.

**Why rejected**: Requires claude-mem to know about our framework specifically — it doesn't. We don't have authorship rights on claude-mem and shouldn't depend on a coupling neither side maintains. Keep concerns separate.

### D) Add a coordinator plugin that orchestrates all the hooks

**Considered shape**: Build a small meta-plugin that intercepts SessionStart, then calls each registered plugin in our preferred order.

**Why rejected**: This is exactly the "coordinator daemon" alternative ADR-003 rejected. We don't have a hook-ordering problem severe enough to justify the infrastructure.

## References

- `wiki/research/claude-mem.md` — its 5 lifecycle hooks + SessionEnd behavior
- `wiki/research/context-mode.md` — its 5 hooks including PreCompact session_resume snapshot
- `wiki/research/superpowers.md` — "No discrete hook system" — Superpowers operates at skill-activation layer
- `wiki/research/ralph.md` — Stop hook collision concern that led to /wrap not Stop in ADR-009
- `wiki/research/prompt-engineering-agent-harness.md` — 9-component reference, lifecycle hooks as harness layer #8
- ADR-006 (Curated Stack) — defines the plugins this ADR coordinates
- ADR-008 (Wake-Up Hook) — our SessionStart implementation
- ADR-009 (Consolidate via /wrap) — our deliberate choice NOT to use Stop hook
