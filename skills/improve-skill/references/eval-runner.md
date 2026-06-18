---
title: "/ren:improve-skill eval-runner — invoking the test suite, scoring"
type: skill-reference
parent_skill: sf-improve-skill
version: 0.1.0
date: 2026-05-28
---

# Eval runner — how the Karpathy loop scores a skill

The Karpathy loop (per `references/karpathy-loop.md`) needs ONE primitive: a function that takes a skill name + optional eval subset and returns a pass rate (0.0 - 1.0). Every keep-or-revert decision in the loop hinges on whether the score improved, stayed flat, or dropped.

This document settles the runner's design **without committing to implementation details** that depend on Skill Creator integration choices we don't yet own.

## The contract `run_evals(...)` must satisfy

```python
def run_evals(
    skill_name: str,
    *,
    eval_subset_ids: list[str] | None = None,   # If set, run only these test IDs
    timeout_seconds: int = 300,
    cwd: Path | None = None,
) -> EvalResult
```

Returns `EvalResult` (defined in `lib/types.py`):
```python
@dataclass(frozen=True)
class EvalResult:
    score: float                    # passed / total, 0.0–1.0
    passed: int
    total: int
    failing_assertion_ids: tuple[str, ...]
    raw_output: str = ""            # captured stdout/stderr for diagnostics
    # all_pass property → True when passed == total and total > 0
```

Properties the loop relies on:

1. **Deterministic given a clean working tree.** Same SKILL.md → same score. If the eval is non-deterministic (e.g., LLM-as-judge with temperature > 0), the runner must average ≥3 runs per assertion and return the binarized majority result. **No stochastic noise allowed in the score itself.**
2. **Fast enough for an iteration cycle.** Target <60s per eval run for typical 5-test skills. If the skill's eval suite legitimately runs longer, the friend can pass `--eval-subset` to narrow scope.
3. **Self-contained.** The runner does not modify the working tree, the git state, or anything outside its captured `raw_output`. Iteration commits must be made by the caller.
4. **Crash-survivable.** A runtime error during eval execution returns `score=0.0` (treat as a regression). The loop uses this signal to revert the iteration without aborting the outer loop.

## eval.json schema (the runner's input contract)

Per ADR-011 §"eval.json schema" (canonical; lines 104-129 of `wiki/decisions/011-skill-schema.md`):

```json
{
  "name": "<skill-name>",
  "tests": [
    {
      "id": "test-1",
      "prompt": "<input that should trigger and exercise the skill>",
      "expected_output_summary": "<one-line description>",
      "binary_assertions": [
        "<unambiguous true/false assertion 1>",
        "<unambiguous true/false assertion 2>"
      ],
      "trigger_test": true
    }
  ],
  "non_triggers": [
    { "id": "non-trigger-1", "prompt": "<...>", "expected_outcome": "skill_not_activated" }
  ]
}
```

Properties the runner consumes:

- `name`: skill identifier (for cross-checking against the directory name)
- `tests[].id`: stable identifier (used by `--eval-subset`)
- `tests[].prompt`: input to the skill
- `tests[].binary_assertions`: list of strings; each is an unambiguous true/false statement about the skill's output
- `tests[].trigger_test`: when True, also assert the skill activated (was selected by the host)
- `non_triggers[]`: prompts where the skill should NOT activate (activation discipline)

Properties the runner CAN ignore (informational only):

- `expected_output_summary`, `description`, `_status`, `_notes`, `$schema`, and any `_`-prefixed keys

## Score calculation

```
score = passed_binary_assertions / total_binary_assertions

where:
  total_binary_assertions = sum over all selected tests of len(test.binary_assertions)
  passed_binary_assertions = sum over each binary_assertion of:
      1 if assertion holds against the skill's actual output, else 0
```

Trigger tests add ONE additional binary assertion: "the skill activated on this prompt." Non-triggers contribute ONE assertion: "the skill did NOT activate on this prompt." Both count toward `total`.

If `total == 0` after subset filtering (degenerate case): return `EvalResult(score=0.0, passed=0, total=0, failing_assertion_ids=())` with a clear marker that no tests ran. The loop treats this as `eval_unrunnable` (one of the `ExitReason` enum members in `lib/types.py`).

## How natural-language binary_assertions are evaluated

Per ADR-011: binary_assertions are **strings** — unambiguous true/false statements like *"Output contains a code block in Python"* or *"No m-dashes in the response."*

These are NOT pytest-style assertions on a returned value. They're natural-language claims about the skill's output. Evaluation requires an LLM-as-judge:

1. Run the skill with the test prompt; capture the full output.
2. For each `binary_assertion` string, ask an LLM: *"Given the following output, is this statement TRUE or FALSE? `<assertion>`. Output exactly TRUE or FALSE."*
3. Treat the LLM's response as the binary outcome (after stripping case/whitespace).

The judge LLM should be a **cheap, fast model** (e.g., Haiku — fast turnaround, lower per-call cost; per `references/budget-tracking.md` model-pricing entries). Using Sonnet/Opus for judging is wasteful; the judge's task is yes/no on a short statement, not creative reasoning.

**Determinism requirement** (per §1 above): if the judge is invoked with `temperature > 0`, run 3 times per assertion and take the majority. With `temperature == 0`, one call suffices. Default: temperature 0 + one call.

## Integration with Skill Creator (open question)

Per ADR-011 § "eval.json schema":

> compatible with Skill Creator's `run_eval.py` per research

Skill Creator ships its own eval runner (`scripts/run_eval.py` per ADR-006's adoption). Two design paths:

1. **Adopt Skill Creator's runner directly.** Invoke it as a subprocess; parse its output into our `EvalResult`. Pros: zero reinvention; their format is the canonical compatibility surface. Cons: subprocess overhead per iteration; output parsing brittleness if their format evolves.
2. **Reimplement against the same eval.json schema.** Use our own LLM-judge invocation. Pros: tight integration with our budget tracker (we sum the judge's usage directly); avoid subprocess overhead. Cons: schema drift between our runner + theirs is now possible.

**V1 decision (revised 2026-06-18, C5a): path 2 — our own LLM-judge.** Rationale: no dependency on
Skill Creator's internal script surface; direct budget integration (judge token usage is summed
directly into the orchestrator's budget accounting); we own `eval.json`'s schema. The Phase-0
spike (`SPIKE_FINDINGS.md`) also confirmed that `--bare` skips auth (all authenticated calls must
be non-bare), making the "shell out to Skill Creator's `run_eval.py` via `--bare`" approach
non-viable without additional credential handling. Path 1 is therefore rejected.

The wrapper isolates the choice — anything OUTSIDE `lib/eval_runner.py` sees only the `run_evals()` contract; we can swap implementations transparently.

**`--bare` auth note (from SPIKE_FINDINGS.md):** `--bare` skips the credential store → "Not
logged in". All authenticated sub-calls (judge + change-proposer) must run **non-bare**. The
`bare` parameter in `claude_cli.run_print` is retained but defaults effectively to non-bare for
any authenticated call. Document that `bare=True` will NOT authenticate.

## `--eval-subset` semantics

When the friend passes `--eval-subset` to `/ren:improve-skill`:

```
/ren:improve-skill sf-wrap --eval-subset routine-debug-session-no-signal,decision-session-creates-adr
```

The runner:
1. Parses the comma-separated list of test IDs
2. Filters `eval.json`'s `tests[]` to only those whose `id` matches
3. Asserts at least one test matched (else `PreFlightError`)
4. Runs ONLY those tests; ignores `non_triggers` unless explicitly listed

Use case: friend wants to drill in on a specific failing test rather than re-running the full suite each iteration. Trades full-coverage assurance for iteration speed.

## Failure modes the loop must handle

| Runner exit | EvalResult shape | Loop action |
|---|---|---|
| All assertions pass | `score=1.0, all_pass=True` | Exit loop with `ExitReason.ALL_ASSERTIONS_PASS` |
| Partial pass | `score<1.0`, `failing_assertion_ids` non-empty | Continue: feed failing IDs into next change proposal |
| Eval framework crash | `score=0.0, raw_output` contains traceback | Treat iteration as regressed; revert; log; continue |
| eval.json malformed | Pre-flight should have caught this | If we hit it mid-loop: `ExitReason.EVAL_UNRUNNABLE` |
| Timeout exceeded | `score=0.0`; raw_output notes timeout | Same as crash: revert, continue |
| Zero tests after subset filter | `total=0, score=0.0` | `ExitReason.EVAL_UNRUNNABLE` |

## Reporting failing_assertion_ids upstream

`failing_assertion_ids` is a tuple of `<test-id>:<assertion-index>` strings:

```python
EvalResult(
    score=0.75,
    passed=15,
    total=20,
    failing_assertion_ids=(
        "decision-session-creates-adr:2",         # 3rd assertion (0-indexed: 2) in this test
        "format-violation-recovery:0",             # 1st assertion in this test
        "wiki-write-failure-rollback:1",           # 2nd assertion in this test
        ...
    ),
)
```

The change-proposer prompt receives this list verbatim:
*"Of the 20 binary assertions in your eval, these are failing: <list>. Propose ONE change to SKILL.md or references/ that would improve at least one of these without regressing the others."*

This is the load-bearing prompt for the Karpathy loop. The proposer doesn't see the full eval output (token budget); just the IDs of what's failing. Discipline-narrowing per PY's research.

## References

- ADR-011 (Skill Schema) — eval.json shape, binary-assertion discipline
- ADR-012 (Two-Layer Self-Improvement) — the loop this runner serves
- `references/karpathy-loop.md` — the discipline + loop body
- `references/budget-tracking.md` — model pricing for the judge LLM
- `wiki/research/skill-creator.md` — Skill Creator's run_eval.py we may adopt
- `wiki/research/simon-scrapes-self-improving-skills.md` — eval format origin
