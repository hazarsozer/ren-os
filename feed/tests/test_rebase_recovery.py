"""
M5 (REVIEW-v1.0-preship): stalled-rebase recovery in feed.io_github._try_rebase.

A clone must never be left stuck in REBASE state — that silently swallows all future
feed writes until a manual `git rebase --abort` (documented nowhere). C3 PREVENTS the
corruption that causes this on fresh repos; M5 RECOVERS an already-stuck clone.

Uses real on-disk git (no mocks), like the other feed/tests/ git-touching units.

Run with: python3 -m pytest feed/tests/test_rebase_recovery.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from feed import io_github


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=check,
    )


def _bare_and_two_clones(tmp_path: Path) -> tuple[Path, Path, Path]:
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(bare)], check=True)

    a = tmp_path / "a"
    subprocess.run(["git", "clone", "-q", str(bare), str(a)], check=True)
    _git(a, "config", "user.email", "a@e.com")
    _git(a, "config", "user.name", "a")
    (a / "shared.txt").write_text("base\n")
    _git(a, "add", "-A")
    _git(a, "commit", "-q", "-m", "seed")
    _git(a, "push", "-q", "origin", "main")

    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(bare), str(b)], check=True)
    _git(b, "config", "user.email", "b@e.com")
    _git(b, "config", "user.name", "b")
    return bare, a, b


def _make_conflict(a: Path, b: Path) -> None:
    """`a` advances the remote; `b` makes a conflicting local commit on the same line."""
    (a / "shared.txt").write_text("from-a\n")
    _git(a, "add", "-A")
    _git(a, "commit", "-q", "-m", "a change")
    _git(a, "push", "-q", "origin", "main")

    (b / "shared.txt").write_text("from-b\n")
    _git(b, "add", "-A")
    _git(b, "commit", "-q", "-m", "b change")


def test_rebase_in_progress_detection_and_abort(tmp_path):
    _bare, a, b = _bare_and_two_clones(tmp_path)
    _make_conflict(a, b)
    assert not io_github._rebase_in_progress(b)

    # A real conflicting pull leaves b mid-rebase.
    _git(b, "pull", "--rebase", check=False)
    assert io_github._rebase_in_progress(b)

    io_github._abort_rebase(b, timeout_s=10)
    assert not io_github._rebase_in_progress(b)


def test_try_rebase_on_conflict_leaves_clone_unstuck(tmp_path):
    _bare, a, b = _bare_and_two_clones(tmp_path)
    _make_conflict(a, b)

    err = io_github._try_rebase(b, timeout_s=10)
    assert err is not None  # conflict surfaced → caller queues
    assert not io_github._rebase_in_progress(b)  # but the clone is NOT left stuck


def test_try_rebase_clears_preexisting_stuck_rebase(tmp_path):
    _bare, a, b = _bare_and_two_clones(tmp_path)
    _make_conflict(a, b)

    # Simulate a clone left stuck by a prior (pre-M5) run.
    _git(b, "pull", "--rebase", check=False)
    assert io_github._rebase_in_progress(b)

    # _try_rebase must clear the stale state (start-abort) and not leave it stuck.
    io_github._try_rebase(b, timeout_s=10)
    assert not io_github._rebase_in_progress(b)
