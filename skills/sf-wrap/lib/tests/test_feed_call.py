"""Tests for skills.sf_wrap.lib.feed_call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from ..feed_call import (
    INTERNAL_BUG_VIOLATIONS,
    RE_PROMPTABLE_VIOLATIONS,
    USER_ACTIONABLE_MESSAGES,
    USER_ACTIONABLE_VIOLATIONS,
    FeedCallOutcome,
    do_feed_write,
)


# ---------------------------------------------------------------------------
# Fake feed result shape — duck-types feed.FeedWriteResult
# ---------------------------------------------------------------------------


@dataclass
class FakeFeedResult:
    """Mimics feed.FeedWriteResult for injection."""

    success: bool = False
    entry_id: str = ""
    pushed: bool = False
    queued: bool = False
    error: str | None = None
    violation: str | None = None


def _make_writer(result: FakeFeedResult, second_result: FakeFeedResult | None = None):
    """Build a fake writer that returns `result` on first call, `second_result` on second."""
    calls = {"count": 0}

    def writer(**kwargs) -> FakeFeedResult:
        calls["count"] += 1
        if calls["count"] >= 2 and second_result is not None:
            return second_result
        return result

    writer.calls = calls  # type: ignore[attr-defined]
    return writer


def _basic_kwargs(**overrides):
    """Default kwargs for do_feed_write that callers usually want."""
    defaults = dict(
        task_brief="Worked on auth — fixed JWT validation. Touched: api/auth.py.",
        project="sample",
        files_touched=["api/auth.py", "tests/test_auth.py"],
        skip_feed_flag=False,
        is_skip_active_fn=lambda flag: (False, ""),
        get_handle_fn=lambda: "test-friend",
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Violation categorization tables
# ---------------------------------------------------------------------------


class TestViolationCategorizationTables:
    def test_user_actionable_two_codes(self):
        """Pin: only two codes are user-actionable; others get different treatment."""
        assert USER_ACTIONABLE_VIOLATIONS == {"not-bootstrapped", "schema-mismatch"}

    def test_re_promptable_four_codes(self):
        assert RE_PROMPTABLE_VIOLATIONS == {
            "too-long", "forbidden-substring", "html-bleed", "shape-mismatch",
        }

    def test_internal_bug_four_codes(self):
        assert INTERNAL_BUG_VIOLATIONS == {
            "missing-files", "missing-project", "missing-cwd", "unknown-kind",
        }

    def test_user_actionable_messages_cover_each_code(self):
        for code in USER_ACTIONABLE_VIOLATIONS:
            assert code in USER_ACTIONABLE_MESSAGES, f"missing message for {code}"

    def test_categorization_is_partition(self):
        """Each violation code appears in exactly one category (no overlap)."""
        overlap = (
            USER_ACTIONABLE_VIOLATIONS & RE_PROMPTABLE_VIOLATIONS
            | USER_ACTIONABLE_VIOLATIONS & INTERNAL_BUG_VIOLATIONS
            | RE_PROMPTABLE_VIOLATIONS & INTERNAL_BUG_VIOLATIONS
        )
        assert overlap == set(), f"violation categories overlap: {overlap}"


# ---------------------------------------------------------------------------
# Skip path
# ---------------------------------------------------------------------------


class TestSkipChain:
    def test_skip_returns_skipped_outcome_no_writer_called(self):
        writer = _make_writer(FakeFeedResult())
        outcome = do_feed_write(
            **_basic_kwargs(
                is_skip_active_fn=lambda flag: (True, "wrap-flag"),
                feed_writer=writer,
            )
        )
        assert outcome.skipped
        assert outcome.skip_reason == "wrap-flag"
        assert not outcome.written
        assert "feed skipped" in outcome.user_message
        assert writer.calls["count"] == 0  # writer not invoked

    def test_skip_chain_priorities(self):
        """The skip resolver is the single source of truth; whatever it returns is honored."""
        for reason in ["wrap-flag", "env-var", "session-disabled"]:
            outcome = do_feed_write(
                **_basic_kwargs(
                    is_skip_active_fn=lambda flag, r=reason: (True, r),
                )
            )
            assert outcome.skipped
            assert outcome.skip_reason == reason
            assert reason in outcome.user_message


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestSuccessPaths:
    def test_success_pushed(self):
        writer = _make_writer(FakeFeedResult(success=True, pushed=True, entry_id="abc"))
        outcome = do_feed_write(**_basic_kwargs(feed_writer=writer))
        assert outcome.written
        assert outcome.pushed
        assert not outcome.queued
        assert "✓ feed entry pushed" in outcome.user_message

    def test_success_queued(self):
        """Success but push deferred (auth/network failure on push)."""
        writer = _make_writer(FakeFeedResult(success=True, pushed=False, queued=True))
        outcome = do_feed_write(**_basic_kwargs(feed_writer=writer))
        assert outcome.written
        assert outcome.queued
        assert not outcome.pushed
        assert "queued locally" in outcome.user_message


# ---------------------------------------------------------------------------
# User-actionable violations
# ---------------------------------------------------------------------------


class TestUserActionableViolations:
    def test_not_bootstrapped_no_reprompt(self):
        writer = _make_writer(FakeFeedResult(success=False, violation="not-bootstrapped"))
        outcome = do_feed_write(
            **_basic_kwargs(
                feed_writer=writer,
                reprompter=lambda v, s: s,  # would normally retry, but should NOT here
            )
        )
        assert not outcome.written
        assert outcome.raw_violation == "not-bootstrapped"
        assert not outcome.reprompt_attempted  # explicit pin
        assert "/sf:install" in outcome.user_message
        assert writer.calls["count"] == 1  # writer NOT retried

    def test_schema_mismatch_no_reprompt(self):
        writer = _make_writer(FakeFeedResult(success=False, violation="schema-mismatch"))
        outcome = do_feed_write(
            **_basic_kwargs(
                feed_writer=writer,
                reprompter=lambda v, s: s,
            )
        )
        assert not outcome.written
        assert "/sf:update" in outcome.user_message
        assert not outcome.reprompt_attempted
        assert writer.calls["count"] == 1


# ---------------------------------------------------------------------------
# Internal bug violations
# ---------------------------------------------------------------------------


class TestInternalBugViolations:
    @pytest.mark.parametrize(
        "violation", ["missing-files", "missing-project", "missing-cwd", "unknown-kind"],
    )
    def test_internal_bug_message_includes_file_a_bug(self, violation: str):
        writer = _make_writer(FakeFeedResult(success=False, violation=violation))
        outcome = do_feed_write(**_basic_kwargs(feed_writer=writer))
        assert not outcome.written
        assert outcome.raw_violation == violation
        assert "file a bug" in outcome.user_message.lower() or "validation error" in outcome.user_message.lower()


# ---------------------------------------------------------------------------
# Re-promptable violations
# ---------------------------------------------------------------------------


class TestRepromptableViolations:
    def test_too_long_with_reprompter_retries_once(self):
        """First call returns too-long; reprompter returns shorter; retry succeeds."""
        writer = _make_writer(
            FakeFeedResult(success=False, violation="too-long"),
            second_result=FakeFeedResult(success=True, pushed=True),
        )
        outcome = do_feed_write(
            **_basic_kwargs(
                feed_writer=writer,
                reprompter=lambda v, s: "Short brief.",  # under 300 chars
            )
        )
        assert outcome.written
        assert outcome.pushed
        assert outcome.reprompt_attempted
        assert "after re-prompt" in outcome.user_message
        assert writer.calls["count"] == 2

    def test_no_reprompter_abandons_immediately(self):
        """Without a reprompter, re-promptable violations also abandon (no retry)."""
        writer = _make_writer(FakeFeedResult(success=False, violation="too-long"))
        outcome = do_feed_write(
            **_basic_kwargs(
                feed_writer=writer,
                reprompter=None,
            )
        )
        assert not outcome.written
        assert not outcome.reprompt_attempted
        assert "too-long" in outcome.user_message
        assert writer.calls["count"] == 1

    def test_second_failure_abandons(self):
        """Re-prompter produces still-violating brief → abandon per team-lead spec."""
        writer = _make_writer(
            FakeFeedResult(success=False, violation="forbidden-substring"),
            second_result=FakeFeedResult(success=False, violation="too-long"),
        )
        outcome = do_feed_write(
            **_basic_kwargs(
                feed_writer=writer,
                reprompter=lambda v, s: "Still has ```code``` issues.",  # invalid: backticks
            )
        )
        # Pre-validation on the recomposed brief catches it before writer is called again
        assert not outcome.written
        assert outcome.reprompt_attempted
        assert "after re-prompt" in outcome.user_message


# ---------------------------------------------------------------------------
# Pre-validation catches violations BEFORE calling feed
# ---------------------------------------------------------------------------


class TestPreValidation:
    def test_oversize_brief_caught_pre_call(self):
        """Brief >300 chars caught by our pre-validator; writer not invoked."""
        writer = _make_writer(FakeFeedResult(success=True, pushed=True))
        long_brief = "x" * 301
        outcome = do_feed_write(
            **_basic_kwargs(
                task_brief=long_brief,
                feed_writer=writer,
                reprompter=None,
            )
        )
        assert not outcome.written
        assert outcome.raw_violation == "pre-validation"
        assert writer.calls["count"] == 0  # writer NEVER called

    def test_code_block_caught_pre_call(self):
        writer = _make_writer(FakeFeedResult(success=True, pushed=True))
        outcome = do_feed_write(
            **_basic_kwargs(
                task_brief="Has ```code``` in it.",
                feed_writer=writer,
            )
        )
        assert not outcome.written
        assert writer.calls["count"] == 0

    def test_pre_validation_reprompt_succeeds(self):
        """Pre-validation fails; reprompter returns valid brief; writer called once with new."""
        writer = _make_writer(FakeFeedResult(success=True, pushed=True))
        outcome = do_feed_write(
            **_basic_kwargs(
                task_brief="x" * 301,
                feed_writer=writer,
                reprompter=lambda v, s: "Shorter brief.",
            )
        )
        assert outcome.written
        assert writer.calls["count"] == 1  # one call with the recomposed brief


# ---------------------------------------------------------------------------
# Handle resolution failure
# ---------------------------------------------------------------------------


class TestHandleResolution:
    def test_handle_resolver_raises_surfaces_remediation(self):
        """If handle() raises (identity.md missing), outcome surfaces /sf:interview pointer."""
        def raising_handle():
            raise RuntimeError("identity.md missing")

        writer = _make_writer(FakeFeedResult(success=True, pushed=True))
        outcome = do_feed_write(
            **_basic_kwargs(
                feed_writer=writer,
                get_handle_fn=raising_handle,
            )
        )
        assert not outcome.written
        assert outcome.raw_violation == "not-bootstrapped"
        assert "/sf:interview" in outcome.user_message or "/sf:install" in outcome.user_message
        assert writer.calls["count"] == 0  # writer NEVER called when handle missing


# ---------------------------------------------------------------------------
# Result immutability
# ---------------------------------------------------------------------------


class TestOutcomeImmutability:
    def test_frozen(self):
        outcome = FeedCallOutcome(
            written=True, pushed=True, queued=False, skipped=False,
            skip_reason="", reprompt_attempted=False,
            user_message="x", raw_violation=None,
        )
        with pytest.raises(Exception):
            outcome.written = False  # type: ignore[misc]
