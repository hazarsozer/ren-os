---
title: Skills & Self-Improvement (Nate Herk, 2026)
type: research
source: "raw/transcripts/ — multiple Nate Herk 2026 videos"
ingested: 2026-06-08
tags: [aios, skills, skill-creator, self-improvement, evals, claude-code]
status: ingested
attribution: "Nate Herk | AI Automation (YouTube), 2026 videos"
related: [nate-herk-best-6-skills, simon-scrapes-self-improving-skills, skill-creator, ralph, simon-scrapes-claude-skills-upgrade]
---

# Skills & Self-Improvement (Nate Herk, 2026)

## TL;DR

Across a cluster of 2026 videos Nate Herk documents the current state of Claude Code's skills primitives and two distinct improvement loops: a manual feedback-cycle approach (watch agent work live, fix skill.md after each run, converge in ~5–10 cycles) and a first-party eval-backed loop via the new Anthropic `skill-creator` plugin. The most significant new CC primitives — `skill-creator`, skill evals/benchmarks, trigger-tuning, and the `Plugin Marketplace` — are flagged as `new_since_may2026` and land at Pillar 5 (self-improving capabilities) directly. The grill-me skill surfaces a complementary knowledge-extraction pattern that strengthens the context layer rather than the skills layer. Taken together the videos establish that skill health now requires three disciplines: authoring economics (stable-id caching, sub-agent delegation, reference-file offload), maintenance cadence (regression + retirement scans), and taxonomy hygiene (capability-uplift vs. encoded-preference).

## New Claude Code primitives

### [NEW] Official skill-creator plugin (Anthropic)

An Anthropic-published CC plugin installable via `/plugins → manage plugins → search 'skill-creator'`. Creates new skills from natural-language specs, improves existing skills, runs formal evals against example corpora, benchmarks pass-rate / wall-time / token-count with and without the skill, and tunes trigger descriptions to reduce misfires. This is the first-party, versioned replacement for hand-rolled self-improvement loops like the framework's current `improve-skill`. Key invocation: `/skill-creator eval --skill <name> --examples <dir>`.

### [NEW] Skill eval / benchmark primitive

The skill-creator exposes a structured eval loop: supply example inputs + desired outputs (approved prior outputs as fixtures), run the agent against them, report pass-rate, wall time, and token count side-by-side with vs. without the skill loaded. Designed to catch two signals: regressions (model update breaks previously-passing skill) and retirement candidates (base model now outperforms the skill unaided).

### [NEW] Skill trigger tuning

A sub-function of skill-creator that tests candidate natural-language prompts against all loaded skills, then edits each skill's description YAML to sharpen auto-invocation accuracy. Produces a before/after train/test score chart. Becomes important once 10+ skills are loaded, when trigger collision and misfires degrade UX meaningfully.

### [NEW] Plugin registry / /plugins UI

Claude Code's `/plugins` command surfaces an Anthropic-official and community plugin marketplace, browsable and installable per-user or per-project. The skill-creator is the first official plugin published there. Distinct from MCP servers — this is a packaged skill/command distribution channel built into CC itself.

### [NEW] Agent View (`claude agents`) + `/bg` flag

Native CLI dashboard showing all running CC sessions in one terminal tab; sessions report yellow (waiting on input) or green (complete) with elapsed time. `/bg` puts a live session into Agent View mid-conversation; `claude --bg "<task>"` launches a background session directly. Inline Space-to-reply from Agent View handles approval gates without entering the session.

### [NEW] /goal command

Sets an autonomous objective that CC pursues in a loop — experiments, iterates, and runs for hours (overnight if needed) until the metric or done-criterion is hit. Depth-first: agent keeps iterating until `done=true` is triggered. Contrasts with dynamic workflows (breadth / fan-out). Pairs directly with the framework's Karpathy-style improve-skill loop.

### [NEW] Dynamic Workflows

CC generates a JavaScript file that fans out potentially hundreds of parallel sub-agents, collects results, and synthesizes them. Invoked explicitly ("set up a dynamic workflow to…"). Saved to `.claude/workflows/` and reusable; visible live via `/workflows` command. Released with Claude Opus 4.8.

### [NEW] CronCreate / CronList / CronDelete tools

Native CC scheduling tools. `CronCreate` accepts cron syntax and registers a session-scoped recurring task. `CronList` enumerates active crons for the current session. `CronDelete` removes by job-id. These are the mechanism behind the existing `/loop` skill and are not yet documented in the framework wiki. Session-scoped: die if the session closes; auto-expire at 3 days.

### [NEW] Cloud Routines (remote scheduled agents)

Routines running on Anthropic infrastructure — machine and session can be fully off. Trigger modes: time schedule, GitHub event, or API webhook. Quota: 5/day (Pro), 15/day (Max), 25/day (Team/Enterprise). Each run is stateless — cloned environment destroyed after the run; any artifacts must be persisted to GitHub. This is the missing hosted-cadence primitive for the framework's weakest layer.

### [NEW] Ultra Plan

`/ultra-plan` offloads the planning session to a cloud-hosted Anthropic container running Opus 4.6 with 3 parallel exploration agents + 1 critique agent. Plans are drafted in a web UI with inline comment/emoji feedback loops, then "teleported" back to the local terminal for execution. Requires a Git-synced repo. Local terminal stays unblocked during planning. Token cost is hidden from `/cost`.

### [NEW] Auto Permission Mode

A new permission tier between "ask before edits" and "bypass". A per-tool-call AI classifier reviews for destructive or sensitive actions before each execution; safe actions proceed automatically, risky ones are blocked. Activated via `claude --enable-auto-mode`. Currently in research preview, team plan only. Designed for long-running unattended task runs in isolated environments.

---

Skill front-matter fields confirmed (not new but underused): `allowed_tools`, `model`, `hooks`, `agent`, `argument_hint`, `disable_model_invocation`. Progressive 3-level context loading (front-matter → skill.md → reference files) is the platform's built-in loading mechanism; skill authors can exploit it deliberately.

## Techniques worth adopting

**Hardcode stable MCP IDs in skill.md.** When watching a skill execute, Nate noticed it was calling the ClickUp MCP to rediscover list IDs that never change — burning tokens on every invocation. Hardcoding those IDs into skill.md eliminates the discovery round-trip. Applies to any skill that repeatedly queries stable identifiers (project IDs, channel IDs, audience slugs).

**Sub-agent delegation for token-expensive MCP operations.** Rather than letting the orchestrator agent exhaust its context window on a broad ClickUp search, a dedicated sub-agent handles the search and returns only the relevant extract. Pattern: identify high-token MCP operations in a skill → create a lightweight specialist sub-agent → delegate from the skill.md via `agent` front-matter or explicit instruction.

**Pre-scrape external docs into a local `reference.md`.** The skill-builder skill was doing a live web crawl of CC docs on every invocation. Pre-scraping into a reference.md file (pointed to from skill.md) removes HTTP overhead and delivers cheaper, faster, reproducible reads. Refreshing this file on a schedule becomes a natural cadence task.

**Feedback-cycle iteration: watch live, fix after each run.** Explicit protocol: run skill, watch every step, identify token-waste or quality gaps, feed corrections back and let the agent edit skill.md. Skills converge to "really, really good" after ~5–10 cycles. Watching live (not just checking output) catches mid-execution inefficiencies not visible in the final result.

**Context-clear before feedback iteration.** Clear context (at ~62% usage) before sending corrective feedback on a skill draft. Starting a fresh context with only the feedback prevents prior scaffolding from polluting the correction. Applicable to the framework's improve-skill loop.

**Two-tier skill taxonomy: capability-uplift vs. encoded-preference.** Capability-uplift skills compensate for model gaps (e.g., front-end design taste) and may become obsolete as base models improve. Encoded-preference skills encode idiosyncratic personal workflows the base model will never be trained on — durable across model upgrades. Maintenance strategy differs: capability-uplift needs periodic evals; encoded-preference needs regression coverage only.

**Skill trigger tuning as a scheduled maintenance task.** Once 10+ skills are loaded, trigger accuracy degrades. Run skill-creator trigger-tune after adding each new skill and periodically during doctor audits. Should be a standing item in any maintenance cadence.

**Grill-me interview skill.** A short skill prompt that interviews the user one question at a time about a process or plan until no knowledge gaps remain. Each question is asked individually; the skill recommends an answer before asking. Nate extended the base with checkpoint-to-file (write a running markdown snapshot after every Q&A exchange), open-flags tagging (surface questions the user cannot answer, name who to contact), and a post-session offer to update existing skill files with newly surfaced nuance. Attributed to Matt PCO as originator.

**Width vs. depth decision heuristic.** "Does this break into many independent pieces that can run simultaneously?" → dynamic workflow. "Do I need to keep checking against a done criterion until it flips?" → `/goal`. Combining them is possible but expensive; decide deliberately. Nate's full routing ladder: quick ask → skill → sub-agent → agent team → `/goal` → dynamic workflow.

**Haiku workers + Opus synthesis in dynamic workflows.** Route all parallel worker/scoring agents to Haiku (cheap, fast); reserve one Opus agent for final synthesis/ranking. Nate ran 41 Haiku scorers → 1 Opus synthesizer consuming ~5M input tokens cheaply.

## How this informs the framework

### Pillar 5: Self-improving capabilities (dependency-map + bike-method graduation)

**ADOPT — skill-creator as the eval backbone.** The framework ships an EXPERIMENTAL `improve-skill`; the Anthropic `skill-creator` plugin is the first-party, eval-backed replacement. The correct split: delegate eval, benchmark, and trigger-tune to `skill-creator`; reserve the framework's `improve-skill` as a feedback-ingestion front-end (collecting approved outputs as example fixtures). Avoid duplicating Anthropic's official tooling. See [[simon-scrapes-self-improving-skills]] and [[simon-scrapes-claude-skills-upgrade]] for converging outside-in evidence that phased, feedback-driven evolution is the right model.

**ADOPT — capability-uplift vs. encoded-preference taxonomy.** Add a `custom_type` field to each skill's YAML front-matter: `capability-uplift` or `encoded-preference`. This makes the taxonomy machine-readable for the doctor/audit step and determines maintenance strategy (periodic benchmark vs. regression-only). The [[skill-creator]] corpus and the framework's own skill library both benefit from this tagging.

**ADOPT — skill corpus directory.** Persist approved skill outputs as eval fixtures under `.claude/skills/evals/<skill-name>/`. This makes the eval loop self-feeding without extra user effort: every session that approves a skill output is implicitly contributing to the corpus. No extra convention needed beyond naming the directory.

**ADOPT — trigger-tune as a doctor sub-step.** Embed a `skill-creator trigger-tune` invocation in the doctor checklist. As the framework's skill library grows (already ~10 skills), trigger collision will accumulate silently. Doctor is the right place to surface and fix this.

**REBUILD (lightweight) — two skill tiers alongside ADR-011.** The full ADR-011 schema is appropriate for complex, stateful skills. A lightweight alias/prompt tier (short skill.md, no reference files, front-matter only) is appropriate for simple encoded-preference shortcuts ("a prompt you don't want to retype"). The framework should document both tiers explicitly so authors choose the right template for their use case.

**ADOPT — stable-id registry and reference-file caching patterns.** Document the hardcoded-IDs technique and the pre-scrape-to-reference.md technique in the skill authoring guide. Any future CADENCE skill that calls MCPs should capture stable identifiers at authoring time. Reference files should be refreshable via a cadence automation ("refresh skill reference files weekly").

### Pillar 6: Code-map and observability

**ADOPT — skill-inside-workflow nesting.** Sub-agents spawned by dynamic workflows inherit skill access; a workflow can delegate to a named skill without rewriting logic. Document this composition contract so framework authors can build large parallel jobs from existing skill recipes.

**ADOPT — token variance as a skill quality signal.** Tight token variance per run = consistent skill; high variance = inconsistency. The framework could track per-run token counts in session memory and surface high-variance skills as improvement candidates during doctor audits. This is a lightweight observability primitive requiring only wrap-step logging.

**KEEP — bike-method graduation framing.** [[nate-herk-ai-os]] established the bike-method framing for phased trust. The eval loop now gives the framework a concrete mechanism to operationalize "earning autonomy" — a skill graduates from experimental to stable when its eval pass-rate clears a threshold across N runs. This closes the loop between the framing and the mechanics.

### CADENCE layer (weakest — multiple converging signals)

The most important CADENCE findings from this cluster: `CronCreate/CronList/CronDelete` tools exist now and are not documented in the wiki; Cloud Routines (15/day on Max, machine-off, stateless) are the lowest-friction hosted-cadence option; `/goal` is a native loop-until-done primitive that can run 24h+; `claude --bg "<task>"` + Agent View provides a fire-and-monitor substrate. A skill-audit cadence task (weekly regression + retirement scan via skill-creator benchmark across all capability-uplift skills) is the most immediately actionable CADENCE improvement that also strengthens Pillar 5.

See the positioning spec for full CADENCE design direction.

## Tensions / open questions

1. **skill-creator vs. improve-skill overlap.** The feedback-ingestion front-end (improve-skill) still needs a spec defining exactly what it collects and how it hands off to skill-creator. Without this the two loops risk conflicting rather than composing.

2. **Eval fixtures discipline.** The corpus-directory approach only works if approved outputs are actually saved. The framework's wrap command needs an explicit hook that offers to store approved skill outputs after a session — otherwise the corpus remains empty and the eval loop is inert.

3. **Trigger-tune at what threshold?** At 10+ skills per Nate. The framework already has ~10 skills. This is not a future concern — the trigger-tune step should be in the next doctor run.

4. **/goal and context-rot.** `/goal` can run 24h+ unattended. Without an auto-compact cron (Nate's pattern: pair a work cron with a `/clear` cron at slightly higher frequency) context accumulation silently degrades late-iteration quality. Any framework `/goal` wrapper must include this guard.

5. **Grill-me vs. interview skill.** The framework already has interview-style bootstrap. A dedicated persistent-Q&A extraction skill (`/sf:grill`) would address a different use case: deep knowledge extraction for wiki population, not project setup. Worth distinguishing before building to avoid duplication.

6. **Cloud Routines and stateless artifact persistence.** Each routine run destroys the cloud environment; artifacts must be written to GitHub. The framework's session artifacts (wrap outputs, eval results) need a Git-commit step in any routine-based workflow — this is a non-obvious constraint for first-time CADENCE builders.

## Quotes worth preserving

> "hardcoded in these list IDs because when I was watching it, I realized every single time it was doing this, it was calling the ClickUp MCP and it was gathering all these lists and it was searching and parsing the results and then it would extract the ID and that just was taking so long and it was costing me a ton of tokens"

> "Over time, a natural language description of what the skill should do may be enough, with the model figuring out the rest."

> "Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one. For each question, provide your recommended answer. Ask questions one at a time."

> "it spun up 41 Haiku scoring agents because I have 41 skills here, and then it's feeding all of that analysis into an Opus synthesis agent"

> "Cloud Code has three different tools for this sort of thing, which is called cron create, cron list, and cron delete."

> "instead of letting Claude code just start coding when you ask it to build something, it goes through a super super disciplined set of phases"

## Source videos

- `nate-herk-master-95-of-claude-code-skills-in-28-minutes` (signal: medium)
- `nate-herk-claude-code-skills-just-got-even-better` (signal: medium — skill-creator + evals)
- `nate-herk-the-skill-that-10xd-my-claude-code-projects` (signal: low — grill-me)
- `nate-herk-agentic-workflows-just-changed-ai-automation` (signal: medium — WAT + [[ralph]])
- `nate-herk-how-to-build-10000-agentic-workflows-claude-c` (signal: low — WAT)
- `nate-herk-how-id-teach-a-10-year-old-to-build-agentic-w` (signal: low — WAT)
- `nate-herk-multi-agent-building-in-claude-code-somehow-g` (signal: high — Agent View + /bg + /goal)
- `nate-herk-claude-code-dynamic-workflows-clearly-explained` (signal: high — Dynamic Workflows + /effort ultra)
- `nate-herk-i-tested-3-ways-to-deploy-claude-agents-heres` (signal: high — CronCreate + Cloud Routines)
- `nate-herk-stop-using-bypass-permissions-use-this-new-fe` (signal: medium — Auto Permission Mode)
- `nate-herk-claude-code-source-code-just-leaked-8-things` (signal: medium — Daemon + Coordinator flags)
- `nate-herk-planning-in-claude-code-just-got-a-huge-upgra` (signal: high — Ultra Plan)
- `nate-herk-how-to-use-your-claude-code-projects-in-codex` (signal: low — portability)
- `nate-herk-codex-just-10xd-claude-code-projects` (signal: medium — adversarial review)
- `nate-herk-unlock-the-next-evolution-of-claude-code-with` (signal: medium — dispatcher + budget-capped runs)
- `nate-herk-build-sell-claude-code-operating-systems-2-ho` (signal: high — Routines + /loop mechanics)

## Reference

- Positioning spec: `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
- Related corpus pages: [[nate-herk-best-6-skills]], [[simon-scrapes-self-improving-skills]], [[skill-creator]], [[ralph]], [[simon-scrapes-claude-skills-upgrade]]
