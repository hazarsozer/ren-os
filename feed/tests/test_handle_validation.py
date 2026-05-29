"""
M2 + L7 (REVIEW-v1.0-preship): handle format validation / path-traversal guard.

`config.handle()` and the writers must reject a malformed handle (e.g. a hand-edited
identity.md with `handle: ../../etc`) before it reaches filesystem path construction
(`<local_path>/<handle>.log.md`) or the git commit message (L7). The canonical pattern
is ^[a-z][a-z0-9-]*$ — the same one /sf:interview validates at input.

Run with: python3 -m pytest feed/tests/test_handle_validation.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feed import config, feed_write_session_end
from feed.config import HandleNotConfiguredError, InvalidHandleError, validate_handle


REF_TS = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)

VALID_HANDLES = ["hazar", "friend-b", "hazar-new", "self", "a", "x1", "a-b-c", "abc123"]
INVALID_HANDLES = [
    "", "../etc", "a/b", "..", "Hazar", "1x", "-x", "a_b", "a.b", "a b", "héllo", "x/../y",
]


@pytest.fixture
def temp_wiki(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        wiki = Path(tmp) / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        yield wiki


@pytest.fixture
def temp_feed_repo(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        monkeypatch.delenv("SF_SKIP_FEED", raising=False)
        repo = Path(tmp) / "activity-feed"
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", "init"], check=True
        )
        yield repo


# --- validate_handle unit ---------------------------------------------------


@pytest.mark.parametrize("h", VALID_HANDLES)
def test_validate_handle_accepts_valid(h):
    assert validate_handle(h) == h


@pytest.mark.parametrize("h", INVALID_HANDLES)
def test_validate_handle_rejects_invalid(h):
    with pytest.raises(InvalidHandleError):
        validate_handle(h)


def test_invalid_handle_subclasses_not_configured():
    """Existing `except HandleNotConfiguredError` handlers (sf-recall/sf-wrap) must
    still catch the new error with the same /sf:interview remediation."""
    assert issubclass(InvalidHandleError, HandleNotConfiguredError)
    with pytest.raises(HandleNotConfiguredError):
        validate_handle("../../etc/passwd")


# --- config.handle() enforcement --------------------------------------------


def test_handle_raises_on_malformed_identity_handle(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 1\nhandle: ../../etc\n---\n", encoding="utf-8"
    )
    with pytest.raises(InvalidHandleError) as exc:
        config.handle()
    assert "/sf:interview" in str(exc.value)


def test_handle_validates_even_when_strict_schema_false(temp_wiki):
    """Path-safety is independent of schema version: repair-mode (strict_schema=False)
    must still reject a traversal handle."""
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 42\nhandle: ../evil\n---\n", encoding="utf-8"
    )
    with pytest.raises(InvalidHandleError):
        config.handle(strict_schema=False)


def test_handle_accepts_valid_identity_handle(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 1\nhandle: friend-b\n---\n", encoding="utf-8"
    )
    assert config.handle() == "friend-b"


# --- writer guard (L7: bad handle never reaches path/commit) ----------------


def test_writer_rejects_malformed_handle(temp_feed_repo):
    result = feed_write_session_end(
        handle="../../etc", project="sidecar", task_brief="x",
        files_touched=["a.ts"], timestamp=REF_TS,
    )
    assert result.success is False
    assert result.violation == "invalid-handle"
    # Guard fired before path construction → no traversal write happened.
    assert list(temp_feed_repo.glob("*.log.md")) == []


def test_writer_accepts_valid_handle(temp_feed_repo):
    result = feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="ok",
        files_touched=["a.ts"], timestamp=REF_TS,
    )
    assert result.success is True
    assert result.violation is None
    assert (temp_feed_repo / "friend-b.log.md").exists()
