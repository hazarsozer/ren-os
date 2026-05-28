"""
Tests for feed.bootstrap + feed.identity_sync (task #21).

bootstrap covers the Stage 3 contract onboarding-2 consumes:
- detect_repo_state decision tree (3 modes × multiple branches)
- bootstrap_first_friend creates README + log + identity placeholder
- clone_existing handles handle-collision + skip-readme case
- _canonical_repo_id normalizes URL forms

identity_sync covers Stage 4:
- feed_upsert_identity is idempotent (no-op on byte-identical content)
- writes the file even when push fails (graceful degradation)

We DON'T exercise network paths in unit tests — they require gh CLI auth + real
GitHub repos. Network paths are smoke-tested manually via the install flow.

Run with: python3 -m pytest feed/tests/test_bootstrap_identity.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from feed import bootstrap, config, identity_sync, writer
from feed.bootstrap import (
    RepoState,
    _canonical_repo_id,
    _normalize_remote_url,
    _remotes_equivalent,
    _scan_existing_handles,
    feed_bootstrap_first_friend,
    feed_clone_existing,
    feed_detect_repo_state,
)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def temp_root(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        yield Path(tmp)


@pytest.fixture
def existing_clone(temp_root):
    """An existing local clone of `friend-group/activity-feed` with one friend's file."""
    repo = temp_root / "activity-feed"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin",
         "https://github.com/friend-group/activity-feed.git"],
        check=True,
    )
    # An existing friend's log file
    (repo / "friend-b.log.md").write_text(
        "---\nschema_version: 1\nhandle: friend-b\n---\n", encoding="utf-8"
    )
    return repo


# --- _canonical_repo_id normalization -------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("friend-group/activity-feed", "friend-group/activity-feed"),
    ("https://github.com/friend-group/activity-feed", "friend-group/activity-feed"),
    ("https://github.com/friend-group/activity-feed.git", "friend-group/activity-feed"),
    ("git@github.com:friend-group/activity-feed.git", "friend-group/activity-feed"),
    ("git@github.com:Friend-Group/Activity-Feed", "friend-group/activity-feed"),
    ("https://github.com/friend-group/activity-feed/", "friend-group/activity-feed"),
    ("ssh://git@github.com/friend-group/activity-feed.git", "friend-group/activity-feed"),
])
def test_canonical_repo_id_normalizes_url_forms(url, expected):
    assert _canonical_repo_id(url) == expected


def test_remotes_equivalent_across_forms():
    assert _remotes_equivalent(
        "https://github.com/friend-group/activity-feed.git",
        "git@github.com:friend-group/activity-feed",
    )
    assert _remotes_equivalent(
        "friend-group/activity-feed", "friend-group/activity-feed"
    )
    assert not _remotes_equivalent(
        "friend-group/activity-feed", "other/feed"
    )


def test_normalize_shorthand_to_https():
    assert _normalize_remote_url("friend-group/activity-feed") == \
        "https://github.com/friend-group/activity-feed.git"


def test_normalize_preserves_full_urls():
    full = "https://github.com/friend-group/activity-feed.git"
    assert _normalize_remote_url(full) == full
    ssh = "git@github.com:friend-group/activity-feed.git"
    assert _normalize_remote_url(ssh) == ssh


# --- detect_repo_state decision tree --------------------------------------


def test_detect_returns_already_cloned_when_local_clone_matches(existing_clone):
    state = feed_detect_repo_state(
        "https://github.com/friend-group/activity-feed.git", existing_clone,
    )
    assert state.mode == "already-cloned"
    assert state.needs_init is False
    assert "friend-b" in state.existing_handles
    assert state.local_path == existing_clone


def test_detect_recognizes_clone_with_shorthand_url(existing_clone):
    """Shorthand 'owner/repo' should match a clone with the full URL."""
    state = feed_detect_repo_state("friend-group/activity-feed", existing_clone)
    assert state.mode == "already-cloned"


def test_detect_step_2_passes_when_no_local_clone(temp_root, monkeypatch):
    """If no local clone exists, step 2 runs. We mock gh to return non-zero (repo not found)."""
    def fake_subprocess_run(cmd, **kw):
        if cmd[:3] == ["gh", "repo", "view"]:
            return subprocess.CompletedProcess(cmd, 1, "", "GraphQL: Could not resolve to a Repository")
        if cmd[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(cmd, 1, "", "Not Found")
        # Allow real git subprocess for any other call
        return subprocess.run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    state = feed_detect_repo_state(
        "friend-group/nope-doesnt-exist", temp_root / "activity-feed",
    )
    assert state.mode == "first-friend-bootstrap"
    assert state.needs_init is True
    assert state.has_other_friends is False
    assert state.existing_handles == ()


def test_detect_step_3_joiner_clone_when_remote_has_log_files(temp_root, monkeypatch):
    """Remote exists AND has friend log files → joiner-clone."""
    def fake_subprocess_run(cmd, **kw):
        if cmd[:3] == ["gh", "repo", "view"]:
            return subprocess.CompletedProcess(cmd, 0, '{"name":"a","visibility":"private"}', "")
        if cmd[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(
                cmd, 0, '["hazar.log.md", "friend-b.log.md", "README.md"]', ""
            )
        return subprocess.run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    state = feed_detect_repo_state(
        "friend-group/activity-feed", temp_root / "activity-feed",
    )
    assert state.mode == "joiner-clone"
    assert state.has_other_friends is True
    # README.md is correctly filtered (only *.log.md handles)
    assert set(state.existing_handles) == {"hazar", "friend-b"}
    assert state.needs_init is False


def test_detect_step_3_first_friend_bootstrap_when_remote_empty(temp_root, monkeypatch):
    """Remote exists but is empty → first-friend-bootstrap."""
    def fake_subprocess_run(cmd, **kw):
        if cmd[:3] == ["gh", "repo", "view"]:
            return subprocess.CompletedProcess(cmd, 0, '{"name":"a"}', "")
        if cmd[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(cmd, 0, "[]", "")
        return subprocess.run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    state = feed_detect_repo_state(
        "friend-group/empty-repo", temp_root / "activity-feed",
    )
    assert state.mode == "first-friend-bootstrap"
    assert state.has_other_friends is False
    assert state.existing_handles == ()


def test_detect_surfaces_auth_error(temp_root, monkeypatch):
    """gh repo view returning auth-shaped error → RepoState.auth_error populated."""
    def fake_subprocess_run(cmd, **kw):
        if cmd[:3] == ["gh", "repo", "view"]:
            return subprocess.CompletedProcess(
                cmd, 1, "", "HTTP 401: You must authenticate to access this content"
            )
        return subprocess.run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    state = feed_detect_repo_state(
        "private/repo", temp_root / "activity-feed",
    )
    assert state.auth_error is not None
    assert "authenticate" in state.auth_error.lower()


# --- bootstrap_first_friend ------------------------------------------------


def test_bootstrap_first_friend_creates_all_files(temp_root, monkeypatch):
    """Verify README + log file + identities/ placeholder all written."""
    # Stub push to be a no-op so we don't hit network
    monkeypatch.setattr(
        bootstrap.io_github, "push",
        lambda *a, **kw: bootstrap.io_github.PushResult(ok=False, error="no remote"),
    )

    local = temp_root / "activity-feed"
    feed_bootstrap_first_friend(local, "hazar", "friend-group/activity-feed")

    assert (local / ".git").exists()
    assert (local / "README.md").exists()
    assert "friend-group" in (local / "README.md").read_text().lower() or \
        "Activity Feed" in (local / "README.md").read_text()
    assert (local / "hazar.log.md").exists()

    log_text = (local / "hazar.log.md").read_text()
    assert "schema_version: 1" in log_text
    assert "framework_version: 1.0.0" in log_text
    assert "type: feed-entry" in log_text
    assert "handle: hazar" in log_text

    assert (local / "identities" / "hazar.md").exists()
    id_text = (local / "identities" / "hazar.md").read_text()
    assert "handle: hazar" in id_text


def test_bootstrap_first_friend_is_idempotent(temp_root, monkeypatch):
    """Running bootstrap_first_friend twice should not error or overwrite."""
    monkeypatch.setattr(
        bootstrap.io_github, "push",
        lambda *a, **kw: bootstrap.io_github.PushResult(ok=False),
    )

    local = temp_root / "activity-feed"
    feed_bootstrap_first_friend(local, "hazar", "friend-group/activity-feed")

    # Capture content
    log_before = (local / "hazar.log.md").read_text()

    # Run again
    feed_bootstrap_first_friend(local, "hazar", "friend-group/activity-feed")
    log_after = (local / "hazar.log.md").read_text()

    assert log_before == log_after


def test_bootstrap_sets_remote(temp_root, monkeypatch):
    """git remote add origin should be set after bootstrap."""
    monkeypatch.setattr(
        bootstrap.io_github, "push",
        lambda *a, **kw: bootstrap.io_github.PushResult(ok=False),
    )
    local = temp_root / "activity-feed"
    feed_bootstrap_first_friend(local, "hazar", "friend-group/activity-feed")

    result = subprocess.run(
        ["git", "-C", str(local), "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "friend-group/activity-feed" in result.stdout


# --- clone_existing --------------------------------------------------------


def test_clone_existing_rejects_handle_collision(existing_clone, monkeypatch):
    """If <handle>.log.md already exists in the clone, raise FileExistsError."""
    monkeypatch.setattr(
        bootstrap.io_github, "push",
        lambda *a, **kw: bootstrap.io_github.PushResult(ok=False),
    )

    # existing_clone already has friend-b.log.md — try to clone as friend-b
    with pytest.raises(FileExistsError) as excinfo:
        feed_clone_existing(
            "friend-group/activity-feed", existing_clone, "friend-b",
        )
    assert "friend-b" in str(excinfo.value)


def test_clone_existing_creates_new_handle_files(existing_clone, monkeypatch):
    """Successful clone-as-joiner writes own log + identity, doesn't touch others."""
    monkeypatch.setattr(
        bootstrap.io_github, "push",
        lambda *a, **kw: bootstrap.io_github.PushResult(ok=False),
    )

    feed_clone_existing(
        "friend-group/activity-feed", existing_clone, "hazar",
    )

    # New files exist
    assert (existing_clone / "hazar.log.md").exists()
    assert (existing_clone / "identities" / "hazar.md").exists()
    # Existing file untouched
    assert (existing_clone / "friend-b.log.md").exists()
    fb = (existing_clone / "friend-b.log.md").read_text()
    assert "handle: friend-b" in fb


# --- identity_sync ---------------------------------------------------------


@pytest.fixture
def temp_feed_repo(monkeypatch):
    """Initialized git repo so identity_sync can push (even if push fails)."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        repo = Path(tmp) / "activity-feed"
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "T"], check=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", "init"],
            check=True,
        )
        yield repo


def test_upsert_identity_creates_file(temp_feed_repo):
    md = "---\nhandle: hazar\nname: Hazar\n---\n\n# Hazar\n\nFounding friend.\n"
    result = identity_sync.feed_upsert_identity("hazar", md)
    assert result.success is True
    written = (temp_feed_repo / "identities" / "hazar.md").read_text()
    assert written == md


def test_upsert_identity_idempotent_on_unchanged(temp_feed_repo):
    md = "---\nhandle: hazar\n---\n# H\n"
    r1 = identity_sync.feed_upsert_identity("hazar", md)
    r2 = identity_sync.feed_upsert_identity("hazar", md)
    assert r1.success is True
    assert r2.success is True
    assert r2.entry_id == "identity-hazar-unchanged"


def test_upsert_identity_writes_changed_content(temp_feed_repo):
    md1 = "---\nhandle: hazar\nname: Hazar\n---\n# Old\n"
    md2 = "---\nhandle: hazar\nname: Hazar\n---\n# New\n"
    identity_sync.feed_upsert_identity("hazar", md1)
    identity_sync.feed_upsert_identity("hazar", md2)

    written = (temp_feed_repo / "identities" / "hazar.md").read_text()
    assert written == md2
