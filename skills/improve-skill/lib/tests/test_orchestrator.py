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
from ..eval_runner import EvalBackendNotConfiguredError, EvalSpec, EvalTest
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
# Default eval-runner: honest fail-fast (no backend configured)
# ---------------------------------------------------------------------------


class TestDefaultEvalRunnerRequiresBackend:
    def test_default_eval_runner_exits_requires_configured_backend(
        self, tmp_skill_repo: Path, monkeypatch
    ):
        """DEFAULT path (no injected eval_runner): the baseline eval raises the
        typed EvalBackendNotConfiguredError, which the orchestrator catches and
        converts into a clean REQUIRES_CONFIGURED_BACKEND exit. This is the F2b
        fix — the default path must fail HONESTLY, not crash. No exception escapes."""
        import types
        from .. import eval_runner as _er
        # Patch only eval_runner's shutil reference — preflight still sees real shutil.which
        fake_shutil = types.SimpleNamespace(which=lambda _: None)
        monkeypatch.setattr(_er, "shutil", fake_shutil)
        proposer = MagicMock()  # must never be reached — baseline fails first

        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=None,  # use the DEFAULT (raises EvalBackendNotConfiguredError)
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.REQUIRES_CONFIGURED_BACKEND
        assert result.iterations_run == 0
        assert result.branch_name == ""  # no branch created — nothing ran
        assert result.final_score == 0.0
        assert result.baseline_score == 0.0
        assert "not-created" in result.branch_disposition
        proposer.assert_not_called()

    def test_in_loop_backend_loss_exits_cleanly(self, tmp_skill_repo: Path):
        """Defensive: a runner that scores the baseline but then raises
        EvalBackendNotConfiguredError mid-loop is backed out and the loop exits
        cleanly with REQUIRES_CONFIGURED_BACKEND — no exception escapes, and the
        loop does NOT burn budget chasing a runner that can never score."""
        runner = MagicMock(
            side_effect=[
                _make_eval_result(0.5, total=2, failing=("t1:1",)),  # baseline OK
                EvalBackendNotConfiguredError("backend went away mid-loop"),  # in-loop
            ]
        )
        proposer = MagicMock(
            return_value=(_make_proposed_change(), ApiUsage(100, 50), 1)
        )

        result = improve_skill(
            _basic_args(max_iterations=3),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=proposer,
            cwd=tmp_skill_repo,
        )

        assert result.exit_reason == ExitReason.REQUIRES_CONFIGURED_BACKEND
        # The uneval'd iteration was backed out; nothing kept.
        assert result.iterations_kept == 0
        # A branch WAS created (we entered the loop); it is kept for inspection.
        assert result.branch_name != ""
        assert "kept" in result.branch_disposition.lower()


# ---------------------------------------------------------------------------
# Loop body: NotImplementedError from default proposer
# ---------------------------------------------------------------------------


class TestDefaultProposerNotImplemented:
    def test_no_proposer_exits_no_improvement_possible(self, tmp_skill_repo: Path):
        """With a WORKING (injected) eval runner and a proposer that raises
        NotImplementedError, the orchestrator catches it and exits cleanly with
        NO_IMPROVEMENT_POSSIBLE.

        Updated for Task 6: the default proposer is now real (it subprocesses
        claude), so we inject an explicit NotImplementedError-raising stub to
        exercise this orchestrator catch path without touching the network."""
        runner = MagicMock(return_value=_make_eval_result(0.5, total=2, failing=("t1:1",)))

        def _not_impl(*args, **kwargs):
            raise NotImplementedError("stub")

        result = improve_skill(
            _basic_args(),
            skills_root=tmp_skill_repo / "skills",
            eval_runner=runner,
            change_proposer=_not_impl,
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


# ---------------------------------------------------------------------------
# Task 6: _default_change_proposer unit tests
# ---------------------------------------------------------------------------


class TestProposer:
    def _spec(self):
        return EvalSpec(name="wrap", tests=(EvalTest(id="t1", prompt="p", binary_assertions=("a",)),))

    def test_proposer_parses_change(self):
        from ..claude_cli import ClaudeRun
        from ..types import BudgetState
        from ..__init__ import _default_change_proposer

        payload = json.dumps({"target_file": "SKILL.md", "unified_diff": "--- a\n+++ b\n",
                              "summary": "clarify step", "rationale": "why"})
        fake = lambda prompt, **k: ClaudeRun(payload, ApiUsage(100, 50))
        change, usage, turns = _default_change_proposer(self._spec(), ("t1:0",),
                                                        BudgetState(max_budget_usd=5.0), _runner=fake)
        assert isinstance(change, ProposedChange)
        assert change.target_file == "SKILL.md"
        assert usage.output_tokens == 50 and turns == 1

    def test_proposer_raises_on_garbage(self):
        from ..claude_cli import ClaudeRun
        from ..types import BudgetState, ProposerError
        from ..__init__ import _default_change_proposer

        fake = lambda prompt, **k: ClaudeRun("I cannot help with that.", ApiUsage(10, 3))
        with pytest.raises(ProposerError):
            _default_change_proposer(self._spec(), ("t1:0",), BudgetState(max_budget_usd=5.0), _runner=fake)

    def test_proposer_prompt_contains_skill_md_content(self, tmp_path: Path, monkeypatch):
        """Fix 2: proposer prompt must embed the target skill's SKILL.md so the model
        can emit a correct unified diff against files it was actually shown."""
        from ..claude_cli import ClaudeRun
        from ..types import BudgetState
        from ..__init__ import _default_change_proposer, _read_skill_md

        # Write a minimal SKILL.md under skills/<name>/SKILL.md
        skill_name = "wrap"
        skill_md_content = "# wrap skill\nThis is the current SKILL.md content.\n"
        skill_dir = tmp_path / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

        captured_prompts: list[str] = []

        def fake_runner(prompt: str, **k) -> ClaudeRun:
            captured_prompts.append(prompt)
            payload = json.dumps({
                "target_file": "SKILL.md",
                "unified_diff": "--- a\n+++ b\n",
                "summary": "fix",
                "rationale": "why",
            })
            return ClaudeRun(payload, ApiUsage(100, 50))

        spec = EvalSpec(name=skill_name, tests=(EvalTest(id="t1", prompt="p", binary_assertions=("a",)),))

        # Monkeypatch Path("skills") so the reader finds our tmp_path
        monkeypatch.chdir(tmp_path)

        _default_change_proposer(spec, ("t1:0",), BudgetState(max_budget_usd=5.0), _runner=fake_runner)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        # The SKILL.md text must appear verbatim in the prompt sent to the model
        assert "This is the current SKILL.md content." in prompt, (
            f"Proposer prompt did not embed SKILL.md content. Prompt: {prompt[:300]!r}"
        )


# ---------------------------------------------------------------------------
# Task 7: end-to-end loop integration — budget + ProposerError skip + eval-runs
# ---------------------------------------------------------------------------


class TestEndToEndLoop:
    def _lib_module(self):
        """Return the actual module object that owns improve_skill (may be lib or lib.__init__)."""
        import sys
        return sys.modules.get("lib.__init__") or sys.modules["lib"]

    def test_loop_improves_fixture_skill_end_to_end(self, tmp_skill_repo: Path, monkeypatch):
        """Baseline 0.5 → proposer proposes change → re-eval 1.0 → all_assertions_pass.
        Verifies: (a) budget advanced from eval usage, (b) proposer returns clean change."""
        from ..eval_runner import EvalSpec, EvalTest
        _lib = self._lib_module()

        scores = iter([
            EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(30, 10)),
            EvalResult(1.0, 2, 2, (), usage=ApiUsage(30, 10)),
        ])
        fake_eval = lambda name, ids: next(scores)
        fake_prop = lambda spec, failing, budget: (
            ProposedChange("SKILL.md", "--- a\n+++ b\n", "fix", "why"),
            ApiUsage(100, 40),
            1,
        )

        monkeypatch.setattr(_lib, "create_improve_branch", lambda *a, **k: "improve/wrap/ts")
        monkeypatch.setattr(_lib, "commit_iteration", lambda *a, **k: "deadbeef")
        monkeypatch.setattr(_lib, "apply_proposed_change", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "amend_iteration_metadata", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "squash_merge_on_success", lambda *a, **k: "cafef00d")
        monkeypatch.setattr(_lib, "pre_flight_check", lambda *a, **k: None)
        monkeypatch.setattr(
            _lib, "load_eval_spec",
            lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)),
        )

        args = ImproveSkillArgs(skill_name="wrap", max_iterations=3, max_budget_usd=5.0)
        res = improve_skill(args, eval_runner=fake_eval, change_proposer=fake_prop, cwd=tmp_skill_repo)
        assert res.exit_reason.value == "all_assertions_pass"
        assert res.total_usd_spent > 0  # budget advanced from proposer AND eval usage

    def test_proposer_error_skips_iteration_and_retries(self, tmp_skill_repo: Path, monkeypatch):
        """ProposerError on iterations 1 and 2 → skip; on iteration 3 → success."""
        from ..eval_runner import EvalSpec, EvalTest
        from ..types import ProposerError as PE
        _lib = self._lib_module()

        call_count = [0]

        def fake_prop(spec, failing, budget):
            call_count[0] += 1
            if call_count[0] < 3:
                raise PE("transient failure")
            return (ProposedChange("SKILL.md", "--- a\n+++ b\n", "fix", "why"), ApiUsage(100, 40), 1)

        monkeypatch.setattr(_lib, "create_improve_branch", lambda *a, **k: "improve/wrap/ts")
        monkeypatch.setattr(_lib, "commit_iteration", lambda *a, **k: "deadbeef")
        monkeypatch.setattr(_lib, "apply_proposed_change", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "amend_iteration_metadata", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "squash_merge_on_success", lambda *a, **k: "cafef00d")
        monkeypatch.setattr(_lib, "pre_flight_check", lambda *a, **k: None)
        monkeypatch.setattr(
            _lib, "load_eval_spec",
            lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)),
        )

        # eval returns 1.0 on third proposer call (after 2 skips, third call succeeds)
        eval_results = iter([
            EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(10, 5)),  # baseline
            EvalResult(1.0, 2, 2, (), usage=ApiUsage(10, 5)),           # after 3rd propose
        ])

        def fake_eval_seq(name, ids):
            return next(eval_results)

        args = ImproveSkillArgs(skill_name="wrap", max_iterations=5, max_budget_usd=5.0)
        res = improve_skill(args, eval_runner=fake_eval_seq, change_proposer=fake_prop, cwd=tmp_skill_repo)
        # skipped 2 ProposerError iterations, then succeeded on 3rd
        assert res.exit_reason.value == "all_assertions_pass"

    def test_three_consecutive_proposer_errors_exits(self, tmp_skill_repo: Path, monkeypatch):
        """3 consecutive ProposerErrors → NO_IMPROVEMENT_POSSIBLE (not infinite loop)."""
        from ..eval_runner import EvalSpec, EvalTest
        from ..types import ProposerError as PE
        _lib = self._lib_module()

        def fake_prop(spec, failing, budget):
            raise PE("always fails")

        monkeypatch.setattr(_lib, "create_improve_branch", lambda *a, **k: "improve/wrap/ts")
        monkeypatch.setattr(_lib, "commit_iteration", lambda *a, **k: "deadbeef")
        monkeypatch.setattr(_lib, "apply_proposed_change", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "amend_iteration_metadata", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "squash_merge_on_success", lambda *a, **k: "cafef00d")
        monkeypatch.setattr(_lib, "pre_flight_check", lambda *a, **k: None)
        monkeypatch.setattr(
            _lib, "load_eval_spec",
            lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)),
        )

        fake_eval = lambda name, ids: EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(10, 5))
        args = ImproveSkillArgs(skill_name="wrap", max_iterations=10, max_budget_usd=5.0)
        res = improve_skill(args, eval_runner=fake_eval, change_proposer=fake_prop, cwd=tmp_skill_repo)
        assert res.exit_reason == ExitReason.NO_IMPROVEMENT_POSSIBLE

    def test_scorer_tamper_skips_iteration_and_retries(self, tmp_skill_repo: Path, monkeypatch):
        """A1: apply raises ScorerTamperError on iters 1-2 (proposer tried to edit eval/),
        then a clean apply on iter 3 → success. The tamper is skipped, not applied."""
        from ..eval_runner import EvalSpec, EvalTest
        from ..scorer_lock import ScorerTamperError
        _lib = self._lib_module()

        fake_prop = lambda spec, failing, budget: (
            ProposedChange("eval/eval.json", "--- a\n+++ b\n", "fix", "why"),
            ApiUsage(100, 40),
            1,
        )
        apply_calls = [0]

        def fake_apply(*a, **k):
            apply_calls[0] += 1
            if apply_calls[0] < 3:
                raise ScorerTamperError("eval/eval.json")
            return None

        monkeypatch.setattr(_lib, "create_improve_branch", lambda *a, **k: "improve/wrap/ts")
        monkeypatch.setattr(_lib, "commit_iteration", lambda *a, **k: "deadbeef")
        monkeypatch.setattr(_lib, "apply_proposed_change", fake_apply)
        monkeypatch.setattr(_lib, "amend_iteration_metadata", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "squash_merge_on_success", lambda *a, **k: "cafef00d")
        monkeypatch.setattr(_lib, "pre_flight_check", lambda *a, **k: None)
        monkeypatch.setattr(
            _lib, "load_eval_spec",
            lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)),
        )

        eval_results = iter([
            EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(10, 5)),  # baseline
            EvalResult(1.0, 2, 2, (), usage=ApiUsage(10, 5)),           # after the clean apply
        ])
        fake_eval = lambda name, ids: next(eval_results)

        args = ImproveSkillArgs(skill_name="wrap", max_iterations=5, max_budget_usd=5.0)
        res = improve_skill(args, eval_runner=fake_eval, change_proposer=fake_prop, cwd=tmp_skill_repo)
        assert res.exit_reason.value == "all_assertions_pass"
        assert apply_calls[0] == 3  # two rejected, one applied

    def test_three_consecutive_scorer_tampers_exit(self, tmp_skill_repo: Path, monkeypatch):
        """A1: a proposer that keeps targeting eval/ → 3 consecutive ScorerTamperError
        → NO_IMPROVEMENT_POSSIBLE via the existing consecutive-skip cap (no infinite loop)."""
        from ..eval_runner import EvalSpec, EvalTest
        from ..scorer_lock import ScorerTamperError
        _lib = self._lib_module()

        fake_prop = lambda spec, failing, budget: (
            ProposedChange("eval/eval.json", "--- a\n+++ b\n", "sneaky", "game the score"),
            ApiUsage(100, 40),
            1,
        )

        def fake_apply(*a, **k):
            raise ScorerTamperError("eval/eval.json")

        monkeypatch.setattr(_lib, "create_improve_branch", lambda *a, **k: "improve/wrap/ts")
        monkeypatch.setattr(_lib, "commit_iteration", lambda *a, **k: "deadbeef")
        monkeypatch.setattr(_lib, "apply_proposed_change", fake_apply)
        monkeypatch.setattr(_lib, "amend_iteration_metadata", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "squash_merge_on_success", lambda *a, **k: "cafef00d")
        monkeypatch.setattr(_lib, "pre_flight_check", lambda *a, **k: None)
        monkeypatch.setattr(
            _lib, "load_eval_spec",
            lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)),
        )

        fake_eval = lambda name, ids: EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(10, 5))
        args = ImproveSkillArgs(skill_name="wrap", max_iterations=10, max_budget_usd=5.0)
        res = improve_skill(args, eval_runner=fake_eval, change_proposer=fake_prop, cwd=tmp_skill_repo)
        assert res.exit_reason == ExitReason.NO_IMPROVEMENT_POSSIBLE


class TestCriticGate:
    """A2 step 4 — final cross-model critic gate before squash-merge + dispositions."""

    def _lib_module(self):
        import sys
        return sys.modules.get("lib.__init__") or sys.modules["lib"]

    def _run(self, tmp_skill_repo, monkeypatch, *, critic_runner,
             critic_model="gpt-5", keep_branch=False):
        from ..eval_runner import EvalSpec, EvalTest
        _lib = self._lib_module()
        merge_calls = []
        scores = iter([
            EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(10, 5)),  # baseline
            EvalResult(1.0, 2, 2, (), usage=ApiUsage(10, 5)),           # after one propose
        ])
        fake_eval = lambda name, ids: next(scores)
        fake_prop = lambda spec, failing, budget: (
            ProposedChange("SKILL.md", "--- a\n+++ b\n", "fix", "why"), ApiUsage(100, 40), 1,
        )
        monkeypatch.setattr(_lib, "create_improve_branch", lambda *a, **k: "improve/wrap/ts")
        monkeypatch.setattr(_lib, "commit_iteration", lambda *a, **k: "deadbeef")
        monkeypatch.setattr(_lib, "apply_proposed_change", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "amend_iteration_metadata", lambda *a, **k: None)
        monkeypatch.setattr(_lib, "squash_merge_on_success",
                            lambda *a, **k: (merge_calls.append(1) or "cafef00d"))
        monkeypatch.setattr(_lib, "pre_flight_check", lambda *a, **k: None)
        monkeypatch.setattr(
            _lib, "load_eval_spec",
            lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)),
        )
        args = ImproveSkillArgs(skill_name="wrap", max_iterations=3, max_budget_usd=5.0,
                                critic_model=critic_model, keep_branch=keep_branch)
        res = improve_skill(args, eval_runner=fake_eval, change_proposer=fake_prop,
                            critic_runner=critic_runner, cwd=tmp_skill_repo)
        return res, merge_calls

    def test_critic_confirms_then_merges(self, tmp_skill_repo: Path, monkeypatch):
        critic = lambda s, ids: EvalResult(1.0, 2, 2, (), usage=ApiUsage(5, 2))
        res, merge_calls = self._run(tmp_skill_repo, monkeypatch, critic_runner=critic)
        assert merge_calls == [1]
        assert "confirmed" in res.branch_disposition
        assert res.exit_reason == ExitReason.ALL_ASSERTIONS_PASS

    def test_critic_disputes_blocks_merge(self, tmp_skill_repo: Path, monkeypatch):
        critic = lambda s, ids: EvalResult(0.5, 1, 2, ("t1:1",), usage=ApiUsage(5, 2))
        res, merge_calls = self._run(tmp_skill_repo, monkeypatch, critic_runner=critic)
        assert merge_calls == []                       # NOT auto-merged
        assert "critic-flagged" in res.branch_disposition
        assert "t1:1" in res.branch_disposition
        assert res.branch_disposition.startswith("kept")

    def test_critic_unavailable_ships_without_confirmation(self, tmp_skill_repo: Path, monkeypatch):
        from ..eval_runner import CriticBackendUnavailable

        def critic(s, ids):
            raise CriticBackendUnavailable("no codex on PATH")

        res, merge_calls = self._run(tmp_skill_repo, monkeypatch, critic_runner=critic)
        assert merge_calls == [1]                       # shipped anyway
        assert "WITHOUT cross-model confirmation" in res.branch_disposition

    def test_no_critic_model_leaves_default_path(self, tmp_skill_repo: Path, monkeypatch):
        sentinel = {"called": False}

        def critic(s, ids):
            sentinel["called"] = True
            return EvalResult(1.0, 2, 2, ())

        res, merge_calls = self._run(tmp_skill_repo, monkeypatch,
                                     critic_runner=critic, critic_model=None)
        assert sentinel["called"] is False              # gate never fired
        assert merge_calls == [1]
        assert "critic" not in res.branch_disposition

    def test_keep_branch_with_critic_reports_but_does_not_merge(self, tmp_skill_repo: Path, monkeypatch):
        critic = lambda s, ids: EvalResult(1.0, 2, 2, (), usage=ApiUsage(5, 2))
        res, merge_calls = self._run(tmp_skill_repo, monkeypatch,
                                     critic_runner=critic, keep_branch=True)
        assert merge_calls == []                         # keep_branch → no merge
        assert "confirmed" in res.branch_disposition     # but verdict reported
        assert res.branch_disposition.startswith("kept")
