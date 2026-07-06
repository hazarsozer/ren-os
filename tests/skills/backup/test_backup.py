"""
Tests for skills.backup.lib — carried from donor `skills/backup/lib/tests/
test_backup.py` (Task 7.3), condensed to cover every public function's core
behavior rather than porting all 677 lines verbatim. Remote-name expectations
updated to `"backup"` (this module's delta from donor's `"origin"` default —
see the module docstring for why).

Run with: uv run pytest tests/skills/backup/test_backup.py -v
"""

from __future__ import annotations

import importlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

backup_lib = importlib.import_module("skills.backup.lib")


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


def _commit_something(path: Path) -> None:
    (path / "file.md").write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


@pytest.fixture
def repo_with_local_remote(tmp_path: Path):
    wiki = tmp_path / "wiki"
    remote = tmp_path / "remote.git"
    _init_repo(wiki)
    _commit_something(wiki)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", backup_lib.BACKUP_REMOTE_NAME, str(remote)],
        cwd=wiki, check=True, capture_output=True,
    )
    return wiki, remote


# ------------------------------------------------------------ looks_like_git_url


@pytest.mark.parametrize(
    "url",
    ["https://github.com/user/repo.git", "git@github.com:user/repo.git", "ssh://git@host/path.git"],
)
def test_looks_like_git_url_accepts_valid(url):
    assert backup_lib.looks_like_git_url(url) is True


@pytest.mark.parametrize("url", ["", "not a url", "/tmp/local/path"])
def test_looks_like_git_url_rejects_invalid(url):
    assert backup_lib.looks_like_git_url(url) is False


def test_looks_like_git_url_non_string_returns_false():
    assert backup_lib.looks_like_git_url(None) is False


# ------------------------------------------------------------- tarball naming


def test_tarball_filename_canonical_format():
    now = datetime(2026, 5, 28, 20, 30, 12, tzinfo=timezone.utc)
    assert backup_lib.tarball_filename_for(now) == "wiki-2026-05-28-203012.tar.gz"


# --------------------------------------------------------- list/prune tarballs


def test_list_existing_tarballs_empty_and_missing_dir(tmp_path):
    assert backup_lib.list_existing_tarballs(tmp_path / "nope") == []
    tmp_path.mkdir(exist_ok=True)
    assert backup_lib.list_existing_tarballs(tmp_path) == []


def test_list_existing_tarballs_ignores_non_matching(tmp_path):
    (tmp_path / "wiki-2026-01-01-000000.tar.gz").write_bytes(b"x")
    (tmp_path / "not-a-tarball.txt").write_bytes(b"y")
    result = backup_lib.list_existing_tarballs(tmp_path)
    assert len(result) == 1


def test_prune_old_tarballs_no_op_under_cap(tmp_path):
    (tmp_path / "wiki-2026-01-01-000000.tar.gz").write_bytes(b"x")
    assert backup_lib.prune_old_tarballs(tmp_path, keep=5) == 0


def test_prune_old_tarballs_over_cap_prunes_oldest(tmp_path):
    for i in range(5):
        p = tmp_path / f"wiki-2026-01-0{i+1}-000000.tar.gz"
        p.write_bytes(b"x")
        time.sleep(0.01)
    deleted = backup_lib.prune_old_tarballs(tmp_path, keep=2)
    assert deleted == 3
    assert len(backup_lib.list_existing_tarballs(tmp_path)) == 2


def test_prune_old_tarballs_negative_keep_raises(tmp_path):
    with pytest.raises(ValueError):
        backup_lib.prune_old_tarballs(tmp_path, keep=-1)


# ---------------------------------------------------------------- git helpers


def test_is_git_repo(tmp_path):
    assert backup_lib.is_git_repo(tmp_path) is False
    _init_repo(tmp_path)
    assert backup_lib.is_git_repo(tmp_path) is True


def test_get_remote_url_none_then_configured(tmp_path):
    _init_repo(tmp_path)
    assert backup_lib.get_remote_url(tmp_path) is None
    subprocess.run(
        ["git", "remote", "add", backup_lib.BACKUP_REMOTE_NAME, "https://example.com/x.git"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    assert backup_lib.get_remote_url(tmp_path) == "https://example.com/x.git"


def test_get_head_info_no_commits_then_with_commit(tmp_path):
    _init_repo(tmp_path)
    assert backup_lib.get_head_info(tmp_path) == (None, None)
    _commit_something(tmp_path)
    sha, date = backup_lib.get_head_info(tmp_path)
    assert sha is not None and date is not None


# ---------------------------------------------------------------- setup_remote


def test_setup_remote_adds_new(tmp_path):
    _init_repo(tmp_path)
    result = backup_lib.setup_remote("https://example.com/x.git", tmp_path)
    assert result.success is True
    assert backup_lib.get_remote_url(tmp_path) == "https://example.com/x.git"


def test_setup_remote_rejects_bad_url(tmp_path):
    _init_repo(tmp_path)
    result = backup_lib.setup_remote("not a url", tmp_path)
    assert result.success is False
    assert result.error == "invalid-url-shape"


def test_setup_remote_refuses_non_git_dir(tmp_path):
    result = backup_lib.setup_remote("https://example.com/x.git", tmp_path)
    assert result.success is False
    assert result.error == "not-a-git-repo"


# --------------------------------------------------------------------- status


def test_status_non_git_dir(tmp_path):
    result = backup_lib.status(tmp_path, tmp_path / "backups")
    assert result.is_git_repo is False


def test_status_git_repo_with_commit_and_remote(repo_with_local_remote):
    wiki, remote = repo_with_local_remote
    result = backup_lib.status(wiki, wiki.parent / "backups")
    assert result.is_git_repo is True
    assert result.remote_url == str(remote)
    assert result.last_commit_sha is not None


# ----------------------------------------------------- has/commit uncommitted


def test_has_uncommitted_changes(tmp_path):
    _init_repo(tmp_path)
    assert backup_lib.has_uncommitted_changes(tmp_path) is False
    (tmp_path / "new.md").write_text("x", encoding="utf-8")
    assert backup_lib.has_uncommitted_changes(tmp_path) is True


def test_commit_pending_changes_creates_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "new.md").write_text("x", encoding="utf-8")
    assert backup_lib.commit_pending_changes(tmp_path) is True
    assert backup_lib.has_uncommitted_changes(tmp_path) is False


def test_commit_pending_changes_clean_tree_is_idempotent(tmp_path):
    _init_repo(tmp_path)
    _commit_something(tmp_path)
    assert backup_lib.commit_pending_changes(tmp_path) is True


# ----------------------------------------------------------------- push_to_remote


def test_push_to_remote_no_remote_configured(tmp_path):
    _init_repo(tmp_path)
    _commit_something(tmp_path)
    pushed, category, _ = backup_lib.push_to_remote(tmp_path)
    assert not pushed
    assert category == "no-remote"


def test_push_to_remote_no_commits(tmp_path):
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", backup_lib.BACKUP_REMOTE_NAME, "https://example.com/x.git"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    pushed, category, _ = backup_lib.push_to_remote(tmp_path)
    assert not pushed
    assert category == "no-commits"


def test_push_to_remote_success(repo_with_local_remote):
    wiki, remote = repo_with_local_remote
    pushed, category, _ = backup_lib.push_to_remote(wiki)
    assert pushed is True
    assert category == ""


# ------------------------------------------------------------------ create_tarball


def test_create_tarball_creates_canonical_name(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "page.md").write_text("x", encoding="utf-8")
    backups = tmp_path / "backups"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    success, target, error = backup_lib.create_tarball(wiki, backups, now=now)
    assert success is True
    assert target.name == "wiki-2026-01-01-000000.tar.gz"


def test_create_tarball_missing_wiki_root_fails_clean(tmp_path):
    success, target, error = backup_lib.create_tarball(tmp_path / "nope", tmp_path / "backups")
    assert success is False
    assert target is None


# ------------------------------------------------------------- backup orchestrator


def test_backup_non_git_dir_refused(tmp_path):
    result = backup_lib.backup(tmp_path, tmp_path / "backups")
    assert result.success is False
    assert result.error == "not-a-git-repo"


def test_backup_no_remote_falls_back_to_tarball(tmp_path):
    wiki = tmp_path / "wiki"
    _init_repo(wiki)
    _commit_something(wiki)
    result = backup_lib.backup(wiki, tmp_path / "backups")
    assert result.success is True
    assert result.method == "tarball"


def test_backup_push_succeeds_no_tarball(repo_with_local_remote):
    wiki, remote = repo_with_local_remote
    result = backup_lib.backup(wiki, wiki.parent / "backups")
    assert result.success is True
    assert result.method == "git-push"


def test_backup_force_tarball_skips_push(repo_with_local_remote):
    wiki, remote = repo_with_local_remote
    result = backup_lib.backup(wiki, wiki.parent / "backups", force_tarball=True)
    assert result.method == "tarball"


def test_backup_tarball_retention_enforced(tmp_path):
    wiki = tmp_path / "wiki"
    _init_repo(wiki)
    _commit_something(wiki)
    backups = tmp_path / "backups"
    for _ in range(3):
        backup_lib.backup(wiki, backups, keep=2)
        time.sleep(0.01)
        (wiki / "change.md").write_text(str(time.time()), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=wiki, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=wiki, check=True, capture_output=True)
    assert len(backup_lib.list_existing_tarballs(backups)) <= 2


# ------------------------------------------------------------------------ backup_configured


def test_backup_configured_true_when_remote_set(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    wiki = tmp_path / "wiki"
    _init_repo(wiki)
    _commit_something(wiki)
    subprocess.run(
        ["git", "remote", "add", backup_lib.BACKUP_REMOTE_NAME, "https://example.com/x.git"],
        cwd=wiki, check=True, capture_output=True,
    )
    assert backup_lib.backup_configured(wiki) is True


def test_backup_configured_true_with_recent_tarball_no_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    wiki = tmp_path / "wiki"
    _init_repo(wiki)

    backups_dir = tmp_path / "plugin-data" / "backups"
    backups_dir.mkdir(parents=True)
    (backups_dir / "wiki-2026-01-01-000000.tar.gz").write_bytes(b"x")

    assert backup_lib.backup_configured(wiki) is True


def test_backup_configured_false_with_nothing_set_up(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    wiki = tmp_path / "wiki"
    _init_repo(wiki)
    assert backup_lib.backup_configured(wiki) is False


# ------------------------------------------------------------------- dataclasses


def test_backup_result_is_frozen():
    result = backup_lib.BackupResult(success=True, method="git-push", path_or_remote="x", message="m")
    with pytest.raises(Exception):
        result.success = False


def test_status_result_is_frozen():
    result = backup_lib.StatusResult(
        wiki_path="x", is_git_repo=True, remote_url=None, last_commit_sha=None,
        last_commit_date=None, tarball_count=0, oldest_tarball_date=None, newest_tarball_date=None,
    )
    with pytest.raises(Exception):
        result.is_git_repo = False
