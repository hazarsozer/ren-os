"""
Tests for lib.suggestions.producers — the promotion-candidate producer
(Task 17, RenOS 0.4.2).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos. Journal lines are seeded
through the real door (`queue.propose_and_apply`) rather than hand-written,
so the test exercises the actual UPDATE/session/page shape the producer
reads.

Run with: uv run pytest tests/lib/suggestions/test_producers.py -v
"""

from __future__ import annotations

import pytest

from lib.companions import Companion, Offer
from lib.memory import quarantine
from lib.memory.queue import Proposal, propose_and_apply
from lib.ren_paths import wiki_root
from lib.suggestions.producers import doctrine_shaping, promotion_candidates, wiki_health_critical


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


def _page_content(page_type: str, body: str) -> str:
    return f"---\ntype: {page_type}\n---\n{body}\n"


def _seed_two_updates(page: str, page_type: str = "preference"):
    """Drive the real write door twice with different sessions and changed
    content, producing two journaled UPDATE entries for `page` across two
    distinct sessions (first write is an ADD, second is the UPDATE that
    matters for the producer's threshold — so seed with an extra ADD+UPDATE
    to get 2 UPDATEs)."""
    propose_and_apply(
        Proposal(
            op="ADD", page=page, content=_page_content(page_type, "v1"),
            reason="seed", producer="retrospective", writer="human", session="s1",
        )
    )
    propose_and_apply(
        Proposal(
            op="UPDATE", page=page, content=_page_content(page_type, "v2"),
            reason="seed", producer="retrospective", writer="human", session="s1",
        )
    )
    propose_and_apply(
        Proposal(
            op="UPDATE", page=page, content=_page_content(page_type, "v3"),
            reason="seed", producer="retrospective", writer="human", session="s2",
        )
    )


def test_reinforced_preference_page_becomes_candidate(wiki):
    _seed_two_updates("projects/x/pref.md")

    specs = promotion_candidates(wiki)

    assert len(specs) == 1
    spec = specs[0]
    assert spec.producer == "promotion"
    assert spec.kind == "structured_action"
    assert spec.payload == {"action": "promote_to_global", "source_page": "projects/x/pref.md"}
    assert spec.fingerprint == "promotion:projects/x/pref.md"


def test_doctrine_type_also_qualifies(wiki):
    _seed_two_updates("projects/x/doc.md", page_type="doctrine")

    specs = promotion_candidates(wiki)

    assert len(specs) == 1
    assert specs[0].payload["source_page"] == "projects/x/doc.md"


def test_only_one_update_does_not_qualify(wiki):
    propose_and_apply(
        Proposal(
            op="ADD", page="projects/x/pref.md", content=_page_content("preference", "v1"),
            reason="seed", producer="retrospective", writer="human", session="s1",
        )
    )
    propose_and_apply(
        Proposal(
            op="UPDATE", page="projects/x/pref.md", content=_page_content("preference", "v2"),
            reason="seed", producer="retrospective", writer="human", session="s1",
        )
    )

    assert promotion_candidates(wiki) == []


def test_quarantined_page_does_not_qualify(wiki):
    _seed_two_updates("projects/x/pref.md")

    page = wiki / "projects" / "x" / "pref.md"
    page.write_text(quarantine.mark(page.read_text(encoding="utf-8")), encoding="utf-8")

    assert promotion_candidates(wiki) == []


def test_already_global_page_does_not_qualify(wiki):
    _seed_two_updates("global/pref.md")

    assert promotion_candidates(wiki) == []


def test_typeless_page_does_not_qualify(wiki):
    (wiki / "projects" / "x").mkdir(parents=True, exist_ok=True)
    page = wiki / "projects" / "x" / "notype.md"
    for session, content in (("s1", "v1"), ("s2", "v2")):
        propose_and_apply(
            Proposal(
                op="UPDATE" if content != "v1" else "ADD",
                page="projects/x/notype.md", content=content,
                reason="seed", producer="retrospective", writer="human", session=session,
            )
        )

    assert promotion_candidates(wiki) == []


def test_unreadable_wiki_root_returns_empty_list(tmp_path, clean_path_env):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    missing = tmp_path / "does-not-exist"
    assert promotion_candidates(missing) == []


# --- doctrine_shaping ---------------------------------------------------

_FAKE_COMPANION = Companion(
    cid="fake-tool",
    kind="tool",
    title="FakeTool",
    pitch="pretend companion for tests",
    install_hint="uv tool install fake-tool",
    detect="fake-tool",
    added_in="0.4.2",
)


def _reconcile_returning(offer):
    def _fake_reconcile():
        return [offer]

    return _fake_reconcile


def test_doctrine_shaping_missing_title_becomes_suggestion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lib.companions.reconcile",
        _reconcile_returning(Offer(_FAKE_COMPANION, installed=True, decision="accepted")),
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "before\n<!-- ren:begin -->\nsome content, no companion mention\n<!-- ren:end -->\nafter\n",
        encoding="utf-8",
    )

    specs = doctrine_shaping(claude_md)

    assert len(specs) == 1
    spec = specs[0]
    assert spec.producer == "doctrine"
    assert spec.kind == "structured_action"
    assert spec.payload == {"action": "refresh_claude_md"}
    assert spec.fingerprint == "doctrine:claude-md:fake-tool"


def test_doctrine_shaping_title_present_in_block_no_suggestion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lib.companions.reconcile",
        _reconcile_returning(Offer(_FAKE_COMPANION, installed=True, decision="accepted")),
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "<!-- ren:begin -->\nFakeTool is already listed here\n<!-- ren:end -->\n",
        encoding="utf-8",
    )

    assert doctrine_shaping(claude_md) == []


def test_doctrine_shaping_not_installed_no_suggestion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lib.companions.reconcile",
        _reconcile_returning(Offer(_FAKE_COMPANION, installed=False, decision="accepted")),
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("<!-- ren:begin -->\nnothing\n<!-- ren:end -->\n", encoding="utf-8")

    assert doctrine_shaping(claude_md) == []


def test_doctrine_shaping_not_accepted_no_suggestion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lib.companions.reconcile",
        _reconcile_returning(Offer(_FAKE_COMPANION, installed=True, decision=None)),
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("<!-- ren:begin -->\nnothing\n<!-- ren:end -->\n", encoding="utf-8")

    assert doctrine_shaping(claude_md) == []


def test_doctrine_shaping_missing_file_no_suggestions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lib.companions.reconcile",
        _reconcile_returning(Offer(_FAKE_COMPANION, installed=True, decision="accepted")),
    )
    missing = tmp_path / "does-not-exist" / "CLAUDE.md"

    assert doctrine_shaping(missing) == []


def test_doctrine_shaping_no_managed_block_no_suggestions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "lib.companions.reconcile",
        _reconcile_returning(Offer(_FAKE_COMPANION, installed=True, decision="accepted")),
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("just plain content, no markers\n", encoding="utf-8")

    assert doctrine_shaping(claude_md) == []


# --- wiki_health_critical -------------------------------------------------


def test_wiki_health_critical_global_prefix_pair_becomes_suggestion(wiki):
    sweep_result = {
        "contradiction_pairs": [
            {"page": "global/rules.md", "with": "projects/x/notes.md", "evidence": "A vs not A"},
        ]
    }

    specs = wiki_health_critical(sweep_result)

    assert len(specs) == 1
    spec = specs[0]
    assert spec.producer == "wiki-health"
    assert spec.kind == "structured_action"
    assert spec.payload == {
        "action": "review_contradiction",
        "page": "global/rules.md",
        "with": "projects/x/notes.md",
        "evidence": "A vs not A",
    }


def test_wiki_health_critical_non_critical_pair_is_excluded(wiki):
    (wiki / "projects" / "x").mkdir(parents=True, exist_ok=True)
    (wiki / "projects" / "x" / "notes.md").write_text(
        "---\ntype: note\n---\nsome content\n", encoding="utf-8"
    )
    (wiki / "projects" / "y").mkdir(parents=True, exist_ok=True)
    (wiki / "projects" / "y" / "other.md").write_text(
        "---\ntype: note\n---\nsome content\n", encoding="utf-8"
    )
    sweep_result = {
        "contradiction_pairs": [
            {"page": "projects/x/notes.md", "with": "projects/y/other.md", "evidence": "A vs not A"},
        ]
    }

    assert wiki_health_critical(sweep_result) == []


def test_wiki_health_critical_doctrine_type_pair_becomes_suggestion(wiki):
    (wiki / "projects" / "x").mkdir(parents=True, exist_ok=True)
    (wiki / "projects" / "x" / "doc.md").write_text(
        "---\ntype: doctrine\n---\nsome content\n", encoding="utf-8"
    )
    (wiki / "projects" / "y").mkdir(parents=True, exist_ok=True)
    (wiki / "projects" / "y" / "other.md").write_text(
        "---\ntype: note\n---\nsome content\n", encoding="utf-8"
    )
    sweep_result = {
        "contradiction_pairs": [
            {"page": "projects/x/doc.md", "with": "projects/y/other.md", "evidence": "A vs not A"},
        ]
    }

    specs = wiki_health_critical(sweep_result)

    assert len(specs) == 1


def test_wiki_health_critical_fingerprint_is_order_stable(wiki):
    sweep_a = {
        "contradiction_pairs": [
            {"page": "global/a.md", "with": "global/b.md", "evidence": "e"},
        ]
    }
    sweep_b = {
        "contradiction_pairs": [
            {"page": "global/b.md", "with": "global/a.md", "evidence": "e"},
        ]
    }

    fp_a = wiki_health_critical(sweep_a)[0].fingerprint
    fp_b = wiki_health_critical(sweep_b)[0].fingerprint

    assert fp_a == fp_b


def test_wiki_health_critical_empty_pairs_returns_empty_list(wiki):
    assert wiki_health_critical({"contradiction_pairs": []}) == []


def test_wiki_health_critical_missing_key_returns_empty_list(wiki):
    assert wiki_health_critical({}) == []
