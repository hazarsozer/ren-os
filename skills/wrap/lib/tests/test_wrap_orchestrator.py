"""Tests for skills.sf_wrap.lib.wrap() orchestrator."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ..__init__ import wrap
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


# ---------------------------------------------------------------------------
# Happy path: none label
# ---------------------------------------------------------------------------


class TestNoneLabelHappyPath:
    def test_none_label_writes_context_only(self, wrap_workspace):
        repo, wiki = wrap_workspace

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_none_classifier,
        )

        assert isinstance(result, WrapResult)
        # CONTEXT.md should be in the changed list
        assert any("CONTEXT.md" in p for p in result.wiki_pages_changed)
        # No master log change (none doesn't trigger it)
        # Master log is NOT touched on none (master log is "log.md" exactly, relative to wiki_root)
        assert "log.md" not in result.wiki_pages_changed
        # No apply error on the happy path
        assert result.apply_error is None


# ---------------------------------------------------------------------------
# Happy path: decision creates page + appends master log
# ---------------------------------------------------------------------------


class TestDecisionLabelHappyPath:
    def test_decision_creates_page_and_master_log(self, wrap_workspace):
        repo, wiki = wrap_workspace

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_decision_classifier,
        )

        # The decisions page is in the changed list (relative path)
        changed_paths = [str(p) for p in result.wiki_pages_changed]
        assert any("decisions/test-decision.md" in p for p in changed_paths)
        # Master log is also touched (non-routine session). Per ADR-026, the
        # wiki IS the git repo, so master log appears as "log.md" exactly.
        assert "log.md" in changed_paths
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

        # Reject any decisions page; approve everything else
        def selective_approve(diff):
            return "decisions/" not in diff.target_file

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_decision_classifier,
            approve_fn=selective_approve,
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
# Wiki apply failure surfaces apply_error (rollback consistency invariant)
# ---------------------------------------------------------------------------


class TestApplyFailure:
    def test_failed_apply_reports_error_no_pages_changed(self, wrap_workspace, monkeypatch):
        """LOAD-BEARING: if wiki apply fails (post-rollback), the result reports
        no pages changed and surfaces the apply error."""
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

        result = wrap(
            _inputs(),
            wiki_root=wiki,
            cwd=repo,
            classifier_fn=_decision_classifier,
        )

        # Rolled back → nothing changed, error surfaced.
        assert result.wiki_pages_changed == ()
        assert "wiki apply failed" in (result.apply_error or "")


# ---------------------------------------------------------------------------
# Default classifier path — the REAL deterministic classify() (F2 closer)
# + dead-code safety for the future LLM path
# ---------------------------------------------------------------------------


class TestRealDefaultClassifier:
    def test_default_classifier_routine_is_none(self, wrap_workspace):
        """classifier_fn=None uses the REAL deterministic classify(). An empty/
        routine transcript → 'none' → CONTEXT.md rewrite only (no signal page)."""
        repo, wiki = wrap_workspace
        result = wrap(_inputs(), wiki_root=wiki, cwd=repo, classifier_fn=None)

        assert isinstance(result, WrapResult)
        assert result.apply_error is None
        assert any("CONTEXT.md" in p for p in result.wiki_pages_changed)
        assert not any("decisions/" in str(p) for p in result.wiki_pages_changed)

    def test_real_default_classifier_decision_creates_page(self, wrap_workspace):
        """F2 closer: the DEFAULT path (no injected classifier) produces real
        signal end-to-end. A /sf:note pin with a decision drives the real
        deterministic classifier to create a decisions/ page — proving the
        default user-facing path is equivalent to the injected-fake tests."""
        repo, wiki = wrap_workspace
        inputs = WrapInputs(
            session_transcript_path=None,
            session_notes=("decision: going with Postgres over Mongo for the store",),
            cwd="/tmp/test-cwd",
            active_project="sample",
        )
        result = wrap(inputs, wiki_root=wiki, cwd=repo, classifier_fn=None)

        assert result.apply_error is None
        changed = [str(p) for p in result.wiki_pages_changed]
        assert any("decisions/" in p for p in changed), changed
        assert "log.md" in changed  # master log appended on non-none signal
        assert list((wiki / "projects" / "sample" / "decisions").glob("*.md"))

    def test_classifier_raising_not_implemented_degrades_to_none(self, wrap_workspace):
        """Dead-code safety: the orchestrator's try/except still catches a
        NotImplementedError from any future/injected classifier and degrades to
        a usable 'none' result (the real default classify() never raises)."""
        repo, wiki = wrap_workspace

        def raising(t, p):
            raise NotImplementedError("future LLM path not wired")

        result = wrap(_inputs(), wiki_root=wiki, cwd=repo, classifier_fn=raising)
        assert isinstance(result, WrapResult)
        assert result.apply_error is None
        assert any("CONTEXT.md" in p for p in result.wiki_pages_changed)


# ---------------------------------------------------------------------------
# Result immutability + structure
# ---------------------------------------------------------------------------


class TestWrapResultShape:
    def test_immutable(self, wrap_workspace):
        repo, wiki = wrap_workspace
        result = wrap(
            _inputs(), wiki_root=wiki, cwd=repo,
            classifier_fn=_none_classifier,
        )
        with pytest.raises(Exception):
            result.wiki_pages_changed = ()  # type: ignore[misc]

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
        )
        assert len(result.next_session_pointer) <= 100
