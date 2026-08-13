"""#58 hotfix — apply_write refuses ADD over an existing page by default.

The install-clobber incident (2026-08-12) wrote skeleton pages over a
populated wiki via direct `apply_write` calls with fresh ADD provenance.
Caller-side exists-checks (lib.skeleton) and queue-side guards
(_check_add_race, propose dedup) never fire on that path — the door itself
must refuse. Queue apply paths opt in via `allow_existing_add=True` because
their ADD semantics are handled upstream (including wrap's documented
same-session L1 re-ADD upsert).

Run with: uv run pytest tests/lib/memory/test_write_apply_add_guard.py -v
"""
import pytest


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _prov(page):
    from lib.memory.provenance import new_provenance
    return new_provenance(writer="human", session="test", op="ADD", page=page)


def test_add_on_absent_page_writes(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    from lib.memory import write_apply
    write_apply.apply_write("fresh.md", "# Fresh\n", _prov("fresh.md"))
    assert (root / "fresh.md").exists()


def test_add_on_existing_page_refused(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    from lib.memory import write_apply
    page = root / "identity.md"
    page.write_text("# Real profile\n", encoding="utf-8")
    with pytest.raises(write_apply.ExistingPageError):
        write_apply.apply_write("identity.md", "# Placeholder\n", _prov("identity.md"))
    assert page.read_text(encoding="utf-8") == "# Real profile\n"


def test_refusal_leaves_no_journal_line(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    from lib.memory import write_apply
    from lib import ren_paths
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    with pytest.raises(write_apply.ExistingPageError):
        write_apply.apply_write("log.md", "# Clobber\n", _prov("log.md"))
    journal = ren_paths.wiki_root() / ".ren" / "journal.jsonl"
    assert not journal.exists() or "log.md" not in journal.read_text(encoding="utf-8")


def test_allow_existing_add_opt_in_overwrites(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    from lib.memory import write_apply
    (root / "l1-page.md").write_text("# First wrap\n", encoding="utf-8")
    write_apply.apply_write(
        "l1-page.md", "# Second wrap\n", _prov("l1-page.md"), allow_existing_add=True
    )
    assert "Second wrap" in (root / "l1-page.md").read_text(encoding="utf-8")


def test_update_op_unaffected(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    from lib.memory import write_apply
    from lib.memory.provenance import new_provenance
    (root / "identity.md").write_text("# Stub\n", encoding="utf-8")
    prov = new_provenance(writer="human", session="test", op="UPDATE", page="identity.md")
    write_apply.apply_write("identity.md", "# Interviewed\n", prov)
    assert "Interviewed" in (root / "identity.md").read_text(encoding="utf-8")


def test_re_archive_suffixes_instead_of_clobbering(tmp_path, monkeypatch):
    """Regression (review HIGH): page archived, recreated, archived again must
    not raise and must preserve BOTH archive copies."""
    root = _setup(tmp_path, monkeypatch)
    from lib.memory import archive, write_apply
    page = root / "notes.md"
    page.write_text("# First life\n", encoding="utf-8")
    first = archive.archive_page("notes.md", "test-session", reason="decay-90d")
    assert first["archive_page"] == "archive/notes.md"
    # recreate and re-archive
    write_apply.apply_write("notes.md", "# Second life\n", _prov("notes.md"))
    second = archive.archive_page("notes.md", "test-session", reason="decay-90d")
    assert second["archive_page"] == "archive/notes-2.md"
    assert "First life" in (root / "archive/notes.md").read_text(encoding="utf-8")
    assert "Second life" in (root / "archive/notes-2.md").read_text(encoding="utf-8")


def test_queue_upsert_path_still_allows_re_add(tmp_path, monkeypatch):
    """wrap's same-session L1 re-ADD (documented upsert) flows through
    propose_and_apply -> apply_auto and must keep working."""
    _setup(tmp_path, monkeypatch)
    from lib.memory.queue import Proposal, propose_and_apply
    p1 = Proposal(op="ADD", page="projects/demo/l1/session-x.md", content="# v1\n",
                  reason="wrap L1", producer="wrap", writer="llm-auto", session="s1")
    entry1, prov1 = propose_and_apply(p1)
    assert prov1 is not None
    p2 = Proposal(op="ADD", page="projects/demo/l1/session-x.md", content="# v2\n",
                  reason="wrap L1", producer="wrap", writer="llm-auto", session="s1")
    entry2, prov2 = propose_and_apply(p2)
    assert prov2 is not None
