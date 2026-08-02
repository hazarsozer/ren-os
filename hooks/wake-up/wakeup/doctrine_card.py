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
_GATE_3_SP = (
    "3. **Dispatch.** Run independent subtasks in parallel, chained ones "
    "sequentially, via `superpowers:subagent-driven-development`. Test-first "
    "(`superpowers:test-driven-development`) inside every subtask."
)
_GATE_3_FALLBACK = (
    "3. **Dispatch.** Run independent subtasks in parallel, chained ones "
    "sequentially, each in a fresh subagent. Test-first inside every subtask: "
    "write the failing test, see it fail, implement, see it pass, commit."
)
_FOOTER_FALLBACK = (
    "\n*(The `superpowers` plugin is a recommended companion that strengthens "
    "these gates — `/ren:doctor` will point you at it.)*"
)

_BODY = """
RenOS execution doctrine — these gates are MANDATORY for design/build work.

{gate1}
2. **Decompose.** Break the approved plan into atomic subtasks — spawn the
   `ren-planner` agent to cut it into briefs, each small enough for a fresh
   subagent (one subtask ≈ one clean context).
{gate3}
4. **Review gate.** Before chaining to the next subtask or claiming done,
   spawn the `ren-reviewer` agent on the work. Findings must be verified with
   runnable repros. Do NOT proceed past unresolved CRITICAL/HIGH findings.
   Work is not done until its line in the project's open-work ledger is closed
   (or consciously added).

Red flags — if you catch yourself thinking any of these, STOP: the gate applies.

| Thought | Reality |
|---|---|
| "Too simple to need a design" | Simple work with unexamined assumptions wastes the most time. |
| "I'll just do this one thing first" | Gates come BEFORE action. |
| "A review here is overkill" | Unreviewed chained work compounds errors. |
| "The plan is in my head" | If it isn't written and approved, it doesn't exist. |
"""


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
        gate3=_GATE_3_SP if superpowers else _GATE_3_FALLBACK,
    )
    if not superpowers:
        body += _FOOTER_FALLBACK
    return f"{SECTION_DOCTRINE}\n{body.strip()}"
