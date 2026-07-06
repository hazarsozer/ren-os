"""
Tests for lib.memory.revert — G4 targeted revert (Task 2.3).

Fixtures are built by driving REAL `write_apply.apply_write` calls (not
hand-written journal/snapshot state) so the layout under test is authentic to
what Task 1.2's write-safety substrate actually produces.

Run with: uv run pytest tests/lib/memory/test_revert.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import revert, write_apply
from lib.memory.provenance import new_provenance


@pytest.fixture
def wiki_root(tmp_path, monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "wiki"
    root.mkdir()
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    return root


def _add(page, content, session="s1", supersedes=None):
    prov = new_provenance("human", session, "ADD", page, supersedes=supersedes)
    write_apply.apply_write(page, content, prov)
    return prov


def _update(page, content, session="s1"):
    prov = new_provenance("human", session, "UPDATE", page)
    write_apply.apply_write(page, content, prov)
    return prov


def _delete(page, session="s1"):
    prov = new_provenance("human", session, "DELETE", page)
    write_apply.apply_write(page, None, prov)
    return prov


# --- basic revert outcomes ---------------------------------------------------


def test_revert_of_update_restores_exact_prior_bytes(wiki_root):
    _add("notes.md", "Original body.\n")
    prior_bytes = (wiki_root / "notes.md").read_bytes()

    prov2 = _update("notes.md", "Updated body.\n")
    assert (wiki_root / "notes.md").read_bytes() != prior_bytes

    result = revert.revert(prov2.write_id)

    assert result.restored is True
    assert result.page == "notes.md"
    assert result.write_id == prov2.write_id
    assert (wiki_root / "notes.md").read_bytes() == prior_bytes


def test_revert_of_add_deletes_the_page(wiki_root):
    prov1 = _add("fresh.md", "Fresh content.\n")
    assert (wiki_root / "fresh.md").exists()

    result = revert.revert(prov1.write_id)

    assert result.restored is True
    assert result.page == "fresh.md"
    assert not (wiki_root / "fresh.md").exists()


def test_revert_of_delete_brings_page_back(wiki_root):
    _add("gone.md", "Will be deleted.\n")
    prior_bytes = (wiki_root / "gone.md").read_bytes()

    prov2 = _delete("gone.md")
    assert not (wiki_root / "gone.md").exists()

    result = revert.revert(prov2.write_id)

    assert result.restored is True
    assert (wiki_root / "gone.md").exists()
    assert (wiki_root / "gone.md").read_bytes() == prior_bytes


def test_revert_unknown_write_id_raises_key_error(wiki_root):
    with pytest.raises(KeyError):
        revert.revert("w-DOES-NOT-EXIST")


def test_revert_journals_a_noop_with_revert_of(wiki_root):
    from lib.memory import journal

    prov1 = _add("notes.md", "Original body.\n")
    prov2 = _update("notes.md", "Updated body.\n")

    revert.revert(prov2.write_id)

    entries = journal.entries(page="notes.md")
    revert_entries = [e for e in entries if e.get("revert_of") == prov2.write_id]
    assert len(revert_entries) == 1
    assert revert_entries[0]["op"] == "NOOP"
    assert revert_entries[0]["writer"] == "human"
    # Sanity: the original ADD/UPDATE entries are still there too.
    assert any(e["write_id"] == prov1.write_id for e in entries)
    assert any(e["write_id"] == prov2.write_id for e in entries)


# --- citers ------------------------------------------------------------------


def test_citers_found_via_all_three_mechanisms_and_self_excluded(wiki_root):
    prov_target = _add("projects/demo/target.md", "Target original body.\n")

    # (a) frontmatter ren_supersedes == reverted write_id
    _add(
        "projects/demo/citer-a.md",
        "Citer A body.\n",
        supersedes=prov_target.write_id,
    )

    # (b) body mentions the write_id string
    _add(
        "projects/demo/citer-b.md",
        f"This references write {prov_target.write_id} explicitly.\n",
    )

    # (c) markdown link to the reverted page's path
    _add(
        "projects/demo/citer-c.md",
        "See [target notes](projects/demo/target.md) for details.\n",
    )

    # (d) cites nothing — must NOT be listed
    _add("projects/demo/unrelated.md", "Nothing related here at all.\n")

    result = revert.revert(prov_target.write_id)

    assert set(result.citers) == {
        "projects/demo/citer-a.md",
        "projects/demo/citer-b.md",
        "projects/demo/citer-c.md",
    }
    assert "projects/demo/target.md" not in result.citers
    assert "projects/demo/unrelated.md" not in result.citers


def test_page_citing_nothing_is_not_listed_alone(wiki_root):
    prov_target = _add("solo/target.md", "Solo target body.\n")
    _add("solo/bystander.md", "Completely unrelated content.\n")

    result = revert.revert(prov_target.write_id)

    assert result.citers == []
