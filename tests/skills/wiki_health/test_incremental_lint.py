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
    # Steady state: a watermark EXISTS (stamped at 0 lines seen), which is
    # what every test below exercises. An ABSENT watermark is the distinct
    # first-run-after-upgrade case — it seeds and lints nothing — and those
    # tests call `_unseed()` explicitly.
    watermark.advance_watermark(0, clean=True)
    return root


def _unseed() -> None:
    """Remove the watermark file: the post-upgrade "never linted" state."""
    (wiki_root() / ".ren" / "wiki_lint_watermark.json").unlink(missing_ok=True)


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
    # Start from a NON-ZERO watermark, where a delta and the absolute total
    # diverge — at W=0 the two are indistinguishable.
    _touch_journal("projects/p/knowledge/topic/alpha.md")
    _touch_journal("projects/p/knowledge/topic/alpha.md")
    watermark.advance_watermark(len(journal.entries()), clean=True)
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


# =====================================================================
# Fix round 1 — regressions for the review findings (2026-08-02)
# =====================================================================


def _clean_wiki(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")


# ---- CRITICAL 1: absolute watermark, from a NON-ZERO starting stamp


def test_watermark_stamps_absolute_total_over_three_runs_from_nonzero(wiki):
    _clean_wiki(wiki)
    # Pre-existing history + an already-advanced watermark: this is the case
    # where a DELTA and the ABSOLUTE total diverge (the bug's blind spot).
    for _ in range(3):
        _touch_journal("projects/p/knowledge/topic/alpha.md")
    watermark.advance_watermark(len(journal.entries()), clean=True)
    assert watermark.read_watermark()["journal_lines_seen"] == 3

    _touch_journal("projects/p/knowledge/topic/alpha.md")
    total = len(journal.entries())

    run1 = wiki_health.run_incremental_lint(session="s-1")
    assert run1["pages_checked"]
    assert watermark.read_watermark()["journal_lines_seen"] == total

    run2 = wiki_health.run_incremental_lint(session="s-1")
    assert run2["pages_checked"] == []
    assert watermark.read_watermark()["journal_lines_seen"] == total

    run3 = wiki_health.run_incremental_lint(session="s-1")
    assert run3["pages_checked"] == []
    assert watermark.read_watermark()["journal_lines_seen"] == total


# ---- IMPORTANT 2: aliased wikilinks


def test_aliased_dangling_link_is_repointed_keeping_the_alias(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\nsee [[old/moved.md|the moved page]]\n")
    _page(wiki, "projects/p/knowledge/other/index.md", "# Other\n\n## Pages\n- moved.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/other/moved.md", "# Moved\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert any(f["fix"] == "dangling-link-repointed" for f in result["fixed"]), result
    text = (wiki / "projects/p/knowledge/topic/alpha.md").read_text(encoding="utf-8")
    assert "[[projects/p/knowledge/other/moved.md|the moved page]]" in text


def test_unfixable_aliased_link_is_never_claimed_as_fixed(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\nsee [[nowhere/at/all.md|alias]]\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["fixed"] == []
    # ...and it did NOT vanish from both dispositions.
    assert any(
        s["payload"]["rule"] == "dangling-link" and s["payload"]["page"].endswith("alpha.md")
        for s in pending_suggestions()
    ), pending_suggestions()


# ---- IMPORTANT 3: `## Pages`-lookalike must not crash the run


def test_undecodable_page_in_scope_does_not_crash_the_run(wiki):
    """`UnicodeDecodeError` is a `ValueError`, NOT an `OSError`, so the
    detection walk's `except OSError` used to let it escape and crash the
    whole lint pass. An undecodable page cannot be linted; it must be
    skipped, and the run must still complete and advance the watermark. No
    hub page is created here — deliberately, so this hits the plain
    detection-walk read directly rather than routing through a hub-fix
    write (a separate call path)."""
    path = wiki / "projects/p/knowledge/topic/alpha.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# Caf\xe9 notes\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")  # must not raise

    assert result["watermark_advanced"] is True
    assert result["fixed"] == []
    assert result["held"] == []


@pytest.mark.parametrize(
    "hub_body",
    [
        "# Topic\n\nwe keep a ## Pages list somewhere\n",
        "# Topic\n\n## Pages (draft)\n- nothing yet\n",
        "# Topic\n\n```\n## Pages\n```\n",
    ],
)
def test_pages_section_lookalikes_do_not_crash_the_run(wiki, hub_body):
    _page(wiki, "projects/p/knowledge/topic/index.md", hub_body, ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["watermark_advanced"] is True
    hub = (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8")
    assert "alpha.md" in hub


# ---- IMPORTANT 4: a HELD proposal is never reported as fixed


def test_a_held_proposal_is_reported_as_held_not_fixed(wiki, monkeypatch):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    lint = importlib.import_module("skills.wiki-health.lib.lint")
    before = (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8")

    class _HeldEntry:
        qid = "q-held"

    monkeypatch.setattr(lint, "propose_and_apply", lambda proposal: (_HeldEntry(), None))

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["fixed"] == []
    assert any(h["fix"] == "hub-missing-entry" and h["qid"] == "q-held" for h in result["held"]), result
    assert (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8") == before
    assert any(s["payload"]["rule"].startswith("held:") for s in pending_suggestions())


# ---- IMPORTANT 5: `clean` reflects OUTSTANDING findings, not just new ones


def test_clean_is_false_while_an_older_finding_is_still_pending(wiki):
    bad = wiki / "projects/p/knowledge/topic/beta.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("# Beta\n\nno frontmatter\n", encoding="utf-8")
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- beta.md\n- gamma.md\n", ptype="l2-map")
    _touch_journal("projects/p/knowledge/topic/beta.md")

    first = wiki_health.run_incremental_lint(session="s-1")
    assert first["queued_suggestions"] == 1
    assert watermark.read_watermark()["clean"] is False

    # A later session touches a DIFFERENT, healthy page. beta.md's finding is
    # still pending and unread — the wiki is not clean.
    _page(wiki, "projects/p/knowledge/topic/gamma.md", "# Gamma\n")
    _touch_journal("projects/p/knowledge/topic/gamma.md")

    second = wiki_health.run_incremental_lint(session="s-1")
    assert second["queued_suggestions"] == 0
    assert watermark.read_watermark()["clean"] is False


# ---- IMPORTANT 6: every fix class converges in one pass


def _journal_len() -> int:
    return len(journal.entries())


def test_hub_fix_converges(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    assert wiki_health.run_incremental_lint(session="s-1")["fixed"]
    before = _journal_len()
    second = wiki_health.run_incremental_lint(session="s-1")
    assert second["fixed"] == []
    assert _journal_len() == before


def test_repoint_fix_converges(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\nsee [[old/moved.md]]\n")
    _page(wiki, "projects/p/knowledge/other/index.md", "# Other\n\n## Pages\n- moved.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/other/moved.md", "# Moved\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    assert wiki_health.run_incremental_lint(session="s-1")["fixed"]
    before = _journal_len()
    second = wiki_health.run_incremental_lint(session="s-1")
    assert second["fixed"] == []
    assert _journal_len() == before


def test_stale_link_fix_converges(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\nsee [[projects/p/knowledge/topic/gone.md]]\n")
    _touch_journal("projects/p/knowledge/topic/gone.md", op="DELETE")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    assert wiki_health.run_incremental_lint(session="s-1")["fixed"]
    before = _journal_len()
    second = wiki_health.run_incremental_lint(session="s-1")
    assert second["fixed"] == []
    assert second["queued_suggestions"] == 0
    assert _journal_len() == before


# ---- IMPORTANT 7: never rewrite links on a page containing a code fence


def test_code_fence_page_links_are_routed_to_suggestions_not_rewritten(wiki):
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n- alpha.md\n", ptype="l2-map")
    _page(
        wiki,
        "projects/p/knowledge/topic/alpha.md",
        "# Alpha\n\nsee [[old/moved.md]]\n\n```md\n[[old/moved.md]]\n```\n",
    )
    _page(wiki, "projects/p/knowledge/other/index.md", "# Other\n\n## Pages\n- moved.md\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/other/moved.md", "# Moved\n")
    before = (wiki / "projects/p/knowledge/topic/alpha.md").read_text(encoding="utf-8")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["fixed"] == []
    assert (wiki / "projects/p/knowledge/topic/alpha.md").read_text(encoding="utf-8") == before
    assert any(s["payload"]["rule"] == "dangling-link" for s in pending_suggestions())


# ---- MINOR: newline hygiene, log.md and quarantined siblings


def test_fix_preserves_absence_of_a_trailing_newline(wiki):
    path = wiki / "projects/p/knowledge/topic/index.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\ntype: l2-map\n---\n# Topic\n\n## Pages\n- keep.md", encoding="utf-8")
    _page(wiki, "projects/p/knowledge/topic/keep.md", "# Keep\n")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    wiki_health.run_incremental_lint(session="s-1")

    text = path.read_text(encoding="utf-8")
    assert "alpha.md" in text
    assert not text.endswith("\n\n")


def test_hub_fix_skips_log_md_and_quarantined_siblings(wiki):
    from lib.memory import quarantine

    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n")
    (wiki / "projects/p/knowledge/topic/log.md").write_text("# Log\n", encoding="utf-8")
    (wiki / "projects/p/knowledge/topic/quar.md").write_text(
        quarantine.mark("---\ntype: knowledge\n---\n# Quar\n"), encoding="utf-8"
    )
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    wiki_health.run_incremental_lint(session="s-1")

    hub = (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8")
    assert "alpha.md" in hub
    assert "log.md" not in hub
    assert "quar.md" not in hub


# ---- FINAL REVIEW 1: the first run after upgrade must not rewrite history


def test_absent_watermark_seeds_and_lints_nothing(wiki):
    """Upgrading from 0.6.4 leaves no watermark file. Before this fix, that
    read as "seen 0 lines" and the FIRST background lint pass expanded to
    every page the journal had ever touched — an unattended full-wiki
    auto-fix the user never asked for. Absent watermark now SEEDS at the
    current journal length and does nothing else."""
    _unseed()
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")
    hub_before = (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8")

    result = wiki_health.run_incremental_lint(session="s-seed")

    assert result["scope"] == "seeded"
    assert result["watermark_seeded"] is True
    assert result["pages_checked"] == []
    assert result["fixed"] == []
    assert result["held"] == []
    assert result["queued_suggestions"] == 0
    assert (wiki / "projects/p/knowledge/topic/index.md").read_text(encoding="utf-8") == hub_before
    assert watermark.read_watermark()["journal_lines_seen"] == _journal_len()
    assert watermark.unlinted()[0] == 0


def test_run_after_seeding_lints_normally(wiki):
    """Steady state starts clean from the seed point: the NEXT write is
    linted as usual."""
    _unseed()
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _touch_journal("projects/p/knowledge/topic/old.md")
    wiki_health.run_incremental_lint(session="s-seed")

    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")
    result = wiki_health.run_incremental_lint(session="s-1")

    assert result["scope"] == "incremental"
    assert any(f["fix"] == "hub-missing-entry" for f in result["fixed"]), result


def test_explicit_full_run_still_lints_history_without_a_watermark(wiki):
    """`full=True` is the deliberate way to lint history — seeding must not
    swallow it."""
    _unseed()
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")

    result = wiki_health.run_incremental_lint(session="s-full", full=True)

    assert result["scope"] == "full"
    assert any(f["fix"] == "hub-missing-entry" for f in result["fixed"]), result


def test_corrupt_but_present_watermark_still_lints_everything(wiki):
    """A CORRUPT stamp is a different case from an absent one: it degrades to
    "lint everything" by design, and that behaviour is preserved."""
    path = wiki / ".ren" / "wiki_lint_watermark.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    result = wiki_health.run_incremental_lint(session="s-corrupt")

    assert result["scope"] == "incremental"
    assert any(f["fix"] == "hub-missing-entry" for f in result["fixed"]), result


# ---- FINAL REVIEW 4: noop-duplicate is "already fixed", not a queue hold


def test_noop_duplicate_is_not_reported_as_a_hold(wiki, monkeypatch):
    """`propose` returns a SYNTHETIC, never-persisted entry with
    status="noop-duplicate" when the proposed content already matches the
    page. That is not a hold: reporting it as one cited a qid absent from the
    queue dir, and left a durable suggestion that could never resolve (which
    also pinned `clean=False` and the wake-up nudge on forever)."""
    _page(wiki, "projects/p/knowledge/topic/index.md", "# Topic\n\n## Pages\n", ptype="l2-map")
    _page(wiki, "projects/p/knowledge/topic/alpha.md", "# Alpha\n\n## Knowledge\n- a fact\n")
    _touch_journal("projects/p/knowledge/topic/alpha.md")

    import lib.memory.queue as queue_mod

    lint = importlib.import_module("skills.wiki-health.lib.lint")

    def fake(proposal):
        # Exactly what `queue.propose` returns when the rewrite normalizes
        # equal to what is already on disk (queue.py `_NOOP_DUPLICATE`):
        # synthetic, never persisted, `prov is None`.
        entry = queue_mod.QueueEntry(
            qid="q-SYNTHETIC", ts="2026-08-02T00:00:00Z", proposal=proposal,
            status="noop-duplicate",
        )
        return entry, None

    monkeypatch.setattr(lint, "propose_and_apply", fake)

    result = wiki_health.run_incremental_lint(session="s-noop")

    assert result["held"] == []
    assert result["fixed"] == []
    assert result["queued_suggestions"] == 0
    assert not [s for s in pending_suggestions() if s["payload"]["rule"].startswith("held:")]
