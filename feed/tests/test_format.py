"""
Tests for feed.format — terse-format builders + validators.

Scaffold phase: minimal coverage of builder happy-path + validator rejections.
Full coverage (binary assertions per ADR-021 §Open Q#2) lands in task #19.

Run with: uv run pytest feed/tests/test_format.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from feed.format import (
    FormatViolation,
    build_start_entry,
    build_end_entry,
    build_release_entry,
    validate_end_entry,
)


REF_TS = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)


# --- builders happy-path -----------------------------------------------------


def test_start_entry_renders_one_line():
    out = build_start_entry("hazar", "~/Dev/sidecar/", REF_TS)
    assert out == "## [2026-05-28 14:30] start | hazar | working in ~/Dev/sidecar/"


def test_start_entry_with_continuation_hint():
    out = build_start_entry(
        "hazar", "~/Dev/sidecar/", REF_TS, continuation_hint="resuming auth work"
    )
    assert "(resuming auth work)" in out
    assert out.startswith("## [2026-05-28 14:30] start | hazar")


def test_start_entry_rejects_overlong_continuation():
    with pytest.raises(FormatViolation, match="continuation-hint-too-long"):
        build_start_entry("hazar", "~/Dev/sidecar/", REF_TS, continuation_hint="x" * 200)


def test_end_entry_renders_template():
    out = build_end_entry(
        "hazar",
        "sidecar",
        "JWT middleware finished",
        ["src/auth/jwt.ts", "src/api/login.ts"],
        REF_TS,
    )
    assert "## [2026-05-28 14:30] end | hazar | session complete" in out
    assert "Worked on sidecar — JWT middleware finished." in out
    assert "Touched: src/auth/jwt.ts, src/api/login.ts." in out


def test_release_entry_renders():
    out = build_release_entry("hazar", "v1.3.0", "see CHANGELOG", REF_TS)
    assert out == "## [2026-05-28 14:30] release | hazar | framework | v1.3.0 shipped — see CHANGELOG"


# --- ≤8 files cap with "…and N more" ----------------------------------------


def test_end_entry_caps_at_8_files():
    files = [f"file{i}.py" for i in range(12)]
    out = build_end_entry("hazar", "sidecar", "many files", files, REF_TS)
    assert "…and 4 more" in out
    assert "file0.py" in out
    assert "file7.py" in out
    assert "file11.py" not in out  # would be cut off


def test_end_entry_exact_8_files_no_overflow():
    files = [f"f{i}.py" for i in range(8)]
    out = build_end_entry("hazar", "sidecar", "exact eight", files, REF_TS)
    assert "…and" not in out


# --- validators reject the right things --------------------------------------


def test_validator_rejects_overlong_body():
    body = "Worked on sidecar — " + ("x" * 300) + ".\nTouched: a.py."
    with pytest.raises(FormatViolation, match="too-long"):
        validate_end_entry(body)


def test_validator_rejects_triple_backticks():
    body = "Worked on sidecar — fix.\nTouched: a.py.\n```code```"
    # The 3-line shape will fail shape-mismatch first; but the substring check should
    # surface before that on a 2-line body containing fences:
    body = "Worked on sidecar — ```fix```.\nTouched: a.py."
    with pytest.raises(FormatViolation, match="forbidden-substring"):
        validate_end_entry(body)


def test_validator_rejects_error_prefix():
    body = "Worked on sidecar — Error: something.\nTouched: a.py."
    with pytest.raises(FormatViolation, match="forbidden-substring"):
        validate_end_entry(body)


def test_validator_rejects_traceback():
    body = "Worked on sidecar — saw a Traceback.\nTouched: a.py."
    with pytest.raises(FormatViolation, match="forbidden-substring"):
        validate_end_entry(body)


def test_validator_rejects_html_chars():
    body = "Worked on sidecar — uses <div>.\nTouched: a.py."
    with pytest.raises(FormatViolation, match="html-bleed"):
        validate_end_entry(body)


def test_validator_rejects_wrong_line_count():
    body = "Worked on sidecar — fix.\nTouched: a.py.\nExtra line."
    with pytest.raises(FormatViolation, match="shape-mismatch"):
        validate_end_entry(body)


def test_validator_rejects_missing_files_in_builder():
    with pytest.raises(FormatViolation, match="missing-files"):
        build_end_entry("hazar", "sidecar", "fix it", [], REF_TS)


def test_validator_accepts_happy_path():
    body = "Worked on sidecar — fix login.\nTouched: src/api/login.ts."
    # Should not raise
    validate_end_entry(body)


# --- L4: length cap is on the task brief, not the assembled body ------------


def test_end_entry_accepts_max_brief_even_when_assembled_body_exceeds_300():
    """A 300-char brief is valid even though the assembled body (brief + wrapper +
    files) exceeds 300. Matches sf-wrap's task_brief≤300 contract so a brief sf-wrap
    accepts is one feed accepts (L4 desync fix)."""
    brief = "x" * 300
    out = build_end_entry("hazar", "sidecar", brief, ["a.py"], REF_TS)
    assert f"Worked on sidecar — {brief}." in out  # did not raise; body is well over 300


def test_end_entry_rejects_brief_over_cap_with_actionable_message():
    brief = "x" * 301
    with pytest.raises(FormatViolation, match="too-long") as exc:
        build_end_entry("hazar", "sidecar", brief, ["a.py"], REF_TS)
    assert "task brief" in str(exc.value)
    assert "301" in str(exc.value)


def test_validate_end_entry_body_backstop_when_brief_absent():
    """Direct/legacy callers that pass only `body` still get the body-length backstop."""
    body = "Worked on sidecar — " + ("x" * 300) + ".\nTouched: a.py."
    with pytest.raises(FormatViolation, match="too-long"):
        validate_end_entry(body)  # no task_brief → body backstop applies
