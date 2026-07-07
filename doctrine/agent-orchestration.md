---
type: doctrine
activation: always-on
scope_glob: null
---

# Agent orchestration — decision tree + model routing

A companion to the cadence matrix. **Cadence answers "how should this *recur*?"** (`/loop` · Cron · `/goal` · Cloud Routine). **This answers "how should this *decompose* across agents?"** — when to stay inline, when to fan out, and which model each piece runs on. Both are thin glue over native Claude Code primitives; neither runs a daemon.

## The ladder — pick the lowest rung that fits

Climb only when the rung below genuinely doesn't fit. Each step up costs context + tokens + coordination, so the default is to stay low.

1. **Quick-ask (no decomposition)** — answer inline in the current turn. The default. Use unless the task is genuinely parallel, long-running, or needs isolated context.
2. **Skill** — a *repeatable procedure* you'll want again. Author or invoke a skill — `standard` (full contract), or `tier: lightweight` for a one-prompt shortcut. One job, composable.
3. **Sub-agent** — *one* bounded task that benefits from its own clean context (a focused search, a self-contained change, a review pass). Native `Task`/`Agent`; returns a result to the main thread.
4. **Agent team (parallel sub-agents)** — *several independent* tasks with no shared state, run concurrently. Dispatch them in one batch. **Cap 3–5 concurrent** — past that, coordination + token cost outweigh the speedup and results get hard to synthesize.
5. **`/goal`** — a *long autonomous loop with a measurable exit* (a passing test, a coverage threshold). Never a subjective goal — it loops forever. See `conventions.md`.
6. **Dynamic workflow** — *deterministic multi-stage* orchestration (pipeline / fan-out-then-merge) where control flow should be code, not model judgment. Use when stages have dependencies, you need loop-until-done, or you're driving many pieces with verification between stages.

## Model routing (per piece)

Route each agent to the cheapest model that does its job — don't run a fleet on the flagship:

- **Haiku** — cheap, frequent **worker** agents: parallel search, mechanical edits, classification, extraction. The default for fan-out workers.
- **Sonnet** — main development, **orchestrating** the workers, and non-trivial coding.
- **Opus** — only the hardest reasoning: architecture calls, adversarial review, deep synthesis.

Rule of thumb: a 3–5 agent fan-out is Haiku workers under a Sonnet orchestrator; reserve Opus for the one step that genuinely needs it.

## Anti-patterns

- **Fanning out a sequential task.** If step B needs step A's output, that's a pipeline (rung 6) or inline — not a parallel team.
- **A team where a sub-agent would do.** One bounded task = one sub-agent (rung 3). A "team of one" is pure overhead.
- **Unbounded fan-out.** No 20-agent swarms; cap at 3–5 and batch. If you bound coverage, say what you dropped.
- **Flagship workers.** Don't run mechanical parallel work on Opus/Sonnet when Haiku suffices.
- **A subjective `/goal`.** No measurable exit → it never terminates. Pair with the cadence "measurable exit" convention.

## See also

- `cadence-matrix.md` — the *recurrence* axis (`/loop` · Cron · `/goal` · Cloud Routine).
- `conventions.md` — self-terminating loops, measurable `/goal` exits, failure footer.

## Skill execution tiers — route work DOWN, keep judgment UP

Every RenOS skill declares `execution_tier` in its SKILL.md frontmatter (doctor lints it). The main session is usually the most expensive model in the room — mechanical skill work at that tier wastes tokens. Route by the declaration:

- **`deterministic`** — the skill's `lib/` scripts do the work; no LLM reasoning beyond invoking them. Run inline; never spawn an agent for these.
- **`worker`** — the reasoning is self-contained (facts in → drafts out): delegate it to a cheap worker-model subagent (Sonnet/Haiku-class) and take the output back. Inline only when subagents aren't available.
- **`judgment`** — main model only: queue approvals, durability calls, live dialog with the friend, and anything needing the conversation itself in context (wrap's L1 narrative is the canonical case — a subagent can't summarize a conversation it never saw).
