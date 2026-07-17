"""Tests for lib.skeleton — the manifest-driven wiki-skeleton loader.

Load-bearing contract under test: additive-never-overwrite. copy_if_missing
must never clobber an existing user file; create_if_missing must never touch
an existing directory. All fixtures use tmp_path — never the real ~/.renos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.skeleton import stamp_skeleton

SKELETON_ROOT = Path(__file__).resolve().parents[2] / "wiki-skeleton"


@pytest.fixture(autouse=True)
def _align_wiki_root(tmp_path, monkeypatch):
    """stamp_skeleton routes file writes through lib.memory.write_apply (Task
    9.3 FIX 1), which resolves pages against ren_paths.wiki_root() — so the
    env override must make wiki_root() == the target_root these tests pass
    (tmp_path/"wiki"), per lib/skeleton.py's module docstring."""
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / ".renos"))


def _placeholders() -> dict[str, str]:
    return {
        "handle": "test-friend",
        "name": "Test Friend",
        "today": "2026-01-01",
        "framework_version": "0.2.0",
    }


def test_first_run_writes_full_master_profile(tmp_path):
    target = tmp_path / "wiki"
    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    assert "index.md" in result.written
    assert "log.md" in result.written
    assert "identity.md" in result.written
    assert "LICENSES.md" in result.written
    assert "research/" in result.written
    assert "decisions/" in result.written
    assert "alternatives/" in result.written
    assert "patterns/" in result.written
    assert "projects/" in result.written
    assert result.skipped == []

    assert (target / "index.md").is_file()
    assert (target / "research").is_dir()


def test_copy_if_missing_never_overwrites_existing_file(tmp_path):
    target = tmp_path / "wiki"
    target.mkdir()
    sentinel = "MY OWN CONTENT — DO NOT TOUCH"
    (target / "index.md").write_text(sentinel, encoding="utf-8")

    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    assert (target / "index.md").read_text(encoding="utf-8") == sentinel
    assert "index.md" in result.skipped
    assert "index.md" not in result.written


def test_create_if_missing_never_touches_existing_directory(tmp_path):
    target = tmp_path / "wiki"
    research_dir = target / "research"
    research_dir.mkdir(parents=True)
    marker = research_dir / "my-research.md"
    marker.write_text("existing research", encoding="utf-8")

    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    assert marker.exists()
    assert marker.read_text(encoding="utf-8") == "existing research"
    assert "research/" in result.skipped


def test_rerun_is_idempotent_no_writes_second_time(tmp_path):
    target = tmp_path / "wiki"
    stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    second = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    assert second.written == []
    assert set(second.skipped) == {
        "index.md",
        "log.md",
        "identity.md",
        "LICENSES.md",
        "research/",
        "decisions/",
        "alternatives/",
        "patterns/",
        "projects/",
    }


def test_partial_additive_diff_only_writes_missing_entries(tmp_path):
    """Simulates an upgrade: friend already has some files, manifest adds more."""
    target = tmp_path / "wiki"
    target.mkdir()
    (target / "identity.md").write_text("already interviewed", encoding="utf-8")

    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    assert "identity.md" in result.skipped
    assert (target / "identity.md").read_text(encoding="utf-8") == "already interviewed"
    assert "index.md" in result.written
    assert "log.md" in result.written


def test_placeholder_substitution_fills_known_vars(tmp_path):
    target = tmp_path / "wiki"
    stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    identity_text = (target / "identity.md").read_text(encoding="utf-8")
    assert "test-friend" in identity_text
    assert "Test Friend" in identity_text
    assert "0.2.0" in identity_text
    assert "{{handle}}" not in identity_text
    assert "{{name}}" not in identity_text


def test_missing_placeholder_leaves_literal_and_warns(tmp_path):
    target = tmp_path / "wiki"
    incomplete = {"today": "2026-01-01", "framework_version": "0.2.0"}
    # handle/name deliberately omitted.

    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=incomplete,
    )

    identity_text = (target / "identity.md").read_text(encoding="utf-8")
    assert "{{handle}}" in identity_text
    assert "{{name}}" in identity_text
    assert any("handle" in w for w in result.warnings)
    assert any("name" in w for w in result.warnings)


def test_venture_module_not_stamped_by_master_profile(tmp_path):
    target = tmp_path / "wiki"
    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    assert not (target / "venture").exists()
    assert not any(p.startswith("venture") for p in result.written)
    assert not any(p.startswith("venture") for p in result.skipped)


def test_venture_module_stamps_when_profile_requested(tmp_path):
    target = tmp_path / "wiki"
    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="venture",
        placeholders=_placeholders(),
    )

    assert "venture/company.md" in result.written
    assert "venture/market.md" in result.written
    assert "venture/icp.md" in result.written
    assert "venture/team.md" in result.written
    assert "venture/brain-dump.md" in result.written
    assert (target / "venture" / "company.md").is_file()


def test_unknown_profile_raises(tmp_path):
    with pytest.raises(KeyError):
        stamp_skeleton(
            skeleton_root=SKELETON_ROOT,
            target_root=tmp_path / "wiki",
            profile="does-not-exist",
            placeholders=_placeholders(),
        )


def test_stamped_pages_are_journaled_with_provenance_and_revertible(tmp_path):
    """Task 9.3 FIX 1 regression (holistic-review CRITICAL): founding pages
    must carry provenance, appear in the journal, and be revertible — the
    reviewer's failure scenario was revert() on index.md raising KeyError."""
    from lib.memory import journal, revert
    from lib.memory.provenance import read_frontmatter_provenance

    target = tmp_path / "wiki"
    stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )

    stamped_pages = [p for p in target.rglob("*.md")]
    assert stamped_pages, "expected stamped markdown pages"
    journaled_pages = {e["page"] for e in journal.entries()}
    for page_abs in stamped_pages:
        rel = page_abs.relative_to(target).as_posix()
        prov = read_frontmatter_provenance(page_abs.read_text(encoding="utf-8"))
        assert prov is not None, f"{rel}: no provenance frontmatter"
        assert prov["writer"] == "human"
        assert rel in journaled_pages, f"{rel}: no journal line"

    index_write_id = read_frontmatter_provenance(
        (target / "index.md").read_text(encoding="utf-8")
    )["write_id"]
    result = revert.revert(index_write_id)
    assert result.restored
    assert not (target / "index.md").exists()  # revert of an ADD deletes


def test_path_prefix_nests_profile_entries_under_a_subdirectory(tmp_path):
    """The `project` profile's paths (e.g. "overview.md") are relative to
    wiki/projects/<slug>/, not the wiki root — path_prefix lets a caller
    (skills.bootstrap-project) stamp them at the right nested location while
    still resolving writes through write_apply against ren_paths.wiki_root()
    (see module docstring)."""
    target = tmp_path / "wiki"
    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="project",
        placeholders=_placeholders(),
        path_prefix="projects/my-idea/",
    )

    assert "overview.md" in result.written
    assert (target / "projects" / "my-idea" / "overview.md").is_file()


def test_path_prefix_copy_if_missing_still_never_overwrites(tmp_path):
    target = tmp_path / "wiki"
    nested = target / "projects" / "my-idea"
    nested.mkdir(parents=True)
    sentinel = "MY OWN OVERVIEW — DO NOT TOUCH"
    (nested / "overview.md").write_text(sentinel, encoding="utf-8")

    result = stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="project",
        placeholders=_placeholders(),
        path_prefix="projects/my-idea/",
    )

    assert (nested / "overview.md").read_text(encoding="utf-8") == sentinel
    assert "overview.md" in result.skipped
    assert "overview.md" not in result.written
