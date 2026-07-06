"""
End-to-end test for the routine-spec 2→3 migration (Task 6.3), mirroring the
structure of donor's routine-spec-1→2 test (`skills/wiki-migration/tests/
test_routine_spec_migration.py`) but scoped to just this migration script —
the doctor/chain-computer discovery machinery donor's test also exercises is
out of scope here (that subsystem hasn't been carried into RenOS yet).

Drives `migrate.sh` via subprocess against a hand-built v2 fixture (the same
fixture shape as donor's real routine-spec template, already carrying the
verification_strategy/verification_tools fields the 1-to-2 migration adds).

Run with: uv run pytest tests/migrations/test_routine_spec_2_to_3.py -v
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_MIG = Path(__file__).resolve().parents[2] / "migrations" / "routine-spec-2-to-3"
_MIGRATE = _MIG / "migrate.sh"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "routine-spec-v2" / "sample-1.md"


def _run(cmd: list[str], **env: str) -> subprocess.CompletedProcess[str]:
    base = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    base.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=base)


def _migrate(page: Path, wiki: Path, snap: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        ["bash", str(_MIGRATE), str(page)],
        REN_WIKI_ROOT=str(wiki), REN_SNAPSHOT_DIR=str(snap),
    )


@pytest.fixture
def staged(tmp_path: Path):
    """A wiki tree with the v2 fixture copied in + a byte-identical snapshot tree."""
    wiki = tmp_path / "wiki"
    (wiki / "routines").mkdir(parents=True)
    page = wiki / "routines" / "sample-1.md"
    shutil.copy(_FIXTURE, page)
    snap = tmp_path / "snap"
    (snap / "routines").mkdir(parents=True)
    shutil.copy(_FIXTURE, snap / "routines" / "sample-1.md")
    return wiki, page, snap


def test_bumps_schema_and_adds_allowlist_and_exit_criterion(staged):
    wiki, page, snap = staged
    r = _migrate(page, wiki, snap)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout

    text = page.read_text(encoding="utf-8")
    assert "schema_version: 3" in text
    assert "schema_version: 2" not in text
    assert "allowlist:" in text
    assert "  paths: []" in text
    assert "  capabilities: []" in text
    assert 'exit_criterion: "MIGRATED — declare a real exit criterion"' in text


def test_overwrites_old_free_text_failure_handler(staged):
    wiki, page, snap = staged
    original = page.read_text(encoding="utf-8")
    assert 'failure_handler: "email me@example.com via Resend MCP"' in original

    _migrate(page, wiki, snap)

    migrated = page.read_text(encoding="utf-8")
    assert "failure_handler: notify-journal" in migrated
    assert "email me@example.com via Resend MCP" not in migrated
    assert migrated.count("failure_handler:") == 1


def test_preserves_pre_existing_verification_fields_from_1_to_2(staged):
    """The v2 fixture already carries verification_strategy/verification_tools
    (added by the 1-to-2 migration) — 2-to-3 must not touch them."""
    wiki, page, snap = staged
    _migrate(page, wiki, snap)

    text = page.read_text(encoding="utf-8")
    assert "verification_strategy: manual" in text
    assert "verification_tools: []" in text


def test_body_byte_identical(staged):
    wiki, page, snap = staged
    orig_body = _FIXTURE.read_text(encoding="utf-8").split("---\n", 2)[2]
    _migrate(page, wiki, snap)
    new_body = page.read_text(encoding="utf-8").split("---\n", 2)[2]
    assert new_body == orig_body


def test_idempotent_rerun_skips(staged):
    wiki, page, snap = staged
    _migrate(page, wiki, snap)
    after_first = page.read_text(encoding="utf-8")

    r2 = _migrate(page, wiki, snap)
    assert r2.returncode == 0
    assert "SKIP" in r2.stdout
    assert page.read_text(encoding="utf-8") == after_first


def test_does_not_double_insert_allowlist_on_rerun(staged):
    wiki, page, snap = staged
    _migrate(page, wiki, snap)
    _migrate(page, wiki, snap)  # idempotent no-op, but prove no duplication either way

    text = page.read_text(encoding="utf-8")
    assert text.count("allowlist:") == 1
    assert text.count("exit_criterion:") == 1


def test_missing_env_vars_fails_with_exit_2(staged):
    wiki, page, snap = staged
    r = _run(["bash", str(_MIGRATE), str(page)])  # no REN_WIKI_ROOT/REN_SNAPSHOT_DIR
    assert r.returncode == 2


def test_missing_page_argument_fails_with_exit_2(staged):
    wiki, page, snap = staged
    r = _run(["bash", str(_MIGRATE)], REN_WIKI_ROOT=str(wiki), REN_SNAPSHOT_DIR=str(snap))
    assert r.returncode == 2


def test_nonexistent_page_fails_with_exit_2(staged, tmp_path):
    wiki, page, snap = staged
    r = _run(
        ["bash", str(_MIGRATE), str(tmp_path / "does-not-exist.md")],
        REN_WIKI_ROOT=str(wiki), REN_SNAPSHOT_DIR=str(snap),
    )
    assert r.returncode == 2
