"""
Tests for skills.pin.lib — the pin/correction verb (Task 4.2).

pin()/correct() are thin producers over lib.memory.queue: exactly one
Proposal per call, always producer="pin", writer="human", salience=True.
Nothing here writes to a wiki page directly — that's the queue's job via
approve()/apply().

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/pin/test_pin.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import journal, quarantine, queue
from lib.ren_paths import wiki_root
from skills.pin.lib import correct, pin


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


def test_pin_on_fresh_page_proposes_add_with_salience_and_human_writer(wiki):
    entry = pin("remember this exactly", page="fresh.md", session="sess-1")

    assert entry.status == "pending"
    assert entry.proposal.op == "ADD"
    assert entry.proposal.page == "fresh.md"
    assert entry.proposal.content == "remember this exactly"
    assert entry.proposal.producer == "pin"
    assert entry.proposal.writer == "human"
    assert entry.proposal.salience is True
    assert entry.proposal.reason == "user pin"


def test_pin_on_existing_page_proposes_update(wiki):
    existing = wiki / "existing.md"
    existing.write_text("old content", encoding="utf-8")

    entry = pin("new take", page="existing.md", session="sess-1")

    assert entry.proposal.op == "UPDATE"
    assert entry.proposal.page == "existing.md"


def test_correct_with_replacement_proposes_update(wiki):
    entry = correct("wrong-page.md", "the corrected text", session="sess-1")

    assert entry.proposal.op == "UPDATE"
    assert entry.proposal.content == "the corrected text"
    assert entry.proposal.reason == "user correction"
    assert entry.proposal.producer == "pin"
    assert entry.proposal.writer == "human"
    assert entry.proposal.salience is True


def test_correct_without_replacement_proposes_delete(wiki):
    entry = correct("wrong-page.md", None, session="sess-1")

    assert entry.proposal.op == "DELETE"
    assert entry.proposal.content is None
    assert entry.proposal.reason == "user correction"


def test_applied_pin_lands_with_human_provenance_and_is_not_quarantined(wiki):
    entry = pin("# Real Content\n\nThis should not be quarantined.", page="landed.md", session="sess-1")
    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)

    assert prov.writer == "human"

    page_text = (wiki / "landed.md").read_text(encoding="utf-8")
    assert not quarantine.is_quarantined(page_text)
    assert "This should not be quarantined." in page_text

    entries = journal.entries(page="landed.md")
    assert len(entries) == 1
    assert entries[0]["writer"] == "human"


def test_applied_correction_delete_removes_page(wiki):
    page_abs = wiki / "to-remove.md"
    page_abs.write_text("stale content", encoding="utf-8")

    entry = correct("to-remove.md", None, session="sess-1")
    queue.approve(entry.qid, approved_by="hazar")
    queue.apply(entry.qid)

    assert not page_abs.exists()
