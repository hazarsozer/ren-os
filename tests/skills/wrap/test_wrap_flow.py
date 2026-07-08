"""
Tests for skills.wrap.lib.wrap_session — the wrap write path (Task 4.1).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/wrap/test_wrap_flow.py -v
"""

from __future__ import annotations

import json

import pytest

from lib import ren_paths
from lib.memory import queue, quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.memory.queue import Proposal
from lib.ren_paths import state_dir, wiki_root
from skills.wrap.lib import render_wrap_screen, wrap_session


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


def _llm_by_lookup(mapping: dict[str, str]):
    """A stub llm_call: returns the correct verdict for known item text,
    "session-only" for anything else."""
    def llm_call(prompt: str) -> str:
        for item_text, verdict in mapping.items():
            if item_text in prompt:
                return json.dumps({"verdict": verdict, "reason": f"stub: {verdict}"})
        return json.dumps({"verdict": "session-only", "reason": "stub: unmatched"})
    return llm_call


# --- L1 narrative: always applied + quarantined -----------------------------


def test_l1_is_queued_applied_and_quarantined_as_llm_auto(wiki):
    result = wrap_session(
        narrative_md="# Session summary\n\nDid some work today.\n",
        durable_items=[],
        session="sess-1",
    )

    assert result["l1_qid"]
    entry = queue.get(result["l1_qid"])
    assert entry.status == "applied"
    assert entry.write_id is not None

    page_abs = wiki / "l1" / "session-sess-1.md"
    assert page_abs.exists()
    text = page_abs.read_text(encoding="utf-8")
    assert quarantine.is_quarantined(text) is True

    prov = read_frontmatter_provenance(text)
    assert prov is not None
    assert prov["writer"] == "llm-auto"
    assert prov["write_id"] == entry.write_id


def test_wrap_with_no_durable_items_has_empty_lists(wiki):
    result = wrap_session(narrative_md="Nothing much happened.\n", durable_items=[], session="sess-1")
    assert result["applied"] == []  # v2.2: durable_qids -> applied/held
    assert result["held"] == []
    assert result["gated_out"] == []
    assert result["refused"] == []
    assert result["fail_closed"] is False


# --- durable routing ---------------------------------------------------------


def test_wrap_durable_items_auto_apply(wiki):
    result = wrap_session(
        "# session\nnarrative",
        ["always run the linter before commit"],
        session="s-wrap-1",
        llm_call=_llm_by_lookup({"always run the linter before commit": "durable"}),
    )
    assert len(result["applied"]) == 1 and result["held"] == []
    page = result["applied"][0]["page"]
    assert (ren_paths.wiki_root() / page).exists()


def test_only_durable_verdict_items_are_queued_rest_are_gated_out(wiki):
    durable_item = "We decided to standardize on Postgres for order-history joins."
    chatter_item = "Ran the tests again, still green."

    llm_call = _llm_by_lookup({durable_item: "durable", chatter_item: "discard"})

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[durable_item, chatter_item],
        session="sess-2",
        llm_call=llm_call,
    )

    assert len(result["applied"]) == 1  # v2.2: durable_qids -> applied/held
    assert result["held"] == []
    assert len(result["gated_out"]) == 1
    assert result["gated_out"][0]["item"] == chatter_item
    assert result["gated_out"][0]["verdict"] == "discard"

    # Durable items now auto-apply through the data-plane door (v2.2 pivot):
    # non-global pages resolve to the "auto" tier, so they land applied +
    # quarantined, not pending for human approval.
    durable_entry = queue.get(result["applied"][0]["qid"])
    assert durable_entry.status == "applied"
    assert durable_entry.proposal.writer == "llm-auto"
    assert durable_entry.proposal.producer == "wrap"

    assert result["fail_closed"] is False


def test_fail_closed_flag_is_true_when_llm_call_crashes_for_any_item(wiki):
    def crashing_llm(prompt: str) -> str:
        raise RuntimeError("llm backend down")

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=["some candidate item"],
        session="sess-3",
        llm_call=crashing_llm,
    )

    assert result["fail_closed"] is True
    # Fell back to deterministic -> never durable -> gated out, not queued.
    assert result["applied"] == []  # v2.2: durable_qids -> applied/held
    assert result["held"] == []
    assert len(result["gated_out"]) == 1


def test_fail_closed_flag_is_false_with_no_llm_call_at_all(wiki):
    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=["some candidate item"],
        session="sess-4",
        llm_call=None,
    )
    # No LLM attempted at all -> not a "failure", just an absence. Still never
    # durable, but fail_closed specifically tracks LLM-path failures.
    assert result["fail_closed"] is False
    assert result["applied"] == []  # v2.2: durable_qids -> applied/held
    assert result["held"] == []


# --- secret refusal -----------------------------------------------------------


def test_durable_item_with_planted_secret_is_refused_not_crashed(wiki):
    secret_item = "Remember this AWS key for later: AKIAIOSFODNN7EXAMPLE"
    clean_item = "We decided to switch from webpack to vite for faster hot reload."

    llm_call = _llm_by_lookup({secret_item: "durable", clean_item: "durable"})

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[secret_item, clean_item],
        session="sess-5",
        llm_call=llm_call,
    )

    assert len(result["refused"]) == 1
    assert result["refused"][0]["item"] == secret_item

    # The clean item still made it through fine — one bad item doesn't crash the wrap.
    assert len(result["applied"]) == 1  # v2.2: durable_qids -> applied/held
    entry = queue.get(result["applied"][0]["qid"])
    assert entry.proposal.content == clean_item


# =============================================================================
# render_wrap_screen (G15 unified wrap screen, Task 8.2)
# =============================================================================


def _snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_wrap_screen_all_sections_with_real_session_state(wiki):
    session = "sess-screen-1"

    durable_item = "We decided to standardize on Postgres for order-history joins."
    llm_call = _llm_by_lookup({durable_item: "durable"})

    result = wrap_session(
        narrative_md="# Session summary\n\nDid some work.\n",
        durable_items=[durable_item],
        session=session,
        llm_call=llm_call,
    )
    # v2.2: durable items auto-apply through the data-plane door (non-global
    # page, no contradiction), so they land in "applied", not held pending.
    assert len(result["applied"]) == 1
    assert result["held"] == []
    durable_write_id = result["applied"][0]["write_id"]

    # A second, independent pending entry (a "pin"-shaped human proposal) —
    # v2.2: not a global/ or retrospective target and no contradiction, so
    # it's the "rare residue" case and lists under Suggestions.
    pin_entry = queue.propose(
        Proposal(
            op="ADD",
            page="pinned-note.md",
            content="Remember this exactly.",
            reason="user pin",
            producer="pin",
            writer="human",
            session=session,
            salience=True,
        )
    )

    # An auto-tier applied ROUTINE write (bounded, non-global page).
    auto_entry = queue.propose(
        Proposal(
            op="ADD",
            page="projects/demo/routine-note.md",
            content="Routine bounded note.\n",
            reason="routine check-in",
            producer="routine",
            writer="routine",
            session=session,
        )
    )
    auto_prov = queue.apply_auto(auto_entry.qid)

    # A refused secret item.
    secret_item = "Here's a key: AKIAIOSFODNN7EXAMPLE"
    llm_call_2 = _llm_by_lookup({secret_item: "durable"})
    result2 = wrap_session(
        narrative_md="# Another summary\n",
        durable_items=[secret_item],
        session=session,
        llm_call=llm_call_2,
    )
    assert len(result2["refused"]) == 1

    merged_result = {
        "l1_qid": result["l1_qid"],
        "applied": result["applied"] + result2["applied"],
        "held": result["held"] + result2["held"],
        "gated_out": [],
        "refused": result2["refused"],
        "fail_closed": False,
    }

    screen = render_wrap_screen(merged_result, session)

    assert "## What I learned" in screen
    assert result["l1_qid"] in screen
    assert "applied (quarantined, unreviewed)" in screen

    # v2.2: "Auto-saved" -> "Saved this session"; revert hint is spoken, not a slash command.
    assert "## Saved this session (revertible)" in screen
    assert auto_prov.write_id in screen
    assert durable_write_id in screen  # the auto-applied durable item too
    assert f'say "undo {auto_prov.write_id}" to revert' in screen

    # v2.2: "Needs your OK" is gone; the pin (no global/, no contradiction) is
    # residue and lists under Suggestions instead.
    assert "## Needs your OK" not in screen
    assert "## Suggestions" in screen
    assert pin_entry.qid in screen

    assert "## Refused (not queued)" in screen
    assert "AKIAIOSFODNN7EXAMPLE" not in screen  # never the secret content itself

    # v2.2: no slash-command hints anywhere — answers are conversational.
    assert "/ren:approve" not in screen
    assert "/ren:reject" not in screen
    assert "/ren:revert" not in screen
    assert "happen in chat" in screen


def test_wrap_screen_saved_and_suggestions_sections(wiki):
    # v2.2: "Auto-saved" -> "Saved this session"; "Needs your OK" is gone;
    # pending global/ (instruction-plane) entries surface as "Suggestions";
    # the screen carries NO slash-command hints (answers are conversational).
    session = "sess-screen-4"

    durable_item = "We decided to standardize on Postgres for order-history joins."
    llm_call = _llm_by_lookup({durable_item: "durable"})

    result = wrap_session(
        narrative_md="# Session summary\n",
        durable_items=[durable_item],
        session=session,
        llm_call=llm_call,
    )
    assert len(result["applied"]) == 1
    assert result["held"] == []

    global_entry = queue.propose(
        Proposal(
            op="ADD",
            page="global/naming-convention.md",
            content="Prefer snake_case for Python module names.",
            reason="candidate global convention",
            producer="pin",
            writer="human",
            session=session,
        )
    )

    screen = render_wrap_screen(result, session)

    assert "Saved this session" in screen
    assert "Suggestions" in screen
    assert "Needs your OK" not in screen
    assert "/ren:approve" not in screen

    suggestions_idx = screen.index("## Suggestions")
    assert global_entry.qid in screen[suggestions_idx:]


def test_wrap_screen_supersedes_conflict_flag_present(wiki):
    session = "sess-screen-2"

    # Seed an existing stamped page so a same-page durable proposal picks up
    # a real "supersedes" conflict from lib.memory.semantics.
    seed = queue.propose(
        Proposal(
            op="ADD", page="lessons/exponential-backoff.md",
            content="Original lesson body about exponential backoff.\n",
            reason="seed", producer="wrap", writer="llm-auto", session="seed-session",
        )
    )
    queue.approve(seed.qid, approved_by="hazar")
    queue.apply(seed.qid)

    durable_item = "Exponential backoff prevents hammering a flaky API."
    llm_call = _llm_by_lookup({durable_item: "durable"})

    # wrap_session slugifies the item into its own page name, which won't
    # collide with the seeded page — propose directly against the SAME page
    # instead, to exercise the conflict-flag rendering deterministically.
    conflicting_entry = queue.propose(
        Proposal(
            op="UPDATE", page="lessons/exponential-backoff.md",
            content="Updated lesson body about exponential backoff.\n",
            reason="wrap durable item", producer="wrap", writer="llm-auto", session=session,
        )
    )
    assert any(c.get("kind") == "supersedes" for c in conflicting_entry.conflicts)

    result = {
        "l1_qid": "q-does-not-exist",
        "applied": [],
        "held": [{"qid": conflicting_entry.qid, "page": conflicting_entry.proposal.page,
                  "conflicts": conflicting_entry.conflicts}],
        "gated_out": [],
        "refused": [],
        "fail_closed": False,
    }

    screen = render_wrap_screen(result, session)
    assert "supersedes" in screen


def test_wrap_screen_contradiction_hold_outranks_retrospective_suggestion(wiki):
    # A pending entry produced by "retrospective" (normally a suggestion)
    # that ALSO carries a `contradicts` conflict must render under "Held —
    # contradictions to resolve", not "Suggestions" — otherwise the SKILL.md
    # "yes" path would apply it without a contradiction_resolution record.
    session = "sess-screen-hold-vs-suggestion"

    (wiki_root() / "knowledge").mkdir(parents=True, exist_ok=True)
    seed = queue.propose(
        Proposal(
            op="ADD", page="knowledge/pricing-a.md",
            content="## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
            reason="seed", producer="wrap", writer="llm-auto", session="seed-session",
        )
    )
    queue.approve(seed.qid, approved_by="hazar")
    queue.apply(seed.qid)

    retro_entry = queue.propose(
        Proposal(
            op="ADD", page="knowledge/pricing-b.md",
            content="## Knowledge\nThe pricing model never uses monthly billing cycles.\n",
            reason="skill-candidate promotion", producer="retrospective", writer="llm-auto",
            session=session,
        )
    )
    assert any(c.get("kind") == "contradicts" for c in retro_entry.conflicts)

    result = {
        "l1_qid": "q-does-not-exist",
        "applied": [],
        "held": [],
        "gated_out": [],
        "refused": [],
        "fail_closed": False,
    }

    screen = render_wrap_screen(result, session)

    held_idx = screen.index("## Held — contradictions to resolve")
    assert retro_entry.qid in screen[held_idx:]
    suggestions_idx = screen.index("## Suggestions")
    assert retro_entry.qid not in screen[suggestions_idx:]


def test_wrap_screen_empty_session_is_graceful_minimal(wiki):
    result = {
        "l1_qid": "q-does-not-exist",
        "applied": [],
        "held": [],
        "gated_out": [],
        "refused": [],
        "fail_closed": False,
    }

    screen = render_wrap_screen(result, session="sess-nothing")

    assert "## What I learned" in screen
    assert "(not found)" in screen
    # v2.2: "Auto-saved" -> "Saved this session"; "Needs your OK" is gone;
    # Held is omitted entirely when empty, Suggestions renders "(none)".
    assert "## Saved this session (revertible)" in screen
    assert "(none this session)" in screen
    assert "## Needs your OK" not in screen
    assert "## Held" not in screen
    assert "## Suggestions" in screen
    assert "- (none)" in screen


def test_wrap_screen_writes_nothing(wiki):
    session = "sess-screen-3"
    result = wrap_session(
        narrative_md="# Summary\n", durable_items=[], session=session,
    )

    wiki_before = _snapshot(wiki)
    queue_dir = state_dir() / "queue"
    queue_before = _snapshot(queue_dir) if queue_dir.is_dir() else {}

    render_wrap_screen(result, session)

    wiki_after = _snapshot(wiki)
    queue_after = _snapshot(queue_dir) if queue_dir.is_dir() else {}

    assert wiki_after == wiki_before
    assert queue_after == queue_before
