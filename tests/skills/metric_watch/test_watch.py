"""
Tests for skills.metric-watch.lib — the §3.5 minimal metric-watch routine
(Task 6.3).

Each of the four checks is tested independently on a synthetic fixture
state, plus: quiet state → no findings, one check crashing → the other
findings still land + a check-error finding, and findings land in the
journal via a routine-writer NOOP entry on "_metric-watch".

Every test redirects ren_paths' framework root + plugin data dir to
tmp_path via env vars — never the real ~/.renos or ~/.claude/plugins/data.

Run with: uv run pytest tests/skills/metric_watch/test_watch.py -v
"""

from __future__ import annotations

import importlib
import time

import pytest

from lib.instrument import collect
from lib.memory import journal
from lib.ren_paths import wiki_root

metric_watch = importlib.import_module("skills.metric-watch.lib")


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_DATA", "CLAUDE_SESSION_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    clean_path_env.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_recent_tarball(tmp_path):
    """Keep the backup check quiet: a fresh tarball in the plugin's backups dir."""
    backups_dir = tmp_path / "plugin-data" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    (backups_dir / "wiki-2026-01-01.tar.gz").write_bytes(b"fake tarball content")


# --------------------------------------------------------------------- quiet


def test_quiet_state_produces_no_findings(wiki, tmp_path):
    _make_recent_tarball(tmp_path)  # keep backup check quiet
    # No injected_bytes, no classifier events, no prior memory snapshot, no md files.
    findings = metric_watch.watch(session="sess-1")
    assert findings == []


# -------------------------------------------------------------------- budget


def test_budget_finding_fires_on_injection_growth(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    for _ in range(5):
        collect.record(collect.KIND_INJECTED_BYTES, {"bytes": 100, "session": "s"})
    collect.record(collect.KIND_INJECTED_BYTES, {"bytes": 600, "session": "s"})  # 6x median

    findings = metric_watch.watch(session="sess-1")

    kinds = [f["kind"] for f in findings]
    assert "injection-budget-growth" in kinds


def test_budget_finding_does_not_fire_on_stable_injection_size(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    for _ in range(6):
        collect.record(collect.KIND_INJECTED_BYTES, {"bytes": 100, "session": "s"})

    findings = metric_watch.watch(session="sess-1")
    kinds = [f["kind"] for f in findings]
    assert "injection-budget-growth" not in kinds


# --------------------------------------------------------------- memory growth


def test_memory_growth_finding_fires_on_second_run_after_growth(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    (wiki / "a.md").write_text("x" * 100, encoding="utf-8")
    (wiki / "b.md").write_text("x" * 100, encoding="utf-8")

    first = metric_watch.watch(session="sess-1")
    assert not any(f["kind"] == "memory-growth" for f in first)  # first run: nothing to compare

    for i in range(5):
        (wiki / f"new{i}.md").write_text("x" * 500, encoding="utf-8")

    second = metric_watch.watch(session="sess-2")
    assert any(f["kind"] == "memory-growth" for f in second)


def test_memory_growth_finding_does_not_fire_without_growth(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    (wiki / "a.md").write_text("x" * 100, encoding="utf-8")

    metric_watch.watch(session="sess-1")
    second = metric_watch.watch(session="sess-2")  # no new files added

    assert not any(f["kind"] == "memory-growth" for f in second)


# ------------------------------------------------------------------ classifier


def test_classifier_fail_closed_finding_fires(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "fail_closed", "reason": "boom"})

    findings = metric_watch.watch(session="sess-1")
    matching = [f for f in findings if f["kind"] == "classifier-fail-closed"]
    assert len(matching) == 1
    assert matching[0]["count"] == 1


def test_classifier_no_llm_event_does_not_fire(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "no_llm"})

    findings = metric_watch.watch(session="sess-1")
    assert not any(f["kind"] == "classifier-fail-closed" for f in findings)


def test_classifier_only_fires_for_new_events_across_runs(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "fail_closed"})

    first = metric_watch.watch(session="sess-1")
    assert any(f["kind"] == "classifier-fail-closed" for f in first)

    second = metric_watch.watch(session="sess-2")  # no new classifier events
    assert not any(f["kind"] == "classifier-fail-closed" for f in second)


# ---------------------------------------------------------------------- backup


def test_backup_unconfigured_finding_fires_with_nothing_set_up(wiki, tmp_path):
    findings = metric_watch.watch(session="sess-1")
    assert any(f["kind"] == "backup-unconfigured" for f in findings)


def test_backup_finding_quiet_with_recent_tarball(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    findings = metric_watch.watch(session="sess-1")
    assert not any(f["kind"] == "backup-unconfigured" for f in findings)


def test_backup_finding_fires_with_stale_tarball_only(wiki, tmp_path):
    import os

    backups_dir = tmp_path / "plugin-data" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stale = backups_dir / "wiki-old.tar.gz"
    stale.write_bytes(b"old")
    old_time = time.time() - (10 * 86400)  # 10 days old
    os.utime(stale, (old_time, old_time))

    findings = metric_watch.watch(session="sess-1")
    assert any(f["kind"] == "backup-unconfigured" for f in findings)


# --------------------------------------------------------------- crash isolation


def test_one_check_crashing_does_not_prevent_others(wiki, tmp_path, monkeypatch):
    _make_recent_tarball(tmp_path)
    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "fail_closed"})

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash in memory-growth check")

    monkeypatch.setattr(metric_watch, "_check_memory_growth", _boom)

    findings = metric_watch.watch(session="sess-1")

    kinds = [f["kind"] for f in findings]
    assert "check-error" in kinds
    error_finding = next(f for f in findings if f["kind"] == "check-error")
    assert error_finding["check"] == "memory_growth"
    assert "simulated crash" in error_finding["error"]

    # The other checks still ran and produced their own findings.
    assert "classifier-fail-closed" in kinds


# ------------------------------------------------------------------------ journal


def test_findings_land_in_journal_with_routine_writer(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    findings = metric_watch.watch(session="sess-1")

    entries = journal.entries(page="_metric-watch")
    assert len(entries) == 1
    assert entries[0]["writer"] == "routine"
    assert entries[0]["op"] == "NOOP"
    assert entries[0]["findings"] == findings


def test_multiple_runs_produce_multiple_journal_lines(wiki, tmp_path):
    _make_recent_tarball(tmp_path)
    metric_watch.watch(session="sess-1")
    metric_watch.watch(session="sess-2")

    entries = journal.entries(page="_metric-watch")
    assert len(entries) == 2
