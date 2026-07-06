"""
Tests for skills.wiki-migration.lib — minimal registry + thin verify/apply
primitive (Task 7.3).

Covers: registry loading, migration-chain filtering, running BOTH migration
directories (routine-spec-1-to-2 which expects SF_* env vars, and
routine-spec-2-to-3 which expects REN_*) through the SAME env-mapping-shimmed
runner, and verify_page against both migrations' real verify.json files.

Run with: uv run pytest tests/skills/wiki_migration/test_wiki_migration.py -v
"""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest

wiki_migration = importlib.import_module("skills.wiki-migration.lib")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATIONS = _REPO_ROOT / "migrations"
_MIG_1_TO_2 = _MIGRATIONS / "routine-spec-1-to-2"
_MIG_2_TO_3 = _MIGRATIONS / "routine-spec-2-to-3"
_FIXTURE_V1 = _REPO_ROOT / "tests" / "migrations" / "fixtures"  # sibling fixtures dir, if present
_V2_FIXTURE = _REPO_ROOT / "tests" / "migrations" / "fixtures" / "routine-spec-v2" / "sample-1.md"


# ------------------------------------------------------------------ registry


def test_load_registry_returns_page_types():
    registry = wiki_migration.load_registry()
    assert "routine-spec" in registry["page_types"]
    assert registry["page_types"]["routine-spec"]["current"] == 3


def test_load_registry_missing_file_returns_empty_dict(tmp_path):
    assert wiki_migration.load_registry(tmp_path / "nope.json") == {}


def test_load_registry_malformed_json_returns_empty_dict(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    assert wiki_migration.load_registry(bad) == {}


def test_migration_chain_full_from_version_1():
    chain = wiki_migration.migration_chain("routine-spec", from_version=1)
    assert chain == ["routine-spec-1-to-2", "routine-spec-2-to-3"]


def test_migration_chain_partial_from_version_2():
    chain = wiki_migration.migration_chain("routine-spec", from_version=2)
    assert chain == ["routine-spec-2-to-3"]


def test_migration_chain_empty_from_version_3():
    chain = wiki_migration.migration_chain("routine-spec", from_version=3)
    assert chain == []


def test_migration_chain_unknown_page_type_returns_empty():
    assert wiki_migration.migration_chain("no-such-type", from_version=1) == []


# -------------------------------------------------------------- run_migration


@pytest.fixture
def v1_routine_page(tmp_path):
    """A minimal v1-shaped routine-spec page, hand-built (donor's v1 fixture
    shape) so the 1-to-2 migration (SF_* env vars) has something to run on."""
    wiki = tmp_path / "wiki"
    (wiki / "routines").mkdir(parents=True)
    page = wiki / "routines" / "sample.md"
    page.write_text(
        "---\n"
        "title: \"Routine: x\"\n"
        "type: routine-spec\n"
        "schema_version: 1\n"
        "framework_version: \"0.2.0\"\n"
        "name: \"x\"\n"
        "---\n\n# Routine: x\n",
        encoding="utf-8",
    )
    snap = tmp_path / "snap"
    (snap / "routines").mkdir(parents=True)
    shutil.copy(page, snap / "routines" / "sample.md")
    return wiki, page, snap


@pytest.fixture
def v2_routine_page(tmp_path):
    """A v2-shaped routine-spec page (built from the shared v2 fixture used
    by tests/migrations/test_routine_spec_2_to_3.py), for the 2-to-3
    migration (REN_* env vars)."""
    wiki = tmp_path / "wiki"
    (wiki / "routines").mkdir(parents=True)
    page = wiki / "routines" / "sample.md"
    shutil.copy(_V2_FIXTURE, page)
    snap = tmp_path / "snap"
    (snap / "routines").mkdir(parents=True)
    shutil.copy(_V2_FIXTURE, snap / "routines" / "sample.md")
    return wiki, page, snap


def test_run_migration_1_to_2_via_env_shim(v1_routine_page):
    wiki, page, snap = v1_routine_page
    result = wiki_migration.run_migration(_MIG_1_TO_2, page, wiki, snap)

    assert result.returncode == 0, result.stderr
    assert not result.skipped
    text = page.read_text(encoding="utf-8")
    assert "schema_version: 2" in text
    assert "verification_strategy: manual" in text


def test_run_migration_2_to_3_via_env_shim(v2_routine_page):
    wiki, page, snap = v2_routine_page
    result = wiki_migration.run_migration(_MIG_2_TO_3, page, wiki, snap)

    assert result.returncode == 0, result.stderr
    assert not result.skipped
    text = page.read_text(encoding="utf-8")
    assert "schema_version: 3" in text
    assert "failure_handler: notify-journal" in text


def test_run_migration_full_chain_1_to_3(v1_routine_page):
    """The same runner drives BOTH migration dirs in sequence, despite one
    expecting SF_* and the other REN_* — proving the env-mapping shim works
    end to end, not just per-migration."""
    wiki, page, snap = v1_routine_page

    r1 = wiki_migration.run_migration(_MIG_1_TO_2, page, wiki, snap)
    assert r1.returncode == 0, r1.stderr

    r2 = wiki_migration.run_migration(_MIG_2_TO_3, page, wiki, snap)
    assert r2.returncode == 0, r2.stderr

    text = page.read_text(encoding="utf-8")
    assert "schema_version: 3" in text
    assert "failure_handler: notify-journal" in text
    assert "verification_strategy: manual" in text  # 1-to-2's field survived 2-to-3


def test_run_migration_idempotent_rerun_reports_skip(v2_routine_page):
    wiki, page, snap = v2_routine_page
    wiki_migration.run_migration(_MIG_2_TO_3, page, wiki, snap)

    second = wiki_migration.run_migration(_MIG_2_TO_3, page, wiki, snap)
    assert second.returncode == 0
    assert second.skipped


# ----------------------------------------------------------------- verify_page


def test_verify_page_passes_after_1_to_2_migration(v1_routine_page):
    wiki, page, snap = v1_routine_page
    wiki_migration.run_migration(_MIG_1_TO_2, page, wiki, snap)

    passed, failures = wiki_migration.verify_page(_MIG_1_TO_2 / "verify.json", page)
    assert passed, failures


def test_verify_page_passes_after_2_to_3_migration(v2_routine_page):
    wiki, page, snap = v2_routine_page
    wiki_migration.run_migration(_MIG_2_TO_3, page, wiki, snap)

    passed, failures = wiki_migration.verify_page(_MIG_2_TO_3 / "verify.json", page)
    assert passed, failures


def test_verify_page_fails_before_migration(v2_routine_page):
    wiki, page, snap = v2_routine_page  # still schema_version: 2, not migrated

    passed, failures = wiki_migration.verify_page(_MIG_2_TO_3 / "verify.json", page)
    assert not passed
    assert any("schema_version" in f for f in failures)


def test_verify_page_dotted_path_field_lookup(v2_routine_page):
    wiki, page, snap = v2_routine_page
    wiki_migration.run_migration(_MIG_2_TO_3, page, wiki, snap)

    # allowlist.paths / allowlist.capabilities are nested — verify.json's
    # yaml.present assertions for these must resolve via dotted-path lookup.
    passed, failures = wiki_migration.verify_page(_MIG_2_TO_3 / "verify.json", page)
    assert passed, failures
