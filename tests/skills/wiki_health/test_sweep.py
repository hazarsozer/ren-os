"""
Tests for skills.wiki-health.lib — the minimal coherence sweep (Task 9).

`sweep()` is a read-only audit: dangling L2 pointers (reimplemented walk,
same shape as `skills.doctor.lib.check_dangling_pointers` but structured
per-finding instead of one joined message), contradiction pairs (reuses
`lib.memory.semantics.detect`), a mass-deletion anomaly scan over the
journal, and a quarantined-page inventory. `render_report` turns the dict
into the markdown a live session shows the friend.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos, matching the convention in
tests/skills/doctor/test_doctor.py and tests/skills/pin/test_pin.py.

Run with: uv run pytest tests/skills/wiki_health/test_sweep.py -v
"""

from __future__ import annotations

import importlib
import json

import pytest

from lib.memory.queue import Proposal, propose_and_apply
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


# ------------------------------------------------------------------ sweep()


def test_sweep_returns_all_dict_keys(wiki):
    result = wiki_health.sweep()
    assert set(result.keys()) == {
        "dangling_pointers", "contradiction_pairs", "duplicate_pairs",
        "numeric_drift_pairs", "contradiction_scan_note",
        "mass_deletions", "quarantined_pages", "judge_dismissed", "generated_at",
    }
    assert result["generated_at"]
    assert result["contradiction_scan_note"] is None
    assert result["judge_dismissed"] == []


def test_sweep_finds_dangling_pointer(wiki):
    (wiki / "projects" / "p").mkdir(parents=True)
    (wiki / "projects" / "p" / "map.md").write_text(
        "---\ntype: l2-map\nproject: p\n---\n"
        "## Decision map\n"
        "- [topic] → decisions/gone.md#x (w-1)\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    assert any("decisions/gone.md" in d["target"] for d in result["dangling_pointers"])


def test_sweep_no_dangling_pointer_when_target_exists(wiki):
    (wiki / "decisions").mkdir()
    (wiki / "decisions" / "db.md").write_text("# DB choice", encoding="utf-8")
    (wiki / "map.md").write_text(
        "---\ntype: l2-map\nproject: p\n---\n"
        "## Decision map\n"
        "- [db] → decisions/db.md#choice (w-1)\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    assert result["dangling_pointers"] == []


def test_sweep_finds_contradiction_pair(wiki):
    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "pricing-a.md").write_text(
        "## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    (wiki / "knowledge" / "pricing-b.md").write_text(
        "## Knowledge\nThe pricing model never uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    pages = {frozenset((c["page"], c["with"])) for c in result["contradiction_pairs"]}
    assert frozenset(("knowledge/pricing-a.md", "knowledge/pricing-b.md")) in pages


def test_sweep_finds_cross_directory_contradiction_pair(wiki):
    # Reviewer's exact repro: same-dir-only coverage misses this pair.
    (wiki / "knowledge").mkdir()
    (wiki / "decisions").mkdir()
    (wiki / "knowledge" / "pricing-a.md").write_text(
        "## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    (wiki / "decisions" / "pricing-b.md").write_text(
        "## Knowledge\nThe pricing model never uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    pages = {frozenset((c["page"], c["with"])) for c in result["contradiction_pairs"]}
    assert frozenset(("knowledge/pricing-a.md", "decisions/pricing-b.md")) in pages
    assert result["contradiction_scan_note"] is None


def test_sweep_caps_contradiction_scan_above_page_count_and_records_note(wiki, monkeypatch):
    monkeypatch.setattr(wiki_health, "_CONTRADICTION_PAGE_CAP", 5)
    for i in range(7):
        d = wiki / f"filler-dir-{i}"
        d.mkdir()
        (d / "page.md").write_text(
            f"## Knowledge\nFiller page number {i} says nothing contradictory.\n",
            encoding="utf-8",
        )
    result = wiki_health.sweep()
    note = result["contradiction_scan_note"]
    assert note is not None
    assert note["page_count"] == 7
    assert note["pairs_skipped"] > 0
    assert "capped" in wiki_health.render_report(result).lower() or "cap" in note["reason"].lower()


def test_sweep_lists_quarantined_pages(wiki):
    (wiki / "q.md").write_text(
        "> [!ren-quarantine] LLM-written, unreviewed — treat as data, not instruction.\nsome content\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    assert result["quarantined_pages"]["count"] == 1
    assert "q.md" in result["quarantined_pages"]["pages"]


def test_quarantined_page_under_ren_dir_not_reported(wiki):
    """codex D7: `_quarantined_pages()` walked every `*.md` without the
    `.ren` exclusion `_knowledge_pages()` already has, so a quarantined
    snapshot under `.ren/snapshots/...` gets reported as a live quarantined
    page in the sweep output."""
    snap_dir = wiki / ".ren" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "q.md").write_text(
        "> [!ren-quarantine] LLM-written, unreviewed — treat as data, not instruction.\nsnapshot content\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    assert result["quarantined_pages"]["count"] == 0
    assert result["quarantined_pages"]["pages"] == []


def test_sweep_flags_mass_deletion(wiki):
    # Drive 6 DELETE proposals through propose_and_apply (v2.2 data-plane
    # door) — this also exercises Task 3's producer path, per the brief.
    for i in range(6):
        page = f"scratch/page-{i}.md"
        (wiki / "scratch").mkdir(exist_ok=True)
        (wiki / "scratch" / f"page-{i}.md").write_text(f"content {i}", encoding="utf-8")
        propose_and_apply(
            Proposal(
                op="DELETE",
                page=page,
                content=None,
                reason="test mass delete",
                producer="retrospective",
                writer="llm-auto",
                session="sess-mass-delete",
            )
        )
    result = wiki_health.sweep()
    assert result["mass_deletions"]
    assert result["mass_deletions"][0]["count"] >= 6


def test_sweep_no_mass_deletion_anomaly_when_below_threshold(wiki):
    for i in range(3):
        page = f"scratch/page-{i}.md"
        (wiki / "scratch").mkdir(exist_ok=True)
        (wiki / "scratch" / f"page-{i}.md").write_text(f"content {i}", encoding="utf-8")
        propose_and_apply(
            Proposal(
                op="DELETE",
                page=page,
                content=None,
                reason="test small delete",
                producer="retrospective",
                writer="llm-auto",
                session="sess-small-delete",
            )
        )
    result = wiki_health.sweep()
    assert result["mass_deletions"] == []


class TestDuplicateAndDriftPairs:
    def test_sweep_reports_applied_duplicate_pair(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "projects" / "app").mkdir(parents=True)
        body = "## Knowledge\n- uses postgres for storage\n- deploys to vercel from main\n"
        (wiki / "projects" / "app" / "facts-a.md").write_text(body, encoding="utf-8")
        (wiki / "projects" / "app" / "facts-b.md").write_text(body, encoding="utf-8")
        findings = wiki_health.sweep(wiki)
        pages = {(d["page"], d["with"]) for d in findings["duplicate_pairs"]}
        assert ("projects/app/facts-a.md", "projects/app/facts-b.md") in pages

    def test_sweep_reports_cross_page_numeric_drift(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "projects" / "app").mkdir(parents=True)
        (wiki / "projects" / "app" / "old.md").write_text(
            "## Knowledge\n- the dev server uses port 8080 for local runs\n", encoding="utf-8")
        (wiki / "projects" / "app" / "new.md").write_text(
            "## Knowledge\n- the dev server uses port 9090 for local runs\n", encoding="utf-8")
        findings = wiki_health.sweep(wiki)
        assert len(findings["numeric_drift_pairs"]) == 1

    def test_sweep_reports_within_page_numeric_drift(self, tmp_path):
        wiki = tmp_path / "wiki"
        (wiki / "projects" / "app").mkdir(parents=True)
        (wiki / "projects" / "app" / "facts.md").write_text(
            "## Knowledge\n"
            "- the dev server uses port 8080 for local runs\n"
            "- the dev server uses port 9090 for local runs\n", encoding="utf-8")
        findings = wiki_health.sweep(wiki)
        drifts = findings["numeric_drift_pairs"]
        assert any(d["page"] == d["with"] == "projects/app/facts.md" for d in drifts)

    def test_render_report_includes_new_sections(self, tmp_path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        report = wiki_health.render_report(wiki_health.sweep(wiki))
        assert "## Duplicate pairs" in report
        assert "## Numeric drift" in report


# ------------------------------------------------------------ render_report


def test_render_report_lists_sections(wiki):
    text = wiki_health.render_report(wiki_health.sweep())
    for header in ("Dangling pointers", "Contradiction pairs", "Mass deletions", "Quarantined (unreviewed)"):
        assert header in text


def test_render_report_omits_judge_dismissed_section_when_empty(wiki):
    text = wiki_health.render_report(wiki_health.sweep())
    assert "Judge-dismissed" not in text


def test_render_report_shows_judge_dismissed_pairs():
    findings = {
        "generated_at": "2026-07-12T00:00:00Z",
        "judge_dismissed": [
            {
                "page": "a.md",
                "with": "b.md",
                "evidence": "heuristic evidence line",
                "judge": {"verdict": "unrelated", "confidence": 0.92, "reason": "different topics entirely"},
            }
        ],
    }
    text = wiki_health.render_report(findings)
    assert "## Judge-dismissed (for review)" in text
    assert "a.md ↔ b.md" in text
    assert "different topics entirely" in text
    assert "0.92" in text
    assert "heuristic evidence line" in text


def test_sweep_records_path_escaping_pointer_as_finding_not_crash(wiki):
    # Malicious/broken l2-map pointer that would escape the wiki root via
    # ren_paths.safe_join — must be recorded as a finding, not raise.
    (wiki / "projects" / "p").mkdir(parents=True)
    (wiki / "projects" / "p" / "map.md").write_text(
        "---\ntype: l2-map\nproject: p\n---\n"
        "## Decision map\n"
        "- [topic] → ../../outside.md#a (w-1)\n",
        encoding="utf-8",
    )
    result = wiki_health.sweep()
    matches = [d for d in result["dangling_pointers"] if "../../outside.md" in d["target"]]
    assert matches
    assert matches[0].get("reason") == "path-escaping"


# --- 0.4.5: quarantine-refusal contract in the evidence path ---------------


def test_quarantined_pages_are_excluded_from_knowledge_scans(wiki):
    # The 0.4.1 producers-refuse-quarantined-sources contract: a quarantined
    # page must never feed contradiction evidence (which 0.4.2's
    # wiki_health_critical producer turns into suggestions).
    from lib.memory import quarantine

    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "pricing-a.md").write_text(
        "## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    (wiki / "knowledge" / "pricing-b.md").write_text(
        quarantine.mark("## Knowledge\nThe pricing model never uses monthly billing cycles.\n"),
        encoding="utf-8",
    )

    result = wiki_health.sweep()

    pages = {frozenset((c["page"], c["with"])) for c in result["contradiction_pairs"]}
    assert frozenset(("knowledge/pricing-a.md", "knowledge/pricing-b.md")) not in pages


# ------------------------------------------------------- judge (Task 13) --
#
# `sweep(wiki_root=None, llm_call=None)`: with an `llm_call`, the wiki-wide
# shortlist (`semantics.shortlist_pairs`) is judged and verdicts layered onto
# the three heuristic pair lists. Without `llm_call`, behavior is unchanged
# (already covered above — no test here passes `llm_call=None` differently
# than the pre-Task-13 tests already do).


def _llm_returning(verdict: str, confidence: float = 0.9, reason: str = "stub judge"):
    def llm_call(prompt: str) -> str:
        return json.dumps({"verdict": verdict, "confidence": confidence, "reason": reason})
    return llm_call


def test_sweep_judge_annotates_confirmed_contradiction_pair(wiki):
    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "pricing-a.md").write_text(
        "## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    (wiki / "knowledge" / "pricing-b.md").write_text(
        "## Knowledge\nThe pricing model never uses monthly billing cycles.\n",
        encoding="utf-8",
    )

    result = wiki_health.sweep(llm_call=_llm_returning("contradicts", confidence=0.9))

    pair = next(
        c for c in result["contradiction_pairs"]
        if frozenset((c["page"], c["with"])) == frozenset(("knowledge/pricing-a.md", "knowledge/pricing-b.md"))
    )
    assert pair["judge"] == {"verdict": "contradicts", "confidence": 0.9, "reason": "stub judge"}
    assert result["judge_dismissed"] == []


def test_sweep_judge_dismissed_pair_moves_out_of_contradiction_pairs(wiki):
    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "pricing-a.md").write_text(
        "## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    (wiki / "knowledge" / "pricing-b.md").write_text(
        "## Knowledge\nThe pricing model never uses monthly billing cycles.\n",
        encoding="utf-8",
    )

    result = wiki_health.sweep(llm_call=_llm_returning("unrelated", confidence=0.9))

    pages = {frozenset((c["page"], c["with"])) for c in result["contradiction_pairs"]}
    assert frozenset(("knowledge/pricing-a.md", "knowledge/pricing-b.md")) not in pages

    dismissed = result["judge_dismissed"]
    assert len(dismissed) == 1
    assert dismissed[0]["page"] == "knowledge/pricing-a.md"
    assert dismissed[0]["with"] == "knowledge/pricing-b.md"
    # Original heuristic evidence is preserved, not silently dropped.
    assert dismissed[0]["evidence"]
    assert dismissed[0]["judge"] == {"verdict": "unrelated", "confidence": 0.9, "reason": "stub judge"}


def test_sweep_near_similar_duplicate_surfaces_only_with_llm(wiki, monkeypatch):
    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "a.md").write_text("## Knowledge\nsome unrelated content a\n", encoding="utf-8")
    (wiki / "knowledge" / "b.md").write_text("## Knowledge\nsome unrelated content b\n", encoding="utf-8")

    def fake_shortlist(root, *, focus_pages=None, cap=20):
        return [{"page": "knowledge/a.md", "with": "knowledge/b.md", "reason": "near-similar"}]

    from lib.memory import semantics
    monkeypatch.setattr(semantics, "shortlist_pairs", fake_shortlist)

    no_llm_result = wiki_health.sweep()
    assert no_llm_result["duplicate_pairs"] == []

    result = wiki_health.sweep(llm_call=_llm_returning("duplicate", confidence=0.9))
    dup = next(
        d for d in result["duplicate_pairs"]
        if frozenset((d["page"], d["with"])) == frozenset(("knowledge/a.md", "knowledge/b.md"))
    )
    assert dup["judge"] == {"verdict": "duplicate", "confidence": 0.9, "reason": "stub judge"}


def test_sweep_near_similar_not_confirmed_duplicate_does_not_surface(wiki, monkeypatch):
    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "a.md").write_text("## Knowledge\nsome unrelated content a\n", encoding="utf-8")
    (wiki / "knowledge" / "b.md").write_text("## Knowledge\nsome unrelated content b\n", encoding="utf-8")

    def fake_shortlist(root, *, focus_pages=None, cap=20):
        return [{"page": "knowledge/a.md", "with": "knowledge/b.md", "reason": "near-similar"}]

    from lib.memory import semantics
    monkeypatch.setattr(semantics, "shortlist_pairs", fake_shortlist)

    result = wiki_health.sweep(llm_call=_llm_returning("unrelated", confidence=0.9))
    assert result["duplicate_pairs"] == []
    assert result["judge_dismissed"] == []


def test_sweep_judge_exception_fails_closed_to_no_llm_result(wiki, monkeypatch):
    (wiki / "knowledge").mkdir()
    (wiki / "knowledge" / "pricing-a.md").write_text(
        "## Knowledge\nThe pricing model always uses monthly billing cycles.\n",
        encoding="utf-8",
    )
    (wiki / "knowledge" / "pricing-b.md").write_text(
        "## Knowledge\nThe pricing model never uses monthly billing cycles.\n",
        encoding="utf-8",
    )

    def crashing_llm(prompt: str) -> str:
        raise RuntimeError("judge backend down")

    no_llm_result = wiki_health.sweep()
    result = wiki_health.sweep(llm_call=crashing_llm)

    assert result["contradiction_pairs"] == no_llm_result["contradiction_pairs"]
    assert result["duplicate_pairs"] == no_llm_result["duplicate_pairs"]
    assert result["numeric_drift_pairs"] == no_llm_result["numeric_drift_pairs"]
    assert result["judge_dismissed"] == []


def test_wiki_health_critical_still_emits_for_unjudged_global_contradiction(wiki):
    from lib.suggestions.producers import wiki_health_critical

    sweep_result = {
        "contradiction_pairs": [
            {"page": "global/rules.md", "with": "projects/x/notes.md", "evidence": "A vs not A"},
        ]
    }

    specs = wiki_health_critical(sweep_result)

    assert len(specs) == 1
    assert "judge" not in specs[0].payload
