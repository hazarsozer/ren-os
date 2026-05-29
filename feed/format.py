"""
feed.format — terse-format builders + validators.

Per ADR-021: the terse format IS the privacy mechanism. NO secret scanning. We enforce
format SHAPE: bounded length, no code fences, no error/traceback noise, file-count cap.

Scaffold phase (task #17) ships type definitions + skeleton builders/validators with
basic implementations. Full validation logic lands in task #19 alongside the writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


FeedEntryKind = Literal["start", "end", "release"]

MAX_TASK_BRIEF_CHARS = 300
"""The locked cap on the user-controlled task brief (L4). Matches sf-wrap's
`validate.MAX_SUMMARY_CHARS=300` so the pre-validator and feed agree: a brief sf-wrap
accepts is one feed accepts. The brief is the free prose the user writes; the file list
and the 'Worked on … — ….' / 'Touched: ….' wrapper are structural and don't count."""

MAX_BODY_CHARS = 300
"""Backstop cap on the assembled end-entry body, used only when `validate_end_entry` is
called WITHOUT the separate `task_brief` (direct/legacy callers). The real contract is
`MAX_TASK_BRIEF_CHARS`; this just guards pathological direct-call bodies (L4)."""

MAX_FILES_DISPLAYED = 8
"""Per team-lead addition (2026-05-28): show ≤8 files; render overflow as '…and N more'."""

MAX_CONTINUATION_HINT_CHARS = 140
"""Per plan §2.2: optional start-entry body line is hard-capped."""

FORBIDDEN_SUBSTRINGS_END = (
    "```",      # code fence — terse format never includes code
    "Error:",   # error-noise; almost always comes with multi-line stack traces
    "Traceback", # same
)


@dataclass(frozen=True)
class FeedEntry:
    """Parsed feed entry. Returned by readers, consumed by /sf:catch-up etc."""

    handle: str
    kind: FeedEntryKind
    timestamp: datetime
    project: Optional[str]
    summary: Optional[str]              # task brief for end entries; "working in <dir>" for start
    files: tuple[str, ...]              # empty for non-end entries
    raw_line: str                        # original markdown for fallback display


class FormatViolation(ValueError):
    """Raised when a builder/validator rejects input that breaks the terse-format contract.

    Includes a `reason` attribute matching the codes referenced in lifecycle-2's contract
    (e.g., "too-long", "code-fence", "html-bleed", "missing-files", "shape-mismatch").

    `str(exception)` always begins with the reason code so callers (and pytest match=)
    can pattern-match without digging into the attribute:

        try:
            validate_end_entry(body)
        except FormatViolation as e:
            print(e.reason)         # "too-long"
            print(str(e))           # "too-long: body is 336 chars; cap is 300"
    """

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        # Always include reason as a prefix so str(exc) is grep-friendly
        full_message = f"{reason}: {message}" if message else reason
        super().__init__(full_message)


# --- builders ---------------------------------------------------------------


def build_start_entry(
    handle: str,
    cwd_short: str,
    timestamp: datetime,
    continuation_hint: str | None = None,
) -> str:
    """Render a session-start entry per plan §2.1 / §2.2.

    Args:
        handle: the friend's handle
        cwd_short: cwd with $HOME stripped to ~, truncated at 80 chars
        timestamp: when the session started
        continuation_hint: optional parenthesized body line, ≤140 chars

    Returns the rendered markdown block (no trailing newline).
    """
    ts = timestamp.strftime("%Y-%m-%d %H:%M")
    header = f"## [{ts}] start | {handle} | working in {cwd_short}"
    if continuation_hint:
        if len(continuation_hint) > MAX_CONTINUATION_HINT_CHARS:
            raise FormatViolation(
                "continuation-hint-too-long",
                f"continuation_hint is {len(continuation_hint)} chars; cap is {MAX_CONTINUATION_HINT_CHARS}",
            )
        return f"{header}\n\n({continuation_hint})"
    return header


def build_end_entry(
    handle: str,
    project: str,
    task_brief: str,
    files_touched: list[str],
    timestamp: datetime,
) -> str:
    """Render a session-end entry per plan §2.3.

    Validates the body before returning. Raises FormatViolation on shape violations.
    """
    ts = timestamp.strftime("%Y-%m-%d %H:%M")
    files_csv = _format_files(files_touched)

    body = f"Worked on {project} — {task_brief}.\nTouched: {files_csv}."
    validate_end_entry(body, files_touched=files_touched, task_brief=task_brief)

    return f"## [{ts}] end | {handle} | session complete\n\n{body}"


def build_release_entry(
    handle: str,
    version: str,
    note: str,
    timestamp: datetime,
) -> str:
    """Render a release-announcement entry per plan §2.5 + ADR-019.

    Single line, no body. No role check (social convention v1 per team-lead).
    TODO(v2): role-based write_release authorization.
    """
    ts = timestamp.strftime("%Y-%m-%d %H:%M")
    return f"## [{ts}] release | {handle} | framework | {version} shipped — {note}"


def _format_files(files: list[str]) -> str:
    """Render the file list, applying the ≤8 cap with '…and N more' overflow."""
    if not files:
        raise FormatViolation("missing-files", "end entry must reference at least one file")
    if len(files) <= MAX_FILES_DISPLAYED:
        return ", ".join(files)
    shown = files[:MAX_FILES_DISPLAYED]
    overflow = len(files) - MAX_FILES_DISPLAYED
    return f"{', '.join(shown)} …and {overflow} more"


# --- validators -------------------------------------------------------------


def validate_start_entry(body: str | None) -> None:
    """Validate optional body line for start entries.

    Start entries are usually one line (no body). If a continuation_hint was added,
    we check it fits the cap.
    """
    if body is None:
        return
    if len(body) > MAX_CONTINUATION_HINT_CHARS:
        raise FormatViolation("continuation-hint-too-long")
    if "\n" in body.strip():
        raise FormatViolation("multi-line-hint")


def validate_end_entry(
    body: str,
    files_touched: list[str] | None = None,
    task_brief: str | None = None,
) -> None:
    """Hard-fail validation of an end-entry body.

    Per ADR-021 + lead-approved validator set:
    - task brief ≤ 300 chars (the user-controlled prose; see length note below)
    - no triple-backticks
    - no 'Error:' or 'Traceback' substrings
    - no '<' or '>' outside the header line (header isn't passed to this fn; we just
      check the body has none)
    - exactly two body lines matching the expected templates
    - mentions at least one file or directory

    Raises FormatViolation with a specific reason on first failure. Order matches the
    plan's §2.4 checklist.

    Length (L4): the contract caps the user-controlled TASK BRIEF, not the assembled
    body (which also carries the structural 'Worked on … — ….' / 'Touched: ….' wrapper
    + the already-capped file list). When `task_brief` is supplied — `build_end_entry`
    always does — we check it directly so the message is actionable and we agree with
    sf-wrap's pre-validator. When only `body` is given (direct/legacy callers), we fall
    back to the `MAX_BODY_CHARS` backstop.
    """
    if task_brief is not None:
        if len(task_brief) > MAX_TASK_BRIEF_CHARS:
            raise FormatViolation(
                "too-long",
                f"task brief is {len(task_brief)} chars; cap is {MAX_TASK_BRIEF_CHARS} "
                "(the file list and 'Worked on …' wrapper don't count — shorten the summary)",
            )
    elif len(body) > MAX_BODY_CHARS:
        raise FormatViolation(
            "too-long",
            f"entry body is {len(body)} chars; cap is {MAX_BODY_CHARS}",
        )

    for forbidden in FORBIDDEN_SUBSTRINGS_END:
        if forbidden in body:
            raise FormatViolation(
                "forbidden-substring",
                f"body contains forbidden substring {forbidden!r} (format-noise, not code/secrets)",
            )

    if "<" in body or ">" in body:
        raise FormatViolation(
            "html-bleed",
            "body contains < or > — blocks accidental HTML/private-tag leakage",
        )

    lines = body.split("\n")
    if len(lines) != 2:
        raise FormatViolation(
            "shape-mismatch",
            f"end entry body must be exactly two lines, got {len(lines)}",
        )

    line1, line2 = lines
    if not line1.startswith("Worked on ") or not line1.endswith("."):
        raise FormatViolation(
            "shape-mismatch",
            "line 1 must match 'Worked on <project> — <brief>.'",
        )
    # Per F5 review fix (2026-05-28): explicitly enforce the ` — ` em-dash separator.
    # Without this check, "Worked on X Y." passes startswith+endswith but the reader's
    # END_PROJECT_BRIEF_RE can't parse project/brief back → project=None silently.
    if " — " not in line1:
        raise FormatViolation(
            "shape-mismatch",
            "line 1 must include ' — ' (em-dash) separator between project and brief",
        )
    if not line2.startswith("Touched: ") or not line2.endswith("."):
        raise FormatViolation(
            "shape-mismatch",
            "line 2 must match 'Touched: <files>.'",
        )

    # Files cap check (only when caller passed the original list — builder always does)
    if files_touched is not None and len(files_touched) == 0:
        raise FormatViolation("missing-files", "files_touched is empty")
