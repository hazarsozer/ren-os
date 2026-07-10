"""
Tests for lib.memory.locks — G6 concurrency: file lease/lock + lost-update
detection (Task 1.3).

Two independent primitives under test:
  1. `lease(page, ttl_s)` — exclusive lockfile per page under
     ren_paths.state_dir()/"locks"/. Non-stale existing lock -> LeaseHeld.
     Stale lock -> broken + logged to locks/breaks.log. Always released, even
     on exception.
  2. `content_token` / `check_token` — sha256-based lost-update / corruption
     primitive: unchanged file round-trips, changed file raises LostUpdate.

Every test redirects ren_paths' framework root to a tmp_path via
REN_FRAMEWORK_ROOT (see tests/lib/test_ren_paths.py's `clean_path_env`
fixture) — never the real ~/.renos.

Run with: uv run pytest tests/lib/memory/test_locks.py -v
"""

from __future__ import annotations

import json
import time

import pytest

from lib.memory.locks import (
    LeaseHeld,
    LostUpdate,
    check_token,
    content_token,
    lease,
)
from lib.ren_paths import state_dir


@pytest.fixture
def clean_path_env(monkeypatch):
    """Start from a known-empty env; never touch the real ~/.renos."""
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def temp_root(clean_path_env, tmp_path):
    """Point ren_paths' framework root at tmp_path so state_dir()/locks/ lands there."""
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    return tmp_path


# --------------------------------------------------------------------- lease


def test_lease_acquire_and_release_is_clean(temp_root):
    with lease("identity.md"):
        lock_path = state_dir() / "locks"
        assert list(lock_path.glob("*.lock")), "expected a lockfile while held"

    assert not list((state_dir() / "locks").glob("*.lock")), "lockfile must be gone after release"


def test_acquiring_a_held_lease_raises_lease_held(temp_root):
    with lease("identity.md"):
        with pytest.raises(LeaseHeld):
            with lease("identity.md"):
                pass  # pragma: no cover - must not be reached


def test_same_process_can_reacquire_after_release(temp_root):
    with lease("identity.md"):
        pass

    # No LeaseHeld this time — the first lease released its lockfile on exit.
    with lease("identity.md"):
        pass


def test_lease_released_on_exception_inside_with_block(temp_root):
    with pytest.raises(ValueError):
        with lease("identity.md"):
            raise ValueError("boom")

    assert not list((state_dir() / "locks").glob("*.lock")), "lockfile must be released even on exception"

    # Proves it's actually released, not just present-but-orphaned: re-acquiring works.
    with lease("identity.md"):
        pass


def test_stale_lock_is_broken_and_logged(temp_root):
    locks_dir = state_dir() / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)

    # Hand-craft a lock file with a fake old timestamp (older than ttl_s).
    stale_payload = {"pid": 999999, "session": "old-session", "ts": time.time() - 10_000}
    import hashlib
    lock_path = locks_dir / f"{hashlib.sha1(b'identity.md').hexdigest()}.lock"
    lock_path.write_text(json.dumps(stale_payload), encoding="utf-8")

    with lease("identity.md", ttl_s=300):
        pass  # should succeed: the stale lock was broken, not honored

    breaks_log = locks_dir / "breaks.log"
    assert breaks_log.exists()
    entries = [json.loads(line) for line in breaks_log.read_text(encoding="utf-8").splitlines()]
    assert any(e["page"] == "identity.md" and e["prior_holder"]["session"] == "old-session" for e in entries)


def test_non_stale_lock_within_ttl_raises(temp_root):
    locks_dir = state_dir() / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    lock_path = locks_dir / f"{hashlib.sha1(b'identity.md').hexdigest()}.lock"
    fresh_payload = {"pid": 1, "session": "other-session", "ts": time.time()}
    lock_path.write_text(json.dumps(fresh_payload), encoding="utf-8")

    with pytest.raises(LeaseHeld):
        with lease("identity.md", ttl_s=300):
            pass  # pragma: no cover


def test_corrupt_lockfile_is_treated_as_stale(temp_root):
    locks_dir = state_dir() / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    lock_path = locks_dir / f"{hashlib.sha1(b'identity.md').hexdigest()}.lock"
    lock_path.write_text("not json{{{", encoding="utf-8")

    # A corrupt lockfile must not wedge the lease forever.
    with lease("identity.md", ttl_s=300):
        pass


def test_lease_payload_records_pid_session_ts(temp_root, monkeypatch):
    monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-abc")
    captured = {}

    with lease("identity.md"):
        locks_dir = state_dir() / "locks"
        [lock_file] = list(locks_dir.glob("*.lock"))
        captured.update(json.loads(lock_file.read_text(encoding="utf-8")))

    assert captured["session"] == "sess-abc"
    assert isinstance(captured["pid"], int)
    assert isinstance(captured["ts"], (int, float))


def test_missing_session_env_falls_back_to_unknown(temp_root):
    with lease("identity.md"):
        locks_dir = state_dir() / "locks"
        [lock_file] = list(locks_dir.glob("*.lock"))
        payload = json.loads(lock_file.read_text(encoding="utf-8"))

    assert payload["session"] == "unknown"


def test_different_pages_do_not_contend(temp_root):
    with lease("a.md"):
        with lease("b.md"):
            pass  # different pages -> no contention


def test_concurrent_acquire_race_only_one_winner(temp_root, monkeypatch):
    """codex D1: exists()-check-then-write acquisition is a TOCTOU race — two
    callers can both observe `lock_path.exists() is False` before either
    writes, so both proceed. This test simulates that interleaving by making
    the existence check always report "no lock" (as both racing callers would
    see), then acquiring twice; only the first acquisition may succeed."""
    import lib.memory.locks as locks_mod

    monkeypatch.setattr(locks_mod.Path, "exists", lambda self: False)

    with lease("identity.md"):
        # A second "concurrent" acquirer must still fail even though its
        # exists() check (patched to always return False) can't see the
        # first holder's lockfile — the acquisition itself must be atomic.
        with pytest.raises(LeaseHeld):
            with lease("identity.md"):
                pass  # pragma: no cover


# ------------------------------------------------------------- content_token


def test_content_token_empty_for_absent_file(tmp_path):
    absent = tmp_path / "nope.md"
    assert content_token(absent) == ""


def test_content_token_round_trip_unchanged_file_passes(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("hello world", encoding="utf-8")

    token = content_token(page)
    check_token(page, token)  # must not raise


def test_content_token_changes_when_file_modified(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("hello world", encoding="utf-8")
    token = content_token(page)

    page.write_text("hello world, modified", encoding="utf-8")

    with pytest.raises(LostUpdate):
        check_token(page, token)


def test_content_token_created_after_absent_raises_check(tmp_path):
    page = tmp_path / "page.md"
    token = content_token(page)  # "" — page absent
    assert token == ""

    page.write_text("now it exists", encoding="utf-8")

    with pytest.raises(LostUpdate):
        check_token(page, token)


def test_content_token_deterministic_for_same_bytes(tmp_path):
    page_a = tmp_path / "a.md"
    page_b = tmp_path / "b.md"
    page_a.write_text("identical content", encoding="utf-8")
    page_b.write_text("identical content", encoding="utf-8")

    assert content_token(page_a) == content_token(page_b)
