"""#56 (task 5) — wiki-health + lint dual-accept the folder-note hub
convention (`<dir-name>.md`) alongside the legacy `index.md` convention.

Dual-accept is deliberate: the plugin update lands before the friend runs
`/ren:update`'s migration, so wiki-health must not spray "hubless" findings
on a not-yet-migrated wiki. Doctor's `check_hub_convention` (task 4) is the
single voice for "you haven't migrated" — this module just needs to
recognize both shapes.
"""
from __future__ import annotations

import importlib

import pytest

wiki_health = importlib.import_module("skills.wiki-health.lib")
lint = importlib.import_module("skills.wiki-health.lib.lint")


def _w(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def migrated_wiki(clean_path_env, tmp_path):
    """Post-migration shape: hubs are `<dir-name>.md` folder notes."""
    _w(tmp_path, "index.md", "---\ntype: l2-map\n---\n# Master\n## Decision map\n- [demo](projects/demo/map.md)\n")
    _w(tmp_path, "projects/demo/map.md",
       "---\ntype: l2-map\nproject: demo\n---\n# demo — knowledge map\n"
       "## Knowledge\n## Decision map\n")
    _w(tmp_path, "projects/demo/knowledge/research/research.md",
       "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n- [Alpha](alpha.md)\n")
    _w(tmp_path, "projects/demo/knowledge/research/alpha.md",
       "---\ntype: project-knowledge\n---\n# Alpha\n")
    return tmp_path


@pytest.fixture
def legacy_wiki(clean_path_env, tmp_path):
    """Pre-migration shape: hubs are legacy `index.md`."""
    _w(tmp_path, "index.md", "---\ntype: l2-map\n---\n# Master\n## Decision map\n- [demo](projects/demo/map.md)\n")
    _w(tmp_path, "projects/demo/map.md",
       "---\ntype: l2-map\nproject: demo\n---\n# demo — knowledge map\n"
       "## Knowledge\n## Decision map\n")
    _w(tmp_path, "projects/demo/knowledge/research/index.md",
       "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n- [Alpha](alpha.md)\n")
    _w(tmp_path, "projects/demo/knowledge/research/alpha.md",
       "---\ntype: project-knowledge\n---\n# Alpha\n")
    return tmp_path


# ----------------------------------------------------- _knowledge_tree_findings


def test_folder_note_hub_recognized_no_hubless_finding(migrated_wiki):
    findings = wiki_health._knowledge_tree_findings(migrated_wiki)
    hubless, unlinked = findings
    assert hubless == []


def test_legacy_index_hub_still_recognized(legacy_wiki):
    hubless, unlinked = wiki_health._knowledge_tree_findings(legacy_wiki)
    assert hubless == []


def test_truly_hubless_dir_flagged_with_folder_note_name(migrated_wiki):
    bare = migrated_wiki / "projects/demo/knowledge/bare"
    bare.mkdir()
    (bare / "leaf.md").write_text("---\ntype: project-knowledge\n---\n# L\n", encoding="utf-8")
    hubless, _ = wiki_health._knowledge_tree_findings(migrated_wiki)
    assert any("bare" in h for h in hubless)


# --------------------------------------------------------------------- lint


def test_lint_dispatches_hub_fix_on_folder_note(migrated_wiki):
    hub = migrated_wiki / "projects/demo/knowledge/research/research.md"
    hub.write_text(
        "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n",
        encoding="utf-8",
    )
    (hub.parent / "unlisted-leaf.md").write_text(
        "---\ntype: project-knowledge\n---\n# Unlisted Leaf\n", encoding="utf-8"
    )
    text, added = lint._hub_missing_entries(
        migrated_wiki, "projects/demo/knowledge/research/research.md",
        hub.read_text(encoding="utf-8"),
    )
    assert "- [Unlisted Leaf](unlisted-leaf.md)" in text
    assert added  # non-empty list of added entries


def test_hub_missing_entries_never_lists_hub_itself(migrated_wiki):
    hub = migrated_wiki / "projects/demo/knowledge/research/research.md"
    hub.write_text(
        "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n",
        encoding="utf-8",
    )
    text, added = lint._hub_missing_entries(
        migrated_wiki, "projects/demo/knowledge/research/research.md",
        hub.read_text(encoding="utf-8"),
    )
    assert "research.md" not in "".join(added)


def test_lint_page_dispatches_on_folder_note_hub(migrated_wiki):
    hub_page = "projects/demo/knowledge/research/research.md"
    hub_text = (migrated_wiki / hub_page).read_text(encoding="utf-8")
    (migrated_wiki / "projects/demo/knowledge/research/unlisted-leaf.md").write_text(
        "---\ntype: project-knowledge\n---\n# Unlisted Leaf\n", encoding="utf-8"
    )
    new_text, fixes, judgments = lint._lint_page(
        migrated_wiki, hub_page, hub_text, all_pages=[], deleted=set()
    )
    assert "hub-missing-entry" in fixes
    assert "unlisted-leaf.md" in new_text


def test_lint_page_root_index_still_dispatches():
    """Regression: root `index.md` keeps its current dispatch behavior via
    the `p.name == "index.md"` branch of `_is_hub_page` — not just
    directories inside `knowledge/`."""
    assert lint._is_hub_page("index.md")


def test_is_hub_page_folder_note_requires_knowledge_ancestor():
    # A same-named file outside `knowledge/` is not a hub by accident.
    assert not lint._is_hub_page("projects/demo/demo.md")
    assert lint._is_hub_page("projects/demo/knowledge/research/research.md")


# ------------------------------------------- review findings (#56 round 2)


def test_is_hub_page_rejects_project_literally_named_knowledge():
    # FINDING 1: a project named "knowledge" must not false-positive just
    # because "knowledge" appears in the path string.
    assert not lint._is_hub_page("projects/knowledge/notes/notes.md")


def test_is_hub_page_rejects_archive_knowledge_dir():
    # FINDING 1: an archived dir named "knowledge" must not false-positive.
    assert not lint._is_hub_page("archive/knowledge/misc/misc.md")


def test_is_hub_page_accepts_real_folder_note_hub():
    assert lint._is_hub_page("projects/demo/knowledge/research/research.md")


def test_is_hub_page_accepts_root_index():
    assert lint._is_hub_page("index.md")


def test_hub_missing_entries_collision_dir_never_lists_the_other_hub(migrated_wiki):
    # FINDING 2: both research.md (folder-note) and index.md (legacy) exist
    # in the same dir — linting either must never list the other as an
    # ordinary sibling entry.
    directory = migrated_wiki / "projects/demo/knowledge/research"
    directory.mkdir(parents=True, exist_ok=True)
    hub_a = directory / "research.md"
    hub_a.write_text(
        "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n",
        encoding="utf-8",
    )
    hub_b = directory / "index.md"
    hub_b.write_text(
        "---\ntype: project-knowledge\nhub: true\n---\n# Research (legacy)\n\n## Pages\n",
        encoding="utf-8",
    )

    text_a, added_a = lint._hub_missing_entries(
        migrated_wiki, "projects/demo/knowledge/research/research.md",
        hub_a.read_text(encoding="utf-8"),
    )
    assert "index.md" not in "".join(added_a)
    assert "index.md" not in text_a.replace(hub_a.name, "")

    text_b, added_b = lint._hub_missing_entries(
        migrated_wiki, "projects/demo/knowledge/research/index.md",
        hub_b.read_text(encoding="utf-8"),
    )
    assert "research.md" not in "".join(added_b)


def test_leaf_linked_only_from_folder_note_hub_is_not_unlinked(migrated_wiki):
    # FINDING 3: the link_text corpus extension (collecting both hub
    # candidates, not just legacy `index.md`) is load-bearing — without it,
    # a leaf mentioned only inside its folder-note hub (not the project map)
    # is a false-positive "unlinked" finding.
    hubless, unlinked = wiki_health._knowledge_tree_findings(migrated_wiki)
    assert "projects/demo/knowledge/research/alpha.md" not in unlinked


def test_is_hub_page_folder_note_branch_delegates_to_page_types():
    """#76: the folder-note condition was written twice, independently.

    One predicate now, in lib/ (skills may import lib; lib must not import
    skills). The index.md branch is NOT part of this — it answers a different
    question and stays in the lint.
    """
    import importlib
    from pathlib import PurePosixPath

    page_types = importlib.import_module("lib.memory.page_types")
    lint_mod = importlib.import_module("skills.wiki-health.lib.lint")

    folder_notes = [
        "projects/demo/knowledge/research/research.md",
        "projects/demo/knowledge/lessons/lessons.md",
    ]
    non_folder_notes = [
        "projects/demo/demo.md",
        "projects/knowledge/notes/notes.md",
        "archive/knowledge/misc/misc.md",
        "projects/demo/raw/knowledge/x/x.md",
    ]
    for page in folder_notes + non_folder_notes:
        parts = PurePosixPath(page).parts
        assert lint_mod._is_hub_page(page) == page_types._is_folder_note_hub(parts), page


def test_is_hub_page_index_branch_is_untouched():
    """The index.md branch answers a DIFFERENT question and must survive."""
    import importlib

    lint_mod = importlib.import_module("skills.wiki-health.lib.lint")

    assert lint_mod._is_hub_page("index.md")
    assert lint_mod._is_hub_page("projects/demo/knowledge/research/index.md")
