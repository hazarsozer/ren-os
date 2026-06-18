"""
sf-improve-skill local types.

Frozen dataclasses per dotfiles python/coding-style.md (immutability default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IterationStatus(str, Enum):
    """Final state of a Karpathy-loop iteration."""

    PENDING = "pending"        # commit made; eval not yet run
    IMPROVED = "improved"      # score went up; kept
    NEUTRAL = "neutral"        # score unchanged; kept (enabling moves)
    REVERTED = "reverted"      # score dropped; git-reset


class ExitReason(str, Enum):
    """Why the loop stopped."""

    ALL_ASSERTIONS_PASS = "all_assertions_pass"      # success
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    MAX_BUDGET_REACHED = "max_budget_reached"
    MAX_TURNS_SHADOW_REACHED = "max_turns_shadow_reached"
    USER_CANCELLED = "user_cancelled"
    EVAL_UNRUNNABLE = "eval_unrunnable"
    NO_IMPROVEMENT_POSSIBLE = "no_improvement_possible"  # all iterations regressed
    REQUIRES_CONFIGURED_BACKEND = "requires_configured_backend"  # default eval backend not configured (EXPERIMENTAL)


@dataclass(frozen=True)
class ImproveSkillArgs:
    """Parsed CLI arguments for /ren:improve-skill."""

    skill_name: str
    autonomous: bool = False
    interactive: bool = True
    max_iterations: int | None = None
    max_budget_usd: float | None = None
    max_turns_shadow: int | None = None
    branch_prefix: str = "improve"
    base_ref: str = "HEAD"
    keep_branch: bool = False
    dry_run: bool = False
    eval_subset_path: str | None = None
    bare: bool = True  # passed to inner sub-runs
    eval_runs: int = 1


@dataclass(frozen=True)
class ApiUsage:
    """Mirrors the standard Anthropic API usage object."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_input_with_cache(self) -> int:
        return self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens


@dataclass(frozen=True)
class BudgetState:
    """Running budget totals across a loop run."""

    max_budget_usd: float
    shadow_usd: float = 0.0
    max_turns_shadow: int | None = None
    shadow_turns: int = 0

    @property
    def remaining_usd(self) -> float:
        return max(self.max_budget_usd - self.shadow_usd, 0.0)

    @property
    def usd_exhausted(self) -> bool:
        # Below a minimum-viable-spend threshold means no meaningful sub-run remains
        return self.remaining_usd <= 0.05

    @property
    def turns_exhausted(self) -> bool:
        if self.max_turns_shadow is None:
            return False
        return self.shadow_turns >= self.max_turns_shadow


@dataclass(frozen=True)
class EvalResult:
    """Output of running the target skill's eval suite."""

    score: float  # 0.0 - 1.0 (pass rate)
    passed: int
    total: int
    failing_assertion_ids: tuple[str, ...]
    raw_output: str = ""  # stdout/stderr capture; for diagnostics on errors
    usage: ApiUsage = field(default_factory=lambda: ApiUsage(0, 0))

    @property
    def all_pass(self) -> bool:
        return self.passed == self.total and self.total > 0


@dataclass(frozen=True)
class ProposedChange:
    """One LLM-proposed change to the target skill."""

    target_file: str  # relative path under skills/<name>/
    unified_diff: str
    summary: str  # short one-line commit summary
    rationale: str  # longer prose justification


@dataclass(frozen=True)
class IterationOutcome:
    """The full record of a single iteration."""

    iteration: int
    proposed_change: ProposedChange
    score_before: float
    score_after: float
    status: IterationStatus
    commit_sha: str | None  # None if reverted
    usd_spent: float
    turns_spent: int


@dataclass(frozen=True)
class LoopState:
    """Mutable-by-replacement loop state (still frozen dataclass; new instance per iteration)."""

    skill_name: str
    branch_name: str
    base_ref: str
    args: ImproveSkillArgs
    budget: BudgetState
    iteration: int
    baseline_score: float  # tracks "best score so far" — updated only on improvement
    history: tuple[IterationOutcome, ...] = ()

    def with_iteration_advanced(
        self,
        outcome: IterationOutcome,
        new_budget: BudgetState,
        new_baseline: float,
    ) -> "LoopState":
        """Return a new LoopState reflecting one completed iteration."""
        return LoopState(
            skill_name=self.skill_name,
            branch_name=self.branch_name,
            base_ref=self.base_ref,
            args=self.args,
            budget=new_budget,
            iteration=self.iteration + 1,
            baseline_score=new_baseline,
            history=self.history + (outcome,),
        )


@dataclass(frozen=True)
class ImproveSkillResult:
    """Final summary returned to the user."""

    skill_name: str
    branch_name: str
    exit_reason: ExitReason
    final_score: float
    baseline_score: float
    iterations_run: int
    iterations_kept: int
    iterations_reverted: int
    total_usd_spent: float
    total_turns: int
    branch_disposition: str  # "squash-merged" | "kept" | "empty-deleted"
    history: tuple[IterationOutcome, ...]
    elapsed_seconds: float


class PreFlightError(Exception):
    """Raised by lib/preflight.py when a pre-flight check fails."""

    pass


class ProposerError(Exception):
    """Raised by the change-proposer when claude returns no parseable change.
    The orchestrator treats it as a skipped iteration, not a fatal stop."""

    pass
