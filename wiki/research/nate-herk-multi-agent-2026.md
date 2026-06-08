---
title: "Multi-Agent & Orchestration (Nate Herk, 2026)"
type: research
source: "raw/transcripts/ — multiple Nate Herk 2026 videos"
ingested: 2026-06-08
tags: [aios, multi-agent, agent-teams, dynamic-workflows, managed-agents, a2a, claude-code]
status: ingested
attribution: "Nate Herk | AI Automation (YouTube), 2026 videos"
related: [simon-scrapes-agentic-os, caleb-agent-harness, nate-herk-ai-os]
---

# Multi-Agent & Orchestration (Nate Herk, 2026)

## TL;DR

Across a dozen 2026 videos Nate Herk traces Claude Code's multi-agent surface from sub-agent delegation through Agent Teams, dynamic fan-out workflows, and fully managed cloud routines. The through-line is a capability ladder — skill → sub-agent → team → /goal → dynamic workflow — that maps every task to the cheapest and safest execution tier. Three new platform primitives arrived post-May 2026 and are directly usable today: Agent Teams (peer-to-peer messaging, shared task list), dynamic workflows (JS fan-out across 100+ Haiku workers), and Agent View + /bg (unified multi-session dashboard). Together these give the startup-framework's weakest layer — CADENCE — a concrete implementation path for the first time: Pillar 3 (Capabilities/Skills) gains a model-routing decision rule, and Pillar 5 (Cadence) gains native primitives to replace the current SessionStart-hook stub.

## New Claude Code primitives

Each entry marked [NEW] was released or confirmed after May 2026.

**[NEW] Agent Teams (TeamCreate)** — Named parallel agents with a shared task list; teammates communicate peer-to-peer via SendMessage rather than routing through the main session. An orchestrator-lead agent manages the team and can send a graceful shutdown signal. Enabled via env flag in settings.json. Why it matters: gives the framework a supported multi-agent primitive for tasks that are genuinely interdependent (agents need to hand off results to each other), filling the gap left by independent sub-agent fan-out which cannot coordinate.

**[NEW] SendMessage tool** — Any agent in a team can message a named teammate directly. The routing must be spelled out explicitly in each agent's prompt; agents will not infer recipient. Why it matters: enables dependency-driven handoff patterns (e.g. "when API spec is done, send to the back-end dev agent") without going back through the orchestrator on every exchange.

**[NEW] Plan Approval Mode for agent teams** — Each teammate submits a plan that must be approved by the orchestrator or the human before execution begins. Why it matters: this is a review gate directly analogous to the framework's existing "instructions != capabilities" safety principle; it should be the default posture for any Agent Team spawned inside a framework project.

**[NEW] Agent View (claude agents) + /bg flag** — A native CLI dashboard (research preview, ~June 2026) showing all running CC sessions in a single pane. Sessions display status: yellow = waiting on input, green = complete, plus elapsed time. `/bg` puts a live session into the background; `claude --bg "<task>"` launches a new background session directly. Inline reply from agent view (Space key) lets the founder approve a waiting agent without entering the session. Why it matters: this is the missing orchestration UI the CADENCE layer needs — background agents are now launchable and monitorable without terminal-tab chaos.

**[NEW] /goal command** — Sets an autonomous objective that CC pursues in a loop, spawning sub-agents as needed, until an explicit measurable criterion is met. Can run 24h+. Depth-first (iterate until done), contrasts with workflow width (fan-out). Why it matters: the closest native primitive to a scheduled, hands-off cadence run the framework has ever had access to.

**[NEW] Dynamic Workflows** — CC generates a JavaScript file that fans out potentially hundreds of parallel sub-agents, collects their results, and synthesizes them. Saved to `.claude/workflows/` and reusable. Visible live via `/workflows`. Released with Claude Opus 4.8. Why it matters: enables batch parallelism (e.g. all 41 skills scored simultaneously by Haiku agents, ranked by one Opus agent) that would otherwise be prohibitively sequential.

**[NEW] Ultra Code mode (/effort → ultra)** — Sets reasoning to x-high AND wraps every prompt in a dynamic workflow by default. Bypasses many permission confirmations. Most expensive mode. Why it matters: risk surface — this conflicts with the framework's permission-scope model; the doctor skill should detect and warn when ultra mode is active.

**[NEW] /deep research** — Built-in slash command that automatically invokes a parallel-agent, claim-voting research workflow and returns a cited report. Why it matters: zero-config competitive/market research usable as a weekly cadence task.

**[NEW] Cloud Routines** — Named routines running on Anthropic infrastructure; no local machine required. Three trigger types: cron schedule (min 1 hour), API webhook, GitHub event. Each run clones the linked GitHub repo, reads CLAUDE.md, runs the agent, destroys the environment, and can push results back to GitHub. Limits: 5/day (Pro), 15/day (Max $200/mo), 25/day (Team/Enterprise). Cloud environment object stores secrets; network access is tierable (trusted/full/custom). Why it matters: this is the highest-value CADENCE primitive for a solo founder — truly asynchronous, machine-off, retryable automation. The Max plan at 15 runs/day is sufficient for daily digests, weekly reviews, and PR watchers simultaneously.

**[NEW] CronCreate / CronList / CronDelete tools** — Native CC scheduling primitives underlying the /loop skill. CronCreate accepts cron syntax and registers a session-scoped recurring task. Terminal sessions: survive /clear, persist up to 7 days. Desktop app: /clear kills all crons, 3-day expiry. Up to 30-minute jitter on firing — treat as interval-based, not wall-clock-exact. Why it matters: the framework documents /loop as a skill but does not yet expose the underlying cron tools; surfacing them directly closes the biggest documented gap in CADENCE.

**[NEW] Managed Agents (Claude Console)** — Anthropic-hosted cloud containers: define task, tools, guardrails; Anthropic provisions the sandbox. Charged at 8 cents/hour plus token costs. CLI-invokable from inside a CC session using project context for richer system prompt generation. Credential Vault handles team-shared encrypted MCP credentials. Future features in early access: Outcomes (explicit success criteria + self-iterate), Callable Agents (coordinator invokes specialized managed agents), Persistent Memory across sessions. Why it matters: for always-on use cases that exceed routine run quotas, managed agents are the hosted sub-agent primitive — but the heartbeat/cron gap requires an external scheduler (trigger.dev, n8n) until Anthropic ships native crons for them.

**[NEW] claude remote-control** — CLI command (or `/remote-control` slash command) that generates a session URL and QR code; any browser or phone gets a synced window into the local CC session. Pro/Max personal plan only. Session persists as long as the local terminal and machine stay on. Why it matters: short-term cadence bridge — solo founder can trigger and monitor long-running parallel agent jobs from mobile before true cloud scheduling covers all cases.

**[NEW] /voice native command** — CC shipped a native `/voice` slash command for talking directly to the terminal. Still rolling out at time of recording. Why it matters: low-friction task dispatch for cadence triggers, not a deep multi-agent concern but worth noting for future hook design.

**[NEW] Auto Dream** — Background sub-agent running periodically (time interval or session-count threshold) to consolidate, prune, and refresh Claude's `.md` memory files. Activated via `/memory` menu; manual trigger `/dream`. Touches only memory files, never code. Three-phase sub-agent: gather session info → read current memory files → consolidate/prune → write back. Why it matters: the framework's session-lifecycle trio (sf-wrap / sf-note / sf-recall) handles write and inject but has no background cleanup pass; Auto Dream is that missing layer.

## Techniques worth adopting

**Capability ladder for task routing** — Nate's explicit decision sequence: quick ask → skill (repeatable preference) → sub-agent (parallel side task) → agent team (peer-communicating crew) → /goal (loop until done criterion flips) → dynamic workflow (giant parallel batch). Use this to prevent over-engineering: most framework tasks should never escalate past the skill or sub-agent tier.

**Haiku workers + Opus synthesis split** — In dynamic workflows and agent teams, route all parallel worker/scoring agents to Haiku (cheap, fast). Reserve one Opus agent for the final synthesis/ranking step. Nate ran 41 Haiku scorers → 1 Opus synthesizer consuming ~5M input tokens cheaply. The 7–10x sub-agent cost multiplier makes model routing a high-leverage default, not an optimization.

**3-to-5 agent cap** — Each additional agent multiplies token cost linearly. Cap at 2–5 for non-trivial teams; fall back to sequential sub-agents for inherently ordered pipelines. Beyond 5, costs compound faster than coordination benefits.

**Goal-first prompt structure for agent teams** — Open team-creation prompts with an explicit GOAL paragraph (end state, why the team exists). Spawned agents have zero prior context — they receive only the orchestrator's prompt. Without a goal paragraph, specialists produce disconnected outputs.

**Assign file/directory territory per agent** — Each agent owns specific paths. Shared file access causes overwrites. Enforce in team prompt: "you own src/frontend/, do not write to src/backend/".

**Named recipient in handoff instructions** — Inside each agent's prompt, spell out who to message and when. Agents will not infer routing.

**Width vs. depth decision heuristic** — "Does this break into many independent pieces that can run simultaneously?" → dynamic workflow. "Do I need to keep checking against a done criterion until it flips?" → /goal. Combining both is possible but expensive; do it deliberately.

**Lean repo per routine** — For each cloud routine, create a dedicated minimal GitHub repo. A massive CLAUDE.md + codebase burns context budget on irrelevant tokens. Routine-specific repos contain only the small CLAUDE.md, required skills, and no project code.

**Skill-as-routine prompt pattern** — Routine prompts reference a named skill (slash command) and provide an explicit order of operations rather than ad-hoc inline instructions. Makes routine behavior predictable and reusable.

**Stateless-run memory trail via GitHub branch writes** — Each cloud routine run is stateless (clone → run → destroy) but the agent can persist state by writing a state file or run-log to the repo on each run, enabling cross-run memory without an external DB.

**Prompt-level failure handler** — Append to every routine: "If this run fails for any reason, send a notification with the error." Silent failure is the main risk for headless async runs.

**Self-terminating cron loops** — When setting up a cron loop, include an instruction to kill itself after N iterations or after a time window. Prevents orphaned background crons.

**Auto-compact cron guard** — Run a second cron whose sole job is to inject /clear. Prevents context rot when a long-running automation loop accumulates context.

**Seed teams with local docs** — Before spawning any agents, read unfamiliar API or MCP documentation into a local markdown file. Agents look it up instantly without re-fetching.

**Graceful shutdown protocol** — End multi-agent sessions by sending a shutdown signal via the main agent, wait for each teammate to confirm readiness before force-closing. Prevents incomplete state.

**Temporary file buffer for mid-run state** — Instruct agents to write intermediate results to temp files. Prevents lost work when context windows fill or a teammate is slow.

## How this informs the framework

### Pillar 3: Capabilities / Skills

**ADOPT — capability ladder as a routing decision tree.** Encode Nate's ladder as a decision tree inside the framework's planning or doctor skill. Five questions, each maps to a tier:

```
1. Is this a repeatable preference or workflow I've codified? → skill
2. Can this be parallelised as a side task with its own context? → sub-agent (Haiku)
3. Do tasks need to communicate and hand off results to each other? → agent team (3–5 cap, Plan Approval Mode on)
4. Do I need to iterate against a measurable exit criterion until it flips? → /goal
5. Is this a giant batch job with N independent items to score/process in parallel? → dynamic workflow (Haiku workers + Opus synthesis)
```

**ADOPT — per-sub-agent model routing as a framework-level CLAUDE.md rule.** The skill front-matter `model` field is the exact enforcement mechanism. Canonical rule: worker sub-agents → Haiku; orchestration/synthesis → Sonnet; deep analysis (architectural decisions, final ranking) → Opus only when Sonnet fails. This maps to the existing 3-tier model strategy in the user's global rules and eliminates a per-project configuration burden.

**ADOPT — two-tier skill taxonomy tagging.** Tag each framework skill in its YAML front-matter as `capability-uplift` (model-gap compensation, monitor for retirement) or `encoded-preference` (idiosyncratic workflow, durable across model upgrades). Drives maintenance: schedule benchmarks only for capability-uplift skills via skill-creator eval; treat encoded-preference skills as long-lived.

**KEEP — improve-skill loop.** Agent Teams Plan Approval Mode and the skill-creator's eval/benchmark primitives augment but do not replace the current EXPERIMENTAL improve-skill. When Anthropic ships Outcomes (self-evaluate against explicit success criteria), absorb it into the improve-skill loop rather than building a parallel path.

### Pillar 5: Cadence

**REBUILD — CADENCE layer around native primitives.** The SessionStart hook is too thin. The upgrade path, in increasing power:

1. **Session-scoped cron (now):** CronCreate/CronList/CronDelete, exposed directly as `sf-cadence-start`; pair every work cron with a /clear cron to prevent context rot; self-terminating after N iterations.
2. **Background sessions (now):** Agent View + `claude --bg` for "fire and monitor" automation; SessionStart hook or a cron invokes `claude --bg "<task>"` and the founder monitors from the single agent-view dashboard.
3. **Cloud Routines (now):** Lean-repo-per-routine pattern; skill-as-routine prompt; prompt-level failure notification via Resend MCP (globally registered); stateless-run memory trail via GitHub branch write; network access = trusted by default.
4. **Managed Agents + external heartbeat (now):** For always-on use cases; trigger.dev or n8n HTTP-poll scaffold for the 5–30 minute heartbeat gap until native crons land on managed agents.
5. **Daemon mode + Coordinator mode (roadmap):** Source-code leak confirms both exist behind `user_type === 'ant'` flag. When public, rebuild CADENCE foundations around them; have a spec-ready design waiting.

**ADOPT — /goal as the CADENCE backbone for long-running routines.** Wrapping solo-founder routines (e.g. "keep watching for PR review readiness until merged", "improve this skill until test coverage > 80%") in `/goal` fills the scheduled-automation story without external cron infrastructure.

**ADOPT — Routines cadence path into the doctor audit.** Doctor should surface: active cron list (CronList), active cloud routines, routine quota usage (Max = 15/day), any routine with network_access = full that processes external content (flag for prompt-injection risk), any local desktop scheduled tasks not paused before planned shutdown (catch-up replay risk).

### Reference

Positioning spec: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md` — CADENCE as the weakest layer, wiki as governable single source of truth, native CC primitives as muscle wired in via thin glue with execution writing results back to the wiki.

Also relevant: [[simon-scrapes-agentic-os]] (shift-based handoff artifacts), [[caleb-agent-harness]] (harness engineering patterns), [[nate-herk-ai-os]] (Four C's architecture and "instructions != capabilities" safety model).

## Tensions / open questions

1. **Agent Teams cost vs. sub-agent fan-out.** Teams multiply cost linearly per agent AND add coordination overhead (SendMessage, Plan Approval gate). For the solo-founder use case most "multi-agent" tasks are better served by a dynamic workflow (fan-out) or sequential sub-agents than a full peer-communicating team. Document the decision threshold: teams are warranted only when interdependency and peer communication are genuinely required, not just because the feature exists.

2. **Cloud Routine quota exhaustion.** Max plan = 15 runs/day. A solo founder running daily digest + weekly review + PR watcher + memory compaction could saturate quota within a single project, before any product-specific routines are added. The framework needs a quota allocation strategy: reserve N slots for core framework maintenance, M for product automations, and surface remaining quota in the doctor skill.

3. **Lean-repo discipline vs. framework context.** Cloud Routines benefit from minimal repos (less context waste), but the framework's value proposition is the accumulated wiki and CLAUDE.md context. The tension: routines that need full project context will burn quota faster; routines that get a lean repo lose access to the framework's accumulated state. Resolution: introduce a "routine-context bundle" skill that extracts only the slice of the wiki relevant to a given routine and packages it into the lean repo.

4. **Daemon mode timing.** The leaked source confirms Daemon mode is built. The framework should not build a competing persistent-background-process story now and then have to tear it down. The CADENCE layer should be designed so that Daemon mode can be plugged in as the execution substrate without restructuring the skill/routine authoring model.

5. **Ultra mode + dynamic workflows as permission vectors.** Both modes bypass confirmation gates that the framework's safety model treats as mandatory. The doctor audit must surface these: /effort ultra active → warn; dynamic workflow running with external data access → check network tier.

## Quotes worth preserving

> "Agent teams have a team lead, maybe like a project manager, and it creates all of these different agents and a shared task list. So, the huge unlock here is that individual teammates can talk to each other." — nate-herk-how-to-build-claude-agent-teams-better-than-9

> "it spun up 41 Haiku scoring agents because I have 41 skills here, and then it's feeding all of that analysis into an Opus synthesis agent" — nate-herk-claude-code-dynamic-workflows-clearly-explained

> "One agent works for a while then leaves structured artifacts like notes, to-dos, differences, what changed, what broke, what's next. Then the next shift picks up from there." — nate-herk-agentic-workflows-just-changed-ai-automation

> "CloudCode has finally brought us routines, which basically means you can inject a prompt into CloudCode, but it can be running on the web. So, your laptop does not have to stay open." — nate-herk-claude-code-finally-gave-us-scheduled-automat

> "Cloud Code has three different tools for this sort of thing, which is called cron create, cron list, and cron delete." — nate-herk-i-tested-3-ways-to-deploy-claude-agents-heres

> "Heartbeats just basically means cron, every 30 minutes, every 5 minutes, you can have open claw just wake up and do things. And that's basically why it feels like it's an always-on assistant." — nate-herk-i-tested-claudes-new-managed-agents-what-you

> "The architecture is clearly built to support decomposition, splitting work across multiple agents that can run in parallel. There are even concepts in the source for background tasks, work that continues while you're focused on something else." — nate-herk-claude-code-source-code-just-leaked-8-things

> "What I actually want to know is what they're building, what decisions they're making, and whether it's about to do something that I'd agree with or disagree with. That's the real product that I think we need when it comes to visualization." — nate-herk-i-can-actually-watch-my-ai-agents-work-now

> "you start a coding task on your computer, and you're kind of desk bound, but then using the remote control, you can control it from anywhere" — nate-herk-claude-code-just-added-what-everyone-wanted-r

## Source videos

- nate-herk-master-95-of-claude-code-skills-in-28-minutes (signal: medium)
- nate-herk-claude-code-skills-just-got-even-better (signal: medium)
- nate-herk-agentic-workflows-just-changed-ai-automation (signal: medium)
- nate-herk-how-to-build-claude-agent-teams-better-than-9 (signal: high)
- nate-herk-how-id-teach-a-10-year-old-to-build-agentic-w (signal: low)
- nate-herk-multi-agent-building-in-claude-code-somehow-g (signal: high)
- nate-herk-claude-code-dynamic-workflows-clearly-explained (signal: high)
- nate-herk-the-easiest-way-to-host-your-claude-code-agen (signal: medium)
- nate-herk-claude-code-just-added-what-everyone-wanted-r (signal: high)
- nate-herk-claude-code-finally-gave-us-scheduled-automat (signal: high)
- nate-herk-i-tested-3-ways-to-deploy-claude-agents-heres (signal: high)
- nate-herk-i-tested-claudes-new-managed-agents-what-you (signal: high)
- nate-herk-claude-code-source-code-just-leaked-8-things (signal: medium)
- nate-herk-claude-code-just-dropped-memory-20 (signal: high)
- nate-herk-i-can-actually-watch-my-ai-agents-work-now (signal: low)
- nate-herk-18-claude-code-token-hacks-in-18-minutes (signal: medium)
- nate-herk-32-claude-code-hacks-in-16-mins (signal: high)

## Reference

Positioning spec: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
