"""
Integration drill — Phase 2 exit criterion 7 (spec §3.10):
"a bad write can be found (provenance), reverted (targeted revert), and its
downstream flagged — demonstrated end-to-end."

Drives ONLY the public interfaces of the Phase 1+2 modules (queue, journal,
revert, quarantine) the way a real caller would — propose/approve/apply, never
poking at journal/snapshot files directly. This is the Phase 2 gate: after this
passes, Phase 4 (wrap/pin/recall) starts.

Run with: uv run pytest tests/integration/test_integrity_drill.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import journal, queue, quarantine, revert
from lib.memory.queue import Proposal
from lib.ren_paths import wiki_root


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


def _propose_approve_apply(**kwargs):
    """propose -> approve -> apply through the one public door; returns
    (QueueEntry as reloaded after apply, Provenance)."""
    entry = queue.propose(Proposal(**kwargs))
    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)
    return queue.get(entry.qid), prov


def test_bad_add_is_found_reverted_and_downstream_flagged(wiki):
    # 1. Seed a good page via the queue (human, producer=pin).
    good_entry, good_prov = _propose_approve_apply(
        op="ADD",
        page="projects/demo/good.md",
        content="The build command is `make build`.\n",
        reason="seed correct fact",
        producer="pin",
        writer="human",
        session="sess-human",
    )
    good_bytes_before = (wiki / "projects/demo/good.md").read_bytes()

    # 2. A BAD write arrives: wrap producer, llm-auto writer, wrong fact.
    bad_entry, bad_prov = _propose_approve_apply(
        op="ADD",
        page="projects/demo/bad.md",
        content="The build command is `make compile`.\n",
        reason="session-end summary (unreviewed)",
        producer="wrap",
        writer="llm-auto",
        session="sess-wrap",
    )
    bad_page_abs = wiki / "projects/demo/bad.md"
    assert bad_page_abs.exists()
    assert quarantine.is_quarantined(bad_page_abs.read_text(encoding="utf-8")) is True

    # 3. A third page cites the bad page (markdown link) via a human queue write.
    citer_entry, citer_prov = _propose_approve_apply(
        op="ADD",
        page="projects/demo/citer.md",
        content="See [bad notes](projects/demo/bad.md) for details.\n",
        reason="cross-reference",
        producer="pin",
        writer="human",
        session="sess-human",
    )

    # 4. FIND the bad write via journal, filtering by writer class.
    llm_auto_entries = [e for e in journal.entries() if e.get("writer") == "llm-auto"]
    assert len(llm_auto_entries) == 1
    assert llm_auto_entries[0]["write_id"] == bad_prov.write_id

    # 5. REVERT the bad write.
    result = revert.revert(llm_auto_entries[0]["write_id"])

    assert not bad_page_abs.exists()  # it was an ADD -> reverting deletes it
    assert "projects/demo/citer.md" in result.citers

    revert_entries = [
        e for e in journal.entries(page="projects/demo/bad.md")
        if e.get("revert_of") == bad_prov.write_id
    ]
    assert len(revert_entries) == 1
    assert revert_entries[0]["op"] == "NOOP"

    # 6. Aftermath.
    # The good page is untouched.
    assert (wiki / "projects/demo/good.md").read_bytes() == good_bytes_before

    # History is not rewritten: the queue entry for the bad write still shows
    # "applied" with its original write_id.
    reloaded_bad_entry = queue.get(bad_entry.qid)
    assert reloaded_bad_entry.status == "applied"
    assert reloaded_bad_entry.write_id == bad_prov.write_id

    # A fresh propose on the same page works — no wedged lock left behind by
    # revert's lease.
    fresh_entry, fresh_prov = _propose_approve_apply(
        op="ADD",
        page="projects/demo/bad.md",
        content="The build command is `make build` (corrected).\n",
        reason="corrected re-add",
        producer="pin",
        writer="human",
        session="sess-human",
    )
    assert bad_page_abs.exists()
    assert fresh_prov.write_id != bad_prov.write_id


def test_bad_update_over_good_page_reverts_to_original_bytes(wiki):
    # Seed the good page.
    _, good_prov = _propose_approve_apply(
        op="ADD",
        page="projects/demo/shared.md",
        content="The default port is 8080.\n",
        reason="seed correct fact",
        producer="pin",
        writer="human",
        session="sess-human",
    )
    page_abs = wiki / "projects/demo/shared.md"
    original_bytes = page_abs.read_bytes()

    # A bad UPDATE arrives over it.
    _, bad_prov = _propose_approve_apply(
        op="UPDATE",
        page="projects/demo/shared.md",
        content="The default port is 9090.\n",
        reason="session-end summary (unreviewed)",
        producer="wrap",
        writer="llm-auto",
        session="sess-wrap",
    )
    assert page_abs.read_bytes() != original_bytes

    llm_auto_entries = [
        e for e in journal.entries(page="projects/demo/shared.md")
        if e.get("writer") == "llm-auto"
    ]
    assert len(llm_auto_entries) == 1
    assert llm_auto_entries[0]["write_id"] == bad_prov.write_id

    result = revert.revert(bad_prov.write_id)

    assert page_abs.read_bytes() == original_bytes
    assert result.restored is True
