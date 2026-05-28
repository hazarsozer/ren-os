---
title: Ralph / Ralph Wiggum (Anthropic) — Stop-Hook Loop Pattern for Autonomous Iteration
type: research
source_url: https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum
related_repos: [https://github.com/snarktank/ralph, https://github.com/madhavajay/ralph, https://github.com/frankbria/ralph-claude-code, https://github.com/wiggumdev/ralph]
source_fetched: 2026-05-28
license: see anthropics/claude-code (likely permissive)
ingested: 2026-05-28
tags: [autonomous-loops, stop-hook, lightweight-harness, ralph, optional, foreground-research]
status: ingested
related: [caleb-agent-harness, simon-scrapes-self-improving-skills, py-harness-engineering]
---

# Ralph / Ralph Wiggum — Stop-Hook Loop Pattern

## TL;DR

The canonical "lightweight harness" pattern, coined by Geoffrey Huntley with the line "Ralph is a Bash loop." Anthropic officially packaged it as the **ralph-wiggum** plugin (or ralph-loop) — a `Stop` hook that intercepts session exit and re-feeds the same prompt until a completion token is output. Multiple community implementations exist; Anthropic's version is the canonical reference. Not a tool we adopt by default for v1, but a **pattern we should know about** and possibly recommend for autonomous overnight runs. Worth flagging for our own design: it uses the Stop hook, which our `consolidate` skill also wants to use — potential collision.

## The pattern

> "Ralph is a Bash loop" — a simple `while true` that repeatedly feeds an AI agent a prompt file.

Anthropic's twist: instead of an external bash loop, **use a Stop hook to keep the session alive**. The loop runs INSIDE Claude Code, not around it.

```
You run ONCE:
  /ralph-loop "Your task description" --completion-promise "DONE"

Then Claude Code automatically:
  1. Works on the task
  2. Tries to exit
  3. Stop hook blocks exit
  4. Stop hook re-feeds the same prompt
  5. Repeat until <promise>COMPLETE</promise> emitted
     OR --max-iterations reached
     OR /cancel-ralph called
```

## Architecture (genuinely tiny)

**Files**:
- `hooks/stop-hook.sh` — the Stop interceptor that re-feeds the prompt
- A prompt file (passed via `/ralph-loop`)
- Project files (persist between iterations naturally)
- Git history (provides context of past changes)

**No daemon. No worker service. No database.** State persists via the filesystem and git. This IS the "lightweight harness" Caleb cited.

## Slash commands

- `/ralph-loop "<prompt>" --max-iterations <n> --completion-promise "<text>"`
- `/cancel-ralph`

## Prompt structure (best practice)

```
Build a REST API for todos.

When complete:
- All CRUD endpoints working
- Input validation in place
- Tests passing (coverage > 80%)
- README with API docs
- Output: <promise>COMPLETE</promise>
```

Key principles:
1. **Clear completion criteria** (not vague goals)
2. **Incremental phases** (break complex tasks into stages)
3. **Self-correction loops** (TDD, iterative testing)
4. **Escape hatches** (always include `--max-iterations`)

## Documented success cases (per README)

- **6 repositories generated overnight** at a Y Combinator hackathon
- **$50K contract completed for $297 in API costs**
- **A programming language created over 3 months** of Ralph iteration

These are notable but should be taken with grain-of-salt — successful Ralph runs require well-scoped tasks with measurable completion.

## Anti-patterns (when NOT to use Ralph)

- Tasks requiring human judgment or design decisions
- One-shot operations (single fix, single tweak)
- Tasks with unclear success criteria
- Production debugging (too much risk)

## Safety considerations

- `--max-iterations` is the **primary safety mechanism**. Default recommendation: ALWAYS include it.
- `--completion-promise` uses **exact string matching** — can't handle multiple completion conditions
- Infinite loops are possible on impossible tasks (without max-iterations)
- The Stop hook itself bypasses normal session-end semantics → conflicts with other plugins that touch Stop

## How this informs the framework

### Don't adopt by default; recommend for specific use cases

Ralph is a **pattern, not infrastructure**. We don't bundle it; we mention it in the framework's docs as the right tool for:
- Overnight autonomous tasks with measurable completion criteria
- Skill self-improvement loops (Karpathy-style, per Simon Scrapes)
- Long-running spec-driven implementations

### Critical: Stop hook collision concern

Our framework's `consolidate` skill needs the Stop hook (or `/wrap` slash command + manual call) to harvest session learnings into the wiki.

**If a user is running Ralph AND our framework, both want Stop.** Two interpretations:
- Ralph's stop hook blocks exit → re-feeds prompt → consolidate never runs
- Or our consolidate runs first → Ralph re-feeds → context now polluted with our consolidation message

**Resolution options**:
1. Our consolidate is `/wrap`-only (manual), no Stop hook → no collision, but less automatic
2. Our consolidate registers AFTER Ralph (if Claude Code supports hook ordering) → fragile
3. Our consolidate detects Ralph mode and disables itself during Ralph runs
4. Document mutual exclusion: "don't run Ralph and the framework's consolidate hook in the same session"

The simplest path: **`/wrap` slash command instead of Stop hook for consolidate**. Cleaner, no collision, user has explicit control.

This is a real design decision the foreground research surfaced. Document in the consolidate-skill ADR.

### Reinforcement of "lightweight is enough" thesis

Ralph + ~$297 → a $50K contract proves that **the harness doesn't need to be heavy to be effective**. Validates our Approach A+ (no daemon, files + hooks) direction.

> Mature harness work looks less like building structure up and more like pruning it down. — PY's harness-engineering source

Ralph is the absolute floor of that pruning: a Stop hook + a prompt file. Worth holding in mind as we design our framework — keep pruning until there's nothing left to remove without losing function.

### Could the framework provide a "consolidate-loop" using Ralph's pattern?

Speculation, not a v1 decision: a Ralph-style loop applied to wiki maintenance — re-feed a "verify wiki has no orphans, no contradictions, no stale claims" prompt on a schedule, with completion token "WIKI HEALTHY." Could automate the lint-wiki pattern Karpathy described. Out of v1 scope but interesting v2.

## Tensions / open questions

1. **Stop hook collision** between Ralph + our consolidate → resolve at design-doc time. Tentative answer: use `/wrap` slash command, not Stop hook.
2. **Multi-author Ralph runs** — if friends share a wiki and one runs Ralph overnight, what happens to the shared wiki? Probably nothing destructive (Ralph touches project code, not wiki), but worth thinking through.
3. **`--max-iterations` default** — Ralph doesn't enforce one. Our framework's docs should recommend a conservative default (e.g., 10) when introducing the pattern.
4. **License of `anthropics/claude-code` repo** — not in this README. Verify.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Caleb Agent Harness | Ralph IS the lightweight harness Caleb cited as canonical |
| Simon Scrapes Self-Improving Skills | The Karpathy auto-research loop Simon applied to skills is one specific instance of the Ralph pattern |
| PY Harness Engineering | Ralph operationalizes "fresh context per iteration" + "discipline-narrowing beats broadening" |
| Karpathy LLM Wiki | Ralph's loop pattern is what Karpathy's "auto-research" generalized into a wiki-maintenance / source-ingestion pattern |

## Followups

- Verify license of `anthropics/claude-code` repo (parent of ralph-wiggum)
- Decide consolidate hook strategy in design doc (Stop hook vs. `/wrap` slash command)
- Document Ralph as a "recommended-but-not-bundled" tool in framework docs

## Reference

- Anthropic official: https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum
- Also: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/ralph-loop
- Community implementations: snarktank/ralph, madhavajay/ralph, frankbria/ralph-claude-code, wiggumdev/ralph
- Origin: Geoffrey Huntley ("Ralph is a Bash loop")
- Fetched: 2026-05-28
- License: TBD (likely permissive, parent repo)
