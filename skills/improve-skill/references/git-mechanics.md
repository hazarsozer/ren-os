---
title: "/ren:improve-skill git mechanics — branch, commit, revert, merge"
type: skill-reference
parent_skill: sf-improve-skill
version: 0.1.0
date: 2026-05-28
---

# Git mechanics for the Karpathy loop

The improve-skill loop uses **git as its memory** (per ADR-012). This doc settles the exact mechanics: branch naming, commit messages, revert procedure, merge policy, and crash-recovery semantics.

## Branch naming

```
improve/<skill-name>/<YYYY-MM-DD-HHMMSS>
```

- Always rooted at the user's `--base-ref` (default: current `HEAD`)
- The timestamp is collision-proof; even if a friend launches two runs in the same minute on the same skill, the seconds disambiguate
- `--branch-prefix` overrides the `improve` segment (e.g., `--branch-prefix experiment` → `experiment/sf-wrap/...`)

Implementation:
```python
def create_improve_branch(skill_name: str, *, prefix: str, base_ref: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    branch_name = f"{prefix}/{skill_name}/{timestamp}"
    subprocess.run(["git", "switch", "-c", branch_name, base_ref], check=True)
    return branch_name
```

## Pre-flight working-tree check

Before creating the branch, **the working tree must be clean**:

```python
def assert_working_tree_clean() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    )
    if result.stdout.strip():
        raise PreFlightError(
            "Working tree has uncommitted changes. "
            "Commit or stash before running /ren:improve-skill. "
            "(We don't want to mix WIP with improve-loop commits.)"
        )
```

This is non-negotiable. If the loop reverts an iteration via `git reset --hard HEAD~1` and the user had unrelated WIP in the working tree, the WIP would be obliterated. The pre-flight check protects them.

## Commit per iteration

Each iteration produces exactly ONE commit:

```
iter <N>: <short proposal summary>

<proposed_change.rationale>

improve-skill metadata:
  iteration: N
  score_before: 0.823 (14/17)
  score_after: 0.882 (15/17)  # filled in after eval
  status: pending             # one of: pending, improved, neutral, reverted
  budget_remaining_usd: 7.42
  shadow_turns: 14
```

The metadata block in the commit body lets `git log` carry the loop's full state — no separate state file needed. Crash recovery just re-reads the latest commit's metadata.

**Commit timing**:
1. Apply the proposed diff
2. Stage the changed files: `git add skills/<skill>/`
3. Commit with `status: pending` + score_after blank
4. Run evals
5. Amend the commit to fill in `score_after` + `status` (via `git commit --amend --no-edit -m <updated body>`)

This amend pattern is safe because the iteration commit is only ever on the improve branch — no risk of rewriting shared history.

## Revert on score drop

```python
def revert_last_iteration(reason: str) -> None:
    # Capture the metadata before reset so we can re-log it
    subprocess.run(["git", "reset", "--hard", "HEAD~1"], check=True)
    log.info("Reverted iteration: %s", reason)
```

Mechanics:
- `git reset --hard HEAD~1` discards the iteration commit AND all working-tree changes from it
- Equivalent to never having applied the change
- The git reflog still records the reset (recoverable if catastrophically needed via `git reflog` + `git checkout <sha>`)

**Important**: only `--hard` reset against HEAD~1 on the improve branch. NEVER `--hard` reset against a base branch. The improve branch is the only place where we own the history.

## Score-flat keep

If score stays the same after a change, KEEP the commit. Some changes are enabling moves — they don't immediately improve the score but unlock subsequent improvements. The next iteration may build on them.

The commit metadata records `status: neutral`. The user can review the neutral chain via `git log --grep "status: neutral"` if curious.

## Success exit: squash-merge

When all assertions pass:

```python
def squash_merge_on_success(branch: str, base_ref: str, *, keep_branch: bool) -> None:
    if keep_branch:
        log.info("Branch kept (--keep-branch): %s", branch)
        return

    # Squash-merge to base
    subprocess.run(["git", "switch", base_ref], check=True)
    subprocess.run(["git", "merge", "--squash", branch], check=True)

    # Compose the squash commit body from the iteration history
    summary = compose_squash_commit_message(branch)
    subprocess.run(["git", "commit", "-m", summary], check=True)

    # Delete the improve branch (history preserved in reflog)
    subprocess.run(["git", "branch", "-D", branch], check=True)
```

Squash commit body:
```
improve(<skill-name>): <N> iterations; score <baseline>% → 100%

Iterations:
- iter 1 (improved): <one-line>
- iter 2 (neutral): <one-line>
- iter 3 (reverted): <one-line>
- iter 4 (improved): <one-line>
...

Total spend: $<X> USD
Wall clock: <duration>
Improve branch (now deleted): improve/<skill-name>/<timestamp>
```

The squash collapses N iteration commits into ONE clean commit on the base branch. Friends reading `git log` on the base branch see a single improve commit, not a noisy chain.

## Partial-success exit: branch kept

When the loop runs out of budget/iterations/turns WITHOUT reaching 1.0 score:

```python
def keep_branch_on_partial(branch: str, exit_reason: str, final_score: float) -> None:
    log.info(
        "Branch retained for inspection: %s (exit: %s; final score: %.1f%%)",
        branch, exit_reason, final_score * 100,
    )
```

We do NOT auto-squash-merge a partial run. Reasoning:
- The friend may want to inspect what worked vs what didn't
- The friend may want to manually pick the best subset of iterations
- The friend may want to delete the branch and start fresh with different params
- Auto-merging garbage to main is worse than leaving a clearly-named branch around

The friend's next step is up to them — `git switch main` (or wherever) + decide.

## All-iterations-regressed exit

A degenerate case: every iteration the LLM tried got reverted. The branch ends up at the same commit as `--base-ref`. No work happened.

We still log the run summary so the friend knows: "12 iterations attempted, all reverted, baseline 73.9%, no net improvement." Branch is kept (empty of new commits, but still present) so the friend can `git log --all` and see the run happened.

## Ctrl-C / cancellation

If the friend Ctrl-C's mid-iteration:

```python
def cleanup_on_cancel() -> None:
    # Discard any uncommitted iteration-in-progress changes
    subprocess.run(["git", "checkout", "--", "."], check=True)
    # Branch stays as-is at the last completed iteration
    log.info("Cancelled. Branch retained at: %s (HEAD: %s)", current_branch, head_sha)
```

We do NOT auto-revert the last completed iteration on Ctrl-C. That iteration was deliberate; the friend may want to keep it. They can manually `git reset --hard HEAD~1` if they don't.

## Crash recovery (CC sub-process crash, OOM, etc.)

The loop is restart-safe:

1. If the process dies between an iteration's apply and eval → the iteration commit is in `pending` state in the metadata. On restart, re-read `git log -1 --pretty=%B`, see `status: pending`, re-run the eval to determine keep/revert.
2. If the process dies between eval and amend → same as above; eval is rerun.
3. If the process dies between iterations → restart at iteration N+1.

The restart logic is:
```python
def resume_or_start(branch_name: str | None) -> None:
    if branch_name and branch_exists(branch_name):
        subprocess.run(["git", "switch", branch_name], check=True)
        last_commit = parse_iteration_metadata(get_last_commit_body())
        if last_commit.status == "pending":
            log.info("Resuming: last iter %d was pending; re-running eval", last_commit.iteration)
            # ... re-run eval, finalize the commit
        # ... continue from iter N+1
    else:
        create_improve_branch(...)
        # ... start at iter 1
```

V1 may NOT ship the auto-resume — friends can manually re-invoke with the same args. Keep this in `references/` as the intended V2 behavior.

## Never push from the loop

The improve branch is local-only. The loop does NOT `git push`. If the friend wants to share progress, they push manually:

```bash
$ git push -u origin improve/sf-wrap/2026-05-28-220000
```

Why: the loop generates many commits (one per iteration). Pushing each one would spam the remote. Squash-merge (on success) produces a clean single commit; that's the thing worth pushing.

## Interaction with the user's existing git workflow

`/ren:improve-skill` runs on the user's actual git repo (the framework's source repo). Considerations:
- The improve branch is created from `--base-ref` (default `HEAD`). If the friend is on `main`, branch is created from `main`.
- The friend's editor may show the improve branch in their branch picker. Naming convention (`improve/<skill>/<timestamp>`) makes them sortable + easy to bulk-delete (`git branch -D improve/<skill>/2026-05-*`).
- If the friend uses worktrees, the improve branch lives in the same worktree they invoked from. No worktree management by the skill.

## Implementation note

The git operations are wrapped in `skills/sf-improve-skill/lib/git_mechanics.py` (pending). Tests use a tmpdir + `git init` + fixtures to validate each operation in isolation without touching the framework's actual git history.

## References

- ADR-012 (Two-Layer Self-Improvement) — uses git as memory; one change per iteration; revert on score drop
- `references/karpathy-loop.md` — the loop's discipline that this implements
- `references/budget-tracking.md` — the budget primitive interleaved with iterations
