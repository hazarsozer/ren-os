"""
Tests for lib.instrument.miss_log — G12 mechanical wake-up miss log (Task 3.3).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/instrument/test_miss_log.py -v
"""

from __future__ import annotations

import pytest

from lib.instrument import miss_log
from lib.ren_paths import wiki_root


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def isolated_state(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    wiki_root().mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_empty_state_returns_zeroed_report(isolated_state):
    report = miss_log.misses()
    assert report.fetches == 0
    assert report.misses == 0
    assert report.miss_rate == 0.0


def test_fetch_of_surfaced_page_is_not_a_miss(isolated_state):
    miss_log.log_surface(["a.md", "b.md"], session="s1")
    miss_log.log_fetch("a.md", "query about a", session="s1")

    report = miss_log.misses()
    assert report.fetches == 1
    assert report.misses == 0
    assert report.miss_rate == 0.0


def test_fetch_of_unsurfaced_page_in_surfaced_session_is_a_miss(isolated_state):
    miss_log.log_surface(["a.md"], session="s1")
    miss_log.log_fetch("z.md", "query about z", session="s1")

    report = miss_log.misses()
    assert report.fetches == 1
    assert report.misses == 1
    assert report.miss_rate == 1.0


def test_session_without_surface_record_is_excluded_from_both_counts(isolated_state):
    miss_log.log_fetch("x.md", "query", session="s-no-surface")

    report = miss_log.misses()
    assert report.fetches == 0
    assert report.misses == 0
    assert report.miss_rate == 0.0


def test_miss_rate_math_with_mixed_hits_and_misses(isolated_state):
    miss_log.log_surface(["a.md", "b.md"], session="s1")
    miss_log.log_fetch("a.md", "q1", session="s1")   # hit
    miss_log.log_fetch("b.md", "q2", session="s1")   # hit
    miss_log.log_fetch("z.md", "q3", session="s1")   # miss

    report = miss_log.misses()
    assert report.fetches == 3
    assert report.misses == 1
    assert report.miss_rate == pytest.approx(1 / 3)


def test_multiple_surface_records_for_same_session_are_unioned(isolated_state):
    miss_log.log_surface(["a.md"], session="s1")
    miss_log.log_surface(["b.md"], session="s1")  # a second wake-up run in the same session
    miss_log.log_fetch("b.md", "q", session="s1")

    report = miss_log.misses()
    assert report.fetches == 1
    assert report.misses == 0  # b.md was surfaced by the second record


def test_since_filtering_excludes_earlier_records(isolated_state, monkeypatch):
    from lib.instrument import collect

    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-01T00:00:00Z")
    miss_log.log_surface(["old.md"], session="s-old")
    miss_log.log_fetch("old.md", "q", session="s-old")

    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-02-01T00:00:00Z")
    miss_log.log_surface(["new.md"], session="s-new")
    miss_log.log_fetch("z.md", "q", session="s-new")  # a miss, but only after the cutoff

    report = miss_log.misses(since="2026-01-15T00:00:00Z")
    assert report.fetches == 1
    assert report.misses == 1
    assert report.miss_rate == 1.0


def test_independent_sessions_do_not_cross_contaminate(isolated_state):
    miss_log.log_surface(["a.md"], session="s1")
    miss_log.log_surface(["z.md"], session="s2")

    miss_log.log_fetch("z.md", "q", session="s1")  # z.md wasn't surfaced in s1 -> miss
    miss_log.log_fetch("z.md", "q", session="s2")  # z.md WAS surfaced in s2 -> hit

    report = miss_log.misses()
    assert report.fetches == 2
    assert report.misses == 1
    assert report.miss_rate == pytest.approx(0.5)
