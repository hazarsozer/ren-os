"""#39 — wiki-health `stale_facts` check: scan durable pages for `ren-volatile`
markers, verify checkable kinds against ground truth, and queue a correction
for each stale line (trust-user targets route to suggestions instead).

Fixture convention copied from tests/skills/wiki_health/test_quarantine_screen.py
(REN_FRAMEWORK_ROOT points `wiki_root()` at a tmp dir so both the sweep and
the write queue operate on the same tree) — no shared isolated_wiki fixture
exists in this codebase.
"""
from __future__ import annotations

import importlib

import pytest

from lib.ren_paths import wiki_root

wiki_health = importlib.import_module("skills.wiki-health.lib")


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


def _write_page(root, rel, body, trust=None):
    page = root / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    fm = "---\ntype: model-trust\n"
    if trust is not None:
        fm += f'ren_trust: "{trust}"\n'
    fm += "---\n"
    page.write_text(fm + body, encoding="utf-8")
    return rel


def test_stale_fact_detected_and_correction_queued(wiki, monkeypatch):
    from lib.memory.volatile import CHECKERS

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "30")
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\nRenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n",
    )

    result = wiki_health.sweep(wiki, apply_corrections=True)
    stale = result["stale_facts"]["stale"]
    assert len(stale) == 1
    assert stale[0]["page"] == rel
    assert stale[0]["ground_truth"] == "30"
    assert result["stale_facts"]["corrections_queued"] == 1

    text = (wiki / rel).read_text(encoding="utf-8")
    lines = text.splitlines()
    corrected_line = next(l for l in lines if "ren-volatile: release-count" in l)
    assert "30" in corrected_line
    assert "12" not in corrected_line


def test_two_numbers_before_marker_falls_back_to_report_only(wiki, monkeypatch):
    # An earlier unrelated number ("2020") before the marker must never be
    # confused for the volatile fact — ambiguous (2+ candidates) falls back
    # to report-only, not a confidently-wrong correction.
    from lib.memory.volatile import CHECKERS

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "30")
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\nAs of 2020, RenOS has shipped 12 releases. "
        "<!-- ren-volatile: release-count -->\n",
    )
    text_before = (wiki / rel).read_text(encoding="utf-8")

    result = wiki_health.sweep(wiki, apply_corrections=True)
    stale = result["stale_facts"]["stale"]
    assert len(stale) == 1
    assert stale[0]["ground_truth"] == "30"
    assert result["stale_facts"]["corrections_queued"] == 0

    # page is byte-identical — no correction was applied
    assert (wiki / rel).read_text(encoding="utf-8") == text_before


def test_user_trust_page_routes_to_suggestion(wiki, monkeypatch):
    from lib.memory.volatile import CHECKERS
    from lib import suggestions

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "30")
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\nRenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n",
        trust="user",
    )

    result = wiki_health.sweep(wiki, apply_corrections=True)
    assert result["stale_facts"]["stale"] == [] or result["stale_facts"]["corrections_queued"] == 0
    assert result["stale_facts"]["corrections_queued"] == 0

    text_before = (wiki / rel).read_text(encoding="utf-8")
    line_no = next(
        i for i, l in enumerate(text_before.splitlines(), start=1)
        if "ren-volatile: release-count" in l
    )
    pending = suggestions.pending_suggestions()
    hit = next(
        s for s in pending
        if s["producer"] == "wiki-health" and s["fingerprint"] == f"stale-fact:{rel}:{line_no}"
    )
    assert hit["fingerprint"] == f"stale-fact:{rel}:{line_no}"

    # page itself is untouched — correction never applied directly
    text = (wiki / rel).read_text(encoding="utf-8")
    assert "12 releases" in text


def test_unverifiable_kind_inventoried_only(wiki):
    from lib import suggestions

    rel = _write_page(
        wiki, "projects/app/knowledge/mystery.md",
        "# Mystery\nSome fact. <!-- ren-volatile: some-unknown-kind -->\n",
    )

    result = wiki_health.sweep(wiki)
    unverifiable = result["stale_facts"]["unverifiable"]
    assert any(u["page"] == rel and u["kind"] == "some-unknown-kind" for u in unverifiable)
    assert result["stale_facts"]["stale"] == []
    assert result["stale_facts"]["corrections_queued"] == 0
    assert suggestions.pending_suggestions() == []


def test_checker_without_ground_truth_skips_with_no_queue(wiki, monkeypatch):
    from lib.memory.volatile import CHECKERS

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: None)
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\nRenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n",
    )

    result = wiki_health.sweep(wiki)
    assert result["stale_facts"]["stale"] == []
    assert any(u["page"] == rel for u in result["stale_facts"]["unverifiable"])
    assert result["stale_facts"]["corrections_queued"] == 0


def test_report_renders_stale_facts_section(wiki, monkeypatch):
    from lib.memory.volatile import CHECKERS

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "30")
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\nRenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n",
    )

    result = wiki_health.sweep(wiki)
    report = wiki_health.render_report(result)
    assert rel in report
    assert "30" in report
    assert "Stale facts" in report


def test_default_sweep_is_read_only(wiki, monkeypatch):
    """#C2: `sweep()` without `apply_corrections` reports stale facts and
    writes NOTHING — no queue entry, no suggestion, no page edit. Wrap's
    close-out calls this on every session; it must never write unattended."""
    from lib.memory.volatile import CHECKERS
    from lib.memory import queue
    from lib import suggestions

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "30")
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\nRenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n",
    )
    text_before = (wiki / rel).read_text(encoding="utf-8")

    result = wiki_health.sweep(wiki)

    # Reported...
    assert [s["page"] for s in result["stale_facts"]["stale"]] == [rel]
    # ...but nothing written anywhere.
    assert result["stale_facts"]["corrections_queued"] == 0
    assert (wiki / rel).read_text(encoding="utf-8") == text_before
    assert [e for e in queue.all_entries() if e.proposal.page == rel] == []
    assert suggestions.pending_suggestions() == []


def test_two_stale_markers_on_one_page_both_corrected_in_one_write(wiki, monkeypatch):
    """#I1: two markers on one page must not oscillate — both corrections
    land, in a SINGLE write for that page."""
    from lib.memory.volatile import CHECKERS
    from lib.memory import queue

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "30")
    monkeypatch.setitem(CHECKERS, "framework-version", lambda root: "9.9.9")
    rel = _write_page(
        wiki, "projects/app/knowledge/versions.md",
        "# Versions\n"
        "RenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n"
        "RenOS is currently at 0.0.1. <!-- ren-volatile: framework-version -->\n",
    )

    result = wiki_health.sweep(wiki, apply_corrections=True)

    assert len(result["stale_facts"]["stale"]) == 2
    assert result["stale_facts"]["corrections_queued"] == 1  # ONE write, both fixes

    text = (wiki / rel).read_text(encoding="utf-8")
    release_line = next(l for l in text.splitlines() if "release-count" in l)
    version_line = next(l for l in text.splitlines() if "framework-version" in l)
    assert "30" in release_line and "12" not in release_line
    assert "9.9.9" in version_line and "0.0.1" not in version_line

    page_writes = [e for e in queue.all_entries() if e.proposal.page == rel]
    assert len(page_writes) == 1


def test_ren_internal_tree_is_never_scanned_or_written(wiki, monkeypatch):
    """`.ren/` holds the write-safety substrate — per-write snapshots revert
    restores from. `_stale_facts` walked it like ordinary wiki content, so a
    snapshot's copy of a page reported as its own stale finding and, on the
    apply path, was REWRITTEN through the write queue: a later revert would
    restore a doctored copy and look successful.

    `_quarantined_pages` in this same module already excludes `.ren/`; this
    walk didn't. Asserts both halves — not reported, and not mutated on disk.
    """
    from lib.memory.volatile import CHECKERS

    monkeypatch.setitem(CHECKERS, "release-count", lambda root: "44")
    body = "# Versions\nRenOS has shipped 12 releases. <!-- ren-volatile: release-count -->\n"
    rel = _write_page(wiki, "projects/app/knowledge/versions.md", body)

    snapshot = wiki / ".ren" / "snapshots" / "w-TESTID" / "projects" / "app" / "knowledge" / "versions.md"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text((wiki / rel).read_text(encoding="utf-8"), encoding="utf-8")
    before = snapshot.read_bytes()

    result = wiki_health.sweep(wiki, apply_corrections=True)

    pages = [s["page"] for s in result["stale_facts"]["stale"]]
    assert pages == [rel], f"`.ren/` tree leaked into the scan: {pages}"
    assert snapshot.read_bytes() == before, "the write-safety snapshot was mutated"
