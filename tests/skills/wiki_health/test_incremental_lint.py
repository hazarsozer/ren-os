"""
Tests for `skills.wiki-health.lib.run_incremental_lint` — Task 3, RenOS 0.6.5
("shipped agents"). The lint is the engine the `ren-wiki-lint` agent drives:
it selects pages from the Task 2 watermark, applies MECHANICALLY SAFE fixes
through the write queue (`propose_and_apply` — never a direct write), routes
JUDGMENT-shaped findings to the durable suggestion store, and stamps the
watermark forward.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — matching tests/skills/wiki_health/test_sweep.py.

Run with: uv run pytest tests/skills/wiki_health/test_incremental_lint.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.memory import journal
from lib.memory.provenance import Provenance
from lib.ren_paths import wiki_root
from lib.suggestions import pending_suggestions

wiki_health = importlib.import_module("skills.wiki-health.lib")
watermark = importlib.import_module("skills.wiki-health.lib.watermark")


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


def _prov(page: str, op: str = "UPDATE") -> Provenance:
    return Provenance(
        write_id="w-test", ts="2026-08-02T00:00:00Z", writer="human",
        session="s", op=op, page=page, supersedes=None,
    )


def _touch_journal(page: str, op: str = "UPDATE") -> None:
    journal.append(_prov(page, op))


def _page(wiki, rel: str, body: str, ptype: str = "knowledge") -> None:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntype: {ptype}\n---\n{body}", encoding="utf-8")


# --------------------------------------------------- (a) safe fix: hub entry


def test_hub_index_missing_entry_is_fixed_through_the_queue(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["scope"] == "incremental"
    assert any(
        f["page"] == "projects/p/knowledge/topic/index.md" and f["fix"] == "hub-missing-entry"
        for f in result["fixed"]
    ), result
    hub = (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8")
    assert "alpha.md" in hub


# ------------------------------------------- (b) judgment → suggestion store


def test_schema_violation_becomes_a_pending_suggestion_not_a_write(wiki):
    path = wiki / "projects/p/knowledge/topic/beta.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Beta\n\nno frontmatter at all\n", encoding="utf-8")
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- beta.md\n", ptype="l2-map")
    before = path.read_text(encoding="utf-8")
    _touch_journal("projects/p/knowledge/topic/beta.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["queued_suggestions"] >= 1
    assert not any(f["page"].endswith("beta.md") for f in result["fixed"])
    assert path.read_text(encoding="utf-8") == before
    pend = pending_suggestions()
    assert any(
        s["producer"] == "wiki-health"
        and s["kind"] == "structured_action"
        and s["payload"]["action"] == "review_lint_finding"
        and s["fingerprint"].startswith("wiki-lint:projects/p/knowledge/topic/beta.md:")
        for s in pend
    ), pend


# ------------------------------------------------------- (c) watermark stamp


def test_clean_run_advances_watermark_clean_true(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["queued_suggestions"] == 0
    assert result["watermark_advanced"] is True
    stamp = watermark.read_watermark()
    assert stamp["clean"] is True
    assert stamp["journal_lines_seen"] == len(journal.entries())


def test_dirty_run_advances_watermark_clean_false(wiki):
    path = wiki / "projects/p/knowledge/topic/beta.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Beta\n\nno frontmatter\n", encoding="utf-8")
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- beta.md\n", ptype="l2-map")
    _touch_journal("projects/p/knowledge/topic/beta.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["watermark_advanced"] is True
    assert watermark.read_watermark()["clean"] is False


# ------------------------------------------------------------- (d) full=True


def test_full_scope_ignores_the_watermark(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    _page(wiki, "projects/p/knowledge/other/index.md", "# Other\n\n## Pages\n- gamma.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/other/gamma.md", "# Gamma\n")
    # No journal lines at all — the incremental scope would be empty.
    incremental = wiki_health.run_incremental_lint(session="s-1")
    assert incremental["pages_checked"] == []

    result = wiki_health.run_incremental_lint(session="s-1", full=True)

    assert result["scope"] == "full"
    assert "projects/p/knowledge/topic/alpha.md" in result["pages_checked"]
    assert "projects/p/knowledge/other/gamma.md" in result["pages_checked"]


# --------------------------------------------------------------- (e) raw/ is


def test_lint_never_writes_under_project_raw(wiki):
    raw = wiki / "projects/p/raw/source.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("# Source\n\nno frontmatter, a defect anywhere else\n", encoding="utf-8")
    before = raw.read_text(encoding="utf-8")
    _touch_journal("projects/p/raw/source.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert not any("raw/" in f["page"] for f in result["fixed"])
    assert raw.read_text(encoding="utf-8") == before
    assert result["queued_suggestions"] >= 1
    assert any(s["fingerprint"].startswith("wiki-lint:projects/p/raw/source.md:") for s in pending_suggestions())


# ------------------------------------------------------ (f) second run is dry


def test_second_run_after_a_clean_pass_checks_zero_pages(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    first = wiki_health.run_incremental_lint(session="s-1")
    assert first["pages_checked"]

    second = wiki_health.run_incremental_lint(session="s-1")
    assert second["pages_checked"] == []
    assert second["fixed"] == []


# ------------------------------------------- extra safe-fix classes (step 3)


def test_dangling_wikilink_to_renamed_page_is_repointed(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\nsee [[old/place/moved.md]]\n")
    _page(wiki, "projects/p/knowledge/other/index.md", "# Other\n\n## Pages\n- moved.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/other/moved.md", "# Moved\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert any(f["fix"] == "dangling-link-repointed" for f in result["fixed"]), result
    text = (wiki / "projects/p/knowledge/topic/alpha.md").read_text(encoding="utf-8")
    assert "[[projects/p/knowledge/other/moved.md]]" in text


def test_link_to_deleted_page_is_commented_out_not_removed(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\nsee [[projects/p/knowledge/topic/gone.md]]\n")
    _touch_journal("projects/p/knowledge/topic/gone.md", op="DELETE")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert any(f["fix"] == "stale-link-commented" for f in result["fixed"]), result
    text = (wiki / "projects/p/knowledge/topic/alpha.md").read_text(encoding="utf-8")
    assert "<!--" in text and "gone.md" in text


def test_instruction_plane_pages_are_never_auto_fixed(wiki):
    path = wiki / "decisions" / "policy.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Policy\n\nno frontmatter\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    _touch_journal("decisions/policy.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["fixed"] == []
    assert path.read_text(encoding="utf-8") == before
    assert result["queued_suggestions"] >= 1
