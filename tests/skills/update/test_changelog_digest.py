"""Tests for skills/update/lib changelog_digest."""

from pathlib import Path

from skills.update import lib as update_lib

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


def test_prerelease_header_does_not_glue(tmp_path):
    """Prerelease headers must not glue onto the preceding section body."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [0.4.1]\nB\n\n## [0.4.1-rc.1]\nRC\n\n## [0.4.0]\nA\n", encoding="utf-8")
    out = update_lib.changelog_digest("0.4.0", "0.4.1", cl)
    assert "B" in out and "RC" not in out and "A" not in out


def test_reversed_range_returns_empty(tmp_path):
    """Reversed version range must return empty string."""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [0.4.1]\nB\n", encoding="utf-8")
    assert update_lib.changelog_digest("0.4.1", "0.4.0", cl) == ""
