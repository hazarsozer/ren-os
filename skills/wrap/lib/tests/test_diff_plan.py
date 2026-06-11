"""Tests for skills.sf_wrap.lib.diff_plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from ..diff_plan import (
    _LABEL_TARGETS,
    _primary_label,
    _slugify,
    compose_diff_plan,
)
from ..types import (
    CandidateArtifact,
    ClassifierResult,
    DiffKind,
    WrapInputs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wiki_root(tmp_path: Path) -> Path:
    """Build a minimal wiki layout for testing."""
    root = tmp_path / "wiki"
    root.mkdir()
    (root / "log.md").write_text("# Master log\n\n", encoding="utf-8")
    (root / "decisions").mkdir()
    (root / "patterns").mkdir()
    return root


@pytest.fixture
def project_wiki(wiki_root: Path) -> Path:
    """Add a project sub-wiki to the wiki root."""
    proj = wiki_root / "projects" / "sample"
    proj.mkdir(parents=True)
    (proj / "log.md").write_text("# Sample log\n\n", encoding="utf-8")
    (proj / "STATE.md").write_text("# State\n\n## Recent decisions\n\n", encoding="utf-8")
    (proj / "decisions").mkdir()
    (proj / "patterns").mkdir()
    return proj


def _inputs(active_project: str | None = "sample") -> WrapInputs:
    return WrapInputs(
        session_transcript_path=None,
        session_notes=(),
        cwd="/tmp/test-cwd",
        active_project=active_project,
    )


def _classifier(labels: tuple, artifacts: tuple = ()) -> ClassifierResult:
    return ClassifierResult(
        labels=labels,
        reasoning="test reasoning",
        candidate_artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# _LABEL_TARGETS table
# ---------------------------------------------------------------------------


class TestLabelTargetsTable:
    def test_table_covers_all_seven_labels(self):
        """Pin: the mapping table MUST cover all 7 SignalLabels."""
        from ..types import SignalLabel
        from typing import get_args
        all_labels = set(get_args(SignalLabel))
        assert set(_LABEL_TARGETS.keys()) == all_labels

    def test_none_label_targets_empty(self):
        """For label=='none', no per-label files are touched (CONTEXT/log still always)."""
        assert _LABEL_TARGETS["none"] == frozenset()


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Postgres over MongoDB", "postgres-over-mongodb"),
            ("Auth middleware composition pattern", "auth-middleware-composition-pattern"),
            ("Numbers 1.2.3 in title", "numbers-1-2-3-in-title"),
            ("  Leading and trailing  ", "leading-and-trailing"),
            ("Punctuation! Lots, of? it.", "punctuation-lots-of-it"),
            ("", "untitled"),
            ("---", "untitled"),
        ],
    )
    def test_slugify(self, title: str, expected: str):
        assert _slugify(title) == expected


# ---------------------------------------------------------------------------
# _primary_label
# ---------------------------------------------------------------------------


class TestPrimaryLabel:
    def test_single_label(self):
        assert _primary_label(("decision",)) == "decision"
        assert _primary_label(("none",)) == "none"

    def test_priority_purpose_shift_wins(self):
        assert _primary_label(("lesson", "purpose_shift", "decision")) == "purpose_shift"

    def test_priority_decision_over_lesson(self):
        assert _primary_label(("lesson", "decision")) == "decision"

    def test_priority_stack_change_over_pattern(self):
        assert _primary_label(("pattern", "stack_change")) == "stack_change"


# ---------------------------------------------------------------------------
# compose_diff_plan — none case
# ---------------------------------------------------------------------------


class TestNoneCase:
    def test_unscoped_none_produces_empty_plan(self, wiki_root: Path):
        """Unscoped (no project) + none = nothing to do."""
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project=None),
            classifier_result=_classifier(("none",)),
            next_session_pointer="Session ended; routine work.",
            summary_line="Routine debugging.",
        )
        # No CONTEXT (unscoped), no project log, no master log (none doesn't trigger)
        assert plan.entries == ()

    def test_scoped_none_still_rewrites_context_and_project_log(
        self, wiki_root: Path, project_wiki: Path
    ):
        """Scoped + none = CONTEXT.md rewrite + project log append; NO master log."""
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("none",)),
            next_session_pointer="Continuing on auth refactor.",
            summary_line="Fixed off-by-one in JWT verifier.",
        )
        target_files = [e.target_file for e in plan.entries]
        # CONTEXT.md is present (relative path now: projects/sample/CONTEXT.md)
        assert any("CONTEXT.md" in t for t in target_files)
        # Project log appended (relative path: projects/sample/log.md)
        assert any("projects/sample/log.md" in t for t in target_files)
        # Master log is NOT touched on none (master log is "log.md" exactly)
        assert "log.md" not in target_files


# ---------------------------------------------------------------------------
# compose_diff_plan — decision case
# ---------------------------------------------------------------------------


class TestDecisionCase:
    def test_decision_creates_new_page(self, wiki_root: Path, project_wiki: Path):
        artifact = CandidateArtifact(
            label="decision",
            proposed_title="Postgres over MongoDB",
            proposed_summary="Chose Postgres for ACID + relational fit.",
            target_file="wiki/projects/sample/decisions/postgres-over-mongo.md",
        )
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("decision",), (artifact,)),
            next_session_pointer="Continuing implementation.",
            summary_line="Locked decision on Postgres.",
        )

        target_files = [e.target_file for e in plan.entries]
        # New decisions page
        new_page = [t for t in target_files if "decisions/postgres-over-mongodb.md" in t]
        assert len(new_page) == 1
        # The corresponding entry should be CREATE
        new_page_entry = next(e for e in plan.entries if e.target_file == new_page[0])
        assert new_page_entry.kind == DiffKind.CREATE
        # And contains the required frontmatter triple
        assert 'type: decision' in new_page_entry.unified_diff
        assert 'schema_version: 1' in new_page_entry.unified_diff
        assert 'framework_version: "1.0.0"' in new_page_entry.unified_diff

    def test_decision_appends_master_log(self, wiki_root: Path, project_wiki: Path):
        artifact = CandidateArtifact(
            label="decision",
            proposed_title="Test",
            proposed_summary="x",
            target_file="x",
        )
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("decision",), (artifact,)),
            next_session_pointer="ctx",
            summary_line="x",
        )
        # Master log SHOULD be touched (non-routine session). Paths are
        # relative to wiki_root per ADR-026 (wiki IS the git repo), so
        # master log appears as "log.md" exactly (not "projects/<name>/log.md").
        target_files = [e.target_file for e in plan.entries]
        master_log = [t for t in target_files if t == "log.md"]
        assert len(master_log) == 1, f"expected master log.md; got {target_files}"


# ---------------------------------------------------------------------------
# compose_diff_plan — pattern case
# ---------------------------------------------------------------------------


class TestPatternCase:
    def test_pattern_creates_new_page_under_project(self, wiki_root: Path, project_wiki: Path):
        artifact = CandidateArtifact(
            label="pattern",
            proposed_title="Auth Middleware Composition",
            proposed_summary="Reusable composition pattern.",
            target_file="patterns/auth-middleware-composition.md",
        )
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("pattern",), (artifact,)),
            next_session_pointer="ctx",
            summary_line="x",
        )
        target_files = [e.target_file for e in plan.entries]
        assert any("patterns/auth-middleware-composition.md" in t for t in target_files)

    def test_pattern_unscoped_writes_to_master(self, wiki_root: Path):
        """Cross-project pattern (no active project) writes to master wiki/patterns/."""
        artifact = CandidateArtifact(
            label="pattern",
            proposed_title="Cross Project Pattern",
            proposed_summary="useful",
            target_file="patterns/cross-project-pattern.md",
        )
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project=None),
            classifier_result=_classifier(("pattern",), (artifact,)),
            next_session_pointer="ctx",
            summary_line="x",
        )
        target_files = [e.target_file for e in plan.entries]
        # Should target master wiki/patterns/, not projects/*/patterns/
        master_pattern = [
            t for t in target_files
            if "patterns/cross-project-pattern.md" in t and "projects" not in t
        ]
        assert len(master_pattern) == 1


# ---------------------------------------------------------------------------
# Diff content sanity
# ---------------------------------------------------------------------------


class TestDiffContent:
    def test_context_md_create_when_missing(self, wiki_root: Path):
        """CONTEXT.md doesn't exist yet → kind=CREATE; diff is git-apply-friendly."""
        proj = wiki_root / "projects" / "sample"
        proj.mkdir(parents=True)
        (proj / "log.md").write_text("# log\n", encoding="utf-8")

        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("none",)),
            next_session_pointer="First session pointer.",
            summary_line="first",
        )

        ctx = next(e for e in plan.entries if "CONTEXT.md" in e.target_file)
        assert ctx.kind == DiffKind.CREATE
        # New file diffs include "new file mode" header for git apply
        assert "new file mode" in ctx.unified_diff
        # Content carries the frontmatter triple
        assert "type: project-context" in ctx.unified_diff

    def test_context_md_edit_when_exists(self, wiki_root: Path, project_wiki: Path):
        """CONTEXT.md exists → kind=EDIT; diff is unified-format edit."""
        (project_wiki / "CONTEXT.md").write_text(
            "---\ntitle: Old\ntype: project-context\n---\n\nOld content.\n",
            encoding="utf-8",
        )
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("none",)),
            next_session_pointer="New session pointer with different content.",
            summary_line="x",
        )
        ctx = next(e for e in plan.entries if "CONTEXT.md" in e.target_file)
        assert ctx.kind == DiffKind.EDIT
        # Standard unified diff has --- and +++ lines (no "new file mode")
        assert "new file mode" not in ctx.unified_diff


# ---------------------------------------------------------------------------
# Atomicity invariant
# ---------------------------------------------------------------------------


class TestAtomicityInvariant:
    def test_plan_carries_full_context_rewrite_text(self, wiki_root: Path, project_wiki: Path):
        """The DiffPlan exposes context_md_rewrite as a top-level field — used
        by /ren:wrap step 10 (next-session pointer for the brief summary)."""
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project="sample"),
            classifier_result=_classifier(("none",)),
            next_session_pointer="THE pointer text",
            summary_line="x",
        )
        assert plan.context_md_rewrite == "THE pointer text"

    def test_plan_is_immutable(self, wiki_root: Path):
        plan = compose_diff_plan(
            wiki_root=wiki_root,
            inputs=_inputs(active_project=None),
            classifier_result=_classifier(("none",)),
            next_session_pointer="x",
            summary_line="x",
        )
        with pytest.raises(Exception):
            plan.entries = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Framework version resolution
# ---------------------------------------------------------------------------


class TestFrameworkVersionResolution:
    def test_frontmatter_uses_resolver_not_hardcoded(self, monkeypatch):
        """New-page frontmatter must reflect the resolved framework version,
        not a hardcoded '1.0.0'. Override via the highest-precedence env tier."""
        from ..diff_plan import _frontmatter_for
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "9.9.9")
        fm = _frontmatter_for("decision", "Title", "2026-05-31")
        assert 'framework_version: "9.9.9"' in fm, fm

    def test_frontmatter_uses_default_when_no_env_override(self, monkeypatch):
        """No env override → the resolver loads sf_paths, whose own lowest tier
        returns its default ('1.0.0'). This exercises the success path's default,
        NOT the resolver's except-branch fallback (see the test below for that)."""
        from ..diff_plan import _frontmatter_for
        monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", raising=False)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        fm = _frontmatter_for("decision", "Title", "2026-05-31")
        assert 'framework_version: "1.0.0"' in fm

    def test_framework_version_falls_back_on_load_failure(self, monkeypatch):
        """Force the except branch: if sf_paths.py can't be loaded, the resolver
        returns its hardcoded '1.0.0' fallback so frontmatter is never broken."""
        import importlib.util
        from .. import diff_plan
        monkeypatch.setattr(
            importlib.util, "spec_from_file_location",
            lambda *a, **k: (_ for _ in ()).throw(OSError("forced")),
        )
        assert diff_plan._framework_version() == "1.0.0"
