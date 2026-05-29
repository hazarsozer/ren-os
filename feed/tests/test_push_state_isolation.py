"""
C3 unit guard (REVIEW-v1.0-preship §C3): io_github._stage_and_commit must NEVER commit
per-clone local-only state (.queue.log / .state.json / .queue.log.lock) to the shared
repo — even when the clone has NO .gitignore.

The committed .gitignore (written at bootstrap, inherited by joiners) is the primary
mechanism; this test isolates the defense-in-depth backstop — the `git reset` of
config.FEED_LOCAL_ONLY_FILES after `git add -A`. Deleting that reset makes this test
fail (the state files get committed), so it is a true regression guard.

Run with: python3 -m pytest feed/tests/test_push_state_isolation.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from feed import config, io_github


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)


def _tracked(repo: Path) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    return {line for line in out.splitlines() if line}


def test_stage_and_commit_excludes_state_files_without_gitignore(tmp_path):
    """Backstop in isolation: a clone missing its .gitignore must still never commit
    the per-clone local-only state files."""
    repo = tmp_path / "activity-feed"
    repo.mkdir()
    _init_repo(repo)

    # Deliberately NO .gitignore — exercise the `git reset` backstop alone.
    (repo / "hazar.log.md").write_text("---\nhandle: hazar\n---\n", encoding="utf-8")
    for name in config.FEED_LOCAL_ONLY_FILES:
        (repo / name).write_text("local-only\n", encoding="utf-8")

    err = io_github._stage_and_commit(repo, "C3 backstop test")
    assert err is None, f"_stage_and_commit reported: {err}"

    tracked = _tracked(repo)
    assert "hazar.log.md" in tracked, "the real log file must be committed"
    for name in config.FEED_LOCAL_ONLY_FILES:
        assert name not in tracked, f"{name} was committed despite the C3 backstop"


def test_stage_and_commit_commits_real_content(tmp_path):
    """Sanity: the backstop doesn't over-reach — normal tracked files still commit."""
    repo = tmp_path / "activity-feed"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".gitignore").write_text("\n".join(config.FEED_LOCAL_ONLY_FILES) + "\n", encoding="utf-8")
    (repo / "hazar.log.md").write_text("entry\n", encoding="utf-8")
    (repo / "identities").mkdir()
    (repo / "identities" / "hazar.md").write_text("id\n", encoding="utf-8")

    err = io_github._stage_and_commit(repo, "real content")
    assert err is None, f"_stage_and_commit reported: {err}"

    tracked = _tracked(repo)
    assert {".gitignore", "hazar.log.md", "identities/hazar.md"} <= tracked
