"""Execution doctrine card injected into every wake-up (spec: 0.6.4).

Kept stdlib-only and py3.9-safe: this rides the wake-up hook, which the
cold-machine seam executes on python:3.9-slim with no dependencies.
"""
from __future__ import annotations

from lib import ren_paths

SECTION_DOCTRINE = "## How we work (execution doctrine)"

_GATE_1_SP = (
    "1. **Brainstorm gate.** You MUST NOT design or build anything without an "
    "approved spec/plan. If none exists, invoke `superpowers:brainstorming` "
    "first — pin purpose, constraints, and approaches with the user before code."
)
_GATE_1_FALLBACK = (
    "1. **Brainstorm gate.** You MUST NOT design or build anything without an "
    "approved spec/plan. If none exists, work the idea back and forth with the "
    "user first — purpose, constraints, 2-3 approaches with trade-offs — and get "
    "explicit approval on a written design before code."
)
_GATE_2_SP = (
    "2. **Isolate & plan.** Set up an isolated workspace "
    "(`superpowers:using-git-worktrees`), then write the implementation plan "
    "with `superpowers:writing-plans` — the MAIN planning step; bite-sized "
    "TDD tasks with exact files and code."
)
_GATE_2_FALLBACK = (
    "2. **Isolate & plan.** Work on an isolated branch/worktree, then write "
    "the implementation plan — bite-sized test-first tasks with exact files "
    "and code — before any implementation."
)
_GATE_3 = (
    "3. **Decompose.** For multi-part plans, spawn the `ren-planner` agent to "
    "cut approved work into atomic briefs (one subtask ≈ one clean context). "
    "Skip only when the plan is already atomic — lowest rung that fits."
)
_GATE_4_SP = (
    "4. **Dispatch.** Execute via `superpowers:subagent-driven-development`: "
    "one fresh subagent per task, independent tasks in parallel, chained ones "
    "sequentially, test-first (`superpowers:test-driven-development`) inside "
    "each. Route every subagent to the cheapest class that fits per "
    "`doctrine/model-classes.md` — orchestrator-class workers are an "
    "anti-pattern."
)
_GATE_4_FALLBACK = (
    "4. **Dispatch.** One fresh subagent per subtask; independent tasks in "
    "parallel, chained ones sequentially; test-first inside each (failing "
    "test, implement, pass, commit). Route every subagent to the cheapest "
    "class that fits per `doctrine/model-classes.md` — orchestrator-class "
    "workers are an anti-pattern."
)
_GATE_5 = (
    "5. **Per-task review.** Review each task's work before chaining to the "
    "next — do not let unreviewed work compound."
)
_GATE_6 = (
    "6. **Review gate.** Before claiming done, spawn the `ren-reviewer` agent "
    "on the full train. Findings must be verified with runnable repros. Do "
    "NOT proceed past unresolved CRITICAL/HIGH findings. Work is not done "
    "until its open-work ledger line is closed."
)
_GATE_7_SP = (
    "7. **Finish.** Integrate via `superpowers:finishing-a-development-branch` "
    "and follow the repo's publish checklist when releasing."
)
_GATE_7_FALLBACK = (
    "7. **Finish.** Merge/integrate deliberately and follow the repo's "
    "publish checklist when releasing."
)
_FOOTER_FALLBACK = (
    "\n*(The `superpowers` plugin is a recommended companion that strengthens "
    "these gates — `/ren:doctor` will point you at it.)*"
)

_BODY = """
RenOS execution doctrine — these gates are MANDATORY for design/build work.

{gate1}
{gate2}
{gate3}
{gate4}
{gate5}
{gate6}
{gate7}

Red flags — if you catch yourself thinking any of these, STOP: the gate applies.

| Thought | Reality |
|---|---|
| "Too simple to need a design" | Simple work with unexamined assumptions wastes the most time. |
| "The plan is in my head" | If it isn't written and approved, it doesn't exist. |
| "This subagent needs the strongest model" | Route by class per `doctrine/model-classes.md`; judgment stays up, work goes down. |
"""


_COMPACT_BODY = """
RenOS execution doctrine — these gates are MANDATORY for design/build work.

1. **Brainstorm gate.** No design or build work without an approved spec/plan.
2. **Isolate & plan.** Worktree (`superpowers:using-git-worktrees`), then the
   implementation plan via `superpowers:writing-plans`.
3. **Decompose.** `ren-planner` briefs for multi-part plans (skip if atomic).
4. **Dispatch.** `superpowers:subagent-driven-development`, test-first per task;
   route subagents by class per `doctrine/model-classes.md` — never
   orchestrator-class workers.
5. **Per-task review** before chaining; then the **`ren-reviewer` gate** on the
   full train — clear every CRITICAL/HIGH and close the open-work ledger line.
"""


def render_doctrine_card_compact() -> str:
    """Head-preserving fallback used when the full card cannot fit its budget.

    The generic truncator keeps a text's TAIL, which on the full card elides the
    header and gates 1-3 — it drops exactly the part the card exists to deliver.
    Rather than change `truncate_text_to_tokens` (shared with other callers),
    the wake-up composer swaps in this variant, which is sized to survive the
    band-low calibration ratio (650 tokens x 1.5 chars/token = 975 chars) intact.
    """
    return f"{SECTION_DOCTRINE}\n{_COMPACT_BODY.strip()}"


def superpowers_installed() -> bool:
    """True when a superpowers plugin dir exists in the local plugin cache."""
    cache = ren_paths.claude_user_dir() / "plugins" / "cache"
    try:
        return any(p.is_dir() for p in cache.glob("*/superpowers"))
    except OSError:
        return False


def render_doctrine_card(superpowers: bool) -> str:
    body = _BODY.format(
        gate1=_GATE_1_SP if superpowers else _GATE_1_FALLBACK,
        gate2=_GATE_2_SP if superpowers else _GATE_2_FALLBACK,
        gate3=_GATE_3,
        gate4=_GATE_4_SP if superpowers else _GATE_4_FALLBACK,
        gate5=_GATE_5,
        gate6=_GATE_6,
        gate7=_GATE_7_SP if superpowers else _GATE_7_FALLBACK,
    )
    if not superpowers:
        body += _FOOTER_FALLBACK
    return f"{SECTION_DOCTRINE}\n{body.strip()}"
