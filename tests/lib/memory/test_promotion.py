"""
Tests for lib.memory.promotion — typed global-tier promotion (Task 4.5).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/memory/test_promotion.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import queue
from lib.memory.promotion import GLOBAL_PREFIX, PromotionError, demote_check, promote_to_global
from lib.memory.provenance import new_provenance, stamp_frontmatter
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


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _stamped(body, *, writer="human", op="ADD", session="sess-1", supersedes=None):
    prov = new_provenance(writer, session, op, "unused.md", supersedes=supersedes)
    return stamp_frontmatter(body, prov), prov


# --- typed check --------------------------------------------------------


def test_promote_doctrine_page_creates_pending_entry_with_promoted_from(wiki):
    body = "---\ntitle: Coding style\ntype: doctrine\n---\nAlways write tests first.\n"
    text, prov = _stamped(body)
    _write(wiki, "projects/demo/style.md", text)

    entry = promote_to_global("projects/demo/style.md", "sess-2")

    assert entry.status == "pending"
    assert entry.proposal.page == "global/style.md"
    assert entry.proposal.writer == "human"
    assert entry.proposal.producer == "promotion"
    assert entry.proposal.op == "ADD"
    assert f"promoted-from: projects/demo/style.md ({prov.write_id})" in entry.proposal.content
    # Original typed frontmatter is preserved in the proposed content.
    assert "type: doctrine" in entry.proposal.content


def test_promote_preference_page_works(wiki):
    body = "---\ntitle: Editor preference\ntype: preference\n---\nUse tabs, not spaces.\n"
    text, prov = _stamped(body)
    _write(wiki, "projects/demo/prefs.md", text)

    entry = promote_to_global("projects/demo/prefs.md", "sess-2")

    assert entry.proposal.page == "global/prefs.md"
    assert f"promoted-from: projects/demo/prefs.md ({prov.write_id})" in entry.proposal.content


@pytest.mark.parametrize(
    "frontmatter_type_line",
    ["", "type: project-fact\n", "type: l2-map\n", "type: lesson\n"],
)
def test_promote_rejects_missing_or_wrong_type(wiki, frontmatter_type_line):
    body = f"---\ntitle: Some page\n{frontmatter_type_line}---\nSome fact about this project.\n"
    text, _ = _stamped(body)
    _write(wiki, "projects/demo/fact.md", text)

    with pytest.raises(PromotionError, match="typed"):
        promote_to_global("projects/demo/fact.md", "sess-2")


# --- quarantine check -----------------------------------------------------


def test_promote_rejects_quarantined_source(wiki):
    from lib.memory.quarantine import mark

    body = "---\ntitle: LLM doctrine draft\ntype: doctrine\n---\nMaybe write tests first?\n"
    text, _ = _stamped(body, writer="llm-auto")
    text = mark(text)
    _write(wiki, "projects/demo/draft-doctrine.md", text)

    with pytest.raises(PromotionError, match="quarantined"):
        promote_to_global("projects/demo/draft-doctrine.md", "sess-2")


# --- missing source --------------------------------------------------------


def test_promote_missing_source_raises_promotion_error(wiki):
    with pytest.raises(PromotionError):
        promote_to_global("projects/demo/does-not-exist.md", "sess-2")


# --- explicit target -------------------------------------------------------


def test_promote_respects_explicit_target_page(wiki):
    body = "---\ntitle: House style\ntype: doctrine\n---\nBody text.\n"
    text, _ = _stamped(body)
    _write(wiki, "projects/demo/style.md", text)

    entry = promote_to_global(
        "projects/demo/style.md", "sess-2", target_page="global/coding/house-style.md"
    )
    assert entry.proposal.page == "global/coding/house-style.md"


def test_promotion_target_with_traversal_is_rejected(wiki):
    body = "---\ntitle: House style\ntype: doctrine\n---\nBody text.\n"
    text, _ = _stamped(body)
    _write(wiki, "projects/demo/style.md", text)

    with pytest.raises(PromotionError):
        promote_to_global(
            "projects/demo/style.md", "sess-2", target_page="global/../identity.md"
        )


# --- promote onto existing global page -> UPDATE + supersedes conflict -----


def test_promote_onto_existing_global_page_is_update_with_conflicts(wiki):
    existing_body = "---\ntitle: House style\ntype: doctrine\n---\nOld body text.\n"
    existing_text, existing_prov = _stamped(existing_body, session="sess-0")
    _write(wiki, "global/style.md", existing_text)

    source_body = "---\ntitle: House style v2\ntype: doctrine\n---\nNew body text.\n"
    source_text, _ = _stamped(source_body, session="sess-1")
    _write(wiki, "projects/demo/style.md", source_text)

    entry = promote_to_global("projects/demo/style.md", "sess-2")

    assert entry.proposal.op == "UPDATE"
    assert entry.proposal.page == "global/style.md"
    assert entry.conflicts != []
    assert any(c.get("kind") == "supersedes" for c in entry.conflicts)


# --- demote_check ------------------------------------------------------------


def test_demote_check_clean_tier_returns_empty(wiki):
    body = "---\ntitle: Doctrine A\ntype: doctrine\n---\nBody.\n"
    text, _ = _stamped(body)
    _write(wiki, "global/a.md", text)

    assert demote_check() == []


def test_demote_check_flags_non_doctrine_page_under_global(wiki):
    good_body = "---\ntitle: Doctrine A\ntype: doctrine\n---\nBody.\n"
    good_text, _ = _stamped(good_body)
    _write(wiki, "global/a.md", good_text)

    bad_body = "---\ntitle: Drifted page\ntype: project-fact\n---\nThis shouldn't be here.\n"
    bad_text, _ = _stamped(bad_body)
    _write(wiki, "global/b.md", bad_text)

    violations = demote_check()
    assert violations == ["global/b.md"]


def test_demote_check_missing_directory_returns_empty(wiki):
    assert demote_check() == []


# --- end-to-end: approve -> apply lands under global/, not quarantined -----


def test_promote_rejects_non_global_target(wiki):
    body = "---\ntitle: House style\ntype: doctrine\n---\nBody text.\n"
    text, _ = _stamped(body)
    _write(wiki, "projects/demo/style.md", text)

    with pytest.raises(PromotionError, match="global/"):
        promote_to_global("projects/demo/style.md", "sess-2", target_page="projects/app/sneaky.md")


def test_promote_approve_apply_lands_under_global_not_quarantined(wiki):
    from lib.memory.quarantine import is_quarantined

    body = "---\ntitle: House style\ntype: doctrine\n---\nWrite tests first, always.\n"
    text, _ = _stamped(body)
    _write(wiki, "projects/demo/style.md", text)

    entry = promote_to_global("projects/demo/style.md", "sess-2")
    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)

    page_abs = wiki / "global" / "style.md"
    assert page_abs.exists()
    applied_text = page_abs.read_text(encoding="utf-8")
    assert is_quarantined(applied_text) is False
    assert prov.writer == "human"
    assert "type: doctrine" in applied_text
    assert "promoted-from: projects/demo/style.md" in applied_text
