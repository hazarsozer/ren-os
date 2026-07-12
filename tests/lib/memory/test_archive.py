"""
Tests for lib.memory.archive — the archive tier (Task 16, RenOS 0.5.3).

archive-never-delete: `archive_page` moves a page to `archive/<rel>` (a
journaled ADD carrying the full prior content + `archived_from`/`archive_reason`
stamps) then journaled-DELETEs the original — both through `write_apply.apply_write`,
the single write door. Nothing is physically deleted; the archive copy is the
recovery path, and it deliberately does NOT depend on snapshot retention
(Codex R7 amendment) since snapshots prune to 50.

Run with: uv run pytest tests/lib/memory/test_archive.py -v
"""

from __future__ import annotations

import shutil

import pytest

from lib import ren_paths
from lib.memory import archive, journal, locks, revert, snapshot, write_apply
from lib.memory.provenance import new_provenance


@pytest.fixture
def wiki_root(tmp_path, monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "wiki"
    root.mkdir()
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    return root


def _add(page, content, session="s1"):
    prov = new_provenance("human", session, "ADD", page)
    write_apply.apply_write(page, content, prov)
    return prov


# --------------------------------------------------------------- is_archived


def test_is_archived_true_for_archive_prefix():
    assert archive.is_archived("archive/notes.md") is True


def test_is_archived_false_for_ordinary_page():
    assert archive.is_archived("notes.md") is False


# ---------------------------------------------------------------- archive_page


def test_archive_page_moves_content_to_archive_prefix(wiki_root):
    _add("notes.md", "Original body.\n")

    result = archive.archive_page("notes.md", "s1", reason="stale")

    assert result["archive_page"] == "archive/notes.md"
    assert not (wiki_root / "notes.md").exists()
    archived = (wiki_root / "archive" / "notes.md").read_text(encoding="utf-8")
    assert "Original body.\n" in archived


def test_archive_page_stamps_archived_from_and_reason(wiki_root):
    _add("notes.md", "Body.\n")

    archive.archive_page("notes.md", "s1", reason="superseded")

    archived = (wiki_root / "archive" / "notes.md").read_text(encoding="utf-8")
    assert 'archived_from: "notes.md"' in archived
    assert 'archive_reason: "superseded"' in archived


def test_archive_page_body_is_byte_identical(wiki_root):
    _add("notes.md", "Line one.\nLine two.\n")
    prior_body = "Line one.\nLine two.\n"

    archive.archive_page("notes.md", "s1", reason="stale")

    archived = (wiki_root / "archive" / "notes.md").read_text(encoding="utf-8")
    assert archived.endswith(prior_body)


def test_archive_page_journals_both_writes(wiki_root):
    _add("notes.md", "Body.\n")

    result = archive.archive_page("notes.md", "s1", reason="stale")

    entries = journal.entries()
    add_entry = next(e for e in entries if e["write_id"] == result["add_write_id"])
    del_entry = next(e for e in entries if e["write_id"] == result["delete_write_id"])

    assert add_entry["op"] == "ADD"
    assert add_entry["page"] == "archive/notes.md"
    assert del_entry["op"] == "DELETE"
    assert del_entry["page"] == "notes.md"
    assert del_entry["archived_to"] == "archive/notes.md"


def test_archive_page_writes_are_producer_writer_routine(wiki_root):
    _add("notes.md", "Body.\n")

    result = archive.archive_page("notes.md", "s1", reason="stale")

    entries = journal.entries()
    add_entry = next(e for e in entries if e["write_id"] == result["add_write_id"])
    del_entry = next(e for e in entries if e["write_id"] == result["delete_write_id"])
    assert add_entry["writer"] == "routine"
    assert del_entry["writer"] == "routine"


def test_archive_page_refuses_global_page(wiki_root):
    _add("global/policy.md", "Policy.\n")

    with pytest.raises(ValueError):
        archive.archive_page("global/policy.md", "s1", reason="stale")


def test_archive_page_refuses_already_archived_page(wiki_root):
    _add("archive/notes.md", "Already archived.\n")

    with pytest.raises(ValueError):
        archive.archive_page("archive/notes.md", "s1", reason="stale")


# ------------------------------------------------------------- trust preserved


def test_archive_page_preserves_foreign_trust(wiki_root):
    prov = new_provenance("llm-auto", "s1", "ADD", "foreign.md", trust="foreign")
    write_apply.apply_write("foreign.md", "QUARANTINE\n\nBody.\n", prov)

    archive.archive_page("foreign.md", "s1", reason="stale")

    archived = (wiki_root / "archive" / "foreign.md").read_text(encoding="utf-8")
    assert 'ren_trust: "foreign"' in archived


def test_archive_page_preserves_user_trust(wiki_root):
    _add("notes.md", "Body.\n")  # _add uses writer="human" -> trust "user"

    archive.archive_page("notes.md", "s1", reason="stale")

    archived = (wiki_root / "archive" / "notes.md").read_text(encoding="utf-8")
    assert 'ren_trust: "user"' in archived


def test_archived_foreign_page_still_escaped_on_recall_fetch(wiki_root, monkeypatch):
    from skills.recall.lib import fetch

    prov = new_provenance("llm-auto", "s1", "ADD", "foreign.md", trust="foreign")
    write_apply.apply_write("foreign.md", "Body about widgets.\n", prov)

    archive.archive_page("foreign.md", "s1", reason="stale")

    results = fetch(
        "widgets",
        "s1",
        k=5,
        include_archived=True,
        include_quarantined=True,
    )
    hit = next(r for r in results if r["page"] == "archive/foreign.md")
    assert hit["content"] != "Body about widgets.\n"  # escaped, not literal


# ---------------------------------------------------------------------- revert


def test_revert_of_both_archive_writes_restores_original(wiki_root):
    _add("notes.md", "Original body.\n")
    prior_bytes = (wiki_root / "notes.md").read_bytes()

    result = archive.archive_page("notes.md", "s1", reason="stale")

    revert.revert(result["delete_write_id"])
    revert.revert(result["add_write_id"])

    assert (wiki_root / "notes.md").read_bytes() == prior_bytes
    assert not (wiki_root / "archive" / "notes.md").exists()


def test_archive_page_raises_on_concurrent_update_between_read_and_delete(wiki_root):
    """rev-t16 finding #2: a concurrent UPDATE landing between archive_page's
    initial content read and its DELETE call must not be silently discarded.
    `archive_page` now threads an `expect_token` captured at read-time through
    to the DELETE `apply_write` call, so a page that changed underneath it
    raises `LostUpdate` instead of racing."""
    _add("notes.md", "v1 content\n")

    real_apply_write = write_apply.apply_write
    calls = {"n": 0}

    def racy_apply_write(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # Fire a concurrent UPDATE right after the ADD call (first call),
            # before archive_page's own DELETE call (second call) runs.
            concurrent_prov = new_provenance("human", "s2", "UPDATE", "notes.md")
            real_apply_write("notes.md", "v2 CONCURRENT UPDATE\n", concurrent_prov)
        return real_apply_write(*args, **kwargs)

    write_apply.apply_write = racy_apply_write
    try:
        with pytest.raises(locks.LostUpdate):
            archive.archive_page("notes.md", "s1", reason="stale")
    finally:
        write_apply.apply_write = real_apply_write

    # Nothing lost: the original page is still live with the concurrent update.
    assert (wiki_root / "notes.md").read_text(encoding="utf-8").endswith("v2 CONCURRENT UPDATE\n")


def test_restore_from_archive_copy_does_not_depend_on_delete_snapshot(wiki_root):
    """Codex R7 amendment: restoration must not depend on snapshot retention
    (snapshots prune to 50) — the archive copy carries the full content, so
    restoring is still possible even after the DELETE write's own snapshot
    dir is gone."""
    _add("notes.md", "Original body.\n")
    prior_content = "Original body.\n"

    result = archive.archive_page("notes.md", "s1", reason="stale")

    # Simulate the DELETE write's snapshot having been pruned away.
    delete_snapshot_dir = ren_paths.state_dir() / "snapshots" / result["delete_write_id"]
    shutil.rmtree(delete_snapshot_dir, ignore_errors=True)

    with pytest.raises(FileNotFoundError):
        snapshot.restore(result["delete_write_id"], "notes.md")

    # The archive copy is still the source of truth: its body is exactly the
    # prior content, so a normal write can reconstruct the page without ever
    # touching the pruned DELETE snapshot.
    archived_content = (wiki_root / "archive" / "notes.md").read_text(encoding="utf-8")
    assert archived_content.endswith(prior_content)

    restore_prov = new_provenance("human", "s1", "ADD", "notes.md")
    write_apply.apply_write("notes.md", prior_content, restore_prov)
    assert (wiki_root / "notes.md").read_text(encoding="utf-8").endswith(prior_content)
