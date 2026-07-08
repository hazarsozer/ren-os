"""
Tests for lib.memory.queue — the G1 single write-queue (Task 2.1).

propose -> approve -> apply is the only door to a wiki page write. Persistence
IS the state (one JSON file per entry under state_dir()/"queue/"); every call
re-reads from disk, so these tests also prove restart survival.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/memory/test_queue.py -v
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from lib.memory import journal, queue, quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.memory.queue import Proposal, QueueStateError
from lib.memory.scrub import SecretsFound
from lib.ren_paths import state_dir, wiki_root


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proposal(**overrides):
    defaults = dict(
        op="ADD",
        page="notes.md",
        content="hello world",
        reason="testing",
        producer="wrap",
        writer="human",
        session="sess-1",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


# ------------------------------------------------------------------ propose


def test_propose_persists_file_and_returns_entry_with_qid_and_ts(wiki):
    entry = queue.propose(_proposal())

    assert entry.qid.startswith("q-")
    assert entry.ts
    assert entry.status == "pending"

    path = state_dir() / "queue" / f"{entry.qid}.json"
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["qid"] == entry.qid


@pytest.mark.parametrize(
    "field_name,bad_value",
    [("op", "BOGUS"), ("producer", "not-a-producer"), ("writer", "not-a-writer")],
)
def test_bad_field_raises_value_error(wiki, field_name, bad_value):
    with pytest.raises(ValueError):
        _proposal(**{field_name: bad_value})


def test_content_with_planted_secret_raises_secrets_found_and_writes_no_file(wiki):
    fake_github_token = "ghp_" + "a" * 40

    with pytest.raises(SecretsFound):
        queue.propose(_proposal(content=f"here is a token: {fake_github_token}"))

    queue_dir = state_dir() / "queue"
    assert not queue_dir.exists() or list(queue_dir.glob("*.json")) == []


def test_duplicate_pending_propose_is_idempotent_same_qid(wiki):
    first = queue.propose(_proposal(page="dup.md", content="same content"))
    second = queue.propose(_proposal(page="dup.md", content="same content"))

    assert first.qid == second.qid
    assert len(list((state_dir() / "queue").glob("*.json"))) == 1


def test_different_content_same_page_creates_new_entry(wiki):
    first = queue.propose(_proposal(page="dup2.md", content="version A"))
    second = queue.propose(_proposal(page="dup2.md", content="version B"))

    assert first.qid != second.qid
    assert len(list((state_dir() / "queue").glob("*.json"))) == 2


@dataclass(frozen=True)
class _FakeConflict:
    kind: str
    page: str
    write_id: str | None
    evidence: str


def test_conflicts_attached_when_semantics_detect_returns_one(wiki, monkeypatch):
    class _FakeSemantics:
        @staticmethod
        def detect(op, page, content, wiki_root):
            return [_FakeConflict(kind="contradicts", page=page, write_id="w-old-1", evidence="stub")]

    monkeypatch.setattr(queue, "_semantics", _FakeSemantics)

    entry = queue.propose(_proposal(page="conflicted.md", content="new take"))

    assert len(entry.conflicts) == 1
    assert entry.conflicts[0]["kind"] == "contradicts"
    assert entry.conflicts[0]["write_id"] == "w-old-1"


def test_conflicts_empty_when_semantics_detect_returns_empty_list(wiki, monkeypatch):
    class _FakeSemantics:
        @staticmethod
        def detect(op, page, content, wiki_root):
            return []

    monkeypatch.setattr(queue, "_semantics", _FakeSemantics)

    entry = queue.propose(_proposal(page="clean.md", content="nothing conflicting"))
    assert entry.conflicts == []


def test_conflicts_empty_when_semantics_module_absent(wiki, monkeypatch):
    monkeypatch.setattr(queue, "_semantics", None)

    entry = queue.propose(_proposal(page="no-semantics.md", content="whatever"))
    assert entry.conflicts == []


# ------------------------------------------------------------------ pending


def test_pending_ordering_is_oldest_first(wiki):
    a = queue.propose(_proposal(page="a.md", content="a"))
    b = queue.propose(_proposal(page="b.md", content="b"))
    c = queue.propose(_proposal(page="c.md", content="c"))

    qids = [e.qid for e in queue.pending()]
    assert qids == sorted([a.qid, b.qid, c.qid])
    assert qids == [a.qid, b.qid, c.qid]


def test_pending_excludes_non_pending_entries(wiki):
    entry = queue.propose(_proposal(page="soon-approved.md", content="x"))
    queue.approve(entry.qid, approved_by="hazar")

    assert queue.pending() == []


# ------------------------------------------------------------- approve/apply


def test_apply_before_approve_raises_queue_state_error(wiki):
    entry = queue.propose(_proposal(page="too-early.md", content="x"))

    with pytest.raises(QueueStateError):
        queue.apply(entry.qid)


def test_approve_then_apply_happy_path_writes_page_and_journal(wiki):
    entry = queue.propose(_proposal(page="approved-page.md", content="# Hello\n\nbody text"))
    queue.approve(entry.qid, approved_by="hazar")

    prov = queue.apply(entry.qid)

    page_abs = wiki / "approved-page.md"
    assert page_abs.exists()
    text = page_abs.read_text(encoding="utf-8")
    assert "ren_write_id" in text
    assert prov.write_id in text

    entries = journal.entries(page="approved-page.md")
    assert len(entries) == 1
    assert entries[0]["write_id"] == prov.write_id

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "applied"
    assert reloaded.write_id == prov.write_id


def test_apply_fills_supersedes_from_supersedes_conflict(wiki, monkeypatch):
    class _FakeSemantics:
        @staticmethod
        def detect(op, page, content, wiki_root):
            return [_FakeConflict(kind="supersedes", page=page, write_id="w-original-write-id", evidence="stub")]

    monkeypatch.setattr(queue, "_semantics", _FakeSemantics)

    entry = queue.propose(_proposal(page="superseding.md", content="the new version"))
    queue.approve(entry.qid, approved_by="hazar")
    queue.apply(entry.qid)

    entries = journal.entries(page="superseding.md")
    assert len(entries) == 1
    assert entries[0]["supersedes"] == "w-original-write-id"


def test_reject_from_pending_records_reason(wiki):
    entry = queue.propose(_proposal(page="rejected-pending.md", content="x"))
    queue.reject(entry.qid, "not needed")

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "rejected"
    assert reloaded.rejected_reason == "not needed"


def test_reject_from_approved_records_reason(wiki):
    entry = queue.propose(_proposal(page="rejected-approved.md", content="x"))
    queue.approve(entry.qid, approved_by="hazar")
    queue.reject(entry.qid, "changed my mind")

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "rejected"
    assert reloaded.rejected_reason == "changed my mind"


def test_get_unknown_qid_raises_key_error(wiki):
    with pytest.raises(KeyError):
        queue.get("q-does-not-exist")


def test_approve_twice_raises_queue_state_error(wiki):
    entry = queue.propose(_proposal(page="double-approve.md", content="x"))
    queue.approve(entry.qid, approved_by="hazar")

    with pytest.raises(QueueStateError):
        queue.approve(entry.qid, approved_by="hazar")


def test_reject_after_applied_raises_queue_state_error(wiki):
    entry = queue.propose(_proposal(page="applied-then-reject.md", content="x"))
    queue.approve(entry.qid, approved_by="hazar")
    queue.apply(entry.qid)

    with pytest.raises(QueueStateError):
        queue.reject(entry.qid, "too late")


# -------------------------------------------------------------- persistence


def test_restart_survival_fresh_reads_see_identical_state(wiki):
    entry = queue.propose(_proposal(page="survives.md", content="persist me"))
    queue.approve(entry.qid, approved_by="hazar")

    # Simulate "process restart": no module-level cache to clear, just call
    # fresh module-level functions again and confirm identical state.
    reloaded = queue.get(entry.qid)
    assert reloaded.qid == entry.qid
    assert reloaded.status == "approved"
    assert reloaded.approved_by == "hazar"
    assert reloaded.proposal.page == "survives.md"
    assert reloaded.proposal.content == "persist me"


# ---------------------------------------------------- quarantine wiring (2.4)


def test_llm_auto_add_is_quarantined_and_still_carries_provenance(wiki):
    entry = queue.propose(
        _proposal(
            page="llm-note.md",
            content="# LLM summary\n\nSome unreviewed narrative.\n",
            writer="llm-auto",
            producer="wrap",
        )
    )
    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)

    text = (wiki / "llm-note.md").read_text(encoding="utf-8")
    assert quarantine.is_quarantined(text) is True

    read_prov = read_frontmatter_provenance(text)
    assert read_prov is not None
    assert read_prov["write_id"] == prov.write_id
    assert read_prov["writer"] == "llm-auto"


def test_human_add_is_not_quarantined(wiki):
    entry = queue.propose(
        _proposal(page="human-note.md", content="# Human note\n\nReviewed content.\n", writer="human")
    )
    queue.approve(entry.qid, approved_by="hazar")
    queue.apply(entry.qid)

    text = (wiki / "human-note.md").read_text(encoding="utf-8")
    assert quarantine.is_quarantined(text) is False


def test_apply_auto_quarantines_llm_auto_content(wiki):
    entry = queue.propose(
        _proposal(page="lessons/x.md", content="a fact", writer="llm-auto")
    )
    queue.apply_auto(entry.qid)

    text = (wiki / "lessons/x.md").read_text(encoding="utf-8")
    assert quarantine.is_quarantined(text) is True


def test_quarantine_banner_does_not_break_frontmatter_stamping(wiki):
    entry = queue.propose(
        _proposal(
            page="llm-note-2.md",
            content="# Another summary\n\nMore narrative text.\n",
            writer="llm-auto",
        )
    )
    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)

    text = (wiki / "llm-note-2.md").read_text(encoding="utf-8")
    # Frontmatter must still be the FIRST thing in the file (banner goes in the
    # body, after frontmatter) and provenance must round-trip cleanly.
    assert text.startswith("---\n")
    read_prov = read_frontmatter_provenance(text)
    assert read_prov["write_id"] == prov.write_id
    assert read_prov["op"] == "ADD"


# ------------------------------------------------ propose_and_apply (Task 3)


def test_propose_and_apply_data_plane_applies_immediately(wiki):
    entry, prov = queue.propose_and_apply(_proposal(page="lessons/y.md", content="f"))

    assert prov is not None and entry.status == "applied"
    assert (wiki / "lessons/y.md").exists()


def test_propose_and_apply_global_page_stays_pending(wiki):
    entry, prov = queue.propose_and_apply(
        _proposal(page="global/rule.md", content="r", producer="promotion")
    )

    assert prov is None and entry.status == "pending"


def test_propose_and_apply_contradiction_holds_for_reasoning(wiki, monkeypatch):
    class _FakeSemantics:
        @staticmethod
        def detect(op, page, content, wiki_root):
            return [_FakeConflict(kind="contradicts", page=page, write_id=None, evidence="opposite claim")]

    monkeypatch.setattr(queue, "_semantics", _FakeSemantics)

    entry, prov = queue.propose_and_apply(
        _proposal(page="lessons/z.md", content="g", writer="llm-auto")
    )

    assert prov is None and entry.status == "pending"


# -------------------------------------------------- resolve_and_apply (Task 4)


def test_resolve_and_apply_records_resolution(wiki):
    entry = queue.propose(
        _proposal(page="lessons/z.md", content="new claim", writer="llm-auto")
    )
    entry.conflicts.append({"kind": "contradicts", "page": "lessons/z.md", "evidence": "old"})
    queue._persist(entry)

    prov = queue.resolve_and_apply(
        entry.qid, "old claim was pre-refactor; new claim verified against src/"
    )

    lines = [l for l in journal.entries(page="lessons/z.md") if l.get("write_id") == prov.write_id]
    assert len(lines) == 1
    assert lines[0]["contradiction_resolution"].startswith("old claim was")
    assert lines[0]["auto"] is True

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "applied"
    assert reloaded.approved_by == "model-resolved"
    assert reloaded.write_id == prov.write_id


def test_resolve_and_apply_rejects_blank_resolution(wiki):
    entry = queue.propose(_proposal(page="lessons/w.md", content="c"))

    with pytest.raises(ValueError):
        queue.resolve_and_apply(entry.qid, "   ")


# ------------------------------------------------- approve_and_apply (Task 8)


def test_approve_and_apply_is_a_queue_function(wiki):
    entry = queue.propose(_proposal(page="global/rule.md", producer="promotion"))

    prov = queue.approve_and_apply(entry.qid, who="hazar")

    assert prov.write_id
    reloaded = queue.get(entry.qid)
    assert reloaded.status == "applied"
    assert reloaded.approved_by == "hazar"
    assert reloaded.write_id == prov.write_id


def test_approve_and_apply_unknown_qid_raises_key_error(wiki):
    with pytest.raises(KeyError):
        queue.approve_and_apply("q-does-not-exist", who="hazar")


def test_approve_and_apply_twice_raises_queue_state_error(wiki):
    entry = queue.propose(_proposal(page="global/twice.md", producer="promotion"))
    queue.approve_and_apply(entry.qid, who="hazar")

    with pytest.raises(QueueStateError):
        queue.approve_and_apply(entry.qid, who="hazar")


def test_corrupt_entry_file_does_not_take_down_pending(wiki, capsys):
    """Final-verification regression: one hand-corrupted queue JSON must not
    crash whole-queue listing — it's skipped with a warning; healthy entries
    still list; the corrupt file is left in place for inspection."""
    good = queue.propose(_proposal(page="notes/good.md", content="a healthy entry"))
    corrupt_path = state_dir() / "queue" / "q-00000000000000000000000000.json"
    corrupt_path.write_text("{ this is not json", encoding="utf-8")

    listed = queue.pending()
    assert [e.qid for e in listed] == [good.qid]
    assert corrupt_path.exists()
    assert "skipping unparsable entry file" in capsys.readouterr().err
