---
title: Cadence & Scheduled Automation (Nate Herk, 2026)
type: research
source: "raw/transcripts/ — multiple Nate Herk 2026 videos"
ingested: 2026-06-08
tags: [aios, cadence, routines, cron, scheduled-automation, deployment, claude-code]
status: ingested
attribution: "Nate Herk | AI Automation (YouTube), 2026 videos"
related: [nate-herk-ai-os, ralph, py-harness-engineering, caleb-agent-harness]
---

# Cadence & Scheduled Automation (Nate Herk, 2026)

## TL;DR

Across ~15 videos spanning April–June 2026, Nate Herk maps every layer of the CADENCE problem: the gap between an interactive Claude Code session and an agent that acts while the laptop is closed. The picture that emerges is a three-tier ladder — /loop for intra-session recurring checks, CronCreate for session-scoped scheduled loops, and Cloud Routines for machine-off production runs — each with distinct tradeoffs in statefulness, cost, and reliability. The critical deployment insight is that scheduled automation deploys *code*, not the agent itself; self-healing and judgment stay in the interactive session. A concrete external runtime (Trigger.dev or Modal for deterministic scripts, Cloud Routines for agentic runs) bridges the gap until Anthropic's unreleased Daemon mode lands.

## New Claude Code primitives

### [NEW] Cloud Routines (remote scheduled automations)
A CC primitive (research preview, April 2026): configure a named routine — prompt + linked GitHub repo + model + connectors + schedule — and it runs on Anthropic's cloud infrastructure on a time schedule, API POST, or GitHub event, with no local machine required. Each run clones the linked repo, loads CLAUDE.md, runs the agent, then destroys the environment. Results or branches are pushed back to GitHub.

- Why it matters: first native machine-off cadence primitive; closes the single biggest gap in the framework's CADENCE layer
- Plan limits: Pro = 5/day, Max ($200/mo) = 15/day, Team/Enterprise = 25/day; minimum interval = 1 hour; each run gets 4 vCPUs / 16 GB RAM

### [NEW] Three trigger types for Routines
Routines fire on: (1) cron-style schedule (natural language, min 1 hour), (2) outbound API POST from another automation, (3) GitHub webhook events — new PR, push, issue, release. The API trigger enables chaining: one automation POSTs to launch another.

- Why it matters: event-driven cadence, not just time-based; enables CI/CD integration and cross-automation orchestration from a single framework entry point

### [NEW] Cloud Environment with network access tiers
Each routine attaches to a named cloud environment that stores env vars and sets network access: trusted (Anthropic-vetted allowlist), full (unrestricted), or custom (named domains). Secrets live here, not in the GitHub repo.

- Why it matters: trusted mode mitigates prompt-injection exfiltration; the tier choice is a direct extension of the framework's "scope the keys" safety model to hosted agents

### [NEW] Connectors (OAuth integrations for Routines)
First-class OAuth connectors (Slack, Gmail, ClickUp) attached to routines — richer authenticated access than raw env-var API keys.

- Why it matters: connects the wiki's Connections layer to cloud-hosted cadence without manual token wrangling

### [NEW] CronCreate / CronList / CronDelete tools
Native CC scheduling primitives. CronCreate accepts cron syntax and registers a session-scoped recurring task. CronList enumerates active crons. CronDelete removes one. The /loop skill is the user-facing wrapper; these are the underlying mechanism.

- Behavioral distinction: in the terminal, crons survive /clear and persist up to 7 days; in the desktop app, /clear kills all crons and expiry is 3 days. Cron firing adds up to 30 minutes of random jitter — interval-based mental model, not wall-clock exact

### [NEW] /loop recurring tasks
Runs a prompt on a recurring interval within a live session (up to 3 days). Distinct from desktop scheduled tasks: /loop retains session context across iterations; desktop scheduled tasks each start as cold fresh sessions.

- Why it matters: intra-session cadence primitive; natural entry point for deployment watches, PR monitors, context-budget checks

### [NEW] /goal command
Sets an autonomous objective the agent pursues in a depth-first loop — iterates, spawns sub-agents as needed, runs up to 24 h+ until an explicit measurable exit criterion is met. Contrast with dynamic workflows, which fan out horizontally.

- Why it matters: long-running, hands-off loop without external scheduler; correct posture is a concrete, measurable done criterion (passing test, coverage threshold) — subjective prompts cause infinite iteration

### [NEW] Dynamic Workflows
CC generates a JavaScript fan-out file that spawns potentially hundreds of parallel sub-agents, collects results, and synthesizes them. Saved to `.claude/workflows/` for reuse. Visible and stoppable via /workflows command. Released with Claude Opus 4.8.

- Why it matters: horizontal parallelism at scale; correct cost discipline is Haiku workers + single Opus synthesizer (Nate ran 41 Haiku scorers → 1 Opus ranker)

### [NEW] Agent View (claude agents) + /bg flag
Native CLI dashboard showing all running CC sessions — status (yellow = waiting, green = done), elapsed time, inline Space-to-reply from the view without entering the session. Launch a new background session with `claude --bg "<task>"` or push a live session into the view with /bg.

- Why it matters: single pane of glass for monitoring parallel or background automations; Space-to-reply gives the founder one-line approve/redirect UX without reading full session context

### [NEW] Auto Permission Mode
Sits between "ask before edits" and "dangerously skip permissions." A per-tool-call classifier reviews each action for destructiveness or prompt-injection risk before executing. Currently research preview, team plan only. Sessions are slightly more expensive due to the classifier.

- Why it matters: correct default permission posture for unattended cadence runs in isolated environments; prevents bypass-permissions over-reach during scheduled automation

### [NEW] claude remote-control
Generates a session URL and QR code. Any browser or phone that hits the URL gets a synced window into the local CC session. Files stay local; model calls go to Anthropic. Requires Pro or Max personal plan; session persists while the local terminal and machine stay on.

- Why it matters: mobile oversight of long-running automation tasks without desk-bound constraint; documented as the short-term cadence bridge until native hosted scheduling matures

### [NEW] Managed Agents (Claude Console)
Anthropic-hosted cloud containers for agents — define task, tools, and guardrails; Anthropic provisions the sandbox. Charged at $0.08/hour active session plus token costs. CLI-buildable from inside a CC project, inheriting its accumulated context.

- Upcoming (early access): Outcomes (explicit success criteria + self-iterate), Callable Agents (coordinator invokes specialist managed agents), Persistent Memory across sessions

### [NEW] Daemon mode + Coordinator mode (source-leaked, not yet public)
Source code references a "Daemon mode" (persistent background agent process, no active user session required) and a "Coordinator mode" (distinct from existing multi-agent coordinator) behind internal feature flags. These are the native cadence primitives the framework should design to absorb when they ship.

## Techniques worth adopting

**Lean repo per routine.** For each cloud routine, create a dedicated minimal GitHub repo rather than pointing at the main project. A large CLAUDE.md + codebase burns context budget and run limits on irrelevant tokens. Routine repos contain only a small CLAUDE.md, required scripts/skills, and nothing else.

**Skill-as-routine prompt.** The most reliable routine prompts reference a named skill slash command and provide an explicit order of operations: "Run /skill-name with these parameters in this order." Matches how local scheduled tasks already invoke skills and ensures predictable one-shot execution.

**Stateless-run memory trail via GitHub branch writes.** Each routine run clones, runs, destroys — but the agent CAN persist state by writing files or committing to a branch that gets pushed back to the repo. This is the mechanism for cross-run memory until native Persistent Memory ships.

**Failure-notification footer in every routine prompt.** Append "If this run fails for any reason, send me a Slack/email notification with the error." Headless async runs fail silently by default; the prompt-level failure handler is zero-infrastructure observability.

**Auto-compact cron loop.** Pair a work cron with a second cron (e.g., every 5 min) whose sole payload is /clear. Prevents context rot when a long-running automation loop accumulates stale context.

**Self-terminating loop.** Include an instruction to kill the cron after N iterations or a time window. Prevents orphaned background crons from persisting past their useful life.

**Test with run-now before scheduling.** Use the "Run Now" button to iterate on a routine interactively before committing it to a schedule — run, observe, fix prompt/env, repeat until it one-shots cleanly. Same discipline as TDD: green before schedule.

**Width vs. depth decision heuristic.** "Does this break into many independent pieces running simultaneously?" → dynamic workflow. "Do I need to keep checking against a done criterion until it flips?" → /goal. Combining them is very expensive; use deliberately.

**Capability ladder for task routing.** Nate's explicit escalation path: quick ask → skill (repeatable) → sub-agent (parallel side task) → agent team (crew that communicates) → /goal (loop until done) → dynamic workflow (giant parallel job). Use the lowest tier that fits.

**WAT classification per automation.** Classify each skill/automation as W-only (workflow markdown, no agentic loop), W+T (workflow + deterministic tool scripts), or W+A+T (full agentic). W+T fits Modal/Trigger.dev scripts; W+A+T needs a CC session or Agent SDK.

**Off-peak scheduling for heavy sessions.** Anthropic throttles session-window drain based on demand. Peak hours are approximately 8am–2pm ET on weekdays. Schedule multi-agent or large refactor cadence runs during off-peak hours to slow drain.

**Session-count trigger alongside time-based cadence.** Auto Dream (the new CC background memory compaction sub-agent) can fire every N sessions rather than on a wall-clock interval. For a solo founder with irregular cadence, session-count triggers are more reliable.

**Explicit env-var sourcing instruction in routine prompt.** Tell Claude exactly where to find secrets: "My X API key is available as an environment variable — use it directly, do not look for a .env." Without this, Claude defaults to searching for .env based on CLAUDE.md conventions and fails silently.

## How this informs the framework

### Pillar 3 — Control the truth / leverage the muscle (including git-based write-back)

KEEP: the wiki-as-single-source-of-truth posture holds for cadence too. Cloud Routines write results back to GitHub; the framework should treat each routine's output as a wiki write, not an orphaned artifact. This is the git-based write-back refinement of the Pillar 3 spec: scheduled automation = muscle that runs on a clock, and its output commits back into the truth layer on every run.

REBUILD: the permission model must extend to hosted contexts. The "scope the keys" principle from [[nate-herk-ai-os]] applies unchanged, but trusted/full/custom network-access tiers add a new axis: a routine running on "full" that processes external content is an exfiltration surface. The doctor skill needs a routine network-access audit column. Auto Permission Mode is the correct posture for unattended runs over bypass-permissions.

ADOPT: lean-repo discipline enforces the "leverage the muscle" side of Pillar 3. A routine's repo should be the minimum viable muscle — only the CLAUDE.md, the skills, the tools; no unrelated project context bloating the run. The framework should ship a `sf-routine-init` command that scaffolds this from a template.

### Pillar 4 — Compounding

ADOPT immediately (no external infra needed):

- /loop as the intra-session cadence primitive: deployment watches, PR monitors, context-budget checkpoints. Wrap in a skill with a measurable stop condition baked in.
- CronCreate/CronDelete as session-scoped scheduled loops: document terminal-vs-desktop behavioral differences and the 30-minute jitter. Pair with an auto-/clear companion cron for context hygiene.
- /goal as the long-running autonomous loop: overnight improve-skill runs, weekly competitive scans via /deep research. Enforce measurable exit criteria in all invocations.

ADOPT with light infra (GitHub repo required):

- Cloud Routines as the production cadence backend. Max plan = 15/day covers a solo founder's typical automation needs. Introduce a `routine-spec` section in the project wiki schema so active routines are documented alongside context, and the wake-up hook can surface which automations are live.

REBUILD to close the observability gap:

- Failure-notification footer as a required framework convention for every routine prompt (use the globally-registered Resend MCP — see [[nate-herk-ai-os]] Connections section).
- Structured activity-log PostToolUse hook emitting JSON events: tool, file, timestamp, agent-id. Gives the solo founder a scannable audit trail without external tooling.
- Agent View + /bg as the monitoring surface: document as the recommended interface for parallel and background automation runs. The Space-to-reply inline approval pattern maps directly to the framework's existing "checkpoint" safety model.

WATCH for Daemon mode + Coordinator mode: these are the native primitives to rebuild CADENCE around once they ship publicly. The framework should have a spec-ready design (lean repos, skill-as-routine prompt, failure notification, write-back to wiki) that wires in immediately on release, without a ground-up rethink.

Reference: see `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md` for the full positioning design; CADENCE is identified there as the framework's weakest layer and the area with the highest near-term payoff.

## Tensions / open questions

1. **Run-quota ceilings vs. compounding ambition.** Max plan = 15 remote routines/day sounds generous until a founder runs daily digest + weekly review + PR watcher + skill-audit = 4+ slots consumed before discretionary automation. The doctor/insights skill should surface live quota consumption so the founder knows their headroom.

2. **Stateless runs and cross-run memory.** The GitHub branch write-back pattern is the right interim answer, but it requires naming conventions and explicit read-at-startup instructions. Without a framework convention, every routine reinvents this. The recall skill should be adapted to read a `state.md` or `run-log.md` from the routine repo at the start of each run.

3. **Agent vs. code deployment boundary.** Nate names this clearly: deployed code has no self-healing; only the active agent session does. The framework's safety model covers tool-scope/permissions but does not yet articulate this boundary. A named principle — "ring keys scope what the agent can do; deployed artifacts are deterministic and carry none of the agent's judgment" — belongs in the CADENCE design spec. Ref: [[ralph]] for the loop-guard pattern that compensates.

4. **Auto Permission Mode is team-plan-only.** The solo Pro or Max user currently cannot access it (research preview). The doctor/bootstrap flow should detect plan tier and emit the correct recommendation: auto mode for team users running unattended cadence; manual allowlist/denylist for solo users. Neither is bypass-permissions.

5. **Lean-repo discipline vs. context reuse.** The lean-repo principle (each routine gets a minimal repo) conflicts with the desire to inherit the full project context that makes managed-agent system prompts rich and specific. Nate's answer: build the managed agent from inside the rich CC session, then export only the necessary context into the lean routine repo. The framework needs a convention for this export step.

6. **/loop vs. CronCreate vs. desktop scheduled tasks vs. Cloud Routines.** Four overlapping primitives with different statefulness, durability, and cost profiles. The framework needs a decision matrix, not just individual docs for each.

## Quotes worth preserving

> "There is one important caveat — the difference between automations that you trigger yourself versus automations that run on a schedule... if you want something to run on a schedule, that's actually going to be you deploying that code, not the actual agent."

> "One agent works for a while then leaves structured artifacts like notes, to-dos, differences, what changed, what broke, what's next. Then the next shift picks up from there."

> "CloudCode has finally brought us routines, which basically means you can inject a prompt into CloudCode, but it can be running on the web. So, your laptop does not have to stay open."

> "Cloud Code has three different tools for this sort of thing, which is called cron create, cron list, and cron delete."

> "It's got a lot more flexible. It has scheduled runs. It has automatic retries. It's got queuing. It's got orchestration."

> "You start a coding task on your computer, and you're kind of desk bound, but then using the remote control, you can control it from anywhere."

> "Heartbeats just basically means cron, every 30 minutes, every 5 minutes, you can have [Claude Code] just wake up and do things. And that's basically why it feels like it's an always-on assistant."

> "The architecture is clearly built to support decomposition, splitting work across multiple agents that can run in parallel. There are even concepts in the source for background tasks, work that continues while you're focused on something else."

> "It spun up 41 Haiku scoring agents because I have 41 skills here, and then it's feeding all of that analysis into an Opus synthesis agent."

> "You can type /loop and tell it, 'Hey, every 5 minutes check in on the deployment.' And Claude will rerun that prompt in that same session every single 5 minutes unless you close out of that session."

## Source videos

- `nate-herk-claude-code-finally-gave-us-scheduled-automat` — Cloud Routines deep dive (high signal)
- `nate-herk-i-tested-3-ways-to-deploy-claude-agents-heres` — CronCreate/Routines/Agent SDK comparison (high signal)
- `nate-herk-multi-agent-building-in-claude-code-somehow-g` — Agent View, /bg, /goal (high signal)
- `nate-herk-claude-code-dynamic-workflows-clearly-explained` — Dynamic Workflows, /goal, Ultra mode (high signal)
- `nate-herk-claude-code-just-added-what-everyone-wanted-r` — remote-control (high signal)
- `nate-herk-how-to-build-claude-agent-teams-better-than-9` — Agent Teams, SendMessage, Plan Approval Mode (high signal)
- `nate-herk-i-tested-claudes-new-managed-agents-what-you` — Managed Agents, heartbeat pattern (high signal)
- `nate-herk-claude-code-just-dropped-memory-20` — Auto Dream, session-count cadence trigger (high signal)
- `nate-herk-the-easiest-way-to-host-your-claude-code-agen` — Trigger.dev MCP, fan-out worker pattern (medium signal)
- `nate-herk-agentic-workflows-just-changed-ai-automation` — WAT framework, Modal deployment, shift artifacts (medium signal)
- `nate-herk-stop-using-bypass-permissions-use-this-new-fe` — Auto Permission Mode (medium signal)
- `nate-herk-18-claude-code-token-hacks-in-18-minutes` — off-peak scheduling, context discipline (medium signal)
- `nate-herk-32-claude-code-hacks-in-16-mins` — /loop, desktop scheduled tasks (high signal)
- `nate-herk-how-to-build-10000-agentic-workflows-claude-c` — WAT, deployment handoff, self-healing loop (low signal)
- `nate-herk-how-id-teach-a-10-year-old-to-build-agentic-w` — WAT, context-rot, code-vs-agent boundary (low signal)
- `nate-herk-claude-code-source-code-just-leaked-8-things` — Daemon mode, Coordinator mode, source analysis (medium signal)
- `nate-herk-i-can-actually-watch-my-ai-agents-work-now` — three-tier agent taxonomy, activity log (low signal)
- `nate-herk-claude-code-skills-just-got-even-better` — skill-audit cadence task (medium signal)

## Reference

- Positioning spec: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
- Ingested: 2026-06-08, from theme brief at `/tmp/themebriefs/cadence-automation.json`
- Cross-links: [[nate-herk-ai-os]], [[ralph]], [[py-harness-engineering]], [[caleb-agent-harness]]
