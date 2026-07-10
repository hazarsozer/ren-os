"""
Tests for lib.suggestions.gate — significance gate functions (Task 15).

The significance gate determines whether a suggestion pattern is rare and
high-stakes enough to warrant being offered to the user. Two predicates:

1. recurs() — checks recurrence: a pattern must appear in >= 3 of the last 5
   sessions (recent_sessions, newest first) to be deemed significant.

2. is_critical_page() — checks if a page is instruction-plane / load-bearing:
   `global/` pages or those with type=doctrine/preference are critical.
   Caller provides the type when it has the page text; is_critical_page itself
   only checks the path prefix.

Doctrine (verbatim from Task 15 brief): "suggestions are rare and high-stakes;
below-threshold patterns accumulate silently; staleness and low-risk
contradictions resolve by recency at write time (queue supersedes) — only
behavior-changing or breakage-critical items may become suggestions."

Run with: uv run pytest tests/lib/suggestions/test_gate.py -v
"""

from __future__ import annotations

import pytest

from lib.suggestions.gate import RECURRENCE_MIN_SESSIONS, RECURRENCE_WINDOW_SESSIONS, is_critical_page, recurs


class TestRecurs:
    """Tests for recurs() — recurrence threshold logic."""

    def test_recurs_3_of_5_true(self):
        """Pattern appears in exactly 3 of the last 5 sessions (the threshold)."""
        evidence = {"s1", "s2", "s3"}
        recent = ["s5", "s4", "s3", "s2", "s1"]  # newest first
        assert recurs(evidence, recent) is True

    def test_recurs_2_of_5_false(self):
        """Pattern appears in only 2 of the last 5 sessions (below threshold)."""
        evidence = {"s1", "s2"}
        recent = ["s5", "s4", "s3", "s2", "s1"]  # newest first
        assert recurs(evidence, recent) is False

    def test_recurs_5_of_5_true(self):
        """Pattern appears in all 5 sessions (exceeds threshold)."""
        evidence = {"s1", "s2", "s3", "s4", "s5"}
        recent = ["s5", "s4", "s3", "s2", "s1"]  # newest first
        assert recurs(evidence, recent) is True

    def test_recurs_window_truncation(self):
        """Pattern appears in 3 old sessions OUTSIDE the last 5 → false.
        Evidence contains s1-s3 but recent only has s6-s10; no overlap."""
        evidence = {"s1", "s2", "s3"}
        recent = ["s10", "s9", "s8", "s7", "s6"]  # newest first, no overlap
        assert recurs(evidence, recent) is False

    def test_recurs_empty_recent_false(self):
        """Empty recent_sessions list always returns false."""
        evidence = {"s1", "s2", "s3"}
        recent = []
        assert recurs(evidence, recent) is False

    def test_recurs_empty_evidence_false(self):
        """Empty evidence_sessions set always returns false."""
        evidence = set()
        recent = ["s5", "s4", "s3", "s2", "s1"]
        assert recurs(evidence, recent) is False

    def test_recurs_recent_longer_than_window(self):
        """Recent list longer than window; only first RECURRENCE_WINDOW_SESSIONS (newest) are considered."""
        # recent has 10 sessions, but only first 5 (the newest) matter
        recent = ["s10", "s9", "s8", "s7", "s6", "s5", "s4", "s3", "s2", "s1"]

        # Case 1: Evidence in the newest sessions (first 5) → True
        evidence_newest = {"s10", "s9", "s8"}  # in newest window
        # First 5: ["s10", "s9", "s8", "s7", "s6"] → s10, s9, s8 all in this window
        assert recurs(evidence_newest, recent) is True

        # Case 2: Evidence in the oldest sessions (outside window) → False
        evidence_oldest = {"s1", "s2", "s3"}  # outside newest window
        # First 5: ["s10", "s9", "s8", "s7", "s6"] → s1, s2, s3 not in this window
        assert recurs(evidence_oldest, recent) is False

    def test_recurs_constants_match_spec(self):
        """Verify constants match the specification."""
        assert RECURRENCE_MIN_SESSIONS == 3
        assert RECURRENCE_WINDOW_SESSIONS == 5


class TestIsCriticalPage:
    """Tests for is_critical_page() — instruction-plane predicate."""

    def test_is_critical_global_prefix(self):
        """Pages starting with 'global/' are critical."""
        assert is_critical_page("global/rules.md") is True
        assert is_critical_page("global/doctrine.md") is True
        assert is_critical_page("global/x/y/z.md") is True

    def test_is_critical_global_root_edge_case(self):
        """Edge case: page exactly equal to 'global' (the prefix root)."""
        # Based on governance.tiers._is_global_page logic
        assert is_critical_page("global") is True

    def test_not_critical_data_plane_page(self):
        """Data-plane pages (non-global) are not critical."""
        assert is_critical_page("projects/x/y.md") is False
        assert is_critical_page("ideas/x.md") is False
        assert is_critical_page("log.md") is False

    def test_not_critical_global_substring_not_prefix(self):
        """Substring 'global' that's not a prefix is not critical."""
        assert is_critical_page("projects/global-config.md") is False
        assert is_critical_page("myglobal/rules.md") is False
