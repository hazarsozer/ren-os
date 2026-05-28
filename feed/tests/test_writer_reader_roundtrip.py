"""
End-to-end tests for feed.writer (split API) + feed.reader against a real on-disk git repo.

Initializes a temporary git repo (no remote, no network), points feed at it via
SF_FRAMEWORK_ROOT env var, then exercises the writer + reader roundtrip using the
PUBLIC SPLIT API (per team-lead arbitration 2026-05-28):

- feed_write_session_start  → log file created, frontmatter present, entry parseable
- feed_write_session_end    → end entry parseable, files extracted, idempotency works
- feed_write_release        → release line parseable
- feed_read_friends_tails   → bucketing, ordering, max_tokens truncation
- read_all_entries          → filtering by since/handles/project

Run with: uv run pytest feed/tests/test_writer_reader_roundtrip.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from feed import (
    config,
    feed_write_session_end,
    feed_write_session_start,
    feed_write_release,
    io_github,
    reader,
)


REF_TS = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)


@pytest.fixture
def temp_feed_repo(monkeypatch):
    """Set up a temp framework root with an initialized activity-feed git repo."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        monkeypatch.delenv("SF_SKIP_FEED", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        repo = Path(tmp) / "activity-feed"
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", "init"],
            check=True,
        )
        yield repo


# === feed_write_session_start =============================================


def test_write_start_creates_log_file(temp_feed_repo):
    result = feed_write_session_start(
        handle="hazar", cwd="/home/test/Dev/sidecar", timestamp=REF_TS,
    )
    assert result.success is True
    assert result.entry_id != ""
    assert result.violation is None

    log_path = temp_feed_repo / "hazar.log.md"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "schema_version: 1" in content
    assert "framework_version: 1.0.0" in content
    assert "type: feed-entry" in content
    assert "handle: hazar" in content
    assert "## [2026-05-28 14:30] start | hazar | working in" in content


def test_write_start_with_continuation_hint(temp_feed_repo):
    result = feed_write_session_start(
        handle="hazar",
        cwd="/home/test/Dev/sidecar",
        timestamp=REF_TS,
        continuation_hint="resuming yesterday's auth work",
    )
    assert result.success is True
    content = (temp_feed_repo / "hazar.log.md").read_text()
    assert "(resuming yesterday's auth work)" in content


def test_write_start_rejects_overlong_continuation(temp_feed_repo):
    result = feed_write_session_start(
        handle="hazar",
        cwd="/Dev/sidecar",
        timestamp=REF_TS,
        continuation_hint="x" * 200,
    )
    assert result.success is False
    assert result.violation == "continuation-hint-too-long"


def test_write_start_skip_writes_nothing(temp_feed_repo):
    result = feed_write_session_start(
        handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS, skip=True,
    )
    assert result.success is True
    assert result.entry_id == ""
    assert result.pushed is False
    assert not (temp_feed_repo / "hazar.log.md").exists()


# === feed_write_session_end ===============================================


def test_write_end_renders_terse_format(temp_feed_repo):
    result = feed_write_session_end(
        handle="hazar",
        project="sidecar",
        task_brief="JWT middleware finished",
        files_touched=["src/auth/jwt.ts", "src/api/login.ts"],
        timestamp=REF_TS,
    )
    assert result.success is True
    content = (temp_feed_repo / "hazar.log.md").read_text()
    assert "## [2026-05-28 14:30] end | hazar | session complete" in content
    assert "Worked on sidecar — JWT middleware finished." in content
    assert "Touched: src/auth/jwt.ts, src/api/login.ts." in content


def test_write_end_rejects_code_fence(temp_feed_repo):
    result = feed_write_session_end(
        handle="hazar",
        project="sidecar",
        task_brief="```code``` snippet pasted",
        files_touched=["a.py"],
        timestamp=REF_TS,
    )
    assert result.success is False
    assert result.violation == "forbidden-substring"


def test_write_end_rejects_html_chars(temp_feed_repo):
    result = feed_write_session_end(
        handle="hazar",
        project="sidecar",
        task_brief="uses <div> rendering",
        files_touched=["a.py"],
        timestamp=REF_TS,
    )
    assert result.success is False
    assert result.violation == "html-bleed"


def test_write_end_rejects_missing_files(temp_feed_repo):
    result = feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix",
        files_touched=[], timestamp=REF_TS,
    )
    assert result.success is False
    assert result.violation == "missing-files"


def test_write_end_skip_writes_nothing(temp_feed_repo):
    result = feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="should not write",
        files_touched=["a.py"], timestamp=REF_TS, skip=True,
    )
    assert result.success is True
    assert result.entry_id == ""
    assert not (temp_feed_repo / "hazar.log.md").exists()


# === feed_write_release ===================================================


def test_write_release_renders(temp_feed_repo):
    result = feed_write_release(
        handle="hazar", version="v1.3.0", note="see CHANGELOG", timestamp=REF_TS,
    )
    assert result.success is True
    content = (temp_feed_repo / "hazar.log.md").read_text()
    assert "release | hazar | framework | v1.3.0 shipped — see CHANGELOG" in content


def test_write_release_skip_writes_nothing(temp_feed_repo):
    result = feed_write_release(
        handle="hazar", version="v1.3.0", note="see CHANGELOG",
        timestamp=REF_TS, skip=True,
    )
    assert result.success is True
    assert result.entry_id == ""
    assert not (temp_feed_repo / "hazar.log.md").exists()


# === idempotency ==========================================================


def test_duplicate_entries_within_minute_are_skipped(temp_feed_repo):
    r1 = feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix bug",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    r2 = feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix bug",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    assert r1.success is True
    assert r2.success is True
    assert r1.entry_id == r2.entry_id

    content = (temp_feed_repo / "hazar.log.md").read_text()
    assert content.count("Worked on sidecar — fix bug.") == 1


def test_different_minute_entries_both_persist(temp_feed_repo):
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix bug",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix bug",
        files_touched=["a.py"], timestamp=REF_TS + timedelta(minutes=5),
    )
    content = (temp_feed_repo / "hazar.log.md").read_text()
    assert content.count("Worked on sidecar — fix bug.") == 2


# === bootstrap pre-check (the "not-bootstrapped" violation) ===============


def test_writer_returns_not_bootstrapped_when_no_git(temp_feed_repo, tmp_path):
    """When local clone has no .git directory, writer returns violation=not-bootstrapped
    so the caller can surface 'run /sf:install Stage 3' instead of generic push error.
    """
    # Move framework root to a directory with NO git repo
    import os
    nogit = tmp_path / "nogit"
    nogit.mkdir(parents=True)
    os.environ["SF_FRAMEWORK_ROOT"] = str(nogit)
    try:
        result = feed_write_session_start(
            handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS,
        )
        assert result.success is False
        assert result.violation == "not-bootstrapped"
        assert "/sf:install" in (result.error or "")
    finally:
        os.environ["SF_FRAMEWORK_ROOT"] = str(temp_feed_repo.parent)


# === reader: parsing roundtrip ============================================


def test_reader_parses_what_writer_wrote(temp_feed_repo):
    feed_write_session_start(
        handle="hazar", cwd="/home/test/Dev/sidecar", timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix login regex",
        files_touched=["src/api/login.ts", "tests/login_test.ts"],
        timestamp=REF_TS + timedelta(hours=2),
    )

    entries = list(reader._parse_log_file(temp_feed_repo / "hazar.log.md"))
    assert len(entries) == 2

    e1, e2 = entries
    assert e1.kind == "start"
    assert e1.handle == "hazar"
    assert e1.timestamp == REF_TS
    assert e1.project == "sidecar"
    assert "working in" in e1.summary

    assert e2.kind == "end"
    assert e2.project == "sidecar"
    assert e2.summary == "fix login regex"
    assert e2.files == ("src/api/login.ts", "tests/login_test.ts")


def test_reader_parses_release_entry(temp_feed_repo):
    feed_write_release(
        handle="hazar", version="v1.3.0", note="see CHANGELOG", timestamp=REF_TS,
    )
    entries = list(reader._parse_log_file(temp_feed_repo / "hazar.log.md"))
    assert len(entries) == 1
    assert entries[0].kind == "release"
    assert "v1.3.0" in entries[0].summary


# === read_friends_tails ===================================================


def test_friends_tails_bucketing(temp_feed_repo):
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix",
        files_touched=["a.py"], timestamp=REF_TS + timedelta(hours=1),
    )
    feed_write_session_start(
        handle="friend-b", cwd="/Dev/restore", timestamp=REF_TS + timedelta(hours=2),
    )

    tail = reader.feed_read_friends_tails(
        own_handle="hazar", n_per_friend=5, include_self=True, refresh=False,
    )

    assert set(tail.friends.keys()) == {"hazar", "friend-b"}
    assert len(tail.friends["hazar"]) == 2
    assert len(tail.friends["friend-b"]) == 1
    assert "Activity Feed" in tail.formatted_header


def test_friends_tails_exclude_self(temp_feed_repo):
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    feed_write_session_start(handle="friend-b", cwd="/Dev/restore", timestamp=REF_TS)

    tail = reader.feed_read_friends_tails(
        own_handle="hazar", include_self=False, refresh=False,
    )
    assert "hazar" not in tail.friends
    assert "friend-b" in tail.friends


def test_friends_tails_n_per_friend_cap(temp_feed_repo):
    for i in range(10):
        feed_write_session_end(
            handle="hazar", project="sidecar", task_brief=f"task {i}",
            files_touched=["a.py"], timestamp=REF_TS + timedelta(minutes=i),
        )

    tail = reader.feed_read_friends_tails(
        own_handle="hazar", n_per_friend=3, refresh=False,
    )
    assert len(tail.friends["hazar"]) == 3
    assert "task 9" in tail.friends["hazar"][-1].summary


def test_friends_tails_max_tokens_truncates(temp_feed_repo):
    for i in range(20):
        feed_write_session_end(
            handle="hazar", project="sidecar", task_brief=f"task {i}",
            files_touched=["a.py"], timestamp=REF_TS + timedelta(minutes=i),
        )

    tail = reader.feed_read_friends_tails(
        own_handle="hazar", n_per_friend=20, max_tokens=50, refresh=False,
    )
    assert tail.truncated is True
    total = sum(len(es) for es in tail.friends.values())
    assert total < 20


# === read_all_entries =====================================================


def test_read_all_entries_filters_by_handle(temp_feed_repo):
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    feed_write_session_start(handle="friend-b", cwd="/Dev/restore", timestamp=REF_TS)

    only_hazar = reader.read_all_entries(from_handles=["hazar"])
    assert all(e.handle == "hazar" for e in only_hazar)


def test_read_all_entries_filters_by_project(temp_feed_repo):
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="fix",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="hazar", project="restore", task_brief="fix",
        files_touched=["b.py"], timestamp=REF_TS + timedelta(minutes=1),
    )

    sidecar_only = reader.read_all_entries(project_filter="sidecar")
    assert len(sidecar_only) == 1
    assert sidecar_only[0].project == "sidecar"


def test_read_all_entries_filters_by_since(temp_feed_repo):
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="old",
        files_touched=["a.py"], timestamp=REF_TS - timedelta(days=10),
    )
    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="new",
        files_touched=["a.py"], timestamp=REF_TS,
    )

    recent = reader.read_all_entries(since=REF_TS - timedelta(days=1))
    assert len(recent) == 1
    assert recent[0].task_brief if hasattr(recent[0], 'task_brief') else recent[0].summary
    assert (recent[0].summary or "") == "new"


# === staleness flag ======================================================


def test_stale_flag_when_no_pull_recorded(temp_feed_repo):
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    tail = reader.feed_read_friends_tails(own_handle="hazar", refresh=False)
    assert tail.stale is True


def test_not_stale_after_recent_pull(temp_feed_repo):
    io_github._record_state(temp_feed_repo, last_pull_ok=True)
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)
    tail = reader.feed_read_friends_tails(own_handle="hazar", refresh=False)
    assert tail.stale is False


# === io_github offline-queue behavior =====================================


def test_push_to_no_remote_queues_or_reports_error(temp_feed_repo):
    """Repo has no remote — push fails. Verify graceful degradation."""
    feed_write_session_start(handle="hazar", cwd="/Dev/sidecar", timestamp=REF_TS)

    log = (temp_feed_repo / "hazar.log.md").read_text()
    assert "start | hazar |" in log

    state = io_github._read_state(temp_feed_repo)
    assert isinstance(state, dict)
