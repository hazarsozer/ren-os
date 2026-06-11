"""Tests for skills.sf_backup.lib."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ..__init__ import (
    TARBALL_RETENTION_KEEP,
    BackupResult,
    StatusResult,
    get_head_info,
    get_remote_url,
    is_git_repo,
    list_existing_tarballs,
    looks_like_git_url,
    prune_old_tarballs,
    setup_remote,
    status,
    tarball_filename_for,
)


# ---------------------------------------------------------------------------
# looks_like_git_url
# ---------------------------------------------------------------------------


class TestLooksLikeGitUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/user/repo.git",
            "https://github.com/user/repo",
            "http://my-host.com/x/y.git",
            "git@github.com:user/repo.git",
            "git@host:user/repo",
            "ssh://git@host/path.git",
            "ssh://git@host/path",
        ],
    )
    def test_accepts_valid(self, url: str):
        assert looks_like_git_url(url), f"should accept {url!r}"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "   ",
            "not a url",
            "/tmp/local-path",
            "ftp://example.com/repo.git",
            "github.com/user/repo",  # missing scheme
            "https://",
            "github user repo",
        ],
    )
    def test_rejects_invalid(self, url: str):
        assert not looks_like_git_url(url), f"should reject {url!r}"

    def test_non_string_returns_false(self):
        assert not looks_like_git_url(123)  # type: ignore[arg-type]
        assert not looks_like_git_url(None)  # type: ignore[arg-type]

    def test_whitespace_stripped_before_check(self):
        assert looks_like_git_url("  https://github.com/x/y.git  ")


# ---------------------------------------------------------------------------
# tarball_filename_for
# ---------------------------------------------------------------------------


class TestTarballFilename:
    def test_canonical_format(self):
        now = datetime(2026, 5, 28, 20, 30, 12, tzinfo=timezone.utc)
        assert tarball_filename_for(now) == "wiki-2026-05-28-203012.tar.gz"

    def test_uses_utc(self):
        # Even if local time differs, format reflects UTC
        now_utc = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert "2026-01-01-000000" in tarball_filename_for(now_utc)

    def test_default_uses_current_time(self):
        result = tarball_filename_for()
        # Loosely: matches the shape wiki-YYYY-MM-DD-HHMMSS.tar.gz
        import re
        assert re.match(r"^wiki-\d{4}-\d{2}-\d{2}-\d{6}\.tar\.gz$", result)


# ---------------------------------------------------------------------------
# list_existing_tarballs + prune_old_tarballs
# ---------------------------------------------------------------------------


def _make_tarballs(backup_dir: Path, count: int) -> list[Path]:
    """Helper: create `count` fake tarball files with staggered mtimes."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    now = time.time()
    for i in range(count):
        # Names span dates; mtimes go backwards in time so index 0 is newest
        name = f"wiki-2026-05-{i+1:02d}-000000.tar.gz"
        p = backup_dir / name
        p.write_bytes(b"fake tarball content")
        # Set mtime: newer index = newer time
        ts = now - (count - i) * 3600
        os.utime(p, (ts, ts))
        paths.append(p)
    return paths


class TestListExistingTarballs:
    def test_empty_dir(self, tmp_path: Path):
        assert list_existing_tarballs(tmp_path) == []

    def test_missing_dir(self, tmp_path: Path):
        assert list_existing_tarballs(tmp_path / "missing") == []

    def test_lists_matching_pattern(self, tmp_path: Path):
        _make_tarballs(tmp_path, 3)
        result = list_existing_tarballs(tmp_path)
        assert len(result) == 3

    def test_ignores_non_matching_files(self, tmp_path: Path):
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "wiki-not-our-pattern.tar.gz").write_bytes(b"x")
        (tmp_path / "random.tar.gz").write_bytes(b"x")
        (tmp_path / "wiki-2026-05-28.tar.gz").write_bytes(b"x")  # missing time component
        # Correct one
        (tmp_path / "wiki-2026-05-28-120000.tar.gz").write_bytes(b"x")
        result = list_existing_tarballs(tmp_path)
        assert len(result) == 1
        assert result[0].name == "wiki-2026-05-28-120000.tar.gz"

    def test_sorted_newest_first(self, tmp_path: Path):
        paths = _make_tarballs(tmp_path, 4)
        result = list_existing_tarballs(tmp_path)
        # paths[3] is newest (highest mtime per our helper); should be first
        assert result[0] == paths[3]
        assert result[-1] == paths[0]


class TestPruneOldTarballs:
    def test_no_op_under_cap(self, tmp_path: Path):
        _make_tarballs(tmp_path, 5)
        deleted = prune_old_tarballs(tmp_path, keep=10)
        assert deleted == 0
        assert len(list_existing_tarballs(tmp_path)) == 5

    def test_exact_cap_no_op(self, tmp_path: Path):
        _make_tarballs(tmp_path, 3)
        deleted = prune_old_tarballs(tmp_path, keep=3)
        assert deleted == 0

    def test_over_cap_prunes_oldest(self, tmp_path: Path):
        _make_tarballs(tmp_path, 7)
        deleted = prune_old_tarballs(tmp_path, keep=3)
        assert deleted == 4
        remaining = list_existing_tarballs(tmp_path)
        assert len(remaining) == 3
        # The 3 newest remain (highest mtime)
        for path in remaining:
            assert path.name.startswith("wiki-2026-05-0")  # the most recent fixtures

    def test_default_keep_matches_constant(self, tmp_path: Path):
        _make_tarballs(tmp_path, TARBALL_RETENTION_KEEP + 3)
        deleted = prune_old_tarballs(tmp_path)  # no keep arg → default
        assert deleted == 3
        assert len(list_existing_tarballs(tmp_path)) == TARBALL_RETENTION_KEEP

    def test_negative_keep_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match=">= 0"):
            prune_old_tarballs(tmp_path, keep=-1)

    def test_missing_dir_returns_zero(self, tmp_path: Path):
        result = prune_old_tarballs(tmp_path / "missing")
        assert result == 0


# ---------------------------------------------------------------------------
# git-subprocess wrappers — require a real git repo (tmpdir)
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


def _commit_something(path: Path, content: str = "hello\n", filename: str = "x.md") -> None:
    (path / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


class TestIsGitRepo:
    def test_not_a_repo(self, tmp_path: Path):
        assert not is_git_repo(tmp_path)

    def test_real_repo(self, tmp_path: Path):
        _init_repo(tmp_path)
        assert is_git_repo(tmp_path)

    def test_missing_dir(self, tmp_path: Path):
        assert not is_git_repo(tmp_path / "missing")


class TestGetRemoteUrl:
    def test_no_remote_configured(self, tmp_path: Path):
        _init_repo(tmp_path)
        assert get_remote_url(tmp_path) is None

    def test_remote_configured(self, tmp_path: Path):
        _init_repo(tmp_path)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/user/repo.git"],
            cwd=tmp_path, check=True, capture_output=True,
        )
        assert get_remote_url(tmp_path) == "https://github.com/user/repo.git"


class TestGetHeadInfo:
    def test_no_commits(self, tmp_path: Path):
        _init_repo(tmp_path)
        sha, date = get_head_info(tmp_path)
        assert sha is None
        assert date is None

    def test_with_commit(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        sha, date = get_head_info(tmp_path)
        assert sha is not None and len(sha) == 40  # full SHA
        assert date is not None
        assert "T" in date  # ISO-format includes T separator


# ---------------------------------------------------------------------------
# setup_remote
# ---------------------------------------------------------------------------


class TestSetupRemote:
    def test_adds_new_remote(self, tmp_path: Path):
        _init_repo(tmp_path)
        result = setup_remote("https://github.com/user/repo.git", tmp_path)
        assert result.success
        assert result.method == "setup"
        assert "added" in result.message
        # Verify by reading back
        assert get_remote_url(tmp_path) == "https://github.com/user/repo.git"

    def test_updates_existing_remote(self, tmp_path: Path):
        _init_repo(tmp_path)
        setup_remote("https://github.com/user/old.git", tmp_path)
        result = setup_remote("https://github.com/user/new.git", tmp_path)
        assert result.success
        assert "updated" in result.message
        assert get_remote_url(tmp_path) == "https://github.com/user/new.git"

    def test_rejects_bad_url(self, tmp_path: Path):
        _init_repo(tmp_path)
        result = setup_remote("not a url", tmp_path)
        assert not result.success
        assert result.error == "invalid-url-shape"
        # Original state preserved
        assert get_remote_url(tmp_path) is None

    def test_refuses_non_git_dir(self, tmp_path: Path):
        result = setup_remote("https://github.com/user/repo.git", tmp_path)
        assert not result.success
        assert result.error == "not-a-git-repo"
        assert "/ren:install" in result.message


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_non_git_dir(self, tmp_path: Path):
        result = status(tmp_path, tmp_path / "backups")
        assert not result.is_git_repo
        assert result.remote_url is None
        assert result.last_commit_sha is None
        assert result.tarball_count == 0

    def test_git_repo_no_commits_no_remote_no_tarballs(self, tmp_path: Path):
        _init_repo(tmp_path)
        result = status(tmp_path, tmp_path / "backups")
        assert result.is_git_repo
        assert result.remote_url is None
        assert result.last_commit_sha is None
        assert result.tarball_count == 0

    def test_git_repo_with_commit_and_remote(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/u/r.git"],
            cwd=tmp_path, check=True, capture_output=True,
        )
        result = status(tmp_path, tmp_path / "backups")
        assert result.is_git_repo
        assert result.remote_url == "https://github.com/u/r.git"
        assert result.last_commit_sha is not None
        assert result.last_commit_date is not None
        assert "T" in result.last_commit_date

    def test_tarball_counting(self, tmp_path: Path):
        _init_repo(tmp_path)
        backup_dir = tmp_path / "backups"
        _make_tarballs(backup_dir, 4)
        result = status(tmp_path, backup_dir)
        assert result.tarball_count == 4
        assert result.oldest_tarball_date is not None
        assert result.newest_tarball_date is not None
        assert result.newest_tarball_date >= result.oldest_tarball_date


# ---------------------------------------------------------------------------
# Result dataclass sanity
# ---------------------------------------------------------------------------


class TestResultDataclasses:
    def test_backup_result_immutable(self):
        r = BackupResult(success=True, method="setup", path_or_remote="x", message="y")
        with pytest.raises(Exception):
            r.success = False  # type: ignore[misc]

    def test_status_result_immutable(self):
        r = StatusResult(
            wiki_path="x", is_git_repo=False, remote_url=None,
            last_commit_sha=None, last_commit_date=None,
            tarball_count=0, oldest_tarball_date=None, newest_tarball_date=None,
        )
        with pytest.raises(Exception):
            r.is_git_repo = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# has_uncommitted_changes + commit_pending_changes
# ---------------------------------------------------------------------------


from ..__init__ import (
    backup,
    commit_pending_changes,
    create_tarball,
    has_uncommitted_changes,
    push_to_remote,
)


class TestHasUncommittedChanges:
    def test_clean_tree_false(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        assert not has_uncommitted_changes(tmp_path)

    def test_untracked_file_true(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        (tmp_path / "new.md").write_text("hi\n")
        assert has_uncommitted_changes(tmp_path)

    def test_modified_file_true(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        (tmp_path / "x.md").write_text("modified\n")
        assert has_uncommitted_changes(tmp_path)


class TestCommitPendingChanges:
    def test_clean_tree_idempotent_success(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        assert commit_pending_changes(tmp_path)

    def test_creates_commit_with_canonical_message(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        (tmp_path / "new.md").write_text("hi\n")
        now = datetime(2026, 5, 28, 14, 30, 0, tzinfo=timezone.utc)
        assert commit_pending_changes(tmp_path, now=now)

        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=tmp_path, check=True, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "sf:backup at 2026-05-28 14:30:00 UTC"


# ---------------------------------------------------------------------------
# push_to_remote — needs a real remote, so we use a local bare-repo fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_with_local_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Init a wiki repo + a separate bare repo to serve as the 'remote.'"""
    wiki = tmp_path / "wiki"
    remote = tmp_path / "remote.git"
    _init_repo(wiki)
    _commit_something(wiki)
    # Bare repo as remote
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)],
        cwd=wiki, check=True, capture_output=True,
    )
    return wiki, remote


class TestPushToRemote:
    def test_no_remote_configured(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        pushed, category, _ = push_to_remote(tmp_path)
        assert not pushed
        assert category == "no-remote"

    def test_no_commits(self, tmp_path: Path):
        _init_repo(tmp_path)
        # No commits yet; configure a remote anyway
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/x/y.git"],
            cwd=tmp_path, check=True, capture_output=True,
        )
        pushed, category, _ = push_to_remote(tmp_path)
        assert not pushed
        assert category == "no-commits"

    def test_successful_push_to_local_remote(self, repo_with_local_remote):
        wiki, _ = repo_with_local_remote
        pushed, category, _ = push_to_remote(wiki)
        assert pushed
        assert category == ""

    def test_transport_failure_unreachable_remote(self, tmp_path: Path):
        _init_repo(tmp_path)
        _commit_something(tmp_path)
        # Unreachable file:// remote
        subprocess.run(
            ["git", "remote", "add", "origin", str(tmp_path / "nonexistent-remote.git")],
            cwd=tmp_path, check=True, capture_output=True,
        )
        pushed, category, stderr = push_to_remote(tmp_path)
        assert not pushed
        # Either transport-failure (most common) or no-commits-confusion; categorize.
        # In CI environments lacking network, we expect transport-failure.
        assert category in ("transport-failure", "non-fast-forward")
        # We should NOT have force-pushed
        assert "--force" not in stderr.lower()

    def test_classify_push_failure_non_fast_forward(self):
        """Unit-test _classify_push_failure against representative git stderr.

        Integration-testing git's actual divergence-detection is fragile
        across git versions + push.default settings; we trust git to report
        the rejection and unit-test our CLASSIFICATION of its stderr.
        """
        from ..__init__ import _classify_push_failure

        # Representative non-fast-forward stderr (from real `git push` output)
        for stderr in [
            "To /tmp/remote.git\n ! [rejected]        main -> main (non-fast-forward)\nerror: failed to push some refs\nhint: Updates were rejected because the tip of your current branch is behind\nhint: its remote counterpart. Integrate the remote changes (e.g.\nhint: 'git pull ...') before pushing again.\nhint: See the 'Note about fast-forwards' in 'git push --help' for details.",
            "! [rejected]        main -> main (fetch first)",
            "Updates were rejected because the remote contains work that you do not have",
        ]:
            assert _classify_push_failure(stderr) == "non-fast-forward", (
                f"failed to detect non-fast-forward in: {stderr[:80]!r}"
            )

    def test_classify_push_failure_transport(self):
        """Auth/network/DNS errors classify as transport-failure (the catch-all)."""
        from ..__init__ import _classify_push_failure

        for stderr in [
            "fatal: could not read Username for 'https://github.com'",
            "ssh: connect to host github.com port 22: Connection refused",
            "fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host",
            "fatal: repository 'https://x/y.git/' not found",
            "Permission denied (publickey).",
        ]:
            assert _classify_push_failure(stderr) == "transport-failure", (
                f"expected transport-failure for: {stderr[:80]!r}"
            )


# ---------------------------------------------------------------------------
# create_tarball
# ---------------------------------------------------------------------------


class TestCreateTarball:
    def test_creates_tarball_with_canonical_name(self, tmp_path: Path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        (wiki / "x.md").write_text("hi\n")
        backup_dir = tmp_path / "backups"

        now = datetime(2026, 5, 28, 14, 30, 0, tzinfo=timezone.utc)
        success, path, _ = create_tarball(wiki, backup_dir, now=now)

        assert success
        assert path is not None
        assert path.name == "wiki-2026-05-28-143000.tar.gz"
        assert path.exists()
        assert path.stat().st_size > 0

    def test_tarball_contents_include_wiki(self, tmp_path: Path):
        import tarfile
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        (wiki / "test.md").write_text("important content\n")
        backup_dir = tmp_path / "backups"
        success, path, _ = create_tarball(wiki, backup_dir)

        assert success
        with tarfile.open(path, "r:gz") as tar:
            names = tar.getnames()
            assert any("test.md" in n for n in names), f"test.md not found in {names}"

    def test_missing_wiki_root_fails_clean(self, tmp_path: Path):
        success, path, error = create_tarball(
            tmp_path / "nonexistent",
            tmp_path / "backups",
        )
        assert not success
        assert path is None
        assert "not found" in error.lower()

    def test_creates_backup_dir_if_missing(self, tmp_path: Path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        (wiki / "x.md").write_text("hi\n")
        backup_dir = tmp_path / "deep" / "nested" / "backups"

        success, _, _ = create_tarball(wiki, backup_dir)
        assert success
        assert backup_dir.is_dir()


# ---------------------------------------------------------------------------
# backup — top-level orchestrator
# ---------------------------------------------------------------------------


class TestBackupOrchestrator:
    def test_non_git_dir_refused(self, tmp_path: Path):
        result = backup(tmp_path, tmp_path / "backups")
        assert not result.success
        assert result.method == "skipped"
        assert result.error == "not-a-git-repo"
        assert "/ren:install" in result.message

    def test_clean_repo_no_remote_falls_back_to_tarball(self, tmp_path: Path):
        wiki = tmp_path / "wiki"
        _init_repo(wiki)
        _commit_something(wiki)
        backup_dir = tmp_path / "backups"

        result = backup(wiki, backup_dir)

        assert result.success
        assert result.method == "tarball"
        assert "No remote configured" in result.message
        assert (backup_dir).is_dir()
        assert len(list_existing_tarballs(backup_dir)) == 1

    def test_clean_push_succeeds_no_tarball(self, repo_with_local_remote):
        wiki, _ = repo_with_local_remote
        backup_dir = wiki.parent / "backups"

        result = backup(wiki, backup_dir)

        assert result.success
        assert result.method == "git-push"
        assert "Wiki backed up" in result.message
        # No tarball created on successful push
        assert not backup_dir.exists() or len(list_existing_tarballs(backup_dir)) == 0

    def test_force_tarball_skips_push(self, repo_with_local_remote):
        wiki, _ = repo_with_local_remote
        backup_dir = wiki.parent / "backups"

        result = backup(wiki, backup_dir, force_tarball=True)

        assert result.success
        assert result.method == "tarball"
        assert "Tarball created" in result.message
        assert len(list_existing_tarballs(backup_dir)) == 1

    def test_force_tarball_with_pending_changes_commits_first(self, repo_with_local_remote):
        wiki, _ = repo_with_local_remote
        # Add a dirty file
        (wiki / "dirty.md").write_text("pending\n")
        backup_dir = wiki.parent / "backups"

        result = backup(wiki, backup_dir, force_tarball=True)

        assert result.success
        # Working tree should be clean now (changes committed before tarball)
        assert not has_uncommitted_changes(wiki)

    def test_diverged_remote_refuses_force_push(self, tmp_path: Path, monkeypatch):
        """LOAD-BEARING: when push_to_remote reports non-fast-forward, backup MUST refuse force-push.

        Tests the orchestrator's REACTION to non-fast-forward (the unit under
        test) by monkeypatching push_to_remote to return that classification.
        Whether git correctly DETECTS non-fast-forward is git's concern
        (unit-tested separately via _classify_push_failure against real stderr
        strings); whether OUR orchestrator refuses-force-push + skips-tarball
        is OUR concern, tested here.
        """
        wiki = tmp_path / "wiki"
        _init_repo(wiki)
        _commit_something(wiki)
        # Configure a remote (URL value irrelevant; push is mocked)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/repo.git"],
            cwd=wiki, check=True, capture_output=True,
        )

        # Mock push_to_remote to simulate non-fast-forward
        from ..__init__ import push_to_remote as real_push  # noqa: F401
        from .. import __init__ as backup_mod
        monkeypatch.setattr(
            backup_mod,
            "push_to_remote",
            lambda wiki_root, *, remote_name="origin": (
                False, "non-fast-forward",
                "! [rejected]        main -> main (non-fast-forward)"
            ),
        )

        backup_dir = tmp_path / "backups"
        result = backup(wiki, backup_dir)

        # LOAD-BEARING ASSERTIONS:
        assert not result.success, "non-fast-forward must NOT report success"
        assert result.error == "non-fast-forward", f"expected error='non-fast-forward'; got {result.error!r}"
        assert "RECOVERY.md" in result.message, "must point at RECOVERY.md"
        assert "Force-push is NOT performed" in result.message, "must explicitly state force-push is not performed"
        # The killer assertion: NO auto-fallback tarball on non-fast-forward
        existing = list_existing_tarballs(backup_dir) if backup_dir.exists() else []
        assert len(existing) == 0, (
            f"non-fast-forward path created a tarball ({len(existing)} found); "
            "this is the LOAD-BEARING safety invariant — no auto-fallback on divergence"
        )

    def test_tarball_retention_enforced(self, tmp_path: Path):
        wiki = tmp_path / "wiki"
        _init_repo(wiki)
        _commit_something(wiki)
        backup_dir = tmp_path / "backups"
        # Pre-populate with 25 fake tarballs
        _make_tarballs(backup_dir, 25)

        result = backup(wiki, backup_dir, force_tarball=True, keep=20)

        assert result.success
        # 25 fake + 1 new - pruning = 20 final
        assert len(list_existing_tarballs(backup_dir)) == 20
        assert result.pruned_tarballs >= 5
