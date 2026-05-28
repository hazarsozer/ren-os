"""
sf-wrap feed integration call site.

Per references/feed-call.md (locked contract with feed-2 + team-lead arbitration):
the wrap skill calls `feed.feed_write_session_end()` at SKILL.md step 6.
This module wraps that call with:

  1. Pre-validation via lib/validate.py (catches format-shape violations early)
  2. Skip-chain resolution via feed.is_skip_active() (single source of truth)
  3. One-retry-then-abandon on FormatViolation (per team-lead's locked spec)
  4. Category routing on the result:
       - format-shape violations → re-prompt LLM once; abandon on second failure
       - user-actionable violations (not-bootstrapped, schema-mismatch) → surface
         remediation pointer; do NOT re-prompt
       - internal bugs (missing-files etc.) → surface bug-filing prompt

The LLM-summary-recomposition callback is INJECTED (similar to sf-improve-skill's
ChangeProposer pattern) so this module is fully unit-testable without invoking
real Claude sub-runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Final

from .validate import validate_summary, truncate_files_touched

logger = logging.getLogger(__name__)


# Violation categorization per references/feed-call.md
USER_ACTIONABLE_VIOLATIONS: Final[frozenset[str]] = frozenset({
    "not-bootstrapped",
    "schema-mismatch",
})
RE_PROMPTABLE_VIOLATIONS: Final[frozenset[str]] = frozenset({
    "too-long",
    "forbidden-substring",
    "html-bleed",
    "shape-mismatch",
})
INTERNAL_BUG_VIOLATIONS: Final[frozenset[str]] = frozenset({
    "missing-files",
    "missing-project",
    "missing-cwd",
    "unknown-kind",
})


# User-facing remediation messages for user-actionable violations
USER_ACTIONABLE_MESSAGES: Final[dict[str, str]] = {
    "not-bootstrapped": (
        "Activity Feed not set up. Run `/sf:install` Stage 3 to bootstrap. "
        "Wiki updates were saved; only the feed entry was skipped."
    ),
    "schema-mismatch": (
        "Feed schema out of date. Run `/sf:update` to migrate. "
        "Wiki updates were saved; only the feed entry was skipped."
    ),
}


@dataclass(frozen=True)
class FeedCallOutcome:
    """Outcome of the feed call site (wraps feed's FeedWriteResult + our UX shape)."""

    written: bool                # True if entry was successfully recorded (success or queued)
    pushed: bool                 # True if also pushed to remote (not just locally queued)
    queued: bool                 # True if locally committed but push deferred
    skipped: bool                # True if skip-chain was active
    skip_reason: str             # populated when skipped (e.g., "wrap-flag", "env-var")
    reprompt_attempted: bool     # True if format-violation triggered a retry
    user_message: str            # the user-facing line to display
    raw_violation: str | None    # the raw violation code (for debugging / /sf:doctor)


# Callback signature: recompose summary in response to a violation.
# `(violation_code, original_summary) -> new_summary`
SummaryReprompter = Callable[[str, str], str]


# Callback signature: invoke the real feed.feed_write_session_end.
# Injected for testability; default delegates to the real feed module.
# Returns a feed.FeedWriteResult-shaped object (anything with success/pushed/
# queued/violation/error attributes).
FeedWriter = Callable[..., "object"]


def _default_feed_writer() -> FeedWriter:
    """Return the real feed.feed_write_session_end, imported lazily."""
    from feed import feed_write_session_end  # late import for test isolation
    return feed_write_session_end


def _default_is_skip_active(wrap_flag: bool) -> tuple[bool, str]:
    """Default: defer to real feed.is_skip_active. Late import for test isolation."""
    from feed import is_skip_active
    return is_skip_active(wrap_flag=wrap_flag)


def _default_get_handle() -> str:
    """Default: defer to feed.config.handle. Late import for test isolation."""
    from feed.config import handle as get_handle
    return get_handle()


def do_feed_write(
    *,
    task_brief: str,
    project: str | None,
    files_touched: list[str],
    skip_feed_flag: bool,
    schema_version: int = 1,
    timestamp: datetime | None = None,
    # Injection points (defaults delegate to real feed module)
    feed_writer: FeedWriter | None = None,
    is_skip_active_fn: Callable[[bool], tuple[bool, str]] | None = None,
    get_handle_fn: Callable[[], str] | None = None,
    reprompter: SummaryReprompter | None = None,
) -> FeedCallOutcome:
    """
    Execute the SKILL.md step 6-7 feed-write flow.

    Args:
        task_brief: The composed terse summary (≤300 chars per ADR-021).
        project: Active project name or None for unscoped.
        files_touched: Files modified during the session.
        skip_feed_flag: From `/sf:wrap --skip-feed`.
        schema_version: Locked at 1 for V1.
        timestamp: Override now() (for tests).
        feed_writer: Inject a custom writer (for tests).
        is_skip_active_fn: Inject a custom skip-resolver (for tests).
        get_handle_fn: Inject a custom handle resolver (for tests).
        reprompter: Callback to recompose the summary on format violation.
            Receives (violation_code, original_summary); returns new summary.
            If None and a re-promptable violation fires, behaves as if the
            reprompt also produced a violation (abandons after first attempt).

    Returns:
        FeedCallOutcome carrying both the user-facing message and structured
        flags the wrap orchestrator uses to compose its final summary line.
    """
    skip_resolver = is_skip_active_fn or _default_is_skip_active
    handle_resolver = get_handle_fn or _default_get_handle

    # --- Pre-call: resolve skip-chain ---
    try:
        skip_active, skip_reason = skip_resolver(skip_feed_flag)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("is_skip_active raised; treating as no-skip: %s", exc)
        skip_active, skip_reason = False, ""

    if skip_active:
        return FeedCallOutcome(
            written=False,
            pushed=False,
            queued=False,
            skipped=True,
            skip_reason=skip_reason,
            reprompt_attempted=False,
            user_message=f"(feed skipped: {skip_reason})",
            raw_violation=None,
        )

    # --- Pre-validation (defense-in-depth per locked contract) ---
    validation = validate_summary(task_brief)
    if not validation:
        # Our own pre-validator caught it BEFORE calling feed.
        # Try one re-prompt if reprompter provided; else abandon.
        if reprompter is None:
            return FeedCallOutcome(
                written=False, pushed=False, queued=False, skipped=False,
                skip_reason="", reprompt_attempted=False,
                user_message=f"⚠ feed entry rejected (pre-validation: {validation.reason}); wiki saved",
                raw_violation="pre-validation",
            )
        new_brief = reprompter("pre-validation", task_brief)
        new_validation = validate_summary(new_brief)
        if not new_validation:
            return FeedCallOutcome(
                written=False, pushed=False, queued=False, skipped=False,
                skip_reason="", reprompt_attempted=True,
                user_message=f"⚠ feed entry rejected after re-prompt ({new_validation.reason}); wiki saved",
                raw_violation="pre-validation",
            )
        task_brief = new_brief  # use the recomposed version

    # Truncate files_touched per the locked spec
    safe_files = truncate_files_touched(files_touched)

    # Resolve handle (may raise on missing identity.md)
    try:
        handle = handle_resolver()
    except Exception as exc:  # noqa: BLE001 — surface as feed-side issue
        return FeedCallOutcome(
            written=False, pushed=False, queued=False, skipped=False,
            skip_reason="", reprompt_attempted=False,
            user_message=(
                f"⚠ couldn't resolve friend handle ({exc}). "
                "Run `/sf:install` Stage 4 or `/sf:interview` to set up identity.md. "
                "Wiki saved."
            ),
            raw_violation="not-bootstrapped",
        )

    # --- Call feed writer ---
    writer = feed_writer or _default_feed_writer()

    result = _call_writer(
        writer,
        handle=handle,
        project=project,
        task_brief=task_brief,
        files_touched=safe_files,
        schema_version=schema_version,
        timestamp=timestamp,
        skip=False,
    )

    return _interpret_result(
        result,
        task_brief=task_brief,
        project=project,
        safe_files=safe_files,
        handle=handle,
        schema_version=schema_version,
        timestamp=timestamp,
        reprompter=reprompter,
        writer=writer,
    )


def _call_writer(
    writer: FeedWriter,
    *,
    handle: str,
    project: str | None,
    task_brief: str,
    files_touched: list[str],
    schema_version: int,
    timestamp: datetime | None,
    skip: bool,
) -> "object":
    """Call the writer with normalized kwargs. Raises only on unexpected errors."""
    return writer(
        handle=handle,
        project=project,
        task_brief=task_brief,
        files_touched=files_touched,
        schema_version=schema_version,
        skip=skip,
        timestamp=timestamp,
    )


def _interpret_result(
    result: "object",
    *,
    task_brief: str,
    project: str | None,
    safe_files: list[str],
    handle: str,
    schema_version: int,
    timestamp: datetime | None,
    reprompter: SummaryReprompter | None,
    writer: FeedWriter,
) -> FeedCallOutcome:
    """Translate a feed result into a FeedCallOutcome with the right user message."""
    success = bool(getattr(result, "success", False))
    pushed = bool(getattr(result, "pushed", False))
    queued = bool(getattr(result, "queued", False))
    violation = getattr(result, "violation", None)
    error = getattr(result, "error", None)

    # Success paths
    if success and pushed:
        return FeedCallOutcome(
            written=True, pushed=True, queued=False, skipped=False,
            skip_reason="", reprompt_attempted=False,
            user_message="✓ feed entry pushed",
            raw_violation=None,
        )
    if success and queued:
        return FeedCallOutcome(
            written=True, pushed=False, queued=True, skipped=False,
            skip_reason="", reprompt_attempted=False,
            user_message="⚠ feed entry queued locally; will retry next session-start",
            raw_violation=None,
        )

    # Failure paths — categorize by violation
    if violation in USER_ACTIONABLE_VIOLATIONS:
        return FeedCallOutcome(
            written=False, pushed=False, queued=False, skipped=False,
            skip_reason="", reprompt_attempted=False,
            user_message=USER_ACTIONABLE_MESSAGES[violation],
            raw_violation=violation,
        )

    if violation in INTERNAL_BUG_VIOLATIONS:
        return FeedCallOutcome(
            written=False, pushed=False, queued=False, skipped=False,
            skip_reason="", reprompt_attempted=False,
            user_message=(
                f"⚠ internal validation error ({violation}); wiki saved. "
                "Please file a bug — our pre-validator missed something."
            ),
            raw_violation=violation,
        )

    if violation in RE_PROMPTABLE_VIOLATIONS:
        if reprompter is None:
            return FeedCallOutcome(
                written=False, pushed=False, queued=False, skipped=False,
                skip_reason="", reprompt_attempted=False,
                user_message=f"⚠ feed entry rejected ({violation}); wiki saved",
                raw_violation=violation,
            )
        new_brief = reprompter(violation, task_brief)
        # Pre-validate the recomposed brief locally before another round-trip
        if not validate_summary(new_brief):
            return FeedCallOutcome(
                written=False, pushed=False, queued=False, skipped=False,
                skip_reason="", reprompt_attempted=True,
                user_message=f"⚠ feed entry rejected after re-prompt ({violation}); wiki saved",
                raw_violation=violation,
            )
        # Retry the writer with the recomposed brief
        retry_result = _call_writer(
            writer,
            handle=handle,
            project=project,
            task_brief=new_brief,
            files_touched=safe_files,
            schema_version=schema_version,
            timestamp=timestamp,
            skip=False,
        )
        retry_success = bool(getattr(retry_result, "success", False))
        retry_pushed = bool(getattr(retry_result, "pushed", False))
        retry_queued = bool(getattr(retry_result, "queued", False))
        retry_violation = getattr(retry_result, "violation", None)

        if retry_success and retry_pushed:
            return FeedCallOutcome(
                written=True, pushed=True, queued=False, skipped=False,
                skip_reason="", reprompt_attempted=True,
                user_message="✓ feed entry pushed (after re-prompt)",
                raw_violation=None,
            )
        if retry_success and retry_queued:
            return FeedCallOutcome(
                written=True, pushed=False, queued=True, skipped=False,
                skip_reason="", reprompt_attempted=True,
                user_message="⚠ feed entry queued (after re-prompt); will retry next session-start",
                raw_violation=None,
            )

        # Second failure → abandon per team-lead's locked spec
        return FeedCallOutcome(
            written=False, pushed=False, queued=False, skipped=False,
            skip_reason="", reprompt_attempted=True,
            user_message=(
                f"⚠ feed entry rejected after re-prompt "
                f"({retry_violation or 'unknown'}); wiki saved"
            ),
            raw_violation=retry_violation or violation,
        )

    # Other failures (e.g., error field populated; unknown violation code)
    err_text = error or str(violation) if violation else "unknown error"
    return FeedCallOutcome(
        written=False, pushed=False, queued=False, skipped=False,
        skip_reason="", reprompt_attempted=False,
        user_message=f"⚠ feed write failed: {err_text}; wiki saved",
        raw_violation=str(violation) if violation else None,
    )


__all__ = [
    "USER_ACTIONABLE_VIOLATIONS",
    "RE_PROMPTABLE_VIOLATIONS",
    "INTERNAL_BUG_VIOLATIONS",
    "USER_ACTIONABLE_MESSAGES",
    "FeedCallOutcome",
    "SummaryReprompter",
    "FeedWriter",
    "do_feed_write",
]
