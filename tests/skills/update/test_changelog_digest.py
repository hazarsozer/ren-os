"""Tests for skills/update/lib changelog_digest."""

from pathlib import Path

import importlib

update_lib = importlib.import_module("skills.update.lib")

SAMPLE = """# Changelog

## [0.3.4] — 2026-07-09 — "docs truth pass"

Docs now say what the code does.

## [0.3.3] — 2026-07-09 — "see what you approve"

- Wake-up lists pending suggestions.

## [0.3.2] — 2026-07-09 — "substrate integrity"

- snapshotRetain wired.
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


def test_digest_includes_only_versions_in_range(tmp_path):
    digest = update_lib.changelog_digest("0.3.2", "0.3.4", _write(tmp_path))
    assert "[0.3.4]" in digest
    assert "[0.3.3]" in digest
    assert "[0.3.2]" not in digest


def test_digest_preserves_section_bodies(tmp_path):
    digest = update_lib.changelog_digest("0.3.2", "0.3.4", _write(tmp_path))
    assert "Wake-up lists pending suggestions." in digest


def test_equal_versions_yield_empty(tmp_path):
    assert update_lib.changelog_digest("0.3.4", "0.3.4", _write(tmp_path)) == ""


def test_missing_file_yields_empty(tmp_path):
    assert update_lib.changelog_digest("0.3.2", "0.3.4", tmp_path / "nope.md") == ""


def test_unparseable_bound_yields_empty(tmp_path):
    assert update_lib.changelog_digest("garbage", "0.3.4", _write(tmp_path)) == ""
