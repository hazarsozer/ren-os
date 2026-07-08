"""
Tests for lib.governance.tiers — the risk-tier gate model (Task 6.1).

Covers: the exhaustive tier table (kind × writer × global/non-global ×
unattended), the UnattendedBlocked refusal, queue_auto_apply_allowed, and the
apply_auto() addition to lib.memory.queue (legality gating, journal
"auto":true tagging, and one-step revert of an auto-applied write).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/governance/test_tiers.py -v
"""

from __future__ import annotations

import pytest

from lib.governance.tiers import Action, UnattendedBlocked, queue_auto_apply_allowed, tier_of
from lib.memory import journal, queue, revert as revert_module
from lib.memory.queue import Proposal, QueueStateError
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


# ------------------------------------------------------------------ tier_of


def test_read_is_always_free():
    for writer in ("human", "llm-auto", "retrospective", "routine"):
        assert tier_of(Action(kind="read", writer=writer)) == "free"


@pytest.mark.parametrize(
    "kind,writer,page,unattended,expected",
    [
        # memory_write: any writer + non-global -> auto (v2.2 data plane)
        ("memory_write", "routine", "projects/x/map.md", False, "auto"),
        ("memory_write", "routine", "projects/x/map.md", True, "auto"),
        # memory_write: routine + global -> ALWAYS diff_approved (strictest gate wins)
        ("memory_write", "routine", "global/policy.md", False, "diff_approved"),
        ("memory_write", "routine", "global", False, "diff_approved"),
        # v2.2: any other writer + non-global -> auto (data plane auto-applies)
        ("memory_write", "human", "projects/x/map.md", False, "auto"),
        ("memory_write", "llm-auto", "projects/x/map.md", False, "auto"),
        ("memory_write", "retrospective", "projects/x/map.md", False, "auto"),
        # memory_write: human + global -> diff_approved (instruction plane keeps the gate)
        ("memory_write", "human", "global/policy.md", False, "diff_approved"),
        # code_write / config_write -> always diff_approved, regardless of writer
        ("code_write", "human", None, False, "diff_approved"),
        ("code_write", "routine", None, False, "diff_approved"),
        ("config_write", "llm-auto", None, False, "diff_approved"),
        # destructive, attended -> ask
        ("destructive", "human", None, False, "ask"),
        ("destructive", "routine", None, False, "ask"),
    ],
)
def test_tier_table(kind, writer, page, unattended, expected):
    action = Action(kind=kind, writer=writer, page=page, unattended=unattended)
    assert tier_of(action) == expected  # v2.2: memory-write non-global pins updated


def test_destructive_unattended_raises_unattended_blocked():
    with pytest.raises(UnattendedBlocked):
        tier_of(Action(kind="destructive", writer="routine", unattended=True))


def test_destructive_unattended_raises_regardless_of_writer():
    for writer in ("human", "llm-auto", "retrospective", "routine"):
        with pytest.raises(UnattendedBlocked):
            tier_of(Action(kind="destructive", writer=writer, unattended=True))


def test_unattended_does_not_downgrade_auto_or_diff_approved():
    # An unattended routine memory write that's already "auto" stays "auto".
    assert tier_of(Action(kind="memory_write", writer="routine", page="p.md", unattended=True)) == "auto"
    # v2.2: an unattended human memory write to a non-global page is now "auto"
    # too (the data plane auto-applies for every writer, attended or not).
    assert tier_of(Action(kind="memory_write", writer="human", page="p.md", unattended=True)) == "auto"
    # An unattended write to a global/ page stays "diff_approved" — the
    # instruction plane's human gate never downgrades, unattended or not.
    assert (
        tier_of(Action(kind="memory_write", writer="human", page="global/policy.md", unattended=True))
        == "diff_approved"
    )


def test_unknown_action_kind_raises_value_error():
    with pytest.raises(ValueError):
        tier_of(Action(kind="not-a-real-kind", writer="human"))


def test_llm_auto_memory_write_is_auto_tier():
    """v2.2 data plane: descriptive memory auto-applies regardless of writer."""
    a = Action(kind="memory_write", writer="llm-auto", page="projects/demo/map.md")
    assert tier_of(a) == "auto"


def test_human_memory_write_is_auto_tier():
    a = Action(kind="memory_write", writer="human", page="lessons/use-uv.md")
    assert tier_of(a) == "auto"


def test_unattended_data_plane_write_is_auto_tier():
    """v2.2: unattended writers get data-plane autonomy (the brain compounds overnight)."""
    a = Action(kind="memory_write", writer="retrospective", page="l1/session-x.md", unattended=True)
    assert tier_of(a) == "auto"


def test_global_page_still_diff_approved_for_every_writer():
    """The instruction plane keeps the human gate — including unattended."""
    for writer in ("human", "llm-auto", "retrospective", "routine"):
        a = Action(kind="memory_write", writer=writer, page="global/style.md")
        assert tier_of(a) == "diff_approved"


def test_destructive_unattended_still_blocked():
    with pytest.raises(UnattendedBlocked):
        tier_of(Action(kind="destructive", writer="human", unattended=True))


# ------------------------------------------------------- queue_auto_apply_allowed


def _proposal(**overrides):
    defaults = dict(
        op="ADD", page="projects/x/notes.md", content="hello", reason="r",
        producer="routine", writer="routine", session="s",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


def test_queue_auto_apply_allowed_true_for_routine_non_global():
    assert queue_auto_apply_allowed(_proposal(writer="routine", page="projects/x/notes.md")) is True


def test_queue_auto_apply_allowed_true_for_any_writer_non_global():
    # v2.2: the data plane auto-applies for every writer class, not just routine.
    assert queue_auto_apply_allowed(_proposal(writer="human", page="projects/x/notes.md")) is True
    assert queue_auto_apply_allowed(_proposal(writer="llm-auto", page="projects/x/notes.md")) is True


def test_queue_auto_apply_allowed_false_for_global_page_even_if_routine():
    assert queue_auto_apply_allowed(_proposal(writer="routine", page="global/policy.md")) is False


# -------------------------------------------------------------------- apply_auto


def test_apply_auto_happy_path(wiki):
    entry = queue.propose(_proposal(page="projects/x/notes.md", content="routine-written content"))

    prov = queue.apply_auto(entry.qid)

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "applied"
    assert reloaded.approved_by == "auto-tier"
    assert reloaded.write_id == prov.write_id

    page_abs = wiki / "projects" / "x" / "notes.md"
    assert page_abs.exists()
    assert "routine-written content" in page_abs.read_text(encoding="utf-8")

    entries = journal.entries(page="projects/x/notes.md")
    assert len(entries) == 1
    assert entries[0]["auto"] is True
    assert entries[0]["writer"] == "routine"


def test_apply_auto_allows_human_writer_proposal_non_global(wiki):
    # v2.2: a human-written non-global memory proposal now resolves to "auto" too.
    entry = queue.propose(_proposal(writer="human", producer="pin", page="projects/x/human.md"))

    prov = queue.apply_auto(entry.qid)

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "applied"
    assert reloaded.write_id == prov.write_id


def test_apply_auto_allows_llm_auto_writer_proposal_non_global(wiki):
    # v2.2: an llm-auto-written non-global memory proposal now resolves to "auto" too.
    entry = queue.propose(_proposal(writer="llm-auto", producer="promotion", page="projects/x/llm.md"))

    prov = queue.apply_auto(entry.qid)

    reloaded = queue.get(entry.qid)
    assert reloaded.status == "applied"
    assert reloaded.write_id == prov.write_id


def test_apply_auto_rejects_global_page_even_for_routine(wiki):
    entry = queue.propose(_proposal(writer="routine", page="global/policy.md"))

    with pytest.raises(QueueStateError):
        queue.apply_auto(entry.qid)


def test_apply_auto_rejects_non_pending_entry(wiki):
    entry = queue.propose(_proposal(page="projects/x/notes.md"))
    queue.apply_auto(entry.qid)  # first call: pending -> applied

    with pytest.raises(QueueStateError):
        queue.apply_auto(entry.qid)  # second call: already applied


def test_apply_auto_does_not_require_prior_approval(wiki):
    """apply_auto works directly from 'pending' — approve() is never called."""
    entry = queue.propose(_proposal(page="projects/x/direct.md"))
    assert entry.status == "pending"

    queue.apply_auto(entry.qid)  # must not raise despite never having been approved


def test_reverting_an_auto_applied_write_works_one_step(wiki):
    entry = queue.propose(_proposal(page="projects/x/revertme.md", content="original routine content"))
    prov = queue.apply_auto(entry.qid)

    page_abs = wiki / "projects" / "x" / "revertme.md"
    assert page_abs.exists()

    result = revert_module.revert(prov.write_id)

    assert result.restored is True
    assert not page_abs.exists()  # it was an ADD, so revert deletes it
