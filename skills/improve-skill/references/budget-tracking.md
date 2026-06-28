---
title: "/ren:improve-skill budget tracking — shadow USD + shadow turns"
type: skill-reference
parent_skill: sf-improve-skill
version: 0.1.0
date: 2026-05-28
---

# Budget tracking

The loop's safety bounds depend on accurate budget accounting. CC's native `--max-budget-usd` works **only in print mode** (verified 2026-05-28 — see `cc-flag-watch.md`). Inner sub-runs use print mode and inherit the CC-native cap; the outer loop tracks a **shadow budget** that combines inner-sub-run usage + any direct API calls we make for orchestration.

Per ADR-012 amendment-of-correction (2026-05-28): `--max-turns` does NOT exist as a CC CLI flag in CC `2.1.154`. We optionally track a **shadow turn count** as belt-and-suspenders.

## Two budgets, two stopping criteria

| Budget | Type | Source of truth | Stops the loop when |
|---|---|---|---|
| **`--max-budget-usd N`** | Dollar cap | Sum of all inner-sub-run usage × current model pricing | `cumulative_usd >= max_budget_usd` |
| **`--max-iterations N`** | Iteration cap | Our framework counter | `iteration > max_iterations` |
| **`--max-turns-shadow N`** (optional, framework-internal) | Sub-run turn cap | Sum of responses across all inner sub-runs | `cumulative_turns >= max_turns_shadow` |

**`--max-iterations` is always set.** It's the canonical outer-loop ceiling. `--max-budget-usd` is required only in `--autonomous` mode (per pre-flight). `--max-turns-shadow` is optional and rarely needed in practice.

## Model pricing table

The shadow USD budget needs current per-token prices. We bake them into a config table per plugin version (per ADR-006 versioning):

`skills/sf-improve-skill/references/model-pricing.json` (template):

```json
{
  "$schema": "../../../skills/wiki-migration/schemas.json#/model-pricing",
  "version": "1.0.0",
  "valid_as_of": "2026-05-28",
  "pricing_usd_per_million_tokens": {
    "claude-sonnet-4-6": {
      "input": 3.00,
      "output": 15.00,
      "cache_read": 0.30,
      "cache_creation": 3.75
    },
    "claude-opus-4-5": {
      "input": 15.00,
      "output": 75.00,
      "cache_read": 1.50,
      "cache_creation": 18.75
    },
    "claude-haiku-4-5": {
      "input": 1.00,
      "output": 5.00,
      "cache_read": 0.10,
      "cache_creation": 1.25
    }
  },
  "_notes": "Pricing tracked here per ADR-006 plugin-versioning discipline. Bumps to this file are bound to plugin minor or patch releases. If Anthropic changes pricing mid-version-cycle, /ren:doctor will warn about staleness and prompt /ren:update."
}
```

This is V1 stub data; actual prices need verification against Anthropic's current pricing page before plugin release.

## Shadow USD calculation

After each inner sub-run, we sum the usage from its API response:

```python
def update_shadow_usd(prior_total_usd: float, usage: ApiUsage, model: str) -> float:
    prices = MODEL_PRICING[model]
    spent = (
        usage.input_tokens * prices["input"] / 1_000_000
        + usage.output_tokens * prices["output"] / 1_000_000
        + usage.cache_read_input_tokens * prices["cache_read"] / 1_000_000
        + usage.cache_creation_input_tokens * prices["cache_creation"] / 1_000_000
    )
    return prior_total_usd + spent
```

`ApiUsage` is a frozen dataclass with the standard Anthropic usage fields (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`). We parse it from each inner sub-run's response.

**Where the inner sub-run's response comes from**: the `claude --bare --print --output-format=json --max-budget-usd <remaining> ...` invocation emits a structured JSON object whose schema includes `usage`. We capture that.

## Shadow turn calculation

For optional turn tracking:

```python
def update_shadow_turns(prior_count: int, sub_run_response: dict) -> int:
    # Count assistant turns in the sub-run; for print-mode, this is typically 1
    # but stream-json mode can have multi-turn sub-runs (rare in our use)
    return prior_count + count_assistant_turns(sub_run_response)
```

Rarely binding in practice because each inner sub-run is a single proposed change (one turn). We expose it for users who want a tight ceiling.

## Pre-iteration budget check

Before each iteration:

```python
def pre_iteration_budget_check(state: LoopState) -> ContinueOrStop:
    remaining_usd = state.max_budget_usd - state.shadow_usd
    if remaining_usd <= MIN_VIABLE_USD:  # e.g., $0.05 — too little for any meaningful sub-run
        return Stop("max_budget_reached", state.shadow_usd)

    if state.max_turns_shadow and state.shadow_turns >= state.max_turns_shadow:
        return Stop("max_turns_shadow_reached", state.shadow_turns)

    return Continue(remaining_usd=remaining_usd)
```

The `Continue` carries the remaining budget so the inner sub-run can be invoked with `--max-budget-usd <remaining>` — CC-native enforcement at the sub-run level even though our outer budget is shadow.

## Reporting budget to the user

After each iteration (interactive mode):

```
Iter 3:
  Proposed change: ...
  Inner-sub-run usage: $0.18 (1240 in / 2150 out tokens, claude-sonnet-4-6)
  Cumulative: $1.84 / $8.00 (23%)
  Estimated iterations remaining: ~33 at current pace
```

The "estimated iterations remaining" is `(remaining_usd / mean_usd_per_iter)` — a crude projection that helps the friend decide whether to let it run.

## When CC ships native cross-mode `--max-budget-usd`

Per `cc-flag-watch.md`, the moment CC's `--max-budget-usd` works in non-print mode AND in nested contexts:

- Drop shadow-USD tracking (or keep as belt-and-suspenders — TBD per `cc-flag-watch.md` update protocol)
- Simplify the outer loop's pre-iteration check
- `references/model-pricing.json` becomes optional (kept for reporting, not enforcement)

The transition is a single-line change in `lib/budget.py`'s pre-iteration check.

## When pricing changes

Anthropic announces pricing changes via their docs + CHANGELOG. Our discipline:

1. Watch the Anthropic announcements channel (or set up an alert)
2. Within 7 days of a pricing change, update `references/model-pricing.json` + bump plugin patch version
3. `/ren:doctor` warns when `valid_as_of` is >60 days stale
4. Friends running `/ren:update` get the new pricing; their next `/ren:improve-skill` run uses fresh data

## Implementation note

V1 implementation lives in `skills/sf-improve-skill/lib/budget.py` (pending). The pure-logic functions (`update_shadow_usd`, `pre_iteration_budget_check`) are fully testable without invoking CC; tests use fixture `ApiUsage` instances and known pricing tables.

## References

- ADR-006 (Curated Stack) — plugin versioning discipline that bumps `model-pricing.json`
- ADR-012 (Two-Layer Self-Improvement) — the safety-primitives subsection
- `references/cc-flag-watch.md` — flag-availability watch
- `references/karpathy-loop.md` — the loop body the budget bounds
- `references/git-mechanics.md` — sibling primitive (git is memory; budget is fuel)
