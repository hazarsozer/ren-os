"""
Tests for skills.suggestions.lib — the single interactive approve/reject
surface over lib.suggestions (Task 19, RenOS 0.4.2).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/suggestions/test_suggestions_skill.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import queue
from lib.memory.journal import entries as journal_entries
from lib.ren_paths import wiki_root
from lib.suggestions import SuggestionSpec, record
from skills.suggestions.lib import accept, decline, render_list, render_suggestion


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


def _page_write_spec(page="projects/x/notes.md", **overrides):
    defaults = dict(
        producer="retrospective",
        title=f"Write {page}",
        rationale="you kept saying this — worth writing down",
        evidence={"count": 3},
        kind="page_write",
        payload={
            "op": "ADD",
            "page": page,
            "content": "---\ntitle: Notes\n---\nSomething durable happened.\n",
            "reason": "recurring pattern",
            "producer": "retrospective",
            "writer": "human",
            "session": "s-test",
        },
        fingerprint=f"pw:{page}",
    )
    defaults.update(overrides)
    return SuggestionSpec(**defaults)


# --------------------------------------------------------------- lifecycle


def test_accept_page_write_applies_via_queue_and_records_status(wiki):
    entry = record(_page_write_spec())
    result = accept(entry["sid"], "s-test")

    assert result["applied"] is True
    assert (wiki / "projects/x/notes.md").exists()

    from lib.suggestions import all_suggestions

    stored = next(e for e in all_suggestions() if e["sid"] == entry["sid"])
    assert stored["status"] == "accepted"

    entries = journal_entries("projects/x/notes.md")
    assert len(entries) == 1
    assert entries[0]["op"] == "ADD"


def test_decline_is_durable_and_never_re_offered(wiki):
    spec = _page_write_spec()
    entry = record(spec)
    result = decline(entry["sid"])

    assert result["status"] == "declined"
    assert record(spec) is None  # same fingerprint, never re-nagged


def test_accept_unknown_sid_raises_key_error(wiki):
    with pytest.raises(KeyError):
        accept("s-does-not-exist", "s-test")


def test_render_list_empty_state(wiki):
    assert render_list() == "No pending suggestions."


def test_render_list_numbers_pending_oldest_first(wiki):
    e1 = record(_page_write_spec(page="a.md", fingerprint="pw:a"))
    e2 = record(_page_write_spec(page="b.md", fingerprint="pw:b"))

    rendered = render_list()
    assert rendered.index(e1["title"]) < rendered.index(e2["title"])
    assert rendered.startswith("1.")


def test_render_suggestion_includes_content_preview_for_page_write(wiki):
    entry = record(_page_write_spec())
    rendered = render_suggestion(entry)
    assert "Something durable happened." in rendered
    assert entry["title"] in rendered
    assert entry["producer"] in rendered


def test_accept_global_page_write_applies_under_global(wiki):
    entry = record(_page_write_spec(page="global/decisions.md", fingerprint="pw:global"))
    result = accept(entry["sid"], "s-test")

    assert result["applied"] is True
    assert (wiki / "global/decisions.md").exists()


def test_accept_promote_to_global_applies_via_promotion_and_queue(wiki):
    source = "projects/x/rules.md"
    (wiki / "projects/x").mkdir(parents=True, exist_ok=True)
    (wiki / source).write_text(
        "---\ntitle: Rules\ntype: doctrine\n---\nAlways do X.\n", encoding="utf-8"
    )

    entry = record(
        SuggestionSpec(
            producer="promotion",
            title=f"Promote {source} to global",
            rationale="reinforced repeatedly",
            evidence={"updates": 2, "sessions": ["s1", "s2"]},
            kind="structured_action",
            payload={"action": "promote_to_global", "source_page": source},
            fingerprint=f"promotion:{source}",
        )
    )

    result = accept(entry["sid"], "s-test")

    assert result["applied"] is True
    assert result["detail"]["page"].startswith("global/")
    assert (wiki / result["detail"]["page"]).exists()


def test_accept_refresh_claude_md_writes_managed_block(wiki, monkeypatch, tmp_path):
    claude_dir = tmp_path / "claude-home"
    monkeypatch.setenv("REN_CLAUDE_DIR", str(claude_dir))

    entry = record(
        SuggestionSpec(
            producer="doctrine",
            title="Refresh CLAUDE.md",
            rationale="companion installed but not reflected",
            evidence={"cid": "c-1"},
            kind="structured_action",
            payload={"action": "refresh_claude_md"},
            fingerprint="doctrine:claude-md:c-1",
        )
    )

    result = accept(entry["sid"], "s-test")

    assert result["applied"] is True
    assert (claude_dir / "CLAUDE.md").exists()


def test_accept_review_contradiction_applies_nothing_but_returns_evidence(wiki):
    entry = record(
        SuggestionSpec(
            producer="wiki-health",
            title="Review contradiction: a.md vs b.md",
            rationale="critical-page contradiction",
            evidence={"page": "a.md", "with": "b.md"},
            kind="structured_action",
            payload={"action": "review_contradiction", "page": "a.md", "with": "b.md", "evidence": {"x": 1}},
            fingerprint="wiki-health:contradiction:a.md|b.md",
        )
    )

    result = accept(entry["sid"], "s-test")

    assert result["applied"] is False
    assert result["detail"]["page"] == "a.md"
    assert result["detail"]["with"] == "b.md"


def test_accept_page_write_noop_duplicate_records_decision_without_apply(wiki):
    page = "projects/x/dup.md"
    content = "---\ntitle: Dup\n---\nAlready here.\n"

    # Seed the page with identical content via the normal write door first.
    seeded = queue.propose(
        queue.Proposal(
            op="ADD",
            page=page,
            content=content,
            reason="seed",
            producer="retrospective",
            writer="human",
            session="s-seed",
        )
    )
    queue.approve_and_apply(seeded.qid, who="test")

    entry = record(_page_write_spec(page=page, fingerprint="pw:dup", payload={
        "op": "UPDATE",
        "page": page,
        "content": content,
        "reason": "recurring pattern",
        "producer": "retrospective",
        "writer": "human",
        "session": "s-test",
    }))

    result = accept(entry["sid"], "s-test")

    assert result["applied"] is False
    assert result["detail"] == "content already on page"

    from lib.suggestions import all_suggestions

    stored = next(e for e in all_suggestions() if e["sid"] == entry["sid"])
    assert stored["status"] == "accepted"
