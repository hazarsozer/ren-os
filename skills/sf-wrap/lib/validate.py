"""
sf-wrap pre-validators.

Defense-in-depth format-shape validators for the terse-feed `summary` field.
These run BEFORE calling feed.feed_write_entry so we can re-prompt the LLM
without a round-trip when a violation is caught early. feed.format.validate_end_entry
is the final safety net.

Per the locked lifecycle ↔ feed contract (team-lead arbitration 2026-05-28):
the reject list is format-SHAPE only. No secret-pattern scanning (ADR-021
explicitly rejects framework-level secret scanning; format constraint IS the
privacy mechanism).
"""

from __future__ import annotations

import re
from typing import Final

from .types import FormatViolationReport  # noqa: F401 — re-export

# Locked caps per team-lead arbitration 2026-05-28
MAX_SUMMARY_CHARS: Final[int] = 300
MAX_FILES_DISPLAYED: Final[int] = 8

# Format-shape reject patterns. NO secret-pattern scanning here.
_TRIPLE_BACKTICK: Final[str] = "```"
_NEWLINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\r\n]")
_ERROR_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(Error:|Traceback)")
_ANGLE_BRACKET_PATTERN: Final[re.Pattern[str]] = re.compile(r"[<>]")


def validate_summary(summary: str) -> FormatViolationReport:
    """
    Pre-validate a task_brief / session-end summary against the locked
    terse-format reject list. Returns FormatViolationReport(valid=True) on
    pass, or FormatViolationReport(valid=False, reason=<terse>) on the
    first violation found (short-circuits).

    Defense-in-depth note: feed.format.validate_end_entry runs again on
    feed's side. This pre-validator exists so we can re-prompt the LLM
    locally before the feed call.

    Args:
        summary: The proposed session-end summary text.

    Returns:
        FormatViolationReport. Truthy when valid.
    """
    if not isinstance(summary, str):
        return FormatViolationReport(
            valid=False,
            reason=f"summary must be str, got {type(summary).__name__}",
        )

    if not summary:
        return FormatViolationReport(
            valid=False,
            reason="summary must not be empty",
        )

    if _NEWLINE_PATTERN.search(summary):
        return FormatViolationReport(
            valid=False,
            reason="summary must not contain newlines",
        )

    n_chars = len(summary)
    if n_chars > MAX_SUMMARY_CHARS:
        return FormatViolationReport(
            valid=False,
            reason=f"summary {n_chars} chars; max {MAX_SUMMARY_CHARS}",
        )

    if _TRIPLE_BACKTICK in summary:
        return FormatViolationReport(
            valid=False,
            reason="summary must not contain triple-backtick fences (no code blocks)",
        )

    if _ERROR_MARKER_PATTERN.search(summary):
        return FormatViolationReport(
            valid=False,
            reason="summary must not contain stack-trace markers (Error:/Traceback)",
        )

    if _ANGLE_BRACKET_PATTERN.search(summary):
        return FormatViolationReport(
            valid=False,
            reason="summary must not contain '<' or '>' characters outside the header line",
        )

    return FormatViolationReport(valid=True)


def truncate_files_touched(files: list[str]) -> list[str]:
    """
    Truncate a list of touched files to the locked display cap, appending
    a '…and N more' marker if elided. Used at compose-time, before the
    feed call.

    Args:
        files: Ordered list of file paths the session touched.

    Returns:
        List of length ≤ MAX_FILES_DISPLAYED + 1 (with the "…and N more"
        marker counting as the +1 when truncation occurred).
    """
    if not isinstance(files, list):
        raise TypeError(f"files must be list, got {type(files).__name__}")

    if len(files) <= MAX_FILES_DISPLAYED:
        return list(files)

    keep = files[:MAX_FILES_DISPLAYED]
    elided = len(files) - MAX_FILES_DISPLAYED
    keep.append(f"…and {elided} more")
    return keep


def format_files_touched_for_summary(files: list[str]) -> str:
    """
    Render a files_touched list as a comma-separated string suitable for
    inclusion in a summary line. Applies truncation first.

    Example:
        ['a.py', 'b.py']         → "a.py, b.py"
        list of 12 files          → "f1.py, f2.py, ..., f8.py, …and 4 more"
    """
    truncated = truncate_files_touched(files)
    return ", ".join(truncated)
