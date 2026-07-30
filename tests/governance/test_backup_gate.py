"""
Tests for lib.governance.backup_gate — the backup precondition gate (0.6.0
Task 4, issue #11 §2).

Two of the last four releases fixed data-destroying bugs; a successful
backup is the only real mitigation, and until now it's been a skippable
install offer. `require_backup` makes a configured backup a precondition for
the first ingest-project/bootstrap-project write that would land on a
POPULATED wiki — a fresh/empty wiki always passes (no chicken-and-egg: the
very first bootstrap must be able to run before there's anything to back
up).

Run with: uv run pytest tests/governance/test_backup_gate.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.governance.backup_gate import BackupRequired, require_backup
from lib.skeleton import stamp_skeleton

SKELETON_ROOT = Path(__file__).resolve().parents[2] / "wiki-skeleton"

_PLACEHOLDERS = {
    "handle": "test-friend",
    "name": "Test Friend",
    "today": "2026-01-01",
    "framework_version": "0.6.0",
}


def _stamp_master(tmp_path, monkeypatch) -> Path:
    """Stamp the REAL master profile into a tmp wiki and return its root.

    stamp_skeleton routes writes through lib.memory.write_apply, which
    resolves pages against ren_paths.wiki_root() — so the env override must
    make wiki_root() == the target_root we pass (see lib/skeleton.py's module
    docstring)."""
    target = tmp_path / "wiki"
    monkeypatch.setenv("REN_WIKI_ROOT", str(target))
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / ".renos"))
    stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_PLACEHOLDERS,
    )
    return target


def test_fresh_wiki_passes(tmp_path):
    # empty wiki: nothing to lose yet — no chicken-and-egg on first bootstrap
    require_backup(tmp_path, operation="bootstrap-project")


def test_populated_wiki_without_backup_raises(tmp_path, monkeypatch):
    (tmp_path / "maps").mkdir(parents=True)
    (tmp_path / "maps" / "l2-map.md").write_text("grown content")
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    with pytest.raises(BackupRequired) as e:
        require_backup(tmp_path, operation="ingest-project")
    assert "/ren:backup" in str(e.value)  # message must be actionable
    assert "ingest-project" in str(e.value)  # message must name the operation
    assert "RENOS_ALLOW_NO_BACKUP" in str(e.value)  # message must name the override


def test_override_env_downgrades_to_warning(tmp_path, monkeypatch, capsys):
    (tmp_path / "maps").mkdir(parents=True)
    (tmp_path / "maps" / "l2-map.md").write_text("grown content")
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    monkeypatch.setenv("RENOS_ALLOW_NO_BACKUP", "1")
    require_backup(tmp_path, operation="ingest-project")  # no raise
    assert "no backup configured" in capsys.readouterr().err.lower()


def test_configured_backup_passes(tmp_path, monkeypatch):
    (tmp_path / "maps").mkdir(parents=True)
    (tmp_path / "maps" / "l2-map.md").write_text("grown content")
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: True)
    require_backup(tmp_path, operation="ingest-project")


def test_skeleton_only_wiki_passes(tmp_path, monkeypatch):
    """FIX ROUND 1 (CRITICAL): this test used to hand-write a synthetic
    skeleton (`# Wiki\\n<!-- skeleton -->`), which is why a false positive
    shipped — the REAL shipped templates carry guidance prose, so every
    stamped page looked "grown" and a friend's first ingest/second bootstrap
    on a pristine post-/ren:install wiki tripped the gate. The regression pin
    is now real `stamp_skeleton()` output."""
    target = _stamp_master(tmp_path, monkeypatch)
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    require_backup(target, operation="bootstrap-project")


def test_skeleton_plus_project_skeleton_passes(tmp_path, monkeypatch):
    """The second bootstrap-project on a wiki holding only a first project's
    stamped (untouched) overview page must still pass."""
    target = _stamp_master(tmp_path, monkeypatch)
    stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="project",
        placeholders=_PLACEHOLDERS,
        path_prefix="projects/demo/",
    )
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    require_backup(target, operation="bootstrap-project")


def test_grown_project_page_on_real_skeleton_raises(tmp_path, monkeypatch):
    """...but once a project page actually holds the friend's content, the
    gate MUST fire."""
    target = _stamp_master(tmp_path, monkeypatch)
    (target / "projects" / "demo").mkdir(parents=True)
    (target / "projects" / "demo" / "map.md").write_text(
        "# demo\n\n- [auth] → decisions/003-auth.md#choice (w-123)\n", encoding="utf-8"
    )
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    with pytest.raises(BackupRequired):
        require_backup(target, operation="ingest-project")


def test_grown_research_page_on_real_skeleton_raises(tmp_path, monkeypatch):
    target = _stamp_master(tmp_path, monkeypatch)
    (target / "research" / "sqlite-vs-pg.md").write_text(
        "# SQLite vs Postgres\n\nWe picked SQLite because...\n", encoding="utf-8"
    )
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    with pytest.raises(BackupRequired):
        require_backup(target, operation="ingest-project")


def test_grown_global_page_on_real_skeleton_raises(tmp_path, monkeypatch):
    """`global/` holds human-gated promoted doctrine (the instruction plane,
    lib.memory.promotion.GLOBAL_PREFIX) — the highest-value, least-
    regenerable content the wiki can hold. A wiki with a promotion but no
    project content must still be judged populated."""
    target = _stamp_master(tmp_path, monkeypatch)
    (target / "global").mkdir(parents=True)
    (target / "global" / "testing-philosophy.md").write_text(
        "---\n"
        "type: doctrine\n"
        "promoted-from: research/testing-notes.md (w-042)\n"
        "---\n\n"
        "# Testing Philosophy\n\n"
        "Write the test first, watch it fail, then implement. Coverage "
        "without a red phase first is not TDD — it's just measurement.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    with pytest.raises(BackupRequired):
        require_backup(target, operation="ingest-project")


def test_grown_log_on_real_skeleton_raises(tmp_path, monkeypatch):
    """The stamped log has exactly one `init` entry; a second entry means the
    friend has real history worth backing up."""
    target = _stamp_master(tmp_path, monkeypatch)
    with (target / "log.md").open("a", encoding="utf-8") as handle:
        handle.write("\n## [2026-07-30] ingest | brought in the api repo\n")
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    with pytest.raises(BackupRequired):
        require_backup(target, operation="ingest-project")
