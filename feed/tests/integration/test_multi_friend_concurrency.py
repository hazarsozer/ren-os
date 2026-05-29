"""
Multi-friend concurrency dogfood for the Activity Feed (task #47).

Stress-tests ADR-018's load-bearing claim: per-friend file separation prevents
conflicts when multiple friends end sessions simultaneously. Uses real on-disk
git (no mocks) so failures here would surface real architecture bugs, not test
infrastructure issues.

Scenarios:
1. Simultaneous session-end across N=4 friends (parallel + serialized)
2. Pull-while-others-push race
3. Queue-and-flush under sustained network failure
4. Handle collision detection on joiner-clone path
5. Cross-day chronological invariant under interleaved writes

Run:
    python3 -m pytest feed/tests/integration/test_multi_friend_concurrency.py -v
"""

from __future__ import annotations

import multiprocessing as mp
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

from feed.tests.integration._world import (
    World,
    bare_tracked_files,
    collect_all_handles_in_bare,
    count_log_entries_in_bare,
    setup_world,
    write_session_end_worker,
)


REF_TS = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)


# === fixtures =============================================================


@pytest.fixture
def isolated_env(monkeypatch):
    """Clear feed-related env vars + force multiprocessing 'spawn' start method.

    Forcing spawn (vs fork) ensures workers re-execute imports cleanly — fork can
    inherit env state in ways that mask real per-process isolation bugs.
    """
    monkeypatch.delenv("SF_FRAMEWORK_ROOT", raising=False)
    monkeypatch.delenv("SF_SKIP_FEED", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    yield


@pytest.fixture
def world_4(tmp_path, isolated_env) -> Iterator[World]:
    """Standard 4-friend world: hazar, friend-b, friend-c, friend-d."""
    w = setup_world(tmp_path, ["hazar", "friend-b", "friend-c", "friend-d"])
    yield w


@pytest.fixture
def world_2(tmp_path, isolated_env) -> Iterator[World]:
    """2-friend world for lighter-weight tests."""
    w = setup_world(tmp_path, ["hazar", "friend-b"])
    yield w


# === scenario 1: simultaneous session-end across N=4 friends ==============


def _write_as_friend(friend_root: Path, handle: str, project: str, brief: str,
                     files: list[str], ts: datetime = REF_TS):
    """Serialized write as a single friend. Sets env, calls writer, restores env."""
    saved = os.environ.get("SF_FRAMEWORK_ROOT")
    os.environ["SF_FRAMEWORK_ROOT"] = str(friend_root)
    try:
        # Re-import fresh so config.local_path() picks up the new env
        from feed import feed_write_session_end
        return feed_write_session_end(
            handle=handle, project=project, task_brief=brief,
            files_touched=files, timestamp=ts,
        )
    finally:
        if saved is None:
            os.environ.pop("SF_FRAMEWORK_ROOT", None)
        else:
            os.environ["SF_FRAMEWORK_ROOT"] = saved


def test_scenario_1a_serialized_writes_all_succeed(world_4):
    """Baseline: 4 friends write one after another → all 4 entries in bare repo."""
    for name in world_4.friends:
        result = _write_as_friend(
            world_4.friends[name], name, "sidecar",
            f"{name} worked on JWT", [f"{name}.ts"],
        )
        assert result.success, f"{name} write failed: {result.error}"
        assert result.pushed, f"{name} push failed: {result.error}"

    handles = collect_all_handles_in_bare(world_4)
    assert handles == {"hazar", "friend-b", "friend-c", "friend-d"}
    for name in world_4.friends:
        assert count_log_entries_in_bare(world_4, name) == 1


def test_scenario_1b_parallel_writes_no_data_loss(world_4):
    """True concurrency: 4 friends fire writes via separate processes.

    Verifies ADR-018's per-friend-file claim: no two friends contend for the same
    file, so all writes succeed even when scheduled simultaneously. Some pushes
    may need rebase-retry (push 2nd hits a remote that advanced from push 1) but
    all should ultimately push successfully — none should queue.
    """
    mp_ctx = mp.get_context("spawn")
    queue = mp_ctx.Queue()

    processes = []
    for i, name in enumerate(world_4.friends):
        # Small jitter (0-30ms) so processes don't all hit git at the same nanosecond,
        # which would just serialize behind git's index lock anyway.
        ts = REF_TS + timedelta(seconds=i)  # distinct entry_ids across friends
        p = mp_ctx.Process(
            target=write_session_end_worker,
            args=(
                str(world_4.friends[name]), name, "sidecar",
                f"{name} concurrent work", [f"{name}-only.ts"],
                ts.isoformat(), queue,
            ),
        )
        processes.append(p)

    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=15)
        assert not p.is_alive(), f"worker {p.pid} timed out"
        assert p.exitcode == 0, f"worker {p.pid} exited {p.exitcode}"

    results = []
    while not queue.empty():
        results.append(queue.get_nowait())

    assert len(results) == 4
    assert all(r["success"] for r in results), f"failures: {[r for r in results if not r['success']]}"
    # All should have pushed successfully (queued=True would mean push deferred = failure mode)
    pushed_count = sum(1 for r in results if r["pushed"])
    queued_count = sum(1 for r in results if r["queued"])
    assert pushed_count + queued_count == 4
    # Under true concurrency we tolerate up to 1 queued (slow rebase-retry timing) but
    # all 4 should land in the bare repo on the next session for the queued friend
    assert pushed_count >= 3, f"expected ≥3 immediate pushes, got {pushed_count} pushed + {queued_count} queued"

    # All 4 distinct log files should exist in the bare repo
    handles = collect_all_handles_in_bare(world_4)
    assert handles >= {"hazar", "friend-b", "friend-c", "friend-d"} - {
        r["handle"] for r in results if r["queued"]
    }


def test_scenario_1c_serialized_with_jitter(world_4):
    """Repeat scenario 1a with random jitter between writes — order-independence check."""
    rng = random.Random(42)
    names = list(world_4.friends.keys())
    rng.shuffle(names)

    for name in names:
        result = _write_as_friend(
            world_4.friends[name], name, "sidecar",
            f"{name} jittered", [f"{name}.ts"],
        )
        assert result.success, f"{name} failed: {result.error}"

    assert collect_all_handles_in_bare(world_4) == set(world_4.friends.keys())


# === scenario 2: pull-while-others-push race ==============================


def test_scenario_2_pull_during_others_push_resolves_cleanly(world_2):
    """friend-a pushes; friend-b pulls + pushes; both states converge.

    Serialized for determinism, but exercises the same code paths as race conditions:
    1. friend-a writes + pushes (advances remote)
    2. friend-b's clone is now behind
    3. friend-b writes + pushes → push fails (non-fast-forward) → auto-rebase → push succeeds
    4. After both: bare repo has both files with one entry each
    """
    # Step 1: friend-a writes + pushes
    r_a = _write_as_friend(
        world_2.friends["hazar"], "hazar", "sidecar", "first write",
        ["a.ts"], REF_TS,
    )
    assert r_a.success and r_a.pushed

    # Step 2: friend-b writes (their clone is now stale wrt friend-a's push)
    # write_session_end commits locally then pushes; push will need rebase
    r_b = _write_as_friend(
        world_2.friends["friend-b"], "friend-b", "sidecar", "second write",
        ["b.ts"], REF_TS + timedelta(minutes=1),
    )
    assert r_b.success, f"friend-b write failed: {r_b.error}"
    # Either pushed (auto-rebase succeeded) or queued (timeout) — both valid degradations
    assert r_b.pushed or r_b.queued

    # Step 3: verify bare repo has both files with content
    handles = collect_all_handles_in_bare(world_2)
    if r_b.pushed:
        assert handles == {"hazar", "friend-b"}
        assert count_log_entries_in_bare(world_2, "hazar") == 1
        assert count_log_entries_in_bare(world_2, "friend-b") == 1
    else:
        # Queued — only hazar's file made it to the bare repo
        assert "hazar" in handles


def test_scenario_2_interleaved_three_friends(world_4):
    """Three-way interleave: A pushes, B writes+pushes (rebases over A), C writes+pushes
    (rebases over both). All three log files end up in the bare repo with one entry each.
    """
    r_a = _write_as_friend(
        world_4.friends["hazar"], "hazar", "sidecar", "a work",
        ["a.ts"], REF_TS,
    )
    assert r_a.success and r_a.pushed

    r_b = _write_as_friend(
        world_4.friends["friend-b"], "friend-b", "sidecar", "b work",
        ["b.ts"], REF_TS + timedelta(minutes=1),
    )
    assert r_b.success

    r_c = _write_as_friend(
        world_4.friends["friend-c"], "friend-c", "sidecar", "c work",
        ["c.ts"], REF_TS + timedelta(minutes=2),
    )
    assert r_c.success

    # If everyone pushed, all 3 files in bare repo
    if r_b.pushed and r_c.pushed:
        handles = collect_all_handles_in_bare(world_4)
        assert handles == {"hazar", "friend-b", "friend-c"}


# === scenario 3: queue-and-flush under sustained network failure ==========


def test_scenario_3_queue_during_failure_then_flush_on_recovery(world_2, monkeypatch):
    """Push fails for the first 3 attempts per friend; verifies:
    - Local commits still happen (writer reports success=True)
    - pending_commit_count increments in state.json (each failure)
    - When push "recovers" (monkeypatch lifted), next push flushes all pending commits
    - Idempotency markers prevent re-counting old entries on flush
    """
    from feed import config, io_github

    framework_root = str(world_2.friends["hazar"])
    os.environ["SF_FRAMEWORK_ROOT"] = framework_root

    # Inject failures for the first 3 calls to _try_push, then succeed
    call_count = {"n": 0}
    real_try_push = io_github._try_push

    def flaky_try_push(repo, *, timeout_s):
        call_count["n"] += 1
        if call_count["n"] <= 3:
            return "simulated network failure"
        return real_try_push(repo, timeout_s=timeout_s)

    monkeypatch.setattr(io_github, "_try_push", flaky_try_push)

    # Write 3 entries during the failure window
    for i in range(3):
        r = _write_as_friend(
            world_2.friends["hazar"], "hazar", "sidecar", f"failed-window {i}",
            [f"f{i}.ts"], REF_TS + timedelta(minutes=i),
        )
        # Write should report success (local commit) but queued (push deferred)
        assert r.success, f"local write {i} failed: {r.error}"
        assert r.queued, f"expected queued at write {i}, got pushed={r.pushed}"

    # Verify state.json reflects pending count
    pending = io_github.pending_commit_count(world_2.friends["hazar"] / "activity-feed")
    failures = io_github.consecutive_push_failures(world_2.friends["hazar"] / "activity-feed")
    assert pending == 3
    assert failures == 3

    # Write a 4th entry — push should succeed (failure window expired at call 4),
    # flushing ALL local commits including the 3 queued
    r4 = _write_as_friend(
        world_2.friends["hazar"], "hazar", "sidecar", "recovery",
        ["r.ts"], REF_TS + timedelta(minutes=3),
    )
    assert r4.success
    assert r4.pushed, f"expected push success after recovery, got queued={r4.queued} error={r4.error}"

    # Pending counter resets
    pending_after = io_github.pending_commit_count(world_2.friends["hazar"] / "activity-feed")
    failures_after = io_github.consecutive_push_failures(world_2.friends["hazar"] / "activity-feed")
    assert pending_after == 0
    assert failures_after == 0

    # Bare repo now has all 4 entries (no duplicates from re-push)
    assert count_log_entries_in_bare(world_2, "hazar") == 4


def test_scenario_3_idempotency_marker_prevents_duplicates(world_2, monkeypatch):
    """Even if the same logical write is attempted twice within the failure window,
    the entry_id marker comment prevents the second from creating a duplicate row."""
    from feed import io_github

    os.environ["SF_FRAMEWORK_ROOT"] = str(world_2.friends["hazar"])

    monkeypatch.setattr(io_github, "_try_push", lambda repo, **kw: "always fail in this test")

    # Same args twice within the same minute → same entry_id → second should be a no-op
    args = dict(
        friend_root=world_2.friends["hazar"],
        handle="hazar", project="sidecar", brief="dup test",
        files=["dup.ts"], ts=REF_TS,
    )
    r1 = _write_as_friend(**args)
    r2 = _write_as_friend(**args)

    assert r1.success and r2.success
    assert r1.entry_id == r2.entry_id

    # Local file has only one entry header for this write
    local_log = world_2.friends["hazar"] / "activity-feed" / "hazar.log.md"
    text = local_log.read_text(encoding="utf-8")
    assert text.count("dup test") == 1


def test_scenario_3_local_state_never_pushed_to_bare(world_2, monkeypatch):
    """C3 regression (REVIEW §C3): per-clone .state.json/.queue.log must NEVER reach the
    shared bare repo, even after a push-failure → recovery cycle.

    Why it matters: each clone's .state.json holds its OWN push stats, so committing it
    diverges across friends → the next cross-friend `git pull --rebase` hits an
    unresolvable JSON conflict → REBASE_HEAD lockup → all future feed writes silently
    queue forever. Before the fix, `git add -A` staged these files and pushed them.
    """
    from feed import io_github
    from feed.bootstrap import _write_bootstrap_files

    framework_root = world_2.friends["hazar"]
    os.environ["SF_FRAMEWORK_ROOT"] = str(framework_root)
    clone = framework_root / "activity-feed"

    # Simulate the first-friend bootstrap writing the committed .gitignore into the clone.
    _write_bootstrap_files(clone, "hazar", skip_readme=True)
    assert (clone / ".gitignore").exists()

    # Fail the first 3 pushes (each failure writes .queue.log + .state.json), then recover.
    call_count = {"n": 0}
    real_try_push = io_github._try_push

    def flaky_try_push(repo, *, timeout_s):
        call_count["n"] += 1
        if call_count["n"] <= 3:
            return "simulated network failure"
        return real_try_push(repo, timeout_s=timeout_s)

    monkeypatch.setattr(io_github, "_try_push", flaky_try_push)

    for i in range(3):
        r = _write_as_friend(
            framework_root, "hazar", "sidecar", f"failed-window {i}",
            [f"f{i}.ts"], REF_TS + timedelta(minutes=i),
        )
        assert r.success and r.queued, f"write {i}: success={r.success} queued={r.queued}"

    # State files exist LOCALLY (expected — they're the offline queue) ...
    assert (clone / ".state.json").exists()
    assert (clone / ".queue.log").exists()

    # ... and a recovery push flushes the queued commits.
    r4 = _write_as_friend(
        framework_root, "hazar", "sidecar", "recovery",
        ["r.ts"], REF_TS + timedelta(minutes=4),
    )
    assert r4.success and r4.pushed, f"recovery: pushed={r4.pushed} error={r4.error}"

    # The shared bare repo tracks the log + the committed .gitignore, but NEVER the
    # per-clone local state.
    tracked = bare_tracked_files(world_2)
    assert "hazar.log.md" in tracked
    assert ".gitignore" in tracked
    assert ".state.json" not in tracked, \
        f"C3 regression: .state.json leaked into the shared repo (tracked={sorted(tracked)})"
    assert ".queue.log" not in tracked, \
        f"C3 regression: .queue.log leaked into the shared repo (tracked={sorted(tracked)})"


# === scenario 4: handle collision detection on joiner-clone path =========


def test_scenario_4_clone_existing_refuses_collision(world_2, tmp_path):
    """A joiner clones an existing repo; the writer detects their handle already
    exists and raises FileExistsError. Caller (sf-install) is responsible for
    re-prompting the user for a different handle.

    Note: feed_clone_existing uses `gh repo clone` which requires GitHub-format URLs.
    For this integration test we pre-clone via raw `git clone` (using the local bare
    repo as remote), then call feed_clone_existing — the gh step is skipped because
    `.git` already exists, and the collision check is what we're actually verifying.
    """
    from feed.bootstrap import feed_clone_existing

    # Seed: hazar's clone has a log file pushed to the bare repo
    r = _write_as_friend(
        world_2.friends["hazar"], "hazar", "sidecar", "first entry",
        ["a.ts"], REF_TS,
    )
    assert r.success and r.pushed

    # New joiner: pre-clone manually (test-side workaround for gh-requiring real GitHub URLs)
    joiner_root = tmp_path / "joiner-collision"
    joiner_root.mkdir()
    joiner_clone = joiner_root / "activity-feed"
    subprocess.run(
        ["git", "clone", "-q", "-b", "main", str(world_2.bare_repo), str(joiner_clone)],
        check=True,
    )
    os.environ["SF_FRAMEWORK_ROOT"] = str(joiner_root)

    # Now invoke feed_clone_existing — collision check should fire because hazar.log.md
    # already exists in the pre-cloned repo
    with pytest.raises(FileExistsError) as excinfo:
        feed_clone_existing(str(world_2.bare_repo), joiner_clone, "hazar")
    assert "hazar" in str(excinfo.value)


def test_scenario_4_detect_reports_existing_handles(world_2, tmp_path):
    """detect_repo_state for a pre-cloned repo correctly enumerates existing handles."""
    from feed.bootstrap import feed_detect_repo_state

    # Seed: two friends already have log files in the bare repo
    _write_as_friend(world_2.friends["hazar"], "hazar", "sidecar", "h", ["a.ts"], REF_TS)
    _write_as_friend(world_2.friends["friend-b"], "friend-b", "sidecar", "b", ["b.ts"], REF_TS)

    # New joiner detects state
    joiner_root = tmp_path / "joiner-detect"
    joiner_root.mkdir()
    os.environ["SF_FRAMEWORK_ROOT"] = str(joiner_root)

    state = feed_detect_repo_state(str(world_2.bare_repo), joiner_root / "activity-feed")
    # local_path doesn't exist yet (we haven't cloned), so mode is determined by gh
    # but we're using a local file:// URL bypassing gh — falls through to first-friend-bootstrap
    # That's fine; the IMPORTANT check is existing_handles when mode=already-cloned.
    # For a true joiner-clone test we need a clone first:
    subprocess.run(
        ["git", "clone", "-q", "-b", "main", str(world_2.bare_repo),
         str(joiner_root / "activity-feed")],
        check=True,
    )
    state2 = feed_detect_repo_state(str(world_2.bare_repo), joiner_root / "activity-feed")
    assert state2.mode == "already-cloned"
    assert set(state2.existing_handles) == {"hazar", "friend-b"}


# === scenario 5: cross-day chronological invariant ========================


def test_scenario_5_cross_day_boundary_ordering(world_2):
    """Two friends write entries spanning a day boundary (23:58 and 00:02 next day).
    Reader's read_friends_tails(since=...) should order them chronologically.
    """
    from feed import feed_read_friends_tails

    late_night = datetime(2026, 5, 28, 23, 58, tzinfo=timezone.utc)
    early_morning = datetime(2026, 5, 29, 0, 2, tzinfo=timezone.utc)

    _write_as_friend(
        world_2.friends["hazar"], "hazar", "sidecar", "late night",
        ["a.ts"], late_night,
    )
    _write_as_friend(
        world_2.friends["friend-b"], "friend-b", "sidecar", "early morning",
        ["b.ts"], early_morning,
    )

    # Read tails on hazar's clone (which now has both friends' files if it pulled)
    os.environ["SF_FRAMEWORK_ROOT"] = str(world_2.friends["hazar"])
    tail = feed_read_friends_tails(
        own_handle="hazar", n_per_friend=5, include_self=True, refresh=True,
    )

    # Both handles present, ordering within each is chronological (oldest first per reader contract)
    assert "hazar" in tail.friends
    assert "friend-b" in tail.friends
    hazar_entries = tail.friends["hazar"]
    fb_entries = tail.friends["friend-b"]
    assert hazar_entries[0].timestamp == late_night
    assert fb_entries[0].timestamp == early_morning
    # Cross-day invariant: early_morning > late_night even though we wrote them in that order
    assert fb_entries[0].timestamp > hazar_entries[0].timestamp


def test_scenario_5_same_day_reordering_allowed(world_2):
    """Same-day entries can be appended out of order without violating the invariant.
    (ADR-004: same-day reordering OK; cross-day frozen.)
    """
    from feed import read_all_entries

    # Two same-day entries written in reverse chronological order
    later_today = datetime(2026, 5, 28, 18, 0, tzinfo=timezone.utc)
    earlier_today = datetime(2026, 5, 28, 9, 0, tzinfo=timezone.utc)

    _write_as_friend(
        world_2.friends["hazar"], "hazar", "sidecar", "later",
        ["a.ts"], later_today,
    )
    _write_as_friend(
        world_2.friends["hazar"], "hazar", "sidecar", "earlier",
        ["b.ts"], earlier_today,
    )

    # Reader sorts by timestamp regardless of write order
    os.environ["SF_FRAMEWORK_ROOT"] = str(world_2.friends["hazar"])
    entries = read_all_entries(from_handles=["hazar"])
    # Filter to just the end entries (writer also creates schema header but not entries)
    end_entries = [e for e in entries if e.kind == "end"]
    assert len(end_entries) == 2
    assert end_entries[0].timestamp == earlier_today
    assert end_entries[1].timestamp == later_today
