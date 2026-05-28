"""
Tests for feed.skip.is_skip_active — the single source of truth for the opt-out chain.

This is the ONE module with real implementation in scaffold phase, so it gets real
tests. Verifies the precedence chain (session-disabled > env-var > wrap-flag > default)
and the per-session state file behavior.

Run with: uv run pytest feed/tests/test_skip.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from feed import skip
from feed.skip import is_skip_active, mark_session_disabled


@pytest.fixture
def temp_framework_root(monkeypatch):
    """Redirect feed.config.framework_root() to a temp dir so tests don't pollute ~/."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        # Clear any inherited env vars that would interfere with precedence tests
        monkeypatch.delenv("SF_SKIP_FEED", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        yield Path(tmp)


# --- default behavior --------------------------------------------------------


def test_default_is_not_skipping(temp_framework_root):
    """No state file, no env var, wrap_flag=False → not skipping."""
    skipping, reason = is_skip_active(wrap_flag=False)
    assert skipping is False
    assert reason == "not-skipping"


# --- wrap-flag (lowest precedence) -------------------------------------------


def test_wrap_flag_alone_triggers_skip(temp_framework_root):
    """No state file, no env var, wrap_flag=True → skipping with reason='wrap-flag'."""
    skipping, reason = is_skip_active(wrap_flag=True)
    assert skipping is True
    assert reason == "wrap-flag"


# --- env var (middle precedence) ---------------------------------------------


def test_env_var_truthy_triggers_skip(temp_framework_root, monkeypatch):
    """SF_SKIP_FEED=1 → skipping with reason='env-var'."""
    monkeypatch.setenv("SF_SKIP_FEED", "1")
    skipping, reason = is_skip_active(wrap_flag=False)
    assert skipping is True
    assert reason == "env-var"


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "YES", "True"])
def test_env_var_recognizes_truthy_values(temp_framework_root, monkeypatch, truthy):
    """Multiple truthy spellings are accepted."""
    monkeypatch.setenv("SF_SKIP_FEED", truthy)
    skipping, _ = is_skip_active()
    assert skipping is True


@pytest.mark.parametrize("falsy", ["0", "false", "FALSE", "no", "", "anything"])
def test_env_var_ignores_falsy_values(temp_framework_root, monkeypatch, falsy):
    """Non-truthy env-var values do not trigger skip."""
    monkeypatch.setenv("SF_SKIP_FEED", falsy)
    skipping, reason = is_skip_active()
    assert skipping is False
    assert reason == "not-skipping"


def test_env_var_overrides_wrap_flag_false(temp_framework_root, monkeypatch):
    """Env var dominates when wrap_flag=False — env-var precedence > default."""
    monkeypatch.setenv("SF_SKIP_FEED", "1")
    skipping, reason = is_skip_active(wrap_flag=False)
    assert skipping is True
    assert reason == "env-var"


def test_env_var_dominates_wrap_flag_true(temp_framework_root, monkeypatch):
    """When BOTH env var and wrap_flag are set, env var wins (higher precedence)."""
    monkeypatch.setenv("SF_SKIP_FEED", "1")
    skipping, reason = is_skip_active(wrap_flag=True)
    assert skipping is True
    assert reason == "env-var"


# --- session-disabled (highest precedence) -----------------------------------


def test_session_disabled_marker_triggers_skip(temp_framework_root, monkeypatch):
    """mark_session_disabled writes the state file → is_skip_active sees it."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "abc123")
    mark_session_disabled(session_id="abc123")

    skipping, reason = is_skip_active()
    assert skipping is True
    assert reason == "session-disabled"


def test_session_disabled_dominates_env_var(temp_framework_root, monkeypatch):
    """Session-disabled is highest precedence → wins over env var."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "abc123")
    monkeypatch.setenv("SF_SKIP_FEED", "1")
    mark_session_disabled(session_id="abc123")

    skipping, reason = is_skip_active(wrap_flag=True)
    assert skipping is True
    assert reason == "session-disabled"  # NOT env-var or wrap-flag


def test_session_disabled_only_applies_to_matching_session(temp_framework_root, monkeypatch):
    """State file for session-A should NOT affect session-B."""
    mark_session_disabled(session_id="session-A")
    monkeypatch.setenv("CLAUDE_SESSION_ID", "session-B")

    skipping, _ = is_skip_active()
    # session-B has no state file → no skip from that source
    # But fallback finds the most-recent state file in tests w/o env var... we set env var
    # to session-B explicitly so the fallback isn't triggered. Verify clean.
    assert skipping is False


def test_malformed_state_file_fails_open(temp_framework_root, monkeypatch):
    """Corrupt state file = fail open (do not skip) so user can recover."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "corrupt")
    state_dir = temp_framework_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "session-corrupt.json").write_text("{ not valid json", encoding="utf-8")

    skipping, reason = is_skip_active()
    assert skipping is False
    assert reason == "not-skipping"


def test_missing_skip_feed_field_treated_as_false(temp_framework_root, monkeypatch):
    """State file exists but lacks skip_feed=true → not skipping."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "nokey")
    state_dir = temp_framework_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "session-nokey.json").write_text(
        json.dumps({"some_other_field": True}), encoding="utf-8"
    )

    skipping, _ = is_skip_active()
    assert skipping is False


def test_mark_session_disabled_is_idempotent(temp_framework_root, monkeypatch):
    """Calling mark_session_disabled twice produces the same observable state."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "idem")
    mark_session_disabled(session_id="idem")
    mark_session_disabled(session_id="idem")  # should not error

    skipping, reason = is_skip_active()
    assert skipping is True
    assert reason == "session-disabled"


def test_mark_session_disabled_writes_expected_payload(temp_framework_root, monkeypatch):
    """The state file should be valid JSON with skip_feed=true + reason + timestamp."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "payload")
    mark_session_disabled(session_id="payload", reason="user-disabled")

    state_file = temp_framework_root / "state" / "session-payload.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["skip_feed"] is True
    assert data["reason"] == "user-disabled"
    assert isinstance(data["timestamp"], int)


# --- precedence sanity check (combinatorial) ---------------------------------


def test_full_precedence_chain(temp_framework_root, monkeypatch):
    """All four precedence levels tested in one truth-table flow.

    Order matches plan §6.1 + behavior matrix §6.2.
    """
    # Level 0: nothing set → not-skipping
    skipping, reason = is_skip_active(wrap_flag=False)
    assert (skipping, reason) == (False, "not-skipping")

    # Level 1: only wrap_flag → wrap-flag
    skipping, reason = is_skip_active(wrap_flag=True)
    assert (skipping, reason) == (True, "wrap-flag")

    # Level 2: env var (with or without wrap_flag) → env-var
    monkeypatch.setenv("SF_SKIP_FEED", "1")
    skipping, reason = is_skip_active(wrap_flag=False)
    assert (skipping, reason) == (True, "env-var")
    skipping, reason = is_skip_active(wrap_flag=True)
    assert (skipping, reason) == (True, "env-var")

    # Level 3: session-disabled → session-disabled (regardless of below)
    monkeypatch.setenv("CLAUDE_SESSION_ID", "top")
    mark_session_disabled(session_id="top")
    skipping, reason = is_skip_active(wrap_flag=True)
    assert (skipping, reason) == (True, "session-disabled")
