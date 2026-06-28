"""
End-to-end test for the routine-spec 1→2 migration (C2 — the framework's first
real migration). Drives the bash migrate.sh + verify-page.sh against a fixture,
and the discovery scripts (compute-migration-chain.sh + doctor check-schemas.sh)
against a tmp wiki, per ADR-027 / MIGRATION_PATTERN.md.

Run with:
    python3 -m pytest skills/wiki-migration/tests/ -q
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_WM = Path(__file__).resolve().parents[1]              # skills/wiki-migration/
_REPO = _WM.parents[1]                                 # repo root
_MIG = _WM / "migrations" / "routine-spec-1-to-2"
_MIGRATE = _MIG / "migrate.sh"
_VERIFY_JSON = _MIG / "verify.json"
_VERIFY_PAGE = _WM / "scripts" / "verify-page.sh"
_CHAIN = _WM / "scripts" / "compute-migration-chain.sh"
_SCHEMAS = _WM / "schemas.json"
_DOCTOR_CHECK = _REPO / "skills" / "doctor" / "scripts" / "check-schemas.sh"
_FIXTURE = _WM / "tests" / "fixtures" / "routine-spec-v1" / "sample-1.md"


def _run(cmd: list[str], **env: str) -> subprocess.CompletedProcess[str]:
    base = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    base.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=base)


def _migrate(page: Path, wiki: Path, snap: Path) -> subprocess.CompletedProcess[str]:
    return _run(["bash", str(_MIGRATE), str(page)],
                SF_WIKI_ROOT=str(wiki), SF_SNAPSHOT_DIR=str(snap))


@pytest.fixture
def staged(tmp_path: Path):
    """A wiki tree with the v1 fixture copied in + a byte-identical snapshot tree."""
    wiki = tmp_path / "wiki"
    (wiki / "routines").mkdir(parents=True)
    page = wiki / "routines" / "sample-1.md"
    shutil.copy(_FIXTURE, page)
    snap = tmp_path / "snap"
    (snap / "routines").mkdir(parents=True)
    shutil.copy(_FIXTURE, snap / "routines" / "sample-1.md")
    return wiki, page, snap


class TestMigrateScript:
    def test_bumps_schema_and_adds_fields(self, staged):
        wiki, page, snap = staged
        r = _migrate(page, wiki, snap)
        assert r.returncode == 0, r.stderr
        assert "OK" in r.stdout
        text = page.read_text(encoding="utf-8")
        assert "schema_version: 2" in text
        assert "schema_version: 1" not in text
        assert "verification_strategy: manual" in text
        assert "verification_tools: []" in text

    def test_body_byte_identical(self, staged):
        wiki, page, snap = staged
        orig_body = _FIXTURE.read_text(encoding="utf-8").split("---\n", 2)[2]
        _migrate(page, wiki, snap)
        new_body = page.read_text(encoding="utf-8").split("---\n", 2)[2]
        assert new_body == orig_body

    def test_idempotent_rerun_skips(self, staged):
        wiki, page, snap = staged
        _migrate(page, wiki, snap)
        after_first = page.read_text(encoding="utf-8")
        r2 = _migrate(page, wiki, snap)
        assert r2.returncode == 0
        assert "SKIP" in r2.stdout
        assert page.read_text(encoding="utf-8") == after_first

    def test_does_not_double_insert_existing_strategy(self, staged):
        wiki, page, snap = staged
        seeded = page.read_text(encoding="utf-8").replace(
            "schema_version: 1\n", "schema_version: 1\nverification_strategy: lint\n"
        )
        page.write_text(seeded, encoding="utf-8")
        r = _migrate(page, wiki, snap)
        assert r.returncode == 0, r.stderr
        assert page.read_text(encoding="utf-8").count("verification_strategy:") == 1


class TestVerifyJson:
    def test_verify_passes_on_migrated_output(self, staged):
        wiki, page, snap = staged
        _migrate(page, wiki, snap)
        snap_page = snap / "routines" / "sample-1.md"
        r = _run(["bash", str(_VERIFY_PAGE), str(_VERIFY_JSON), str(page), str(snap_page)],
                 SF_WIKI_ROOT=str(wiki))
        assert r.returncode == 0, r.stderr


class TestDiscovery:
    """The chain computer + doctor must SEE routine-spec (both omitted it pre-C2)."""

    def _wiki_with_v1(self, tmp_path: Path) -> Path:
        wiki = tmp_path / "wiki"
        (wiki / "routines").mkdir(parents=True)
        shutil.copy(_FIXTURE, wiki / "routines" / "sample-1.md")
        return wiki

    def test_chain_computer_finds_routine_spec(self, tmp_path):
        wiki = self._wiki_with_v1(tmp_path)
        r = _run(["bash", str(_CHAIN), str(_SCHEMAS)], SF_WIKI_ROOT=str(wiki))
        assert "routine-spec" in r.stdout, r.stdout
        assert "1-to-2" in r.stdout, r.stdout

    def test_doctor_reports_migration_available(self, tmp_path):
        wiki = self._wiki_with_v1(tmp_path)
        r = _run(["bash", str(_DOCTOR_CHECK), str(_SCHEMAS)],
                 CLAUDE_PLUGIN_OPTION_WIKIROOT=str(wiki))
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("routine-spec|")]
        assert line, f"no routine-spec line in:\n{r.stdout}"
        assert line[0].split("|")[1] == "warn"  # migration available, not "skip"
