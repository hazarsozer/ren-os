"""
Tests for skills.pin.lib — the pin/correction verb (Task 4.2).

pin()/correct() are thin producers over lib.memory.queue: exactly one
Proposal per call, always producer="pin", writer="human", salience=True.
Nothing here writes to a wiki page directly — that's the data-plane door's
job (`propose_and_apply`, v2.2): a non-global page write auto-applies, so
these land `applied` immediately with a `write_id`, not `pending`.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/pin/test_pin.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import journal, quarantine
from lib.memory.promotion import demote_check
from lib.memory.queue import approve_and_apply
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


def test_pin_on_fresh_page_auto_applies_with_salience_and_human_writer(wiki):
    # v2.2: pin is a data-plane write (non-global page) — it now auto-applies
    # through propose_and_apply instead of landing pending for human approval.
    entry = pin("remember this exactly", page="fresh.md", session="sess-1")

    assert entry.status == "applied"
    assert entry.write_id is not None
    assert entry.proposal.op == "ADD"
    assert entry.proposal.page == "fresh.md"
    assert entry.proposal.content == "remember this exactly"
    assert entry.proposal.producer == "pin"
    assert entry.proposal.writer == "human"
    assert entry.proposal.salience is True
    assert entry.proposal.reason == "user pin"

    page_text = (wiki / "fresh.md").read_text(encoding="utf-8")
    assert "remember this exactly" in page_text


def test_pin_on_existing_page_auto_applies_update(wiki):
    existing = wiki / "existing.md"
    existing.write_text("old content", encoding="utf-8")

    entry = pin("new take", page="existing.md", session="sess-1")

    assert entry.proposal.op == "UPDATE"
    assert entry.proposal.page == "existing.md"
    assert entry.status == "applied"  # v2.2: data-plane auto-apply
    assert entry.write_id is not None
    assert "new take" in existing.read_text(encoding="utf-8")


def test_correct_with_replacement_auto_applies_update(wiki):
    entry = correct("wrong-page.md", "the corrected text", session="sess-1")

    assert entry.proposal.op == "UPDATE"
    assert entry.proposal.content == "the corrected text"
    assert entry.proposal.reason == "user correction"
    assert entry.proposal.producer == "pin"
    assert entry.proposal.writer == "human"
    assert entry.proposal.salience is True
    assert entry.status == "applied"  # v2.2: data-plane auto-apply
    assert entry.write_id is not None


def test_correct_without_replacement_auto_applies_delete(wiki):
    page_abs = wiki / "to-remove.md"
    page_abs.write_text("stale content", encoding="utf-8")

    entry = correct("to-remove.md", None, session="sess-1")

    assert entry.proposal.op == "DELETE"
    assert entry.proposal.content is None
    assert entry.proposal.reason == "user correction"
    assert entry.status == "applied"  # v2.2: data-plane auto-apply
    assert not page_abs.exists()


def test_applied_pin_lands_with_human_provenance_and_is_not_quarantined(wiki):
    entry = pin("# Real Content\n\nThis should not be quarantined.", page="landed.md", session="sess-1")

    assert entry.status == "applied"  # v2.2: no separate approve()/apply() step

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

    assert entry.status == "applied"  # v2.2: no separate approve()/apply() step
    assert not page_abs.exists()


# --------------------------------------------------------------------------
# Gate-0 finding b: pin to global/ must stamp `type: preference` so an
# approved global write satisfies lib.memory.promotion.demote_check.
# --------------------------------------------------------------------------


def test_pin_to_global_page_stamps_type_preference_and_satisfies_demote_check(wiki):
    # global/ is instruction-plane — propose_and_apply holds it pending, so
    # a human must approve+apply before it lands on disk (mirrors the real
    # Gate-0 flow: friend approves the pin).
    entry = pin("Ship on Fridays.", page="global/preferences.md", session="sess-1")
    assert entry.status == "pending"

    approve_and_apply(entry.qid, who="hazar")

    page_text = (wiki / "global" / "preferences.md").read_text(encoding="utf-8")
    assert "type: preference" in page_text
    assert "Ship on Fridays." in page_text
    assert demote_check() == []


def test_pin_to_existing_global_page_preserves_existing_type(wiki):
    # The pin content itself already declares `type: doctrine` (e.g. the
    # friend is re-pinning an already-typed global page's content) — the
    # stamp helper must leave it alone, not overwrite with `preference` or
    # add a second frontmatter fence.
    content = "---\ntype: doctrine\n---\nOld rule, restated.\n"

    entry = pin(content, page="global/rules.md", session="sess-1")
    assert entry.status == "pending"

    approve_and_apply(entry.qid, who="hazar")

    page_text = (wiki / "global" / "rules.md").read_text(encoding="utf-8")
    assert page_text.count("---\n") == 2  # no double fence
    assert "type: doctrine" in page_text
    assert "type: preference" not in page_text
    assert demote_check() == []


def test_pin_to_non_global_page_content_unchanged(wiki):
    entry = pin("remember this exactly", page="fresh.md", session="sess-1")

    assert entry.status == "applied"
    assert entry.proposal.content == "remember this exactly"

    page_text = (wiki / "fresh.md").read_text(encoding="utf-8")
    assert "type: preference" not in page_text
