"""
Tests for the G9 unified write-safety substrate (Task 1.2):
lib.memory.journal, lib.memory.snapshot, lib.memory.write_apply.

apply_write is THE only function that touches wiki pages. Order under test,
inside a locks.lease(page):
  1. expect_token check (LostUpdate) — before anything else
  2. snapshot.take (prior bytes or ABSENT marker)
  2.5. scrub (best-effort import; refuses before any page write)
  3. op dispatch (ADD/UPDATE write, DELETE unlink, NOOP no-op)
  4. journal.append — LAST, so a crash before it leaves a snapshot with no
     matching journal line (the detectable-crash invariant)

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/memory/test_write_safety.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import journal, snapshot, write_apply
from lib.memory.locks import LeaseHeld, LostUpdate, content_token, lease
from lib.memory.provenance import new_provenance
from lib.ren_paths import wiki_root


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    """Point ren_paths' framework root at tmp_path; return the wiki root dir."""
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _prov(op="ADD", page="notes.md", supersedes=None):
    return new_provenance(writer="human", session="sess-1", op=op, page=page, supersedes=supersedes)


# ------------------------------------------------------------------- journal


def test_journal_append_and_entries_round_trip(wiki):
    prov = _prov()
    journal.append(prov)

    entries = journal.entries()
    assert len(entries) == 1
    assert entries[0]["write_id"] == prov.write_id
    assert entries[0]["page"] == "notes.md"


def test_journal_entries_filters_by_page(wiki):
    journal.append(_prov(page="a.md"))
    journal.append(_prov(page="b.md"))
    journal.append(_prov(page="a.md"))

    a_entries = journal.entries(page="a.md")
    assert len(a_entries) == 2
    assert all(e["page"] == "a.md" for e in a_entries)


def test_journal_entries_empty_when_no_journal_file(wiki):
    assert journal.entries() == []


def test_journal_append_merges_extra_fields(wiki):
    prov = _prov()
    journal.append(prov, extra={"note": "manual test"})

    entries = journal.entries()
    assert entries[0]["note"] == "manual test"


# ------------------------------------------------------------------ snapshot


def test_snapshot_take_of_absent_page_writes_marker(wiki):
    page_abs = wiki / "new-page.md"
    write_id = "w-0001"

    result = snapshot.take(page_abs, write_id)

    assert result.name.endswith(".absent")
    assert result.exists()


def test_snapshot_take_and_restore_round_trips_bytes(wiki):
    page_abs = wiki / "existing.md"
    page_abs.write_text("original content", encoding="utf-8")
    write_id = "w-0002"

    snapshot.take(page_abs, write_id)
    page_abs.write_text("mutated content", encoding="utf-8")

    snapshot.restore(write_id, "existing.md")
    assert page_abs.read_text(encoding="utf-8") == "original content"


def test_snapshot_restore_of_absent_marker_deletes_page(wiki):
    page_abs = wiki / "brand-new.md"
    write_id = "w-0003"
    snapshot.take(page_abs, write_id)  # page absent -> marker recorded

    page_abs.write_text("this got added by the write", encoding="utf-8")
    assert page_abs.exists()

    snapshot.restore(write_id, "brand-new.md")
    assert not page_abs.exists()


def test_snapshot_restore_raises_when_nothing_snapshotted(wiki):
    with pytest.raises(FileNotFoundError):
        snapshot.restore("w-does-not-exist", "never-snapshotted.md")


def test_snapshot_prune_keeps_n_most_recent(wiki):
    for i in range(4):
        write_id = f"w-000{i}"
        snapshot.take(wiki / f"page{i}.md", write_id)

    snapshot.prune(retain=2)

    from lib.ren_paths import state_dir
    remaining = sorted(p.name for p in (state_dir() / "snapshots").iterdir())
    assert remaining == ["w-0002", "w-0003"]


# --------------------------------------------------------------- write_apply


def test_add_creates_page_journals_once_and_snapshots_absent(wiki):
    prov = _prov(op="ADD", page="identity.md")

    write_apply.apply_write("identity.md", "# Identity\n\nbody", prov)

    page_abs = wiki / "identity.md"
    assert page_abs.exists()
    text = page_abs.read_text(encoding="utf-8")
    assert "ren_write_id" in text
    assert prov.write_id in text
    assert "# Identity" in text

    entries = journal.entries(page="identity.md")
    assert len(entries) == 1
    assert entries[0]["write_id"] == prov.write_id

    from lib.ren_paths import state_dir
    snap_dir = state_dir() / "snapshots" / prov.write_id
    markers = list(snap_dir.glob("*.absent"))
    assert markers, "ADD should snapshot an ABSENT marker (page didn't exist before)"


def test_update_snapshots_prior_bytes_and_replaces_content(wiki):
    page_abs = wiki / "log.md"
    page_abs.write_text("prior content, no frontmatter", encoding="utf-8")

    prov = _prov(op="UPDATE", page="log.md")
    write_apply.apply_write("log.md", "new content", prov)

    assert "new content" in page_abs.read_text(encoding="utf-8")

    # Prior bytes recoverable via snapshot.restore.
    snapshot.restore(prov.write_id, "log.md")
    assert page_abs.read_text(encoding="utf-8") == "prior content, no frontmatter"


def test_delete_removes_page_and_restore_brings_back_exact_bytes(wiki):
    page_abs = wiki / "to-delete.md"
    original_bytes = "content that must survive a revert"
    page_abs.write_text(original_bytes, encoding="utf-8")

    prov = _prov(op="DELETE", page="to-delete.md")
    write_apply.apply_write("to-delete.md", None, prov)

    assert not page_abs.exists()

    snapshot.restore(prov.write_id, "to-delete.md")
    assert page_abs.read_text(encoding="utf-8") == original_bytes


def test_noop_journals_but_leaves_page_untouched(wiki):
    page_abs = wiki / "untouched.md"
    page_abs.write_text("nothing should change", encoding="utf-8")

    prov = _prov(op="NOOP", page="untouched.md")
    write_apply.apply_write("untouched.md", None, prov)

    assert page_abs.read_text(encoding="utf-8") == "nothing should change"
    entries = journal.entries(page="untouched.md")
    assert len(entries) == 1
    assert entries[0]["op"] == "NOOP"


def test_expect_token_mismatch_raises_before_any_snapshot_write_or_journal(wiki):
    page_abs = wiki / "guarded.md"
    page_abs.write_text("current content", encoding="utf-8")
    stale_token = content_token(page_abs)
    page_abs.write_text("someone else changed this", encoding="utf-8")

    prov = _prov(op="UPDATE", page="guarded.md")

    with pytest.raises(LostUpdate):
        write_apply.apply_write("guarded.md", "my new content", prov, expect_token=stale_token)

    assert page_abs.read_text(encoding="utf-8") == "someone else changed this"
    assert journal.entries(page="guarded.md") == []

    from lib.ren_paths import state_dir
    snap_dir = state_dir() / "snapshots" / prov.write_id
    assert not snap_dir.exists(), "no snapshot should be taken before the token check passes"


def test_crash_between_snapshot_and_journal_leaves_page_written_but_no_journal_line(wiki, monkeypatch):
    page_abs = wiki / "crash-test.md"
    prov = _prov(op="ADD", page="crash-test.md")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash before journal append")

    monkeypatch.setattr(write_apply.journal, "append", _boom)

    with pytest.raises(RuntimeError):
        write_apply.apply_write("crash-test.md", "content that made it to disk", prov)

    # The page write happened...
    assert page_abs.exists()
    assert "content that made it to disk" in page_abs.read_text(encoding="utf-8")
    # ...but no journal line exists for it...
    assert journal.entries(page="crash-test.md") == []
    # ...while the snapshot dir DOES exist — this mismatch is the detectable-crash signal.
    from lib.ren_paths import state_dir
    snap_dir = state_dir() / "snapshots" / prov.write_id
    assert snap_dir.exists()


def test_prune_after_four_writes_keeps_two_newest(wiki):
    write_ids = []
    for i in range(4):
        prov = _prov(op="ADD", page=f"page{i}.md")
        write_apply.apply_write(f"page{i}.md", f"content {i}", prov)
        write_ids.append(prov.write_id)

    snapshot.prune(retain=2)

    from lib.ren_paths import state_dir
    remaining = sorted(p.name for p in (state_dir() / "snapshots").iterdir())
    assert remaining == sorted(write_ids)[-2:]


def test_concurrent_lease_held_propagates_lease_held(wiki):
    prov = _prov(op="ADD", page="contended.md")

    with lease("contended.md"):
        with pytest.raises(LeaseHeld):
            write_apply.apply_write("contended.md", "content", prov)

    # Nothing was written since the lease was never acquired by apply_write.
    assert not (wiki / "contended.md").exists()
    assert journal.entries(page="contended.md") == []


def test_scrub_refusal_blocks_write_before_any_page_write_or_journal(wiki, monkeypatch):
    class FakeScrubError(Exception):
        pass

    class _FakeScrubModule:
        @staticmethod
        def scrub_or_raise(content):
            raise FakeScrubError("secret detected")

    monkeypatch.setattr(write_apply, "_scrub", _FakeScrubModule)

    page_abs = wiki / "secret-laden.md"
    prov = _prov(op="ADD", page="secret-laden.md")

    with pytest.raises(FakeScrubError):
        write_apply.apply_write("secret-laden.md", "sk-live-totally-a-secret", prov)

    assert not page_abs.exists(), "page must be unchanged (never existed, still doesn't)"
    assert journal.entries(page="secret-laden.md") == []
