---
title: "Token Economics & Permissions (Nate Herk, 2026)"
type: research
source: "raw/transcripts/ — multiple Nate Herk 2026 videos"
ingested: 2026-06-08
tags: [aios, token-economics, permissions, auto-mode, model-routing, claude-code]
status: ingested
attribution: "Nate Herk | AI Automation (YouTube), 2026 videos"
related: [nate-herk-give-me-10-mins, nate-herk-ai-os, py-harness-engineering, context-mode]
---

# Token Economics & Permissions (Nate Herk, 2026)

## TL;DR

Across a cluster of 2026 videos Nate Herk maps the full cost surface of Claude Code — where tokens go, why they spike, and how to control them — and runs a parallel thread on permission posture, from manual allowlists through the new Auto Permission Mode to the security risks that expand with each new orchestration tier. Three themes recur: **model routing** (Haiku/Sonnet/Opus mapped to task weight), **unattended-run safety** (auto mode as the right posture when a human is not watching), and **session hygiene** (compact cadence, CLAUDE.md line budget, sub-agent delegation discipline). For the startup-framework the most load-bearing finding is that economics and permissions are the same problem viewed from different angles — both converge on "scope deliberately, measure what you can't see, and audit before you burn."

## New Claude Code primitives

**[NEW] Auto Permission Mode** (`--enable-auto-mode`, also VS Code sidebar toggle)
Sits between "ask before each tool call" and "dangerously skip permissions." A per-tool-call AI classifier reviews every action for destructive or sensitive behaviour; safe actions proceed automatically, risky ones are blocked and the agent tries an alternative. Sessions run slightly more expensive due to the classifier. Currently research preview, team plan only. This is the designed-for-unattended-run permission posture — the first native answer to "how do I let agents run overnight without bypass?"

**[NEW] Routines — cloud environment: network access tiers** (trusted / full / custom)
When a Routine runs on Anthropic infrastructure, its network access can be scoped to an allowlist of Anthropic-vetted domains (trusted), unrestricted (full), or a custom domain set. Trusted mitigates prompt-injection exfiltration for routines that process external/untrusted content; full is needed for niche APIs. This is a permission surface that does not exist in local runs.

**[NEW] Routines — run quotas by plan tier**
Daily hard limits: Pro = 5/day, Max ($200/mo) = 15/day, Team/Enterprise = 25/day; minimum schedule interval = 1 hour. Each run: 4 vCPUs, 16 GB RAM, 30 GB disk. These are not configurable — they are a fixed economics ceiling for the CADENCE layer.

**[NEW] Skill-creator — skill eval / benchmark primitive**
The official Anthropic skill-creator plugin (installable from the /plugins registry) exposes a formal eval loop: supply approved-output examples, agent compares skill output vs. examples, reports pass rate, wall time, and token count with-vs-without the skill loaded. Two use-cases: catch regressions after a model update; spot skills the base model now outperforms (retire them). This is the first first-party tool for skills economics.

**[NEW] Skill-creator — skill trigger tuning**
Sub-function of skill-creator: tests natural-language trigger descriptions against all loaded skills, edits each skill's description YAML to reduce misfires, outputs a before/after accuracy chart. With 10+ skills loaded, trigger accuracy degrades measurably — this is the native maintenance tool.

**[NEW] /loop recurring tasks**
Runs a prompt on a recurring interval within a session (up to 3 days max). Retains session context across loops. Distinct from desktop scheduled tasks (which survive restarts but start cold). This is the first intra-session cadence primitive.

**[NEW] Peak/off-peak session throttling**
Anthropic throttles session-window drain rate based on platform demand. Peak hours: 8am–2pm ET weekdays. Off-peak sessions drain more slowly. Not user-configurable, but schedulable around — a concrete CADENCE-layer timing heuristic.

**[NEW] Prompt cache TTL tiers (clarified)**
Subscription sessions: 1-hour TTL. Sub-agents on any plan: always 5-minute TTL (not configurable, even on Max). Three cache-break triggers: idle past TTL, model switch mid-session (including plan-mode toggles), /compact or /clear. Editing CLAUDE.md mid-session does NOT break cache — changes apply only on restart.

**[NEW] /btw side-question overlay**
Slash command that opens a quick overlay for questions that do not enter conversation history. Keeps context clean for off-record clarifications mid-session.

**[NEW] Ultra Plan (cloud-hosted multi-agent planning)**
/ultra-plan offloads the planning step to an Anthropic cloud container running Opus 4.6 with 3 parallel exploration agents + 1 critique agent. Plans reviewable and commentable in a web UI; feedback triggers re-iteration; final plan "teleported" back to the local terminal. Token cost is not reported by /cost. Requires a Git-synced repo. Local terminal stays unblocked while cloud plans.

## Techniques worth adopting

**Model routing as a default rule, not a per-task decision.** Sub-agent runs cost 7–10x more tokens than single-agent sessions because each sub-agent independently reloads its full context. Mitigation: route sub-agents to Haiku for exploration, summarisation, and any task involving 3+ files; keep Sonnet for orchestration; reserve Opus for synthesis and high-stakes decisions. Nate demonstrated 41 Haiku scorers → 1 Opus synthesizer in a workflow run. The routing decision belongs in CLAUDE.md as a standing rule, not per-prompt.

**Compact at 60%, not 95%.** Auto-compact fires at 95% — by then context quality is already degraded. Manual /compact at ~60% with explicit preserve-instructions is the recommended cadence. After 3–4 consecutive compacts, do /clear + session-summary paste instead. The 12%/120k token absolute threshold (same absolute number as 60% of the old 200k window) is a concrete numeric trigger for the wrap skill.

**CLAUDE.md as routing index, not monolith.** Keep under 150–200 lines. Route to external files by path/URL; the system prompt loads the pointer, not the payload. Inline large reference docs destroy the token budget on every message. A self-evolving applied-learning footer (bullets under 15 words each, recording repeated failures and workarounds) provides lightweight cross-session memory that survives /clear.

**Sub-agent delegation rule encoded in CLAUDE.md.** "For any task needing 3+ files or multi-file analysis, spawn a sub-agent (Haiku) and return only summarised insights." This eliminates per-task model selection overhead and caps sub-agent context.

**Per-skill model assignment via front-matter.** The `model:` key in skill YAML front-matter routes that skill to a specific model. High-frequency lightweight skills → Haiku; deep-analysis skills → Opus. The skill-creator can discover and set this automatically.

**Hardcode stable IDs in skill.md.** Any skill that calls an MCP to discover identifiers (project IDs, channel IDs, audience IDs) and then uses them should cache those IDs directly in skill.md at authoring time. Nate watched his pulse-check skill calling ClickUp MCP on every invocation to rediscover the same list IDs; hardcoding them eliminated a multi-round-trip MCP call per run.

**Allowlist + denylist: deny takes priority.** settings.json allowedTools + deniedTools are both honoured, and denylist beats allowlist. Destructive operations (delete, remove, drop) must be in the deny list explicitly — their absence from the allow list is not equivalent.

**Per-project allowlist via settings.json as the solo-founder alternative to auto mode.** Until team plan access arrives, .claude/settings.json allowedTools/deniedTools is the correct manual substitute. Global settings.json sets a shared permission baseline for all new projects.

**Schedule heavy sessions off-peak.** Large refactors, multi-agent runs, and context-heavy sessions should run during off-peak hours (afternoons, evenings, weekends ET) to reduce session-window drain rate.

**Explicit env-var sourcing in every routine prompt.** Routine prompts must tell Claude where to find secrets: "My API key is available as an environment variable — use it directly, do not look for a .env." Without this, Claude defaults to .env search and fails silently.

**Context rot is quantified.** Retrieval accuracy: 92% at 256k tokens, drops to 78% at 1M. Thinking depth drops 67% as sessions grow. "Edit without read" behaviour goes from 6% to 34% in long sessions. 98.5% of tokens in a 100+-message chat are rereading prior history. These are citable thresholds for doctor/insights skill output.

## How this informs the framework

### Pillar 3 — Token Economics, Safety Audits, and the Doctor Extension

The economics and permissions material maps almost entirely to Pillar 3 of the [[nate-herk-give-me-10-mins]] framing extended by the doctor audit design in the positioning spec (see Reference below).

**KEEP — current framework elements confirmed by this corpus:**
- The "instructions != capabilities" / scope-the-keys safety model (see [[nate-herk-ai-os]]) is reinforced by the auto-mode material: even with auto mode, the tool ring is the primary constraint.
- The doctor skill's permission-audit step is correct in principle; it now has a concrete expansion scope (see ADOPT below).
- The sf-wrap / sf-recall session-lifecycle skills address a real, measured problem (98.5% reread overhead, context-rot thresholds).

**REBUILD — framework elements that need updating:**
- **Doctor skill → full session-health audit.** Doctor currently covers permissions only. It should add: (1) /context token-overhead parse — flag MCP server token cost, CLAUDE.md line count, loaded skills baseline; (2) sub-agent model routing audit — flag any sub-agent configuration running on Opus/Sonnet for a read-only or exploratory task; (3) routine network-access tier check — flag routines configured on `full` that process external/untrusted content; (4) auto-mode tier check — detect plan tier and emit the right recommendation (auto mode for team users on unattended runs; manual allowlist/denylist for solo/Pro). This is the "doctor audit extension" described in the positioning spec.
- **Wrap skill → structured session-handoff schema.** The current wrap skill produces a generic summary. The structured schema (decisions locked, what shipped, key files for next session, running state, deferred questions, pick-up block) survives /clear + paste cycles reliably and should replace the current output format. Add the 120k-token threshold as the default trigger signal.
- **CLAUDE.md routing convention.** The framework's bootstrap/install flow should enforce the index pattern from day one: CLAUDE.md under 200 lines, all large reference docs linked by path, not inlined.

**ADOPT — net-new additions this corpus motivates:**
- **Auto Permission Mode as the named unattended-run posture.** When the CADENCE layer is built out, the design doc should specify auto mode (or allowlist fallback for non-team plans) as the default permission posture for any scheduled or headless run. Document the cost premium explicitly. See [[context-mode]] for the complementary tool-output sandboxing approach.
- **Per-skill model routing via front-matter `model:` field.** The framework should document and use this field across all skills, aligned with the existing 3-tier strategy (Haiku → frequent/lightweight, Sonnet → orchestration, Opus → deep synthesis). The skill-creator benchmark primitive is the maintenance tool for this.
- **Skill taxonomy tags (capability-uplift vs. encoded-preference).** Mark each framework skill with a custom_type YAML field. Capability-uplift skills need periodic benchmark eval to check for model-obsolescence; encoded-preference skills (session-lifecycle, wrap, note, recall) are durable and need eval only for regression. The doctor step reads these tags. See [[py-harness-engineering]] for the convergent self-evolution evidence.
- **Stable-ID registry pattern in skill authoring guide.** Any framework skill that calls an MCP to discover identifiers (Resend audience IDs, Calendar resource IDs, etc.) should capture those IDs in skill.md at authoring time, not rediscover them on every run.
- **Sub-agent cache TTL constraint as a CADENCE design constraint.** The 5-minute TTL for all sub-agents (regardless of plan) means orchestrated multi-agent CADENCE runs are cache-cold by default unless tasks complete within 5 minutes. Keep sub-agent task scopes small and fast; prefer sequential over parallel orchestration when token cost matters.
- **Routine-quota awareness in doctor/insights.** Max plan = 15 routine runs/day. The doctor or insights skill should surface current quota usage so the founder knows CADENCE headroom before hitting the cap.
- **/loop as the first intra-session CADENCE primitive.** Document /loop alongside desktop scheduled tasks (stateless, persistent) as a named cadence tier: /loop (stateful, up to 3 days) for intra-session recurring checks; desktop tasks for cross-restart automation; routines for cloud-hosted, machine-off automation.

## Tensions / open questions

1. **Auto mode cost premium at scale.** Auto mode's per-tool-call classifier makes every session "slightly more expensive." For a solo founder running frequent CADENCE automations, this premium compounds. The wiki should document the tradeoff: auto-mode safety premium vs. tight manual allowlist for trusted, narrow-scope recurring tasks. No resolution yet — depends on how many tools the founder's setup exposes.

2. **Sub-agent TTL vs. parallel orchestration preference.** The 5-minute sub-agent TTL strongly penalises multi-agent parallelism unless tasks complete quickly. The framework's default orchestration advice should lean sequential-unless-necessary, but this conflicts with the agent-teams and dynamic-workflow material (see the multi-agent theme page) that favours parallelism for CADENCE. The right heuristic depends on task structure — needs a decision rule, not just a note.

3. **Ultra Plan token cost opacity.** /cost does not report cloud-side ultra-plan tokens. The framework has no way to audit this spend. The doctor step can warn, but cannot measure. Until Anthropic surfaces this in usage dashboards, it is a blind spot in the token-economics audit.

4. **context_mode (SQLite tool-output sandboxing).** Nate references a third-party MCP that intercepts raw tool output into SQLite instead of conversation history, preventing tool-output bloat. This maps to [[context-mode]] in the corpus. Worth evaluating as a default Connection, but it adds an external dependency and MCP token cost of its own — unresolved tradeoff.

5. **Denylist semantics gap.** Destructive operations absent from the allowlist are not the same as being in the denylist. Many users (and likely the current framework install) rely on "not allowed → not possible." This is a security posture gap that the doctor audit should explicitly surface and correct.

## Quotes worth preserving

> "hardcoded in these list IDs because when I was watching it, I realized every single time it was doing this, it was calling the ClickUp MCP and it was gathering all these lists and it was searching and parsing the results and then it would extract the ID and that just was taking so long and it was costing me a ton of tokens"
— nate-herk-master-95-of-claude-code-skills-in-28-minutes

> "auto mode let's Claude handle permissions automatically. Claude checks each tool for risky actions and prompt injection before executing. Actions Claude identify as safe are executed while actions Claude identifies as risky are blocked and Claude may try a different approach."
— nate-herk-stop-using-bypass-permissions-use-this-new-fe

> "it spun up 41 Haiku scoring agents because I have 41 skills here, and then it's feeding all of that analysis into an Opus synthesis agent"
— nate-herk-claude-code-dynamic-workflows-clearly-explained

> "One developer actually tracked a 100-plus message chat and found that 98.5% of all the tokens were just spent rereading the old chat history in the session."
— nate-herk-18-claude-code-token-hacks-in-18-minutes

> "Your sub agents on any plan are going to be 5 minutes."
— nate-herk-the-one-habit-that-doubles-your-claude-code-s

> "I basically just get to reset and it feels like I didn't reset because I already have all that context."
— nate-herk-how-to-manage-your-claude-limits-better-than

> "Ultra plan offloads your planning session to a cloud-hosted instance running Opus 4.6. It uses multi-agent exploration to build a deeper plan than the local mode can."
— nate-herk-planning-in-claude-code-just-got-a-huge-upgra

## Source videos

- nate-herk-master-95-of-claude-code-skills-in-28-minutes
- nate-herk-claude-code-skills-just-got-even-better
- nate-herk-claude-code-dynamic-workflows-clearly-explained
- nate-herk-stop-using-bypass-permissions-use-this-new-fe
- nate-herk-claude-code-source-code-just-leaked-8-things
- nate-herk-18-claude-code-token-hacks-in-18-minutes
- nate-herk-32-claude-code-hacks-in-16-mins
- nate-herk-the-one-habit-that-doubles-your-claude-code-s
- nate-herk-how-to-manage-your-claude-limits-better-than
- nate-herk-planning-in-claude-code-just-got-a-huge-upgra
- nate-herk-codex-just-10xd-claude-code-projects

## Reference

Positioning spec (defines Pillar 3 and the doctor audit extension this page feeds):
`docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
