"""
Test helpers for the multi-friend concurrency dogfood (task #47).

Lives in a top-level module so multiprocessing.Process can pickle worker functions
(local closures inside test files don't pickle on `spawn` start method).

The "world" abstraction sets up a realistic multi-friend topology:

    /tmp/.../activity-feed.git    ← shared "GitHub" bare repo
    /tmp/.../hazar/activity-feed  ← Hazar's clone (his framework_root = /tmp/.../hazar)
    /tmp/.../friend-b/activity-feed
    /tmp/.../friend-c/activity-feed
    /tmp/.../friend-d/activity-feed

Each friend's clone is independent; setting SF_FRAMEWORK_ROOT=/tmp/.../<friend>
makes `feed.config.local_path()` resolve to that friend's clone.

Workers below run in subprocesses (true parallelism) so each can set its own env
without polluting siblings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# Ensure repo root is on sys.path for worker subprocesses spawned via multiprocessing
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class World:
    """A multi-friend git topology rooted at a single tmpdir."""
    tmp_root: Path
    bare_repo: Path
    friends: dict[str, Path]  # name → that friend's framework_root


def setup_world(tmp_root: Path, friend_names: list[str]) -> World:
    """Initialize a bare git repo + N working clones, one per friend.

    The bare repo gets a single seed commit so subsequent pushes can fast-forward
    cleanly without needing --set-upstream tricks.

    Each friend's clone is configured with a unique user.email/name so commits are
    distinguishable in the git log.
    """
    bare = tmp_root / "activity-feed.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(bare)], check=True)

    # Seed the bare repo with an initial commit so push has a base to fast-forward against
    seed = tmp_root / "_seed"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(bare), str(seed)], check=False)
    # On older git versions, "-b main" against an empty bare repo may fail; fall back to init
    if not (seed / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        subprocess.run(
            ["git", "-C", str(seed), "remote", "add", "origin", str(bare)],
            check=True,
        )
    subprocess.run(["git", "-C", str(seed), "config", "user.email", "seed@e.com"], check=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "seed"], check=True)
    (seed / "README.md").write_text("Activity Feed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "commit", "-q", "-m", "seed"], check=True
    )
    subprocess.run(
        ["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True
    )

    friends: dict[str, Path] = {}
    for name in friend_names:
        root = tmp_root / name
        root.mkdir(parents=True, exist_ok=True)
        clone = root / "activity-feed"
        subprocess.run(
            ["git", "clone", "-q", "-b", "main", str(bare), str(clone)], check=True
        )
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.email", f"{name}@e.com"], check=True
        )
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.name", name], check=True
        )
        friends[name] = root

    return World(tmp_root=tmp_root, bare_repo=bare, friends=friends)


def count_log_entries_in_bare(world: World, handle: str) -> int:
    """Count `## [<ts>] <kind> | <handle> |` entries in the bare repo's <handle>.log.md.

    We do this by cloning the bare into a throwaway dir and reading the file directly —
    git's text-mode read of a bare repo file requires checkout, easier to clone.
    """
    inspect = world.tmp_root / f"_inspect-{handle}"
    if inspect.exists():
        subprocess.run(["rm", "-rf", str(inspect)], check=True)
    subprocess.run(
        ["git", "clone", "-q", "-b", "main", str(world.bare_repo), str(inspect)],
        check=True,
    )
    log_file = inspect / f"{handle}.log.md"
    if not log_file.exists():
        return 0
    text = log_file.read_text(encoding="utf-8")
    # Count entry headers
    return sum(1 for line in text.splitlines() if line.startswith("## ["))


def collect_all_handles_in_bare(world: World) -> set[str]:
    """Return the set of distinct handles with log files in the bare repo."""
    inspect = world.tmp_root / "_inspect-all"
    if inspect.exists():
        subprocess.run(["rm", "-rf", str(inspect)], check=True)
    subprocess.run(
        ["git", "clone", "-q", "-b", "main", str(world.bare_repo), str(inspect)],
        check=True,
    )
    return {
        p.stem.removesuffix(".log") for p in inspect.glob("*.log.md")
    }


# === multiprocessing workers ==============================================


def write_session_end_worker(
    framework_root: str,
    handle: str,
    project: str,
    brief: str,
    files: list[str],
    timestamp_iso: Optional[str],
    return_queue,
) -> None:
    """Worker for multiprocessing.Process — perform one session-end write.

    `return_queue` is a multiprocessing.Queue the parent reads from. Each worker
    pushes its FeedWriteResult (as a dict, since the dataclass isn't trivially
    picklable across processes — though it should be; we serialize to dict for
    safety).

    Crucially: this function sets SF_FRAMEWORK_ROOT in the CHILD process's env, so
    `feed.config.local_path()` resolves to that friend's clone. Parent process env
    is unaffected.
    """
    os.environ["SF_FRAMEWORK_ROOT"] = framework_root
    # Re-add sys.path inside the child (spawn start method requires this)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from feed import feed_write_session_end  # imported per-child for env clarity

    ts = datetime.fromisoformat(timestamp_iso) if timestamp_iso else None
    result = feed_write_session_end(
        handle=handle, project=project, task_brief=brief,
        files_touched=files, timestamp=ts,
    )
    return_queue.put({
        "handle": handle,
        "success": result.success,
        "pushed": result.pushed,
        "queued": result.queued,
        "error": result.error,
        "entry_id": result.entry_id,
        "violation": result.violation,
    })
