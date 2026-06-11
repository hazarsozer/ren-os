---
name: improve-skill
description: |
  Use when the friend wants to improve an existing skill's body (SKILL.md
  instructions, references/, examples) against its own eval/eval.json
  binary-assertion test suite. Triggers on the /ren:improve-skill <skill-name>
  slash command. Applies the Karpathy auto-research loop per ADR-012:
  read skill → run evals → propose ONE change → re-run → keep on score
  improvement, revert on score drop. Defaults to interactive mode (user
  approves each change). Autonomous mode (--autonomous) requires hard
  ceilings (--max-iterations AND --max-budget-usd) and uses git as memory
  for atomic revert. Layer 1 (description optimization) is Skill Creator's
  job, NOT this skill — this is Layer 2 (body quality).
version: 0.1.0
license: MIT

framework_version: 1.0.0
schema_version: 1
type: skill

contract:
  required_outputs:
    - "A git branch named improve/<skill-name>/<YYYY-MM-DD-HHMMSS> containing 1+ iteration commits"
    - "Either: all eval assertions pass → squash-merge to base branch (default) or keep branch (--keep-branch)"
    - "Or: max-iterations / budget / turn cap reached → branch retained for inspection"
    - "A run summary listing: iterations executed, score-before vs score-after, commits kept, commits reverted"
  budgets:
    turns: 200                                  # outer loop turns; inner sub-runs separately capped
    files_written: 30                           # SKILL.md, references/*, eval edits if any
    duration_seconds: 7200                      # 2h hard upper bound (12-iteration overnight runs typical)
  permissions:
    read:
      - "skills/<skill-name>/**"
      - "skills/sf-improve-skill/references/**"
    write:
      - "skills/<skill-name>/SKILL.md"
      - "skills/<skill-name>/references/**"
    execute:
      - "git (status, branch, switch, add, commit, reset, restore, merge, log)"
      - "claude --bare --print --max-budget-usd <N> ... (inner sub-runs for change proposals)"
      - "uv run pytest skills/<skill-name>/eval/ (or equivalent eval runner)"
  completion_conditions:
    - "Exit reason in {all_assertions_pass, max_iterations_reached, max_budget_reached, max_turns_shadow_reached, user_cancelled, eval_unrunnable, no_improvement_possible, requires_configured_backend}"
    - "Branch state (kept or squashed-merged) matches the exit-reason policy"
    - "Run summary printed to user"
  output_paths:
    - "skills/<skill-name>/"  # only target skill modified

tags: [self-improvement, karpathy-loop, skill-quality, eval-driven]
related_skills: [skill-creator, sf-doctor]
references_required:
  - "references/karpathy-loop.md"
  - "references/cc-flag-watch.md"
  - "references/git-mechanics.md"
references_on_demand:
  - "references/budget-tracking.md"
  - "references/eval-runner.md"
---

# sf-improve-skill

Layer-2 skill self-improvement per ADR-012. The mechanical realization of Karpathy's "auto-research" pattern applied to a skill's `SKILL.md` body and references. Layer 1 (description optimization for activation reliability) is the Skill Creator's territory; this skill does not touch the description.

> ⚠️ **EXPERIMENTAL — the eval-backed loop requires a configured eval backend.**
> The Karpathy loop scores each iteration by running the target skill's
> `eval/eval.json` through an eval backend (Skill Creator's `run_eval` wrapper,
> or our own LLM-judge path — see `references/eval-runner.md`). That backend is
> **not yet wired**. Until it is, the **default path fails honestly**: it exits
> immediately and cleanly with exit reason `requires_configured_backend` (no
> crash, no branch created, no exception). The full loop is reachable today only
> by injecting a working `eval_runner` (as the unit tests do). This is the
> "bike-method" honest default — a deterministic proposer can't meaningfully
> self-improve a skill, so we don't pretend the default path works.

## When to use this skill

- Friend invokes `/ren:improve-skill <skill-name>` (canonical trigger)
- Friend says any of: "make X skill better", "improve X", "let X learn from its evals", "run the improvement loop on X" — confirm intent + the target skill name, then run
- During `/ren:doctor` if a skill's eval pass rate drops below a threshold (proactive nudge; user invokes manually)

## When NOT to use this skill

- The target skill has no `eval/eval.json` — the loop has no scoring primitive. Refuse with a clear message and (if friend confirms) suggest invoking Skill Creator first to bootstrap evals.
- The target skill's evals are all subjective qualifiers (per ADR-011, eval.json should be binary assertions only). Refuse and explain the binary-assertion requirement.
- The friend wants to improve the description (activation reliability) — direct them to Skill Creator's `/skill-creator > Improve my <skill> description` flow instead. This skill ONLY edits SKILL.md body + references.
- Autonomous mode (`--autonomous`) without ALL the required safety flags set (see "Flag set" below). Refuse pre-flight.

## Flag set (locked per team-lead arbitration, 2026-05-28)

```
/ren:improve-skill <skill-name> [flags]
```

**REQUIRED in `--autonomous` mode** (all must be set; pre-flight refuses to run otherwise):

| Flag | Origin | Purpose |
|---|---|---|
| `--max-iterations N` | Our framework cap | Outer-loop ceiling; canonical safety bound |
| `--max-budget-usd N` | CC-native (print-mode only) | API-cost ceiling; inner `claude --bare --print` sub-runs respect it |

**`--max-turns` is NOT required** because it does not exist as a CC CLI flag in CC `2.1.154` (verified absent — see `references/cc-flag-watch.md` for the watch). Our framework's shadow turn-counter via response-summation fills the gap; that's belt-and-suspenders, not a pre-flight requirement.

**Optional flags**:

| Flag | Default | Purpose |
|---|---|---|
| `--autonomous` | false | Skip per-iteration user approval; required only in unsupervised runs |
| `--interactive` | true | Explicit opt-in (the default); user approves each change |
| `--branch-prefix STR` | `improve` | Override branch-name prefix |
| `--base-ref REF` | `HEAD` | Base for the improve branch + final merge target |
| `--keep-branch` | false | Don't squash-merge on success; leave branch for review |
| `--dry-run` | false | Compose ONE proposed change, show the diff, exit without committing |
| `--eval-subset PATH` | full eval | Run a subset of `eval/eval.json` (useful for partial improvements) |
| `--bare` | true (inner) | Pass `--bare` to inner sub-runs (skip plugin/hook/CLAUDE.md overhead in change-proposal context) |

## Pre-flight check (mandatory)

Before the first iteration:

1. **Target skill exists**: `skills/<skill-name>/SKILL.md` is readable. Else refuse.
2. **Eval file exists + parseable**: `skills/<skill-name>/eval/eval.json` loads as JSON, has `tests[]` with at least one binary assertion (`binary_assertions[]`). Else refuse.
3. **Working tree clean**: `git status --porcelain` is empty. Else refuse with "Commit or stash your changes first." (We don't want to mix improve-loop commits with unrelated WIP.)
4. **Autonomous-mode safety**: if `--autonomous`, require ALL of `--max-iterations` AND `--max-budget-usd`. Else refuse with "Autonomous mode requires --max-iterations N --max-budget-usd N. Refusing to run unbounded."
5. **CC is on the supported PATH**: `claude --version` returns a parseable version. Else refuse with installation instructions.
6. **Initial eval run succeeds**: `uv run pytest skills/<skill-name>/eval/` (or equivalent) runs to completion. If the evals themselves are broken, refuse — we don't want the loop chasing test errors.

Only after all 6 pass does the loop begin.

## The Karpathy loop (8 steps per iteration)

See `references/karpathy-loop.md` for the full prose. Mechanical summary:

```
branch = create_branch(f"improve/{skill}/{timestamp}")

baseline_score = run_evals(skill, eval_subset)
if baseline_score == 1.0:
    exit("no improvements needed", branch_kept=True)

for i in 1..max_iterations:
    # Track budgets BEFORE the inner sub-run
    if budget_exhausted(): exit("budget_exhausted")
    if shadow_turn_count >= max_turns_shadow: exit("max_turns_shadow_reached")

    # Inner sub-run: propose ONE change
    proposed_change = run_inner_sub_run(
        prompt=propose_one_change_prompt(skill, failing_assertions, history),
        flags=["--bare", "--print", "--max-budget-usd", remaining_budget],
    )

    # User approval (interactive only)
    if not autonomous and not user_approves(proposed_change):
        continue   # try a different angle next iteration

    # Apply the change atomically
    apply_change(proposed_change)
    git_commit(f"iter {i}: {proposed_change.summary}")

    # Re-run evals
    new_score = run_evals(skill, eval_subset)

    if new_score < baseline_score:
        git_reset_hard("HEAD~1")
        log("iter %d: reverted (score %.2f → %.2f)", i, baseline_score, new_score)
    elif new_score == baseline_score:
        log("iter %d: neutral (score %.2f)", i, baseline_score)
        # Keep the change — some iterations need to stack
    else:
        log("iter %d: improved (%.2f → %.2f)", i, baseline_score, new_score)
        baseline_score = new_score

    if baseline_score == 1.0:
        break   # all assertions pass; success

# Exit: success → squash-merge unless --keep-branch
#       partial → branch kept; user reviews
#       cap → branch kept; user reviews
```

See `references/git-mechanics.md` for branch / commit / revert / merge details. See `references/budget-tracking.md` for the shadow-budget math (token sums × current model pricing).

## Operating principles (carried from ADR-012)

- **One change per iteration.** Narrow attempt loop. The LLM proposes the SINGLE highest-leverage change; doesn't bundle "refactor everything." This is the load-bearing discipline that makes "keep or revert" work cleanly.
- **Binary assertion only.** Per ADR-011, evals must be binary. Subjective qualifiers go through Skill Creator's qualitative dashboard separately.
- **Git as memory.** Each iteration is one commit; revert is `git reset --hard HEAD~1`. No fancy state management.
- **Autonomous mode never asks the human** during a run. Pre-flight requires the hard ceilings before allowing autonomous mode.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Eval backend not configured (default path, EXPERIMENTAL) | Exit immediately + cleanly; no branch; no exception | "Requires a configured eval backend (EXPERIMENTAL)." → exit reason `requires_configured_backend` |
| Skill not found | Refuse to start | "Skill `<name>` not found. Run `/skill-creator` to bootstrap." |
| `eval/eval.json` missing or malformed | Refuse to start | Pointer to ADR-011 schema |
| Initial eval run errors (not assertion failure — actual test framework error) | Refuse to start | "Fix your evals first." |
| Working tree dirty | Refuse to start | "Commit or stash, then retry." |
| Autonomous mode without required flags | Refuse to start (pre-flight) | "Autonomous mode requires --max-iterations N --max-budget-usd N." |
| Inner sub-run errors mid-iteration | Treat as score=0; revert iteration; continue outer loop | Logged |
| Budget exhausted mid-iteration | Finish current iteration's eval (keep/revert decision), then exit cleanly | Summary printed |
| Shadow turn-cap hit | Same as budget exhaustion | Same |
| User Ctrl-C | `git checkout -- .` to clear dirty state; branch retained for inspection | Branch info printed |
| All iterations regressed (zero net improvement) | Branch kept (don't squash garbage); user inspects `git log` | "No net improvement; branch retained: `<name>`" |
| Eval framework crash | Same as inner sub-run error: treat as score=0 for current iteration | Logged |
| CC sub-process crash | One iteration lost; outer loop retries on next iteration (state re-read from git) | Logged |

## What `/ren:improve-skill` explicitly DOES NOT do

- Touch the skill's `description` field — Layer 1, Skill Creator's job
- Touch any skill OTHER than the named target — the branch isolates writes
- Modify `eval/eval.json` (the source of truth for what "improvement" means; the loop must not move its own goalposts)
- Push the improve branch anywhere — local-only; if friend wants to share progress they push manually
- Run during a dirty working tree — pre-flight refuses

## Implementation note

V1 implementation lives in `skills/sf-improve-skill/lib/`. Inner sub-runs spawn `claude --bare --print --max-budget-usd <remaining>` as subprocesses with stdin = the proposed-change prompt + the skill's current files. Output is parsed as a structured JSON change-proposal (which file to edit, the diff). Apply uses `git apply` for atomicity.

The shadow-budget tracker sums `usage.input_tokens + usage.output_tokens` from each sub-run × the current model's price from `references/model-pricing.json` (file maintained per plugin version). When CC ships a reliable cross-mode `--max-turns` or non-print-mode `--max-budget-usd`, we drop the shadow. See `references/cc-flag-watch.md`.

## References

- ADR-011 (Skill Schema) — defines `eval/eval.json` shape this loop consumes
- ADR-012 (Two-Layer Self-Improvement) — the design + safety primitives
- `references/karpathy-loop.md` — full prose on the loop discipline
- `references/cc-flag-watch.md` — CC CLI flag availability watch list (`--max-turns` etc.)
- `references/git-mechanics.md` — branch / commit / revert / merge details
- `references/budget-tracking.md` — shadow-budget math
- `references/eval-runner.md` — how we invoke pytest against eval/eval.json
