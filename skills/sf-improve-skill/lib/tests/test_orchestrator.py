"""
Tests for skills.sf_improve_skill.lib.improve_skill() orchestrator.

The orchestrator composes real preflight + git_mechanics + budget primitives
with INJECTED fakes for the two LLM-dependent layers (eval_runner +
change_proposer). This lets us exercise the full loop body deterministically
without invoking real Claude sub-runs.

Per the reader/writer asymmetry pattern documented in learnings.md:
- eval_runner failures during the loop are treated as score=0 (revert and continue)
- preflight failures raise PreFlightError (stop the loop entirely)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ..__init__ import improve_skill
from ..budget import load_pricing_table
from ..eval_runner import EvalSpec, EvalTest
from ..types import (
    ApiUsage,
    EvalResult,
    ExitReason,
    ImproveSkillArgs,
    IterationStatus,
    PreFlightError,
    ProposedChange,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_skill_repo(tmp_git_repo: Path) -> Path:
    """
    Augment tmp_git_repo (from conftest.py) with a canonical-ADR-011 eval.json
    so the orchestrator's preflight + load_eval_spec pass cleanly.
    """
    eval_dir = tmp_git_repo / "skills" / "sample-skill" / "eval"
    (eval_dir / "eval.json").write_text(
        json.dumps(
            {
                "name": "sample-skill",
                "tests": [
                    {
                        "id": "t1",
                        "prompt": "do the thing",
                        "binary_assertions": [
                            "output is non-empty",
                            "output contains expected token",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # Commit the updated eval so working tree is clean
    subprocess.run(["git", "add", "skills/"], cwd=tmp_git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture: ADR-011 eval.json"],
        cwd=tmp_git_repo, check=True, capture_output=True,
    )
    return tmp_git_repo


def _make_eval_result(score: float, total: int = 2, failing: tuple[str, ...] = ()) -> EvalResult:
    passed = int(round(score * total))
    return EvalResult(
        score=score,
        passed=passed,
        total=total,
        failing_assertion_ids=failing,
    )


def _make_proposed_change(summary: str = "tightened the language") -> ProposedChange:
    return ProposedChange(
        target_file="skills/sample-skill/SKILL.md",
        unified_diff=(
            "--- a/skills/sample-skill/SKILL.md\n"
            "+++ b/skills/sample-skill/SKILL.md\n"
            "@@ -1,3 +1,4 @@\n"
            " ---\n"
            " name: sample-skill\n"
            "+description: appended by test proposer\n"
            " ---\n"
        ),
        summary=summary,
        rationale="test rationale",
    )


def _basic_args(**overrides) -> ImproveSkillArgs:
    defaults = dict(
        skill_name="sample-skill",
        autonomous=False,
        max_iterations=5,
        max_budget_usd=10.00,
        base_ref="main",
    )
    defaults.update(overrides)
    return ImproveSkillArgs(**defaults)


# ---------------------------------------------------------------------------
# Early-exit: all assertions already pass
# ---------------------------------------------------------------------------


class TestEarlyExitAllPass:
    def test_baseline_perfect_exits_immediately(self, tmp_skill_repo: Path):
        runner = MagicMock(return_value=_make_eval_result(1.0))
        proposer = MagicMock()  # should never be called

        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.ALL_ASSERTIONS_PASS
        assert result.final_score == 1.0
        assert result.iterations_run == 0
        assert result.branch_name == ""  # no branch created on early-exit
        assert result.branch_disposition == "not-created (no improvements needed)"
        proposer.assert_not_called()


# ---------------------------------------------------------------------------
# Loop body: improved iteration is kept
# ---------------------------------------------------------------------------


class TestImprovedIterationKept:
    def test_single_iteration_improves_to_perfect(self, tmp_skill_repo: Path):
        """Baseline 0.5 → proposer applies a change → eval returns 1.0 → keep + squash-merge."""
        # First eval: baseline 0.5 (one failing)
        # Second eval: 1.0 after the change
        runner = MagicMock(
            side_effect=[
                _make_eval_result(0.5, total=2, failing=("t1:1",)),
                _make_eval_result(1.0, total=2),
            ]
        )
        proposer = MagicMock(
            return_value=(
                _make_proposed_change("improved instruction clarity"),
                ApiUsage(input_tokens=500, output_tokens=200),
                1,  # turns_used
            )
        )

        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.ALL_ASSERTIONS_PASS
        assert result.iterations_run == 1
        assert result.iterations_kept == 1
        assert result.iterations_reverted == 0
        assert result.final_score == 1.0
        assert result.baseline_score == 0.5
        assert "squash-merged" in result.branch_disposition
        assert result.total_usd_spent > 0


# ---------------------------------------------------------------------------
# Loop body: regression reverts
# ---------------------------------------------------------------------------


class TestRegressionReverts:
    def test_score_drop_triggers_revert(self, tmp_skill_repo: Path):
        """Baseline 0.5 → bad change → eval drops to 0.0 → revert, iteration counts as reverted."""
        runner = MagicMock(
            side_effect=[
                _make_eval_result(0.5, total=2, failing=("t1:1",)),
                _make_eval_result(0.0, total=2, failing=("t1:0", "t1:1")),
                _make_eval_result(0.5, total=2, failing=("t1:1",)),  # iteration 2 returns to baseline
                _make_eval_result(0.5, total=2, failing=("t1:1",)),  # iteration 2's eval (neutral)
            ]
        )
        proposer = MagicMock(
            return_value=(
                _make_proposed_change("bad change"),
                ApiUsage(input_tokens=100, output_tokens=50),
                1,
            )
        )

        result = improve_skill(
            _basic_args(max_iterations=2),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        # At least one revert should have happened (the score-drop iteration)
        assert result.iterations_reverted >= 1
        # We never improved past the baseline
        assert result.final_score == result.baseline_score
        # The branch is KEPT (no squash on incomplete success)
        assert "kept" in result.branch_disposition.lower()


# ---------------------------------------------------------------------------
# Loop body: budget exhaustion stops the loop
# ---------------------------------------------------------------------------


class TestBudgetExhaustion:
    def test_tiny_budget_stops_early(self, tmp_skill_repo: Path):
        """A $0.01 budget can't sustain any meaningful iteration → stops with max_budget_reached."""
        # We expect the loop to exit before running any iteration because
        # MIN_VIABLE_REMAINING_USD (0.05) > 0.01 budget
        runner = MagicMock(return_value=_make_eval_result(0.5, total=2, failing=("t1:1",)))
        proposer = MagicMock()

        result = improve_skill(
            _basic_args(max_budget_usd=0.01),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.MAX_BUDGET_REACHED
        assert result.iterations_run == 0
        proposer.assert_not_called()


# ---------------------------------------------------------------------------
# Loop body: NotImplementedError from default proposer
# ---------------------------------------------------------------------------


class TestDefaultProposerNotImplemented:
    def test_no_proposer_exits_no_improvement_possible(self, tmp_skill_repo: Path):
        """Without an injected proposer, the default raises NotImplementedError →
        orchestrator catches it and exits cleanly with NO_IMPROVEMENT_POSSIBLE."""
        runner = MagicMock(return_value=_make_eval_result(0.5, total=2, failing=("t1:1",)))

        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=None,  # use default (stubbed)
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.NO_IMPROVEMENT_POSSIBLE
        assert result.iterations_run == 0
        assert result.final_score == 0.5  # unchanged from baseline


# ---------------------------------------------------------------------------
# Pre-flight propagation
# ---------------------------------------------------------------------------


class TestPreflightPropagation:
    def test_autonomous_missing_max_iter_raises(self, tmp_skill_repo: Path):
        """LOAD-BEARING: autonomous mode without --max-iterations must refuse upfront."""
        args = _basic_args(autonomous=True, max_iterations=None, max_budget_usd=10.0)
        with pytest.raises(PreFlightError, match="--max-iterations"):
            improve_skill(
                args,
                skills_root=tmp_skill_repo / "skills",
                eval_runner=MagicMock(),
                change_proposer=MagicMock(),
                cwd=tmp_skill_repo,
            )

    def test_missing_skill_dir_raises(self, tmp_skill_repo: Path):
        args = _basic_args(skill_name="nonexistent-skill")
        with pytest.raises(PreFlightError, match="not found"):
            improve_skill(
                args,
                skills_root=tmp_skill_repo / "skills",
                eval_runner=MagicMock(),
                change_proposer=MagicMock(),
                cwd=tmp_skill_repo,
            )


# ---------------------------------------------------------------------------
# Keep-branch flag
# ---------------------------------------------------------------------------


class TestKeepBranchFlag:
    def test_keep_branch_skips_squash_merge_on_success(self, tmp_skill_repo: Path):
        """With --keep-branch, even a successful improve run does NOT squash-merge."""
        runner = MagicMock(
            side_effect=[
                _make_eval_result(0.5, total=2, failing=("t1:1",)),
                _make_eval_result(1.0, total=2),
            ]
        )
        proposer = MagicMock(
            return_value=(_make_proposed_change(), ApiUsage(100, 50), 1)
        )

        result = improve_skill(
            _basic_args(keep_branch=True),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.ALL_ASSERTIONS_PASS
        # Branch kept; not squash-merged
        assert "squash-merged" not in result.branch_disposition
        assert "kept" in result.branch_disposition.lower()


# ---------------------------------------------------------------------------
# History records iteration outcomes
# ---------------------------------------------------------------------------


class TestHistoryRecords:
    def test_history_captures_iteration_metadata(self, tmp_skill_repo: Path):
        runner = MagicMock(
            side_effect=[
                _make_eval_result(0.5, total=2, failing=("t1:1",)),
                _make_eval_result(1.0, total=2),
            ]
        )
        proposer = MagicMock(
            return_value=(
                _make_proposed_change("clarified instructions"),
                ApiUsage(input_tokens=1000, output_tokens=500),
                1,
            )
        )

        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert len(result.history) == 1
        outcome = result.history[0]
        assert outcome.iteration == 1
        assert outcome.proposed_change.summary == "clarified instructions"
        assert outcome.status == IterationStatus.IMPROVED
        assert outcome.commit_sha is not None
        assert outcome.usd_spent > 0


# ---------------------------------------------------------------------------
# Read-only invariant on the workspace (the LOAD-BEARING pin)
# ---------------------------------------------------------------------------


class TestImmutabilityInvariants:
    def test_result_dataclass_immutable(self, tmp_skill_repo: Path):
        """ImproveSkillResult is frozen — can't accidentally mutate fields after the fact."""
        runner = MagicMock(return_value=_make_eval_result(1.0))
        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            cwd=tmp_skill_repo,
        )
        with pytest.raises(Exception):
            result.final_score = 0.0  # type: ignore[misc]
