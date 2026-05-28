"""Tests for skills.sf_wrap.lib.wrap() orchestrator."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ..__init__ import wrap
from ..feed_call import FeedCallOutcome
from ..types import ClassifierResult, WrapInputs, WrapResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


@pytest.fixture
def wrap_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Init a git repo AT the wiki location (production: wiki IS the git repo per ADR-026).

    Returns (cwd, wiki_root) — they're the same in production; we keep the
    two-tuple shape to keep callers explicit about which slot is which.
    """
    wiki = tmp_path / "wiki"
    _init_repo(wiki)  # git init INSIDE wiki — production layout
    (wiki / "log.md").write_text("# Master log\n\n", encoding="utf-8")
    proj = wiki / "projects" / "sample"
    proj.mkdir(parents=True)
    (proj / "log.md").write_text("# Sample log\n\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wiki, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=wiki, check=True, capture_output=True)
    return wiki, wiki  # repo == wiki


def _inputs(active="sample") -> WrapInputs:
    return WrapInputs(
        session_transcript_path=None,
        session_notes=(),
        cwd="/tmp/test-cwd",
        active_project=active,
        skip_feed_flag=False,
    )


def _none_classifier(t: str, p: str | None) -> ClassifierResult:
    return ClassifierResult(labels=("none",), reasoning="routine")


def _decision_classifier(t: str, p: str | None) -> ClassifierResult:
    from ..types import CandidateArtifact
    return ClassifierResult(
        labels=("decision",),
        reasoning="locked decision",
        candidate_artifacts=(
            CandidateArtifact(
                label="decision",
                proposed_title="Test Decision",
                proposed_summary="The decision body.",
                target_file="wiki/projects/sample/decisions/test-decision.md",
            ),
        ),
    )


def _feed_success() -> FeedCallOutcome:
    return FeedCallOutcome(
        written=True, pushed=True, queued=False, skipped=False,
        skip_reason="", reprompt_attempted=False,
        user_message="✓ feed entry pushed",
        raw_violation=None,
    )


# ---------------------------------------------------------------------------
# Happy path: none label
# ---------------------------------------------------------------------------


class TestNoneLabelHappyPath:
    def test_none_label_writes_context_only(self, wrap_workspace):
        repo, wiki = wrap_workspace
        feed_fn = MagicMock(return_value=_feed_success())

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_none_classifier,
            feed_write_fn=feed_fn,
        )

        assert isinstance(result, WrapResult)
        # CONTEXT.md should be in the changed list
        assert any("CONTEXT.md" in p for p in result.wiki_pages_changed)
        # No master log change (none doesn't trigger it)
        # Master log is NOT touched on none (master log is "log.md" exactly, relative to wiki_root)
        assert "log.md" not in result.wiki_pages_changed
        # Feed write attempted + succeeded
        assert result.feed_write_attempted
        assert result.feed_write_success
        feed_fn.assert_called_once()


# ---------------------------------------------------------------------------
# Happy path: decision creates page + appends master log + feed entry
# ---------------------------------------------------------------------------


class TestDecisionLabelHappyPath:
    def test_decision_creates_page_and_writes_feed(self, wrap_workspace):
        repo, wiki = wrap_workspace
        feed_fn = MagicMock(return_value=_feed_success())

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_decision_classifier,
            feed_write_fn=feed_fn,
        )

        # The decisions page is in the changed list (relative path)
        changed_paths = [str(p) for p in result.wiki_pages_changed]
        assert any("decisions/test-decision.md" in p for p in changed_paths)
        # Master log is also touched (non-routine session). Per ADR-026, the
        # wiki IS the git repo, so master log appears as "log.md" exactly.
        assert "log.md" in changed_paths
        # Feed write succeeded
        assert result.feed_write_success
        # The file was actually written to disk
        decision_file = wiki / "projects" / "sample" / "decisions" / "test-decision.md"
        assert decision_file.exists()
        assert "Test Decision" in decision_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Approval filter
# ---------------------------------------------------------------------------


class TestApprovalFilter:
    def test_rejected_diffs_dont_apply(self, wrap_workspace):
        repo, wiki = wrap_workspace
        feed_fn = MagicMock(return_value=_feed_success())

        # Reject any decisions page; approve everything else
        def selective_approve(diff):
            return "decisions/" not in diff.target_file

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_decision_classifier,
            approve_fn=selective_approve,
            feed_write_fn=feed_fn,
        )

        # Decisions page should be in rejected, not in changed
        rejected_paths = list(result.wiki_pages_skipped)
        changed_paths = list(result.wiki_pages_changed)
        assert any("decisions/" in p for p in rejected_paths)
        assert not any("decisions/" in p for p in changed_paths)
        # The decisions file should NOT exist (not applied)
        decision_file = wiki / "projects" / "sample" / "decisions" / "test-decision.md"
        assert not decision_file.exists()


# ---------------------------------------------------------------------------
# Wiki apply failure aborts feed (consistency invariant)
# ---------------------------------------------------------------------------


class TestApplyFailureAbortsFeed:
    def test_failed_apply_skips_feed(self, wrap_workspace, monkeypatch):
        """LOAD-BEARING: if wiki apply fails (post-rollback), feed write MUST be skipped.

        Why: the feed entry would advertise wiki updates that didn't actually
        land. Better to defer the feed entry until the user retries.
        """
        from .. import __init__ as wrap_mod
        from ..apply import ApplyResult

        repo, wiki = wrap_workspace

        # Mock apply_diff_plan to simulate failure
        monkeypatch.setattr(
            wrap_mod,
            "apply_diff_plan",
            lambda plan, **kw: ApplyResult(
                success=False, diffs_applied=0, diffs_total=1,
                failed_diff_index=0, failed_diff_reason="simulated apply error",
                rollback_performed=True, files_changed=(),
            ),
        )

        feed_fn = MagicMock(return_value=_feed_success())

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_decision_classifier,
            feed_write_fn=feed_fn,
        )

        # LOAD-BEARING: feed was NOT called
        feed_fn.assert_not_called()
        assert not result.feed_write_attempted
        assert "wiki apply failed" in (result.feed_write_error or "")


# ---------------------------------------------------------------------------
# Classifier NotImplementedError degrades to 'none'
# ---------------------------------------------------------------------------


class TestClassifierNotImplemented:
    def test_default_classifier_stubbed_degrades_to_none(self, wrap_workspace):
        """When the classifier raises NotImplementedError (V1 default stub),
        the orchestrator MUST still produce a usable WrapResult by treating
        the session as 'none' (CONTEXT.md rewrite + feed entry only)."""
        repo, wiki = wrap_workspace
        feed_fn = MagicMock(return_value=_feed_success())

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=None,  # use default (stubbed → raises)
            feed_write_fn=feed_fn,
        )

        # Still produces a usable result (no exception leaked)
        assert isinstance(result, WrapResult)
        # No catastrophic failure; treated as routine
        assert result.feed_write_success or result.feed_write_attempted


# ---------------------------------------------------------------------------
# Skip-feed flag honored
# ---------------------------------------------------------------------------


class TestSkipFeedFlag:
    def test_skip_feed_in_inputs_propagated_to_feed_fn(self, wrap_workspace):
        repo, wiki = wrap_workspace
        feed_fn = MagicMock(return_value=FeedCallOutcome(
            written=False, pushed=False, queued=False, skipped=True,
            skip_reason="wrap-flag", reprompt_attempted=False,
            user_message="(feed skipped: wrap-flag)",
            raw_violation=None,
        ))

        skip_inputs = WrapInputs(
            session_transcript_path=None, session_notes=(),
            cwd="/tmp/test", active_project="sample", skip_feed_flag=True,
        )

        result = wrap(
            skip_inputs, wiki_root=wiki, cwd=repo,
            classifier_fn=_none_classifier, feed_write_fn=feed_fn,
        )

        # feed_write_fn received skip_feed_flag=True
        kwargs = feed_fn.call_args.kwargs
        assert kwargs["skip_feed_flag"] is True
        # WrapResult shows feed not attempted (was skipped)
        assert not result.feed_write_attempted
        assert not result.feed_write_success


# ---------------------------------------------------------------------------
# Result immutability + structure
# ---------------------------------------------------------------------------


class TestWrapResultShape:
    def test_immutable(self, wrap_workspace):
        repo, wiki = wrap_workspace
        result = wrap(
            _inputs(), wiki_root=wiki, cwd=repo,
            classifier_fn=_none_classifier,
            feed_write_fn=lambda **kw: _feed_success(),
        )
        with pytest.raises(Exception):
            result.feed_write_success = False  # type: ignore[misc]

    def test_next_session_pointer_capped(self, wrap_workspace):
        """The next-session pointer in the result is truncated to ~100 chars
        (longer text is in CONTEXT.md; the pointer is for the user-facing summary)."""
        repo, wiki = wrap_workspace

        def long_pointer_classifier(t, p):
            return ClassifierResult(
                labels=("none",),
                reasoning="A" * 500,  # very long
            )

        result = wrap(
            _inputs(), wiki_root=wiki, cwd=repo,
            classifier_fn=long_pointer_classifier,
            feed_write_fn=lambda **kw: _feed_success(),
        )
        assert len(result.next_session_pointer) <= 100
