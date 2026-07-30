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

import pytest

from lib.governance.backup_gate import BackupRequired, require_backup


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
    # a stamped-but-untouched skeleton page (no frontmatter, heading-only
    # body) is not "grown content" — must not trip the gate even with no
    # backup configured.
    (tmp_path / "index.md").write_text("# Wiki\n<!-- skeleton -->\n")
    monkeypatch.setattr("lib.governance.backup_gate.backup_configured", lambda root: False)
    require_backup(tmp_path, operation="bootstrap-project")
