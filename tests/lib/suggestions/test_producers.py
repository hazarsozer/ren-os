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


def _seed_updates(page: str, page_type: str = "preference", sessions: tuple[str, ...] = ("s1", "s2", "s3")):
    """Drive the real write door with one journaled UPDATE per session in
    `sessions` (after an initial ADD), producing the recurrence evidence the
    producer's ratified 3-of-5 gate reads (0.4.5: `recurs()`, not ad-hoc
    counts)."""
    propose_and_apply(
        Proposal(
            op="ADD", page=page, content=_page_content(page_type, "v0"),
            reason="seed", producer="retrospective", writer="human", session=sessions[0],
        )
    )
    for i, session in enumerate(sessions, start=1):
        propose_and_apply(
            Proposal(
                op="UPDATE", page=page, content=_page_content(page_type, f"v{i}"),
                reason="seed", producer="retrospective", writer="human", session=session,
            )
        )


def test_reinforced_preference_page_becomes_candidate(wiki):
    _seed_updates("projects/x/pref.md")

    specs = promotion_candidates(wiki)

    assert len(specs) == 1
    spec = specs[0]
    assert spec.producer == "promotion"
    assert spec.kind == "structured_action"
    assert spec.payload == {"action": "promote_to_global", "source_page": "projects/x/pref.md"}
    assert spec.fingerprint == "promotion:projects/x/pref.md"


def test_doctrine_type_also_qualifies(wiki):
    _seed_updates("projects/x/doc.md", page_type="doctrine")

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
    _seed_updates("projects/x/pref.md")

    page = wiki / "projects" / "x" / "pref.md"
    page.write_text(quarantine.mark(page.read_text(encoding="utf-8")), encoding="utf-8")

    assert promotion_candidates(wiki) == []


def test_already_global_page_does_not_qualify(wiki):
    _seed_updates("global/pref.md")

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


def test_two_sessions_do_not_clear_the_recurrence_gate(wiki):
    # 0.4.5: the ratified 3-of-5 gate (spec §5.2) replaces the old ad-hoc
    # 2-updates/2-sessions threshold — two sessions of reinforcement is
    # below-threshold evidence, not a suggestion.
    _seed_updates("projects/x/pref.md", sessions=("s1", "s2"))

    assert promotion_candidates(wiki) == []


def test_evidence_outside_the_last_five_sessions_does_not_qualify(wiki):
    # Reinforced in s1-s3, but five newer sessions (s4-s8) have since
    # happened — the evidence falls outside the 5-session window.
    _seed_updates("projects/x/pref.md", sessions=("s1", "s2", "s3"))
    for s in ("s4", "s5", "s6", "s7", "s8"):
        propose_and_apply(
            Proposal(
                op="ADD", page=f"projects/y/{s}.md", content=_page_content("note", "x"),
                reason="seed", producer="retrospective", writer="human", session=s,
            )
        )

    assert promotion_candidates(wiki) == []


def test_released_but_foreign_page_never_yields_promotion_spec(wiki):
    # Task 9: even after 3-of-5 reinforcement AND the quarantine banner being
    # released, a page whose own ren_trust stamp is "foreign" must never
    # yield a promotion spec — mirrors the existing is_quarantined skip.
    page = "projects/x/foreign-pref.md"
    sessions = ("s1", "s2", "s3")
    propose_and_apply(
        Proposal(
            op="ADD", page=page, content=_page_content("preference", "v0"),
            reason="seed", producer="ingest", writer="llm-auto", session=sessions[0],
        )
    )
    for i, session in enumerate(sessions, start=1):
        propose_and_apply(
            Proposal(
                op="UPDATE", page=page, content=_page_content("preference", f"v{i}"),
                reason="seed", producer="ingest", writer="llm-auto", session=session,
            )
        )

    abs_page = wiki / page
    abs_page.write_text(quarantine.release(abs_page.read_text(encoding="utf-8")), encoding="utf-8")
    assert not quarantine.is_quarantined(abs_page.read_text(encoding="utf-8"))  # banner really released

    assert promotion_candidates(wiki) == []


def test_unreadable_wiki_root_returns_empty_list(tmp_path, clean_path_env):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    missing = tmp_path / "does-not-exist"
    assert promotion_candidates(missing) == []


# --- doctrine_shaping (Gate-0 finding a: render-and-compare) -------------
#
# The predicate no longer looks at companion titles (render_global_block
# never writes them into the managed block, so that check was a permanent
# false positive) — it renders what a refresh WOULD write and compares it
# to disk. `doctrine_root` is pointed at an empty tmp dir in every test so
# `load_all` degrades to `[]` (deterministic doctrine index regardless of
# the real framework's installed doctrine files).


def test_doctrine_shaping_stale_block_suggests_refresh(tmp_path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "before\n<!-- ren:begin -->\nstale content from a previous render\n<!-- ren:end -->\nafter\n",
        encoding="utf-8",
    )
    empty_doctrine_root = tmp_path / "no-doctrine"

    specs = doctrine_shaping(
        claude_md, wiki_root=tmp_path / "wiki", doctrine_root=empty_doctrine_root
    )

    assert len(specs) == 1
    spec = specs[0]
    assert spec.producer == "doctrine"
    assert spec.kind == "structured_action"
    assert spec.payload == {"action": "refresh_claude_md"}
    assert spec.fingerprint == "doctrine:claude-md:refresh"
    assert "out of date" in spec.rationale


def test_doctrine_shaping_up_to_date_no_suggestion(tmp_path):
    from lib.adapter.claude_md import apply_block, render_global_block

    claude_md = tmp_path / "CLAUDE.md"
    wiki_root = tmp_path / "wiki"
    empty_doctrine_root = tmp_path / "no-doctrine"

    content = render_global_block(existing_text="", doctrine_root=empty_doctrine_root, wiki_root=wiki_root)
    apply_block(claude_md, content)

    assert doctrine_shaping(claude_md, wiki_root=wiki_root, doctrine_root=empty_doctrine_root) == []


def test_doctrine_shaping_missing_file_suggests_refresh(tmp_path):
    # Correct behavior: refreshing a nonexistent CLAUDE.md would CREATE it —
    # that's a real diff (existing="" vs the rendered block), so it suggests.
    missing = tmp_path / "does-not-exist" / "CLAUDE.md"
    empty_doctrine_root = tmp_path / "no-doctrine"

    specs = doctrine_shaping(missing, wiki_root=tmp_path / "wiki", doctrine_root=empty_doctrine_root)

    assert len(specs) == 1
    assert specs[0].fingerprint == "doctrine:claude-md:refresh"


def test_doctrine_shaping_no_managed_block_still_compares(tmp_path):
    # No prior ren:begin/end markers — spliced_text appends a brand-new
    # block, which differs from the untouched file, so this still suggests.
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("just plain content, no markers\n", encoding="utf-8")
    empty_doctrine_root = tmp_path / "no-doctrine"

    specs = doctrine_shaping(claude_md, wiki_root=tmp_path / "wiki", doctrine_root=empty_doctrine_root)

    assert len(specs) == 1
    assert specs[0].fingerprint == "doctrine:claude-md:refresh"


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


def test_wiki_health_critical_foreign_page_is_excluded(wiki):
    # Task 9: mirrors the promotion-side foreign skip — a critical-page pair
    # is excluded if either page's ren_trust stamp is "foreign", even though
    # it would otherwise qualify (doctrine type on one side).
    (wiki / "projects" / "x").mkdir(parents=True, exist_ok=True)
    (wiki / "projects" / "x" / "doc.md").write_text(
        '---\ntype: doctrine\nren_write_id: "w-test"\nren_trust: "foreign"\n---\nsome content\n', encoding="utf-8"
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

    assert wiki_health_critical(sweep_result) == []


def test_wiki_health_critical_empty_pairs_returns_empty_list(wiki):
    assert wiki_health_critical({"contradiction_pairs": []}) == []


def test_wiki_health_critical_missing_key_returns_empty_list(wiki):
    assert wiki_health_critical({}) == []
