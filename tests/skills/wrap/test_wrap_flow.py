"""
Tests for skills.wrap.lib.wrap_session — the wrap write path (Task 4.1).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/wrap/test_wrap_flow.py -v
"""

from __future__ import annotations

import json

import pytest

from lib.memory import queue, quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.ren_paths import wiki_root
from skills.wrap.lib import wrap_session


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
    assert result["durable_qids"] == []
    assert result["gated_out"] == []
    assert result["refused"] == []
    assert result["fail_closed"] is False


# --- durable routing ---------------------------------------------------------


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

    assert len(result["durable_qids"]) == 1
    assert len(result["gated_out"]) == 1
    assert result["gated_out"][0]["item"] == chatter_item
    assert result["gated_out"][0]["verdict"] == "discard"

    # Durable items are QUEUED, not auto-applied — pending human approval.
    durable_entry = queue.get(result["durable_qids"][0])
    assert durable_entry.status == "pending"
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
    assert result["durable_qids"] == []
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
    assert result["durable_qids"] == []


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
    assert len(result["durable_qids"]) == 1
    entry = queue.get(result["durable_qids"][0])
    assert entry.proposal.content == clean_item
