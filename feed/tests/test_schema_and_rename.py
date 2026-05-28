"""
Tests for the post-#19 coordination follow-ups (task #36), updated for the split-writer
API (post-refactor task #17 re-do):

- Expanded frontmatter on new <handle>.log.md files (type, framework_version)
- Schema-version drift check in the writer dispatch
- Schema-version guard in config.handle()
- feed.rename_handle helper
- status.sh JSON contract (covered by smoke test, not pytest)
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feed import (
    config,
    feed_write_session_start,
    feed_write_session_end,
    rename_handle,
)
from feed.config import (
    EXPECTED_FEED_SCHEMA_VERSION,
    EXPECTED_IDENTITY_SCHEMA_VERSION,
    HandleNotConfiguredError,
    SchemaVersionMismatchError,
    handle,
)


REF_TS = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def temp_feed_repo(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        monkeypatch.delenv("SF_SKIP_FEED", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
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


@pytest.fixture
def temp_wiki(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        wiki = Path(tmp) / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        yield wiki


# --- expanded frontmatter ---------------------------------------------------


def test_new_log_file_includes_full_frontmatter(temp_feed_repo):
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    text = (temp_feed_repo / "hazar.log.md").read_text()
    assert "schema_version: 1" in text
    assert "framework_version: 1.0.0" in text
    assert "type: feed-entry" in text
    assert "handle: hazar" in text


# --- drift check in writer --------------------------------------------------


def test_writer_refuses_stale_schema_file(temp_feed_repo):
    log_path = temp_feed_repo / "hazar.log.md"
    log_path.write_text(
        "---\nschema_version: 99\nframework_version: 0.9.0\ntype: feed-entry\nhandle: hazar\n---\n\n",
        encoding="utf-8",
    )

    result = feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    assert result.success is False
    assert result.violation == "schema-mismatch"
    assert "99" in (result.error or "")


def test_writer_accepts_matching_schema_file(temp_feed_repo):
    log_path = temp_feed_repo / "hazar.log.md"
    log_path.write_text(
        f"---\nschema_version: {EXPECTED_FEED_SCHEMA_VERSION}\nhandle: hazar\n---\n\n",
        encoding="utf-8",
    )
    result = feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    assert result.success is True
    assert result.violation is None


# --- config.handle() schema guard -------------------------------------------


def test_handle_raises_on_schema_drift(temp_wiki):
    identity = temp_wiki / "identity.md"
    identity.write_text(
        "---\nschema_version: 42\nhandle: hazar\n---\n# Identity\n", encoding="utf-8"
    )

    with pytest.raises(SchemaVersionMismatchError) as excinfo:
        handle()

    assert excinfo.value.found == 42
    assert excinfo.value.expected == EXPECTED_IDENTITY_SCHEMA_VERSION
    assert "run /sf:update" in str(excinfo.value).lower()


def test_handle_strict_false_bypasses_guard(temp_wiki):
    identity = temp_wiki / "identity.md"
    identity.write_text(
        "---\nschema_version: 42\nhandle: hazar\n---\n", encoding="utf-8"
    )
    assert handle(strict_schema=False) == "hazar"


def test_handle_raises_when_missing(temp_wiki):
    with pytest.raises(HandleNotConfiguredError) as excinfo:
        handle()
    assert "/sf:interview" in str(excinfo.value)


def test_handle_raises_when_field_absent(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 1\nname: Hazar\n---\n", encoding="utf-8"
    )
    with pytest.raises(HandleNotConfiguredError):
        handle()


def test_handle_matches_expected_schema_succeeds(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        f"---\nschema_version: {EXPECTED_IDENTITY_SCHEMA_VERSION}\nhandle: hazar\n---\n",
        encoding="utf-8",
    )
    assert handle() == "hazar"


# --- rename_handle ---------------------------------------------------------


def test_rename_handle_moves_log_file(temp_feed_repo):
    feed_write_session_start(handle="hazar-old", cwd="/Dev/sidecar", timestamp=REF_TS)
    assert (temp_feed_repo / "hazar-old.log.md").exists()

    ok = rename_handle("hazar-old", "hazar-new")
    assert ok is True
    assert not (temp_feed_repo / "hazar-old.log.md").exists()
    assert (temp_feed_repo / "hazar-new.log.md").exists()

    text = (temp_feed_repo / "hazar-new.log.md").read_text()
    assert "handle: hazar-new" in text
    assert "handle: hazar-old" not in text


def test_rename_handle_idempotent_on_existing_new(temp_feed_repo):
    feed_write_session_start(handle="hazar-old", cwd="/Dev/sidecar", timestamp=REF_TS)
    feed_write_session_start(handle="hazar-new", cwd="/Dev/restore", timestamp=REF_TS)

    ok = rename_handle("hazar-old", "hazar-new")
    assert ok is False
    assert (temp_feed_repo / "hazar-old.log.md").exists()
    assert (temp_feed_repo / "hazar-new.log.md").exists()


def test_rename_handle_no_old_returns_false(temp_feed_repo):
    ok = rename_handle("never-existed", "new-name")
    assert ok is False


def test_rename_handle_also_moves_identity_file(temp_feed_repo):
    feed_write_session_start(handle="hazar-old", cwd="/Dev/sidecar", timestamp=REF_TS)
    identities = temp_feed_repo / "identities"
    identities.mkdir(parents=True, exist_ok=True)
    (identities / "hazar-old.md").write_text(
        "---\nhandle: hazar-old\nname: H\n---\n# About\n", encoding="utf-8"
    )

    ok = rename_handle("hazar-old", "hazar-new")
    assert ok is True
    assert not (identities / "hazar-old.md").exists()
    assert (identities / "hazar-new.md").exists()
    id_text = (identities / "hazar-new.md").read_text()
    assert "handle: hazar-new" in id_text
