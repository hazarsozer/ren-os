"""
sf-improve-skill library — internal implementation for /ren:improve-skill.

Public entry point: `improve_skill(args: ImproveSkillArgs) -> ImproveSkillResult`.

V1 status: types + pre-flight check are real; Karpathy loop body, git mechanics,
budget tracking, eval-runner are stubs to be filled in over follow-up turns.
"""

from __future__ import annotations

from .types import (
    ApiUsage,
    BudgetState,
    EvalResult,
    ImproveSkillArgs,
    ImproveSkillResult,
    IterationOutcome,
    IterationStatus,
    LoopState,
    PreFlightError,
    ProposedChange,
    ProposerError,
)
from .preflight import (
    pre_flight_check,
    validate_autonomous_flags,
    validate_working_tree_clean,
)

__all__ = [
    # types
    "ApiUsage",
    "BudgetState",
    "EvalResult",
    "ImproveSkillArgs",
    "ImproveSkillResult",
    "IterationOutcome",
    "IterationStatus",
    "LoopState",
    "PreFlightError",
    "ProposedChange",
    # pre-flight
    "pre_flight_check",
    "validate_autonomous_flags",
    "validate_working_tree_clean",
    # pipeline entry (stubbed below; filled in subsequent turns)
    "improve_skill",
]


import json
import time
from pathlib import Path
from typing import Callable

from .budget import (
    PricingTable,
    advance_budget,
    load_pricing_table,
    pre_iteration_check,
)
from .eval_runner import (
    EvalBackendNotConfiguredError,
    EvalSpec,
    filter_tests_by_ids,
    load_eval_spec,
)
from .git_mechanics import (
    amend_iteration_metadata,
    cleanup_on_cancel,
    commit_iteration,
    create_improve_branch,
    revert_last_iteration,
    squash_merge_on_success,
)
from .types import (
    ApiUsage,
    BudgetState,
    ExitReason,
    IterationOutcome,
    IterationStatus,
    ProposedChange,
)


# A change-proposer is a callable that receives (eval_spec, failing_ids, budget)
# and returns (ProposedChange, ApiUsage, turns_consumed). It's injected so the
# orchestrator can be unit-tested without invoking real LLM sub-runs. The real
# implementation will subprocess `claude --bare --print` per references/eval-runner.md.
ChangeProposer = Callable[
    [EvalSpec, tuple[str, ...], BudgetState], "tuple[ProposedChange, ApiUsage, int]"
]

# An eval-runner is a callable that receives (skill_name, eval_subset_ids) and
# returns EvalResult. Injected for testability; default delegates to
# lib.eval_runner.run_evals (currently raises EvalBackendNotConfiguredError —
# the eval-backed loop is EXPERIMENTAL pending a configured backend; the
# orchestrator catches it and exits with REQUIRES_CONFIGURED_BACKEND).
EvalRunner = Callable[[str, "list[str] | None"], "EvalResult"]


def _default_eval_runner(
    skill_name: str,
    subset_ids: "list[str] | None",
    *,
    eval_runs: int = 1,
    skills_root: "Path | None" = None,
) -> "EvalResult":
    """Default: defer to run_evals (raises EvalBackendNotConfiguredError until a
    backend is configured; the orchestrator catches it for an honest exit)."""
    from .eval_runner import run_evals
    return run_evals(
        skill_name,
        eval_subset_ids=subset_ids,
        eval_runs=eval_runs,
        skills_root=skills_root,
    )


def _proposer_prompt(spec: EvalSpec, failing_ids: tuple[str, ...]) -> str:
    return (
        f"You are improving the skill '{spec.name}'. Its eval binary-assertions that are "
        f"FAILING (as <test-id>:<index>): {list(failing_ids)}.\n"
        "Propose ONE change to SKILL.md or a references/ file that fixes at least one of "
        "these WITHOUT regressing the others. Output ONLY JSON with keys: "
        '{"target_file","unified_diff","summary","rationale"}.'
    )


def _default_change_proposer(
    spec: EvalSpec,
    failing_ids: tuple[str, ...],
    budget: BudgetState,
    *,
    _runner=None,
) -> "tuple[ProposedChange, ApiUsage, int]":
    """
    Subprocess `claude --print` (non-bare) with the propose-one-change prompt.
    Parses JSON {target_file, unified_diff, summary, rationale} from output.
    Raises ProposerError on empty or unparseable output.
    """
    from .claude_cli import run_print
    runner = _runner or run_print
    run = runner(_proposer_prompt(spec, failing_ids), bare=False,
                 max_budget_usd=budget.remaining_usd)  # non-bare: --bare skips auth
    text = run.output_text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ProposerError(f"No JSON object in proposer output: {text[:160]!r}")
    try:
        data = json.loads(text[start:end + 1])
        change = ProposedChange(
            target_file=str(data["target_file"]),
            unified_diff=str(data["unified_diff"]),
            summary=str(data.get("summary", "proposed change")),
            rationale=str(data.get("rationale", "")),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        raise ProposerError(f"Malformed proposer JSON: {exc}") from exc
    return change, run.usage, 1


def improve_skill(
    args: ImproveSkillArgs,
    *,
    skills_root: Path | None = None,
    eval_runner: EvalRunner | None = None,
    change_proposer: ChangeProposer | None = None,
    pricing_table: PricingTable | None = None,
    cwd: Path | None = None,
) -> ImproveSkillResult:
    """
    Execute the /ren:improve-skill Karpathy loop.

    Per references/karpathy-loop.md + references/eval-runner.md. Composes
    preflight + git_mechanics + budget + eval_runner. The two LLM-dependent
    layers (the change-proposer and the eval-runner's execution layer) are
    INJECTED as callables — defaults raise NotImplementedError until the
    Skill Creator integration choice is settled, but unit tests can pass
    fakes/mocks to exercise the full loop body deterministically.

    Args:
        args: Parsed CLI args.
        skills_root: Override the skills/ directory (for tests). Default: ./skills/.
        eval_runner: Inject a custom eval runner (for tests). Default delegates
            to lib.eval_runner.run_evals (currently stubbed).
        change_proposer: Inject a custom change-proposer (for tests). Default
            raises NotImplementedError (LLM-sub-run not yet wired).
        pricing_table: Inject a pricing table (for tests). Default loads from
            references/model-pricing.json.
        cwd: Working directory for git operations. Default: current.

    Returns:
        ImproveSkillResult summarizing iterations, scores, commits, exit reason.

    Raises:
        PreFlightError: when pre-flight gates fail (caller's responsibility to surface).
    """
    start_time = time.monotonic()

    # --- Pre-flight (all six gates per SKILL.md) ---
    pre_flight_check(args, skills_root=skills_root, cwd=cwd)

    # --- Load eval spec + apply subset filter ---
    skills_root_resolved = skills_root or Path("skills")
    skill_dir = skills_root_resolved / args.skill_name
    spec = load_eval_spec(skill_dir)
    if args.eval_subset_path:
        # eval_subset_path holds a comma-separated test-id list per CLI parsing
        subset_ids = [s.strip() for s in args.eval_subset_path.split(",") if s.strip()]
        spec = filter_tests_by_ids(spec, subset_ids)

    # --- Baseline eval ---
    runner = eval_runner or (
        lambda s, ids: _default_eval_runner(
            s, ids, eval_runs=args.eval_runs, skills_root=skills_root_resolved
        )
    )
    proposer = change_proposer or _default_change_proposer

    try:
        baseline = runner(args.skill_name, _eval_subset_ids_from_args(args))
    except EvalBackendNotConfiguredError:
        # Default path: no eval backend is configured (the eval-backed loop is
        # EXPERIMENTAL). Fail HONESTLY and cleanly — no branch, no exception
        # escaping — rather than crashing before the proposer's clean exit.
        elapsed = time.monotonic() - start_time
        return ImproveSkillResult(
            skill_name=args.skill_name,
            branch_name="",  # no branch created — nothing ran
            exit_reason=ExitReason.REQUIRES_CONFIGURED_BACKEND,
            final_score=0.0,
            baseline_score=0.0,
            iterations_run=0,
            iterations_kept=0,
            iterations_reverted=0,
            total_usd_spent=0.0,
            total_turns=0,
            branch_disposition="not-created (eval backend not configured — EXPERIMENTAL)",
            history=(),
            elapsed_seconds=elapsed,
        )
    if baseline.all_pass:
        elapsed = time.monotonic() - start_time
        return ImproveSkillResult(
            skill_name=args.skill_name,
            branch_name="",  # no branch created on early-exit
            exit_reason=ExitReason.ALL_ASSERTIONS_PASS,
            final_score=baseline.score,
            baseline_score=baseline.score,
            iterations_run=0,
            iterations_kept=0,
            iterations_reverted=0,
            total_usd_spent=0.0,
            total_turns=0,
            branch_disposition="not-created (no improvements needed)",
            history=(),
            elapsed_seconds=elapsed,
        )

    # --- Initialize budget + branch ---
    table = pricing_table or load_pricing_table()
    budget = BudgetState(
        max_budget_usd=args.max_budget_usd if args.max_budget_usd is not None else float("inf"),
        shadow_usd=0.0,
        max_turns_shadow=args.max_turns_shadow,
        shadow_turns=0,
    )
    # Advance budget for the baseline eval's API usage (turns_used=0 — baseline is scoring,
    # not a Claude sub-run; it still consumes tokens via the LLM-judge path).
    budget = advance_budget(budget, baseline.usage, model=table.default_model, table=table, turns_used=0)
    branch_name = create_improve_branch(
        args.skill_name,
        prefix=args.branch_prefix,
        base_ref=args.base_ref,
        cwd=cwd,
    )

    # --- Iteration loop ---
    baseline_score = baseline.score
    current_score = baseline.score
    history: list[IterationOutcome] = []
    exit_reason = ExitReason.MAX_ITERATIONS_REACHED  # default; overridden below
    max_iter = args.max_iterations if args.max_iterations is not None else 1
    last_failing_ids = baseline.failing_assertion_ids
    consecutive_proposer_errors = 0

    for iteration in range(1, max_iter + 1):
        # Budget gate before each iteration
        decision = pre_iteration_check(budget)
        if not decision.should_continue:
            exit_reason = ExitReason(decision.stop_reason)
            break

        # Propose one change (LLM sub-run; injected for testability)
        try:
            proposed, usage, turns_used = proposer(spec, last_failing_ids, budget)
            consecutive_proposer_errors = 0
        except NotImplementedError:
            # The default proposer raises; if no custom proposer was injected,
            # we exit cleanly with no-improvement-possible.
            exit_reason = ExitReason.NO_IMPROVEMENT_POSSIBLE
            break
        except ProposerError:
            # The real proposer returned unparseable output — skip this iteration
            # and try a different angle. Cap at 3 consecutive failures to avoid
            # burning budget on a stuck proposer.
            consecutive_proposer_errors += 1
            if consecutive_proposer_errors >= 3:
                exit_reason = ExitReason.NO_IMPROVEMENT_POSSIBLE
                break
            continue

        # Advance budget BEFORE applying (the API call happened regardless)
        budget = advance_budget(budget, usage, model=table.default_model, table=table, turns_used=turns_used)

        # Apply change to filesystem + commit
        apply_proposed_change(proposed, skills_root=skills_root_resolved, cwd=cwd)
        commit_sha = commit_iteration(
            iteration,
            proposed.summary,
            cwd=cwd,
            metadata={"score_before": f"{current_score:.3f}"},
        )

        # Re-run evals
        try:
            new_result = runner(args.skill_name, _eval_subset_ids_from_args(args))
            new_score = new_result.score
        except EvalBackendNotConfiguredError:
            # Defensive: a runner that scored the baseline reports the backend is
            # gone mid-loop. This is NOT a transient eval failure — continuing
            # would burn budget on a runner that can never score. Back out the
            # uneval'd commit and exit honestly; no exception escapes.
            revert_last_iteration(
                "eval backend not configured — cannot score iteration",
                cwd=cwd,
            )
            exit_reason = ExitReason.REQUIRES_CONFIGURED_BACKEND
            break
        except Exception:  # noqa: BLE001 — defensive; treat any eval failure as score=0
            new_score = 0.0
            new_result = None

        # Advance budget from re-eval usage
        budget = advance_budget(
            budget,
            new_result.usage if new_result else ApiUsage(0, 0),
            model=table.default_model,
            table=table,
            turns_used=0,
        )

        # Keep/revert decision
        if new_score < current_score:
            revert_last_iteration(
                f"score dropped {current_score:.3f} → {new_score:.3f}",
                cwd=cwd,
            )
            outcome_status = IterationStatus.REVERTED
            kept_sha: str | None = None
        elif new_score == current_score:
            amend_iteration_metadata(
                cwd=cwd,
                status="neutral",
                score_after=f"{new_score:.3f}",
            )
            outcome_status = IterationStatus.NEUTRAL
            kept_sha = commit_sha
        else:
            amend_iteration_metadata(
                cwd=cwd,
                status="improved",
                score_after=f"{new_score:.3f}",
            )
            outcome_status = IterationStatus.IMPROVED
            kept_sha = commit_sha
            current_score = new_score
            if new_result is not None:
                last_failing_ids = new_result.failing_assertion_ids

        history.append(
            IterationOutcome(
                iteration=iteration,
                proposed_change=proposed,
                score_before=current_score if outcome_status != IterationStatus.IMPROVED else baseline_score,
                score_after=new_score,
                status=outcome_status,
                commit_sha=kept_sha,
                usd_spent=budget.shadow_usd,  # cumulative; per-iter delta in metadata
                turns_spent=turns_used,
            )
        )

        # Success exit?
        if current_score >= 1.0:
            exit_reason = ExitReason.ALL_ASSERTIONS_PASS
            break

    # --- Finalize: squash-merge or keep branch ---
    iterations_kept = sum(1 for o in history if o.status != IterationStatus.REVERTED)
    iterations_reverted = sum(1 for o in history if o.status == IterationStatus.REVERTED)

    if exit_reason == ExitReason.ALL_ASSERTIONS_PASS and not args.keep_branch:
        squash_msg = (
            f"improve({args.skill_name}): {len(history)} iterations; "
            f"{baseline_score:.1%} → {current_score:.1%}"
        )
        squash_sha = squash_merge_on_success(
            branch_name,
            base_ref=args.base_ref,
            commit_message=squash_msg,
            cwd=cwd,
        )
        branch_disposition = f"squash-merged ({squash_sha[:8] if squash_sha else 'unknown'})"
    else:
        branch_disposition = f"kept (reason: {exit_reason.value})"

    elapsed = time.monotonic() - start_time
    return ImproveSkillResult(
        skill_name=args.skill_name,
        branch_name=branch_name,
        exit_reason=exit_reason,
        final_score=current_score,
        baseline_score=baseline_score,
        iterations_run=len(history),
        iterations_kept=iterations_kept,
        iterations_reverted=iterations_reverted,
        total_usd_spent=budget.shadow_usd,
        total_turns=budget.shadow_turns,
        branch_disposition=branch_disposition,
        history=tuple(history),
        elapsed_seconds=elapsed,
    )


def _eval_subset_ids_from_args(args: ImproveSkillArgs) -> "list[str] | None":
    """Parse the comma-separated --eval-subset arg into a list (or None)."""
    if not args.eval_subset_path:
        return None
    return [s.strip() for s in args.eval_subset_path.split(",") if s.strip()]


def apply_proposed_change(
    change: ProposedChange,
    *,
    skills_root: Path,
    cwd: Path | None = None,
) -> None:
    """
    Apply a proposed change to the filesystem via `git apply`.

    Per references/git-mechanics.md: the change is a unified diff against
    skills/<skill-name>/<target_file>. We run `git apply` from the wiki root
    (or `cwd`) so the diff resolves correctly.

    Args:
        change: The ProposedChange to apply.
        skills_root: Skills directory root.
        cwd: Working directory for the git command. Default: current.

    Raises:
        subprocess.CalledProcessError if git apply fails (caller should
        revert the iteration's commit).
    """
    import subprocess

    # `git apply` reads the diff from stdin
    subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        input=change.unified_diff,
        text=True,
        cwd=cwd,
        check=True,
        capture_output=True,
    )
