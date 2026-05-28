"""
Tests for skills.sf_wrap.lib.validate.

Per dotfiles python/testing.md: pytest framework. Per common/testing.md: 80%
coverage minimum on this module (achievable since it's pure-logic).

Run with:
    uv run pytest skills/sf-wrap/lib/tests/ -v
"""

from __future__ import annotations

import pytest

# Relative imports: the parent dir `sf-wrap` contains a dash, so absolute
# imports against the package path don't work.
from ..types import FormatViolationReport
from ..validate import (
    MAX_FILES_DISPLAYED,
    MAX_SUMMARY_CHARS,
    format_files_touched_for_summary,
    truncate_files_touched,
    validate_summary,
)


# --- validate_summary -----------------------------------------------------


class TestValidateSummary:
    def test_valid_short_summary_passes(self):
        result = validate_summary("Fixed JWT expired-token bug.")
        assert result.valid
        assert result.reason is None
        assert bool(result) is True

    def test_valid_max_length_passes(self):
        summary = "x" * MAX_SUMMARY_CHARS
        result = validate_summary(summary)
        assert result.valid

    def test_empty_string_rejected(self):
        result = validate_summary("")
        assert not result.valid
        assert "empty" in result.reason

    def test_over_length_rejected(self):
        summary = "x" * (MAX_SUMMARY_CHARS + 1)
        result = validate_summary(summary)
        assert not result.valid
        assert str(MAX_SUMMARY_CHARS) in result.reason
        assert str(MAX_SUMMARY_CHARS + 1) in result.reason

    def test_newline_rejected(self):
        result = validate_summary("Line one.\nLine two.")
        assert not result.valid
        assert "newline" in result.reason

    def test_carriage_return_rejected(self):
        result = validate_summary("Line one.\rLine two.")
        assert not result.valid
        assert "newline" in result.reason

    def test_triple_backtick_rejected(self):
        result = validate_summary("Look at ```code``` here.")
        assert not result.valid
        assert "triple-backtick" in result.reason

    def test_error_marker_rejected(self):
        result = validate_summary("Hit Error: KeyError in line 42.")
        assert not result.valid
        assert "stack-trace" in result.reason

    def test_traceback_marker_rejected(self):
        result = validate_summary("Saw Traceback during the test run.")
        assert not result.valid
        assert "stack-trace" in result.reason

    def test_angle_bracket_rejected(self):
        result = validate_summary("Wrote a <div> tag.")
        assert not result.valid
        assert "<" in result.reason or "'<'" in result.reason

    def test_non_string_rejected(self):
        result = validate_summary(123)  # type: ignore[arg-type]
        assert not result.valid
        assert "str" in result.reason

    @pytest.mark.parametrize(
        "good_summary",
        [
            "Updated dependencies.",
            "Refactored auth module; added refresh-token rotation.",
            "Wrote docs for /sf:wrap. Touched: SKILL.md, README.md.",
            "Single ' apostrophe is fine.",
            "Numbers 1.2.3 and symbols !@#$%^&*() are fine.",
        ],
    )
    def test_realistic_summaries_pass(self, good_summary: str):
        result = validate_summary(good_summary)
        assert result.valid, f"Should pass but got: {result.reason!r}"

    def test_no_secret_scanning(self):
        """ADR-021: format constraint IS the privacy mechanism.

        We deliberately do NOT scan for token / key / password patterns.
        If a friend wants secret scanning, they install AgentShield per-project.
        This test pins that decision so future commits don't accidentally
        sneak in a secret-pattern reject.
        """
        # These look like secrets but contain no rejected format-shape patterns
        # → MUST pass validation.
        result = validate_summary("API key sk-ant-1234567890abcdef remains in env.")
        assert result.valid, (
            "Per ADR-021 we do not perform secret scanning. "
            f"Got: {result.reason!r}"
        )


# --- truncate_files_touched -----------------------------------------------


class TestTruncateFiles:
    def test_under_cap_unchanged(self):
        files = ["a.py", "b.py", "c.py"]
        result = truncate_files_touched(files)
        assert result == files
        assert result is not files  # new list, immutability preserved

    def test_exact_cap_unchanged(self):
        files = [f"f{i}.py" for i in range(MAX_FILES_DISPLAYED)]
        result = truncate_files_touched(files)
        assert len(result) == MAX_FILES_DISPLAYED
        assert result == files

    def test_one_over_cap_truncated(self):
        files = [f"f{i}.py" for i in range(MAX_FILES_DISPLAYED + 1)]
        result = truncate_files_touched(files)
        assert len(result) == MAX_FILES_DISPLAYED + 1
        assert result[-1] == "…and 1 more"

    def test_many_over_cap_truncated(self):
        files = [f"f{i}.py" for i in range(MAX_FILES_DISPLAYED + 5)]
        result = truncate_files_touched(files)
        assert len(result) == MAX_FILES_DISPLAYED + 1
        assert result[-1] == "…and 5 more"

    def test_empty_unchanged(self):
        assert truncate_files_touched([]) == []

    def test_non_list_raises(self):
        with pytest.raises(TypeError, match="list"):
            truncate_files_touched("a,b,c")  # type: ignore[arg-type]


class TestFormatFilesForSummary:
    def test_short_list_rendered(self):
        assert (
            format_files_touched_for_summary(["a.py", "b.py"])
            == "a.py, b.py"
        )

    def test_long_list_elided(self):
        files = [f"f{i}.py" for i in range(MAX_FILES_DISPLAYED + 3)]
        rendered = format_files_touched_for_summary(files)
        assert rendered.endswith("…and 3 more")
        assert rendered.count(", ") == MAX_FILES_DISPLAYED  # 8 files + " …and N more"

    def test_empty_empty(self):
        assert format_files_touched_for_summary([]) == ""


# --- FormatViolationReport semantics --------------------------------------


class TestFormatViolationReport:
    def test_valid_is_truthy(self):
        r = FormatViolationReport(valid=True)
        assert bool(r) is True
        assert r.reason is None

    def test_invalid_is_falsy(self):
        r = FormatViolationReport(valid=False, reason="too long")
        assert bool(r) is False
        assert r.reason == "too long"

    def test_immutable(self):
        r = FormatViolationReport(valid=True)
        with pytest.raises(Exception):  # FrozenInstanceError
            r.valid = False  # type: ignore[misc]
