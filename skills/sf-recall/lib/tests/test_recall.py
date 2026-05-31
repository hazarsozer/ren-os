"""Tests for skills.sf_recall.lib."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ..__init__ import (
    DEFAULT_N_HITS,
    KIND_MULTIPLIERS,
    STOP_WORDS,
    RecallResult,
    grep_wiki,
    recall,
    tokenize_query,
)


# ---------------------------------------------------------------------------
# tokenize_query
# ---------------------------------------------------------------------------


class TestTokenizeQuery:
    def test_lowercases(self):
        assert tokenize_query("Postgres OVER mongo") == ["postgres", "over", "mongo"]

    def test_strips_stopwords(self):
        # "what" and "the" are in STOP_WORDS
        result = tokenize_query("what is the postgres decision")
        assert "what" not in result
        assert "the" not in result
        assert "is" not in result
        assert "postgres" in result
        assert "decision" in result

    def test_splits_on_punctuation(self):
        assert tokenize_query("auth-flow, magic-link!") == ["auth", "flow", "magic", "link"]

    def test_empty_query_returns_empty(self):
        assert tokenize_query("") == []
        assert tokenize_query("   ") == []
        assert tokenize_query("the of an") == []  # all stop-words

    def test_non_string_raises(self):
        with pytest.raises(TypeError, match="str"):
            tokenize_query(123)  # type: ignore[arg-type]

    def test_stop_words_completeness(self):
        """Sanity: a reasonable set of common stop-words is filtered."""
        for sw in ["a", "an", "the", "of", "is", "we", "i", "to"]:
            assert sw in STOP_WORDS


# ---------------------------------------------------------------------------
# grep_wiki — fixtures + scoring
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_wiki(tmp_path: Path) -> Path:
    """Build a small wiki with a decision, a pattern, a research page, and a note."""
    wiki = tmp_path / "wiki"

    # A decision (gets ×1.5 multiplier)
    decisions = wiki / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "001-postgres.md").write_text(
        "---\ntitle: \"Postgres over MongoDB\"\nstatus: accepted\n---\n\n"
        "# Postgres over MongoDB\n\n"
        "We chose Postgres for its ACID guarantees. The relational model "
        "fits our auth schema cleanly. Postgres beats Mongo for our use case.\n",
        encoding="utf-8",
    )

    # A pattern (gets ×1.3 multiplier)
    patterns = wiki / "patterns"
    patterns.mkdir(parents=True)
    (patterns / "auth-middleware.md").write_text(
        "---\ntitle: \"Auth middleware composition pattern\"\n---\n\n"
        "# Auth middleware\n\nReusable composition pattern for guards.\n",
        encoding="utf-8",
    )

    # Plain research page (×1.0)
    research = wiki / "research"
    research.mkdir(parents=True)
    (research / "notes.md").write_text(
        "# Some research\n\nWe explored Postgres and other things.\n",
        encoding="utf-8",
    )

    # A session note (×0.8 — present but lower-authority)
    notes = wiki / ".session-notes"
    notes.mkdir(parents=True)
    (notes / "sess-1.md").write_text(
        "# Session notes\n\n- [t] explored postgres ergonomics\n",
        encoding="utf-8",
    )

    # A file that has NO match for "postgres" — should be excluded from results
    (research / "unrelated.md").write_text(
        "# Random stuff\n\nThis page is about something totally different.\n",
        encoding="utf-8",
    )

    # A hidden dir (.git/) should be skipped
    git_dir = wiki / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD.md").write_text(
        "# Postgres mentioned in git internal — should be skipped\n",
        encoding="utf-8",
    )

    return wiki


class TestGrepWiki:
    def test_finds_decision_first_for_postgres_query(self, sample_wiki: Path):
        hits, truncated = grep_wiki(sample_wiki, "postgres")
        assert len(hits) >= 2  # at least the decision + research + note
        # The decision page should be ranked first (title hit × 1.5 kind multiplier)
        assert "decisions/001-postgres.md" in hits[0].relative_path

    def test_no_hits_for_unmatched_query(self, sample_wiki: Path):
        hits, truncated = grep_wiki(sample_wiki, "nonexistent-keyword-xyz")
        assert hits == ()
        assert not truncated

    def test_empty_query_returns_empty(self, sample_wiki: Path):
        hits, truncated = grep_wiki(sample_wiki, "")
        assert hits == ()
        assert not truncated

    def test_missing_wiki_root_returns_empty(self, tmp_path: Path):
        hits, truncated = grep_wiki(tmp_path / "nonexistent", "postgres")
        assert hits == ()
        assert not truncated

    def test_excludes_hidden_dirs(self, sample_wiki: Path):
        """The `.git/` dir contains a file mentioning postgres; it should NOT appear."""
        hits, _ = grep_wiki(sample_wiki, "postgres")
        paths = [h.relative_path for h in hits]
        for p in paths:
            assert not p.startswith(".git/"), f"hidden dir leaked: {p}"

    def test_includes_session_notes(self, sample_wiki: Path):
        """`.session-notes/` IS included (per SKILL.md — pins are recallable)."""
        hits, _ = grep_wiki(sample_wiki, "postgres")
        paths = [h.relative_path for h in hits]
        assert any(".session-notes/" in p for p in paths)

    def test_kind_multipliers_applied(self, sample_wiki: Path):
        """Decision should score higher than research (both have body hits)."""
        hits, _ = grep_wiki(sample_wiki, "postgres")
        scores = {h.relative_path: h.score for h in hits}
        # Both have content; decision has title + body, research has only body
        assert scores["decisions/001-postgres.md"] > scores["research/notes.md"]

    def test_recency_bonus_applied(self, tmp_path: Path):
        """A recently-touched file should score above an older file with same content."""
        wiki = tmp_path / "wiki"
        decisions = wiki / "decisions"
        decisions.mkdir(parents=True)
        old = decisions / "old.md"
        new = decisions / "new.md"
        old.write_text(
            "---\ntitle: Old decision\n---\n# Old decision\n\nfoo\n", encoding="utf-8"
        )
        new.write_text(
            "---\ntitle: New decision\n---\n# New decision\n\nfoo\n", encoding="utf-8"
        )
        # Make `old` ancient + `new` recent
        import os, time
        ancient = time.time() - (60 * 86400)  # 60 days ago
        recent = time.time() - 3600  # 1 hour ago
        os.utime(old, (ancient, ancient))
        os.utime(new, (recent, recent))

        hits, _ = grep_wiki(wiki, "foo")
        scores = {h.relative_path: h.score for h in hits}
        assert scores["decisions/new.md"] > scores["decisions/old.md"]

    def test_n_hits_cap(self, tmp_path: Path):
        wiki = tmp_path / "wiki"
        research = wiki / "research"
        research.mkdir(parents=True)
        for i in range(15):
            (research / f"page-{i}.md").write_text(
                f"# Page {i}\n\nthe-query-token here\n", encoding="utf-8"
            )
        hits, truncated = grep_wiki(wiki, "the-query-token", n_hits=5)
        assert len(hits) == 5
        assert truncated

    def test_snippet_includes_match(self, sample_wiki: Path):
        hits, _ = grep_wiki(sample_wiki, "postgres")
        for h in hits:
            assert "postgres" in h.snippet.lower()

    def test_unreadable_file_skipped_not_raised(self, sample_wiki: Path):
        """A binary/unreadable file is logged + skipped; doesn't break the walk."""
        # Write a binary file disguised as .md
        bin_path = sample_wiki / "research" / "broken.md"
        bin_path.write_bytes(b"\x80\x81\x82\xff\xfe")
        # Should not raise
        hits, _ = grep_wiki(sample_wiki, "postgres")
        assert len(hits) >= 1  # other pages still matched

    def test_concurrent_delete_during_sort_not_fatal(self, tmp_path, monkeypatch):
        """A file deleted between the scan and the mtime-sort must not crash grep_wiki
        (the sort key's stat() is the unguarded call in grep_wiki)."""
        from ..__init__ import grep_wiki
        wiki = tmp_path / "wiki"
        decisions = wiki / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "a.md").write_text("---\ntitle: A\n---\n# A\n\nfoo here\n", encoding="utf-8")
        (decisions / "b.md").write_text("---\ntitle: B\n---\n# B\n\nfoo here\n", encoding="utf-8")
        real_stat = Path.stat
        def flaky_stat(self, *a, **k):
            if self.name == "a.md":
                raise OSError("simulated concurrent delete")
            return real_stat(self, *a, **k)
        monkeypatch.setattr(Path, "stat", flaky_stat)
        hits, _ = grep_wiki(wiki, "foo")  # must not raise
        assert len(hits) >= 1


# ---------------------------------------------------------------------------
# recall — top-level orchestration
# ---------------------------------------------------------------------------


class TestRecall:
    def test_empty_query_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Empty query"):
            recall("", wiki_root=tmp_path)
        with pytest.raises(ValueError, match="Empty query"):
            recall("   ", wiki_root=tmp_path)

    def test_returns_result_object(self, sample_wiki: Path):
        result = recall("postgres", wiki_root=sample_wiki)
        assert isinstance(result, RecallResult)
        assert result.query == "postgres"
        assert len(result.wiki_hits) >= 1

    def test_has_results_property(self, sample_wiki: Path):
        result = recall("postgres", wiki_root=sample_wiki)
        assert result.has_results

        # Use tokens that don't appear anywhere in the fixture (the previous
        # "totally-not-there" had "totally" which legitimately matches
        # `unrelated.md` containing "totally different" — word-boundary
        # matching still finds it, correctly).
        result = recall("xyzzy quux frobnitz", wiki_root=sample_wiki)
        assert not result.has_results

    def test_read_only_no_modifications(self, sample_wiki: Path, tmp_path: Path):
        """LOAD-BEARING: /sf:recall must not modify the wiki."""
        import hashlib
        before = {
            p: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sample_wiki.rglob("*.md")
        }
        recall("postgres", wiki_root=sample_wiki)
        after = {
            p: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sample_wiki.rglob("*.md")
        }
        assert before == after, "recall() modified wiki files"

    def test_query_is_stripped(self, sample_wiki: Path):
        result = recall("  postgres  ", wiki_root=sample_wiki)
        assert result.query == "postgres"  # whitespace stripped

    def test_immutable_result(self, sample_wiki: Path):
        result = recall("postgres", wiki_root=sample_wiki)
        with pytest.raises(Exception):
            result.query = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sanity: KIND_MULTIPLIERS table is exhaustive vs grep-strategy.md
# ---------------------------------------------------------------------------


class TestKindMultipliers:
    def test_table_pins_three_kinds(self):
        """references/grep-strategy.md documents 3 multipliers: decisions, patterns, .session-notes."""
        assert set(KIND_MULTIPLIERS.keys()) == {"decisions", "patterns", ".session-notes"}

    def test_decisions_outranks_patterns_outranks_notes(self):
        assert (
            KIND_MULTIPLIERS["decisions"]
            > KIND_MULTIPLIERS["patterns"]
            > KIND_MULTIPLIERS[".session-notes"]
        )
