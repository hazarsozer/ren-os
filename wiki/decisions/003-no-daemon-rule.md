---
title: "ADR-003: No-Daemon Rule (Configuration Layer)"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [caleb-agent-harness, ralph, claude-mem, context-mode]
affects-components: [architecture, install, all-future-components]
relates-to: [002-token-efficiency-stack]
---

# ADR-003: No-Daemon Rule (Configuration Layer)

## Context

Early in brainstorming, we proposed Approach A+ (Plugin-only with LLM Wiki memory) over Approach B (Plugin + local service). The reasoning: avoid adding install complexity, keep the configuration auditable, stay aligned with the "lightweight is enough" thesis that surfaced across the research (Caleb's harness narrative, Ralph's success cases, Anthropic's reference harness demos).

However, ADR-002 adopted claude-mem (which runs a Bun worker on port 37777) and Context Mode (which uses subprocess isolation but not a long-running daemon). These don't violate Approach A+ — but they DO have their own daemons or workers. The question of "where does the no-daemon rule actually apply?" needs precision before subsequent ADRs can be honest about what the configuration provides.

The risk of imprecision: future ADRs casually adding small services or background processes for "just one more feature," undermining the lightweight thesis without anyone catching it.

## Decision

**The no-daemon rule applies at the configuration layer only.** The configuration adds zero long-running processes, services, daemons, or background workers of its own. Plugins recommended by the configuration may have their own daemons; that is the plugin's concern, not the configuration's.

**Precise statement of the rule:**

> The startup-framework configuration consists entirely of files (skills, agents, MCP definitions, slash commands, hooks, settings, documentation, wiki content) and configurations of Claude Code. Any process running on a user's machine that has the configuration's name on it must be a child process of Claude Code's natural lifecycle, never an independently-managed background process.

**What this rule covers (forbids at our layer):**
- Long-running HTTP/RPC servers we manage
- Cron jobs or scheduled tasks we install
- systemd / launchd / Windows Service units we create
- Persistent processes that outlive Claude Code sessions
- Background indexers / synchronizers we control

**What this rule does NOT cover (permitted):**
- Subprocesses Claude Code spawns naturally (skills running scripts, agents executing tools, MCP servers Claude Code itself manages)
- Daemons inside plugins we recommend (claude-mem's port 37777 worker, qmd's optional `--http --daemon` mode if ever adopted, Context Mode's subprocess isolation — none of which are "ours")
- Tools the user voluntarily installs alongside the configuration (their personal preference)
- Future v3+ work that consciously decides to break this rule with its own ADR

## Why this rule matters

1. **Install simplicity** — friend group members install with `/plugin install` commands, not by setting up systemd units or launchd plists. Onboarding stays under 10 minutes.

2. **Auditability** — anyone reading the configuration's source code sees the entire surface in markdown files + small scripts. No "wait, what's running on port X?" surprises from our layer.

3. **Cross-platform parity** — friends on Linux desktop, macOS MacBook Air, and (possibly future) Windows all run the same configuration without OS-specific service files.

4. **Failure isolation** — when something goes wrong, the failure surface is bounded. If a hook misbehaves, restarting Claude Code clears it. If a daemon misbehaves, you need to know what's running and how to kill it.

5. **Lightweight harness thesis** — Ralph's documented successes ($50K contract for $297, programming language in 3 months) prove lightweight works. Anthropic's reference harness demo is small. PY's research showed Manus rewriting their harness 5× in 6 months because assumptions expire — adding heavy infrastructure makes rewrites expensive.

## Consequences

**Easier:**
- Onboarding stays simple — no service setup
- Configuration is fully auditable in plain files
- Cross-platform behavior is consistent
- The configuration is cheap to throw away and rewrite when models improve (per PY's "assumptions expire" principle)

**Harder:**
- If a feature genuinely needs a background process, we can't add it without an ADR that consciously breaks this rule (good — forces deliberation)
- Some functionality remains harder than it could be (e.g., wiki indexing requires recalculation on each read at v1; qmd-as-daemon at v2 would be faster but would require a deliberate exception)

**Now impossible:**
- Adding a quiet little "just one daemon" without anyone noticing
- Distributing the configuration as something that includes a runtime service

**Trigger conditions for revisiting (sunset review):**
- Onboarding feedback says friends struggled with multi-plugin daemon management — that would suggest we should consolidate, possibly including running our own coordinator daemon
- A genuinely necessary feature requires a daemon and no plugin solves it — fine, write a follow-up ADR breaking this one
- Performance characteristics of v1 prove untenable at the wiki scales we hit — qmd or a similar tool becomes necessary, and the ADR-005 v2 upgrade decision incorporates this trade-off

## Alternatives considered

### A) No-daemon for the entire stack (configuration + recommended plugins)

**Considered shape**: Reject claude-mem and Context Mode because they have daemons; build our own daemon-free alternatives.

**Why rejected**: This would commit us to either (a) building substitute memory infrastructure (scope explosion) or (b) accepting worse memory behavior than the existing plugins provide. The user's #1 stated pain is token bloat — losing claude-mem and Context Mode would not serve the goal. The right discipline is at our layer; plugins live in a different scope.

### B) No rule at all — let daemons appear as needed

**Considered shape**: Skip this ADR, let future feature ADRs decide on daemons case-by-case.

**Why rejected**: Without an explicit rule, scope creep is easy. Each individual daemon would seem "small" but the cumulative install complexity adds up. Better to make exceptions deliberately than to drift accidentally.

### C) Provide a coordinator daemon that manages claude-mem + Context Mode + our hooks

**Considered shape**: Add a small daemon that mediates between all the moving parts to handle hook ordering, lifecycle, etc.

**Why rejected**: This is solving a problem we don't have yet. ADR-010 (hook ordering) will explore whether plugin-coordination problems are real before we add infrastructure to solve them. If hook ordering becomes painful, that's a future ADR's problem.

## References

- `wiki/research/caleb-agent-harness.md` — lightweight harness thesis; Ralph as canonical small-repo example
- `wiki/research/ralph.md` — documented successes proving lightweight is sufficient ($297 → $50K contract)
- `wiki/research/claude-mem.md` — example of an external plugin with its own daemon (port 37777) — fine because it's not at our layer
- `wiki/research/context-mode.md` — example of subprocess-only isolation, no daemon — possible to be daemon-free at scale, but not required at the plugin layer
- ADR-002 (Token-Efficiency Stack) — adopts the daemon-carrying plugins this rule scopes around
- `wiki/research/py-harness-engineering.md` — "assumptions expire" thesis; lightweight rewrites are cheap
