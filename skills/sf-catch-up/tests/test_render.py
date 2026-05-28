"""
Tests for the /sf:catch-up renderer (task #22).

Covers the 4-stage pipeline: bootstrap-check, filter, group+overlap, render. Uses
feed fixtures populated via the locked split-writer API, then runs the renderer
via subprocess so we exercise the actual CLI surface and exit codes.

Run with: python3 -m pytest skills/sf-catch-up/tests/ -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from feed import feed_write_session_end, feed_write_session_start, feed_write_release


REF_TS = datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc)
RENDER_SCRIPT = REPO_ROOT / "skills" / "sf-catch-up" / "scripts" / "render.py"


@pytest.fixture
def temp_feed_repo(monkeypatch):
    """Initialized git repo so the writers work; SF_FRAMEWORK_ROOT redirected."""
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


def run_render(tmp_root: str, *args: str) -> tuple[int, str, str]:
    """Invoke the render script with given CLI args. Returns (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    env["SF_FRAMEWORK_ROOT"] = tmp_root
    result = subprocess.run(
        [sys.executable, str(RENDER_SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )
    return result.returncode, result.stdout, result.stderr


# --- bootstrap pre-check --------------------------------------------------


def test_returns_2_when_not_bootstrapped(monkeypatch, tmp_path):
    """No .git in <root>/activity-feed → exit 2 + 'Run /sf:install Stage 3' on stderr."""
    nogit_root = tmp_path / "nogit"
    nogit_root.mkdir()
    (nogit_root / "activity-feed").mkdir()
    exit_code, _, stderr = run_render(str(nogit_root))
    assert exit_code == 2
    assert "/sf:install" in stderr


# --- empty result ---------------------------------------------------------


def test_returns_3_when_no_entries_match(temp_feed_repo):
    """Initialized repo but no entries → exit 3 + 'No activity' message."""
    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 3
    assert "No activity" in stdout


def test_empty_message_suggests_widening_filters(temp_feed_repo):
    """User-friendly: tell them how to broaden the search."""
    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent), "nope-project")
    assert exit_code == 3
    assert "--days" in stdout or "filters" in stdout


# --- basic rendering ------------------------------------------------------


def test_renders_by_project_section(temp_feed_repo):
    feed_write_session_start(
        handle="friend-b", cwd="/Dev/sidecar", timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="JWT done",
        files_touched=["src/auth/jwt.ts"], timestamp=REF_TS + timedelta(hours=1),
    )
    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    assert "## By project" in stdout
    assert "### sidecar" in stdout
    assert "**friend-b**" in stdout
    assert "JWT done" in stdout


def test_excludes_self_by_default(temp_feed_repo):
    """Default: own entries excluded so user sees what OTHERS did."""
    # Write own identity so 'self' is defined
    wiki = Path(os.environ["SF_FRAMEWORK_ROOT"]) / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "identity.md").write_text(
        "---\nschema_version: 1\nhandle: hazar\n---\n", encoding="utf-8"
    )

    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="own work",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="other work",
        files_touched=["b.py"], timestamp=REF_TS + timedelta(minutes=5),
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    assert "other work" in stdout
    assert "own work" not in stdout


def test_include_self_flag_includes_own(temp_feed_repo):
    wiki = Path(os.environ["SF_FRAMEWORK_ROOT"]) / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "identity.md").write_text(
        "---\nschema_version: 1\nhandle: hazar\n---\n", encoding="utf-8"
    )

    feed_write_session_end(
        handle="hazar", project="sidecar", task_brief="own work",
        files_touched=["a.py"], timestamp=REF_TS,
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent), "--include-self")
    assert exit_code == 0
    assert "own work" in stdout


def test_excludes_releases_by_default(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="real work",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_release(
        handle="friend-b", version="v1.3.0", note="see CHANGELOG", timestamp=REF_TS,
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    assert "real work" in stdout
    assert "v1.3.0" not in stdout


def test_include_releases_flag_shows_them(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="real work",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_release(
        handle="friend-b", version="v1.3.0", note="see CHANGELOG", timestamp=REF_TS,
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent), "--include-releases")
    assert exit_code == 0
    assert "v1.3.0" in stdout


# --- filters --------------------------------------------------------------


def test_project_substring_filter(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="sidecar work",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="friend-c", project="restore", task_brief="restore work",
        files_touched=["b.py"], timestamp=REF_TS + timedelta(minutes=1),
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent), "side")
    assert exit_code == 0
    assert "sidecar work" in stdout
    assert "restore work" not in stdout


def test_from_handle_filter_repeatable(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="b work",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="friend-c", project="sidecar", task_brief="c work",
        files_touched=["b.py"], timestamp=REF_TS + timedelta(minutes=1),
    )
    feed_write_session_end(
        handle="friend-d", project="sidecar", task_brief="d work",
        files_touched=["c.py"], timestamp=REF_TS + timedelta(minutes=2),
    )

    exit_code, stdout, _ = run_render(
        str(temp_feed_repo.parent), "--from", "friend-b", "--from", "friend-c",
    )
    assert exit_code == 0
    assert "b work" in stdout
    assert "c work" in stdout
    assert "d work" not in stdout


def test_days_filter_excludes_old_entries(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="too old",
        files_touched=["a.py"],
        timestamp=datetime.now(timezone.utc) - timedelta(days=60),
    )
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="recent",
        files_touched=["b.py"], timestamp=datetime.now(timezone.utc) - timedelta(days=2),
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent), "--days", "30")
    assert exit_code == 0
    assert "recent" in stdout
    assert "too old" not in stdout


# --- overlap detection ----------------------------------------------------


def test_overlap_warning_when_two_friends_touched_same_file(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="b touched jwt",
        files_touched=["src/auth/jwt.ts"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="friend-c", project="sidecar", task_brief="c also touched jwt",
        files_touched=["src/auth/jwt.ts"], timestamp=REF_TS + timedelta(hours=2),
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    assert "⚠️" in stdout
    assert "Overlap" in stdout
    assert "friend-b" in stdout and "friend-c" in stdout
    assert "src/auth/jwt.ts" in stdout


def test_no_overlap_warning_when_only_one_friend_touched(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="just me",
        files_touched=["src/auth/jwt.ts"], timestamp=REF_TS,
    )
    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    assert "Overlap" not in stdout


# --- footer ---------------------------------------------------------------


def test_footer_shows_source_attribution(temp_feed_repo):
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="x",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    feed_write_session_end(
        handle="friend-c", project="sidecar", task_brief="y",
        files_touched=["b.py"], timestamp=REF_TS + timedelta(minutes=1),
    )

    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    assert "[feed]" in stdout
    assert "friend-b.log.md" in stdout
    assert "friend-c.log.md" in stdout


def test_stale_banner_when_pull_failed(temp_feed_repo):
    """No remote → pull fails → banner at top of output."""
    feed_write_session_end(
        handle="friend-b", project="sidecar", task_brief="x",
        files_touched=["a.py"], timestamp=REF_TS,
    )
    exit_code, stdout, _ = run_render(str(temp_feed_repo.parent))
    assert exit_code == 0
    # Either banner shown OR sync is "never"/old enough — both signal stale appropriately
    assert "Stale" in stdout or "synced never" in stdout or "stale" in stdout
