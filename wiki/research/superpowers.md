---
title: Superpowers (obra) — Software Development Methodology Skills Framework
type: research
source_url: https://github.com/obra/superpowers
source_fetched: 2026-05-28
license: MIT
version_at_capture: v5.1.0
ingested: 2026-05-28
tags: [skills, methodology, tdd, brainstorming, subagent-dispatch, claude-code, official-marketplace, foreground-research, dogfooding]
status: ingested
related: [nate-herk-best-6-skills, simon-scrapes-self-improving-skills, py-harness-engineering]
---

# Superpowers (obra) — Software Development Methodology Skills Framework

## TL;DR

Built by Jesse Vincent (Prime Radiant). **In the official Anthropic Claude Code marketplace** since January 15, 2026. MIT-licensed. 150K–177K GitHub stars. Provides a 7-phase development methodology (Brainstorm → Worktree → Plan → TDD → Subagent Dev → Review → Finish) as a composable skills framework. **This is the plugin currently powering our brainstorming session right now — we're already dogfooding it.** Multi-platform (Claude Code, Codex CLI, Gemini, Cursor, GitHub Copilot CLI, OpenCode, Factory Droid).

## Crucial context: we're using it right now

The brainstorming skill that's been running this entire framework-design session is from Superpowers v5.1.0, currently installed on the user's machine at `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/`. We're not evaluating an unfamiliar tool — we're documenting one we're actively using.

That's a strong endorsement: the user picked Superpowers, used it, found it useful enough to anchor a multi-hour design session in. Adoption in our framework is essentially confirmed by behavior.

## What it provides

**Testing & Debugging skills:**
- `test-driven-development` — RED-GREEN-REFACTOR cycle (literally deletes code written before tests exist)
- `systematic-debugging` — 4-phase root cause process
- `verification-before-completion`

**Collaboration skills:**
- `brainstorming` — refines ideas; presents design in sections; ends in writing-plans invocation (← THIS is what we're using now)
- `writing-plans`
- `executing-plans`
- `subagent-driven-development` — dispatches fresh subagent per task with two-stage review
- `requesting-code-review`
- `using-git-worktrees`
- `finishing-a-development-branch`

## The 7-phase workflow

| Phase | Skill | Output |
|---|---|---|
| 1. Brainstorm | `brainstorming` | Design doc in readable sections |
| 2. Worktree | `using-git-worktrees` | Isolated branch workspace |
| 3. Plan | `writing-plans` | 2–5 minute tasks with exact file paths |
| 4. TDD | `test-driven-development` | Tests first (enforced by deletion) |
| 5. Subagent Dev | `subagent-driven-development` | Fresh subagent per task |
| 6. Review | `requesting-code-review` | Critical issues block progress |
| 7. Finish | `finishing-a-development-branch` | Merge/PR/keep/discard options |

This 7-phase workflow IS the framework. Skills don't operate in isolation; they chain into this methodology.

## Architecture

- **Skills library** organized by domain (Testing, Debugging, Collaboration, Meta)
- **Git worktrees** for parallel development branches
- **Subagent dispatch** for concurrent task execution (~2-hour autonomous runs without deviation)
- **Cross-platform plugin harnesses** — each platform gets its own config (`.claude-plugin`, `.codex-plugin`, `.cursor-plugin`, etc.)

**No discrete hook system.** Skills trigger automatically based on user intent + skill descriptions. This means **Superpowers does NOT conflict with claude-mem or Context Mode at the lifecycle-hook level** — they operate in different layers. Important compatibility insight.

## License: MIT

Fully permissive. Adoption is unencumbered for any use.

## Install path

For Claude Code:
```
/plugin install superpowers@claude-plugins-official
```

(Official Anthropic marketplace — no separate marketplace add step needed.)

Other platforms (per-harness install):
- Codex CLI: `/plugins` → install
- Gemini CLI: `gemini extensions install https://github.com/obra/superpowers`
- Cursor: `/add-plugin superpowers`
- GitHub Copilot CLI: via `superpowers-marketplace` companion repo
- OpenCode, Factory Droid: separate installation per harness

**Caveat from docs**: install Superpowers separately even if you already use it in another harness. Per-harness independence (no shared state across harnesses).

## How this informs the framework

### Adopt — confirmed by dogfooding

Superpowers goes in our curated stack. Not just because of the 150K+ stars, but because the user is already running it and we've validated its value over hours of brainstorming.

### Specific skills we want active by default

For our friend group:
- **brainstorming** — at the start of any new feature/project decision
- **test-driven-development** — for any new code
- **systematic-debugging** — for any bug investigation
- **writing-plans** + **executing-plans** — for multi-step implementation
- **subagent-driven-development** — for parallelizable work
- **requesting-code-review** — for any commit-worthy change

Less universally relevant (project-specific):
- `using-git-worktrees` — useful for some workflows, overkill for others
- `finishing-a-development-branch` — only if the team uses branch-based workflows

The framework's onboarding can install Superpowers globally + recommend enabling these specific skills.

### The 7-phase methodology IS opinionated

Superpowers is OPINIONATED about how software gets built (TDD mandatory, plans before code, worktrees for parallelism, etc.). For our friend group:
- Pro: the discipline is good for shipping quality code
- Pro: matches "discipline narrowing > expensive broadening" from PY's harness research
- Con: rigid for exploratory / prototyping work
- Con: may not fit all members' working styles

Adoption decision should be explicit in onboarding — friends should know what they're signing up for.

### Hook-level compatibility with claude-mem + Context Mode

Confirmed: Superpowers has no discrete hooks. **Hook ordering concerns only between claude-mem + Context Mode + our framework's own hooks.** Superpowers operates at the skill-activation layer, doesn't touch lifecycle hooks.

This simplifies our stack design — Superpowers is a layer we can add cleanly.

### Subagent-driven development connects to our research convergence

Superpowers' subagent-driven-development implements:
- **Sub-agent management** (Prompt Engineering #4)
- **90% compute through child agents** (PY harness research)
- **Spawn, restrict, collect outputs** (Prompt Engineering pattern)
- **Skill systems** with HITL checkpoints (Simon Scrapes)

It's the existing implementation of patterns we'd otherwise have to build ourselves. Validates the broader thesis.

### The brainstorming skill's flow becomes part of our framework

The current conversation has been running through Superpowers' brainstorming flowchart:
1. Explore project context ✅
2. Offer visual companion (skipped — not needed)
3. Ask clarifying questions ✅ (extensively)
4. Propose 2-3 approaches ✅
5. Present design ⏳ (in progress — research phase ongoing)
6. Write design doc ⏳ (pending)
7. Spec self-review ⏳ (pending)
8. User reviews spec ⏳ (pending)
9. Transition to writing-plans ⏳ (pending)

We're using the skill the framework will recommend. Loop is closed.

## Tensions / open questions

1. **7-phase rigidity for friend-group workflow** — is the friend group's exploratory phase (idea hunting, not feature-shipping) well-served by TDD-mandatory discipline? Possibly NOT for early ideation. Mention in onboarding.
2. **Skill activation reliability** — Simon's self-improving-skills source noted community testing found YAML descriptions as low as 20% activation. Do Superpowers' descriptions hit reliably? Worth a check in our deployment.
3. **Per-harness independence** — friends switching between machines / between Claude Code and Cursor would need to reinstall + reconfigure each. Document in onboarding.
4. **Worktree-based skills** — some friend-group members might not use worktrees. Mention as optional.
5. **Subagent budget against the 5-min TTL** — Superpowers dispatches subagents. Combined with Nate Herk's finding (sub-agent cache TTL = 5 min), heavy parallel subagent use could be expensive. Need to characterize the cost profile.
6. **Comparison to GSD** — Simon and Nate both mentioned GSD as a sub-agent delegation tool. How does Superpowers' `subagent-driven-development` compare to GSD? Are they duplicative? Complementary? Worth a head-to-head check in the next research pass.

## Connections to prior research

| Prior source | What Superpowers confirms / implements |
|---|---|
| Nate Herk Best 6 Skills | Verified: 150K+ stars, official Anthropic marketplace |
| Simon Scrapes Self-Improving Skills | Superpowers' methodology aligns with the self-improvement / binary-assertion practices |
| PY Harness Engineering | Implements ~90% sub-agent compute pattern via `subagent-driven-development` |
| Prompt Engineering Harness | Implements harness components #3 (skills/tools), #4 (sub-agent management), #5 (built-in skills) |
| Caleb Agent Harness | Implements "loops with fresh clean context per iteration" at the sub-agent task level |

## Followups

- Compare Superpowers' subagent-driven-development to GSD (next research target)
- Test Superpowers + claude-mem + Context Mode together in a real session — verify no compatibility issues
- Inspect specific Superpowers skill YAML descriptions for activation reliability
- Inventory which skills we want active by default vs. opt-in for our friend group

## Reference

- GitHub: https://github.com/obra/superpowers
- Companion: https://github.com/obra/superpowers-marketplace
- Anthropic plugin page: https://claude.com/plugins/superpowers
- Author: Jesse Vincent / Prime Radiant
- Fetched: 2026-05-28
- Version at capture: v5.1.0 (released May 4, 2026)
- License: MIT
- In Anthropic official marketplace: since January 15, 2026
- Current usage: powering this brainstorming session
