"""
Tests for lib.memory.promotion.promote_to_project — project-scoped standing
instructions entry path (#63).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/memory/test_promote_to_project.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import promotion, queue
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


def test_first_rule_creates_page_pending(wiki):
    entry = promotion.promote_to_project("Never touch the vendored parser.", "flux", "s-1")

    assert entry.status == "pending"  # instruction-plane hold
    assert entry.proposal.op == "ADD"
    assert entry.proposal.page == "projects/flux/instructions.md"
    assert "type: project-instructions" in entry.proposal.content
    assert "- Never touch the vendored parser." in entry.proposal.content


def test_second_rule_appends_to_existing_page(wiki):
    entry = promotion.promote_to_project("Never touch the vendored parser.", "flux", "s-1")
    queue.approve_and_apply(entry.qid, who="human:test")

    entry2 = promotion.promote_to_project("Always run migrations in a transaction.", "flux", "s-2")

    assert entry2.proposal.op == "UPDATE"
    assert entry2.proposal.page == "projects/flux/instructions.md"
    content = entry2.proposal.content
    first_idx = content.index("- Never touch the vendored parser.")
    second_idx = content.index("- Always run migrations in a transaction.")
    assert first_idx < second_idx


def test_empty_rule_raises(wiki):
    with pytest.raises(promotion.PromotionError):
        promotion.promote_to_project("   ", "flux", "s-1")


def test_bad_slug_raises(wiki):
    with pytest.raises(promotion.PromotionError):
        promotion.promote_to_project("rule", "../evil", "s-1")


def test_quarantined_page_refuses(wiki):
    from lib.memory.quarantine import mark

    page = wiki / "projects/flux/instructions.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "---\ntype: project-instructions\nschema_version: 1\nproject: flux\n"
        'title: "Standing Instructions"\n---\n\n# Standing instructions — flux\n\n## Rules\n'
        "\n- Some prior rule.\n"
    )
    page.write_text(mark(body), encoding="utf-8")

    with pytest.raises(promotion.PromotionError):
        promotion.promote_to_project("rule", "flux", "s-1")
