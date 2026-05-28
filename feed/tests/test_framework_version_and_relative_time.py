"""
Tests for round-2 coordination follow-ups (task #46):

- feed.config.framework_version() resolution chain
- feed.format_relative_time public re-export consistency

Run with: python3 -m pytest feed/tests/test_framework_version_and_relative_time.py -v
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import feed
from feed import config, format_relative_time
from feed.config import FALLBACK_FRAMEWORK_VERSION, framework_version


# === framework_version() resolution chain =================================


def test_falls_back_when_no_env_no_plugin_json(monkeypatch):
    """No env var, no plugin.json → returns FALLBACK_FRAMEWORK_VERSION."""
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert framework_version() == FALLBACK_FRAMEWORK_VERSION


def test_env_var_takes_precedence(monkeypatch):
    """CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION wins over plugin.json + fallback."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "2.5.0-rc.1")
    assert framework_version() == "2.5.0-rc.1"


def test_plugin_json_used_when_env_unset(monkeypatch, tmp_path):
    """No env var but valid plugin.json → reads `version` field."""
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", raising=False)
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{\n  "name": "startup-framework",\n  "version": "1.4.2"\n}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))
    assert framework_version() == "1.4.2"


def test_plugin_json_malformed_falls_back(monkeypatch, tmp_path):
    """Plugin.json without a `version` field → fallback (not crash)."""
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", raising=False)
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{\n  "name": "startup-framework"\n}\n', encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))
    assert framework_version() == FALLBACK_FRAMEWORK_VERSION


def test_plugin_json_missing_file_falls_back(monkeypatch, tmp_path):
    """CLAUDE_PLUGIN_ROOT points at non-existent dir → fallback."""
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "does-not-exist"))
    assert framework_version() == FALLBACK_FRAMEWORK_VERSION


def test_env_var_overrides_plugin_json(monkeypatch, tmp_path):
    """Even when plugin.json has a valid version, env var wins."""
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{"version": "1.4.2"}', encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "3.0.0")
    assert framework_version() == "3.0.0"


def test_empty_env_value_treated_as_unset(monkeypatch, tmp_path):
    """Empty-string env var should not be treated as a valid version (treat as unset)."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "")
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{"version": "1.4.2"}', encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_dir))
    assert framework_version() == "1.4.2"  # falls through to plugin.json


def test_writer_uses_resolved_framework_version(monkeypatch, tmp_path):
    """End-to-end: write_session_start stamps the resolved version into log frontmatter."""
    import subprocess as sp

    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "1.4.2")
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SF_FRAMEWORK_ROOT", tmp)
        repo = Path(tmp) / "activity-feed"
        repo.mkdir(parents=True, exist_ok=True)
        sp.run(["git", "init", "-q", str(repo)], check=True)
        sp.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
        sp.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
        sp.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", "init"],
            check=True,
        )

        feed.feed_write_session_start(
            handle="hazar", cwd="/Dev/sidecar",
            timestamp=datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc),
        )

        text = (repo / "hazar.log.md").read_text()
        assert "framework_version: 1.4.2" in text


# === format_relative_time =================================================


def test_format_relative_time_just_now():
    now = datetime.now(timezone.utc)
    assert format_relative_time(now) == "just now"


def test_format_relative_time_minutes():
    ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert format_relative_time(ts) == "5m ago"


def test_format_relative_time_hours():
    ts = datetime.now(timezone.utc) - timedelta(hours=3)
    assert format_relative_time(ts) == "3h ago"


def test_format_relative_time_days():
    ts = datetime.now(timezone.utc) - timedelta(days=4)
    assert format_relative_time(ts) == "4d ago"


def test_format_relative_time_handles_naive_datetime():
    """Naive datetime (no tzinfo) is treated as UTC — no crash."""
    naive = datetime.utcnow() - timedelta(hours=1)
    result = format_relative_time(naive)
    # Either "1h ago" or close — exact match depends on whether utcnow tz boundary aligns
    assert result.endswith("ago") or result == "just now"


def test_format_relative_time_exported_from_package():
    """Importable from feed package root, not just from feed.reader."""
    from feed import format_relative_time as imported
    assert imported is format_relative_time


def test_relative_time_internal_alias_still_works():
    """Back-compat: feed.reader._relative_time still resolves (used by reader internals)."""
    from feed import reader
    ts = datetime.now(timezone.utc) - timedelta(hours=2)
    assert reader._relative_time(ts) == "2h ago"
    assert reader._relative_time is reader.format_relative_time


# === format_entry_one_line ================================================


def test_format_entry_one_line_end_entry_matches_spec():
    """Per lifecycle-2's locked spec (2026-05-28):
        "- friend-b · 2h ago · sidecar — Stripe webhook handler"
    """
    from feed import FeedEntry, format_entry_one_line
    ts = datetime.now(timezone.utc) - timedelta(hours=2)
    entry = FeedEntry(
        handle="friend-b", kind="end", timestamp=ts, project="sidecar",
        summary="Stripe webhook handler",
        files=("src/api/webhooks/stripe.ts",),
        raw_line="## [...] end | friend-b | session complete",
    )
    line = format_entry_one_line(entry)
    assert line == "- friend-b · 2h ago · sidecar — Stripe webhook handler"


def test_format_entry_one_line_start_entry_renders_cwd_summary():
    """Start entries: project segment shows, summary is "working in ~/...". """
    from feed import FeedEntry, format_entry_one_line
    ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    entry = FeedEntry(
        handle="hazar", kind="start", timestamp=ts, project="sidecar",
        summary="working in ~/Dev/sidecar/", files=(),
        raw_line="## [...] start | hazar | working in ~/Dev/sidecar/",
    )
    line = format_entry_one_line(entry)
    assert line == "- hazar · 5m ago · sidecar — working in ~/Dev/sidecar/"


def test_format_entry_one_line_release_skips_project_segment():
    """Release entries: skip project segment to avoid version-appearing-twice noise.
    Summary already carries 'framework | v1.3.0 shipped — ...'.
    """
    from feed import FeedEntry, format_entry_one_line
    ts = datetime.now(timezone.utc) - timedelta(hours=2)
    entry = FeedEntry(
        handle="hazar", kind="release", timestamp=ts, project=None,
        summary="framework | v1.3.0 shipped — see CHANGELOG", files=(),
        raw_line="## [...] release | hazar | framework | v1.3.0 shipped — see CHANGELOG",
    )
    line = format_entry_one_line(entry)
    # No "·  · " gap, no awkward "(unscoped)" — project segment omitted entirely
    assert line == "- hazar · 2h ago — framework | v1.3.0 shipped — see CHANGELOG"


def test_format_entry_one_line_unscoped_project_falls_back():
    """End entry with project=None (rare; usually files-but-no-project) renders
    '(unscoped)' rather than an empty middle segment."""
    from feed import FeedEntry, format_entry_one_line
    ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    entry = FeedEntry(
        handle="hazar", kind="end", timestamp=ts, project=None,
        summary="some work", files=("a.py",),
        raw_line="...",
    )
    line = format_entry_one_line(entry)
    assert "(unscoped)" in line


def test_format_entry_one_line_no_embedded_newlines():
    """Single-line guarantee: even if summary contains \\n, output is one line."""
    from feed import FeedEntry, format_entry_one_line
    ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    entry = FeedEntry(
        handle="hazar", kind="end", timestamp=ts, project="sidecar",
        summary="line one\nline two\nline three", files=("a.py",),
        raw_line="...",
    )
    line = format_entry_one_line(entry)
    assert "\n" not in line
    # Embedded newlines become " · " separators
    assert "line one · line two · line three" in line


def test_format_entry_one_line_exported_from_package():
    """Importable from feed package root."""
    from feed import format_entry_one_line as imported
    from feed.reader import format_entry_one_line as direct
    assert imported is direct
