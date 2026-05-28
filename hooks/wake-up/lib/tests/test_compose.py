"""Tests for hooks/wake-up/lib (the wake-up compose layer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ..__init__ import (
    CHARS_PER_TOKEN,
    DEFAULT_MAX_TOKENS,
    compose_wake_up_context,
    detect_project,
    estimate_tokens,
    read_log_tail,
    truncate_text_to_tokens,
)


# ---------------------------------------------------------------------------
# estimate_tokens + truncate_text_to_tokens
# ---------------------------------------------------------------------------


class TestTokenHelpers:
    def test_estimate_tokens_chars_per_4(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("a" * 4) == 1
        assert estimate_tokens("a" * 400) == 100

    def test_truncate_under_budget_unchanged(self):
        text = "short"
        assert truncate_text_to_tokens(text, max_tokens=100) == text

    def test_truncate_over_budget_keeps_tail(self):
        text = "a" * 1000  # 250 tokens (chars/4)
        result = truncate_text_to_tokens(text, max_tokens=50)  # 200 chars
        # Marker present
        assert "truncated" in result
        # The tail (last 200 chars) is preserved
        assert result.endswith("a" * 200)

    def test_zero_budget_returns_empty(self):
        assert truncate_text_to_tokens("anything", max_tokens=0) == ""


# ---------------------------------------------------------------------------
# detect_project
# ---------------------------------------------------------------------------


class TestDetectProject:
    @pytest.fixture
    def wiki_with_projects(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        # Monkeypatch HOME so detect_project sees ~/Dev under tmp
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        wiki = tmp_path / "wiki"
        (wiki / "projects" / "sidecar").mkdir(parents=True)
        (wiki / "projects" / "restore").mkdir(parents=True)
        return wiki

    def test_cwd_under_dev_with_known_project(self, wiki_with_projects: Path, monkeypatch):
        # cwd is ~/Dev/sidecar/ (where ~ is tmp_path)
        tmp_home = wiki_with_projects.parent
        cwd = tmp_home / "Dev" / "sidecar"
        cwd.mkdir(parents=True)
        assert detect_project(cwd, wiki_with_projects) == "sidecar"

    def test_cwd_subdir_of_project(self, wiki_with_projects: Path):
        tmp_home = wiki_with_projects.parent
        cwd = tmp_home / "Dev" / "sidecar" / "src" / "deep"
        cwd.mkdir(parents=True)
        assert detect_project(cwd, wiki_with_projects) == "sidecar"

    def test_cwd_under_dev_but_no_matching_wiki_project(self, wiki_with_projects: Path):
        tmp_home = wiki_with_projects.parent
        cwd = tmp_home / "Dev" / "no-such-project"
        cwd.mkdir(parents=True)
        assert detect_project(cwd, wiki_with_projects) is None

    def test_cwd_outside_dev(self, wiki_with_projects: Path):
        tmp_home = wiki_with_projects.parent
        cwd = tmp_home / "not-dev"
        cwd.mkdir()
        assert detect_project(cwd, wiki_with_projects) is None


# ---------------------------------------------------------------------------
# read_log_tail
# ---------------------------------------------------------------------------


class TestReadLogTail:
    def test_returns_last_n_entries(self, tmp_path: Path):
        log = tmp_path / "log.md"
        log.write_text(
            "# Log\n\n"
            "## [2026-01-01 10:00] init | first\n"
            "## [2026-01-02 10:00] decision | second\n"
            "## [2026-01-03 10:00] pattern | third\n"
            "## [2026-01-04 10:00] lesson | fourth\n"
            "## [2026-01-05 10:00] milestone | fifth\n",
            encoding="utf-8",
        )
        result = read_log_tail(log, n_entries=3)
        # Should contain last 3, NOT the first 2
        assert "third" in result
        assert "fourth" in result
        assert "fifth" in result
        assert "first" not in result
        assert "second" not in result

    def test_n_larger_than_entries_returns_all(self, tmp_path: Path):
        log = tmp_path / "log.md"
        log.write_text("# Log\n\n## [2026-01-01 10:00] x | one\n", encoding="utf-8")
        result = read_log_tail(log, n_entries=10)
        assert "one" in result

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert read_log_tail(tmp_path / "no.md", n_entries=5) == ""

    def test_no_entries_returns_empty(self, tmp_path: Path):
        log = tmp_path / "log.md"
        log.write_text("# Log\n\nNo entries yet.\n", encoding="utf-8")
        assert read_log_tail(log, n_entries=5) == ""

    def test_multi_line_entries_preserved(self, tmp_path: Path):
        log = tmp_path / "log.md"
        log.write_text(
            "## [2026-01-01 10:00] init | first\nsub-line 1\nsub-line 2\n"
            "## [2026-01-02 10:00] decision | second\n",
            encoding="utf-8",
        )
        result = read_log_tail(log, n_entries=2)
        assert "sub-line 1" in result
        assert "sub-line 2" in result


# ---------------------------------------------------------------------------
# compose_wake_up_context
# ---------------------------------------------------------------------------


class TestComposeWakeUpContext:
    @pytest.fixture
    def populated_wiki(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        (wiki / "index.md").write_text(
            "# Wiki Index\n\n## Decisions\n- ADR-008\n- ADR-009\n",
            encoding="utf-8",
        )
        (wiki / "log.md").write_text(
            "# Log\n\n## [2026-05-01 10:00] decision | locked X\n"
            "## [2026-05-02 11:00] pattern | new auth pattern\n",
            encoding="utf-8",
        )
        proj = wiki / "projects" / "sample"
        proj.mkdir(parents=True)
        (proj / "index.md").write_text("# Sample project\n\nIndex.\n", encoding="utf-8")
        (proj / "CONTEXT.md").write_text(
            "# Active focus\n\nWorking on JWT refresh logic.\n", encoding="utf-8"
        )
        (proj / "log.md").write_text(
            "# Sample log\n\n## [2026-05-03 09:00] decision | scope expansion\n",
            encoding="utf-8",
        )
        return wiki

    def test_missing_wiki_returns_empty(self, tmp_path: Path):
        result = compose_wake_up_context(
            cwd=tmp_path,
            wiki_root=tmp_path / "nonexistent",
        )
        assert result == ""

    def test_master_only_when_unscoped(self, populated_wiki: Path):
        # cwd outside any project
        result = compose_wake_up_context(
            cwd=populated_wiki.parent / "elsewhere",
            wiki_root=populated_wiki,
        )
        assert "Master wiki index" in result
        assert "Recent master log" in result
        # No project section since cwd doesn't map to a project
        assert "Project context:" not in result

    def test_project_section_when_scoped(self, populated_wiki: Path):
        tmp_home = populated_wiki.parent
        cwd = tmp_home / "Dev" / "sample"
        cwd.mkdir(parents=True)
        result = compose_wake_up_context(
            cwd=cwd,
            wiki_root=populated_wiki,
        )
        # All three project sections present
        assert "Project context: sample" in result
        assert "Session pointer" in result
        assert "Working on JWT refresh logic" in result  # CONTEXT.md content
        assert "Recent sample log" in result
        assert "scope expansion" in result  # project log entry

    def test_source_marker_in_header(self, populated_wiki: Path):
        result = compose_wake_up_context(
            cwd=populated_wiki.parent,
            wiki_root=populated_wiki,
            source="compact",
        )
        assert "source=compact" in result

    def test_feed_callback_appended_when_provided(self, populated_wiki: Path):
        result = compose_wake_up_context(
            cwd=populated_wiki.parent,
            wiki_root=populated_wiki,
            fetch_feed_tail=lambda: "## Activity Feed — recent friend activity\n- friend-b · 2h ago · …",
        )
        assert "Activity Feed" in result
        assert "friend-b" in result

    def test_feed_callback_failure_degrades_silently(self, populated_wiki: Path):
        def boom():
            raise RuntimeError("feed unavailable")

        result = compose_wake_up_context(
            cwd=populated_wiki.parent,
            wiki_root=populated_wiki,
            fetch_feed_tail=boom,
        )
        # Should NOT contain the activity block; should NOT have raised
        assert "Activity Feed" not in result
        # Other sections still produced
        assert "Master wiki index" in result

    def test_overall_budget_cap_enforced(self, populated_wiki: Path):
        # Compose with a tiny cap; verify final output is bounded
        result = compose_wake_up_context(
            cwd=populated_wiki.parent,
            wiki_root=populated_wiki,
            max_tokens=50,  # very small
        )
        # Final size respects the cap (with marker for truncation)
        assert estimate_tokens(result) <= 60  # 50 + slack for the marker line

    def test_default_max_tokens_pinned(self):
        """Pin: DEFAULT_MAX_TOKENS == 5000 per ADR-008's 3-5K target."""
        assert DEFAULT_MAX_TOKENS == 5_000

    def test_chars_per_token_pinned(self):
        """Pin: heuristic = 4 chars/token (matches Anthropic's published guidance)."""
        assert CHARS_PER_TOKEN == 4.0
