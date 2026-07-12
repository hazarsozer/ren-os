"""
Tests for lib.memory.semantics — G3 contradiction/supersede/duplicate detection
(Task 2.2). Deterministic heuristics only; the write queue (Task 2.1, not built
yet) will call `detect()` directly with primitive args.

Run with: uv run pytest tests/lib/memory/test_semantics.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.memory.provenance import new_provenance, stamp_frontmatter
from lib.memory.quarantine import mark as quarantine_mark
from lib.memory.semantics import (
    SHORTLIST_CAP,
    Conflict,
    contradiction_evidence,
    detect,
    duplicate_evidence,
    numeric_drift_evidence,
    shortlist_pairs,
)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _numbered_lines(n: int, start: int = 1) -> list[str]:
    return [f"Line number {i} describes topic {i}." for i in range(start, start + n)]


# --- 1. duplicate: identical restated page ----------------------------------


def test_identical_restated_page_is_duplicate(tmp_path):
    body = "\n".join(_numbered_lines(12)) + "\n"
    _write(tmp_path, "projects/demo/notes.md", body)

    conflicts = detect("UPDATE", "projects/demo/notes.md", body, tmp_path)

    dup = [c for c in conflicts if c.kind == "duplicate"]
    assert len(dup) == 1
    assert dup[0].page == "projects/demo/notes.md"
    assert dup[0].evidence == "line number 1 describes topic 1."


# --- 2. duplicate: near-identical (1 line changed out of 12) ---------------


def test_near_identical_one_line_changed_is_duplicate(tmp_path):
    existing_lines = _numbered_lines(11) + ["Line number 12 describes topic 12."]
    proposed_lines = _numbered_lines(11) + ["A completely rewritten final line."]
    _write(tmp_path, "projects/demo/notes.md", "\n".join(existing_lines) + "\n")

    conflicts = detect(
        "UPDATE", "projects/demo/notes.md", "\n".join(proposed_lines) + "\n", tmp_path
    )

    dup = [c for c in conflicts if c.kind == "duplicate" and c.page == "projects/demo/notes.md"]
    assert len(dup) == 1


# --- 3. genuinely different page → no duplicate -----------------------------


def test_genuinely_different_content_is_not_duplicate(tmp_path):
    _write(tmp_path, "projects/demo/notes.md", "\n".join(_numbered_lines(12)) + "\n")

    different = "Something entirely unrelated about ocean currents and tides.\n"
    conflicts = detect("ADD", "projects/demo/fresh.md", different, tmp_path)

    assert [c for c in conflicts if c.kind == "duplicate"] == []


# --- 4. supersedes: UPDATE on stamped existing page -------------------------


def test_update_on_stamped_page_yields_supersedes_with_write_id(tmp_path):
    prov = new_provenance("human", "sess-1", "ADD", "projects/demo/notes.md")
    original = stamp_frontmatter("Some original body text.\n", prov)
    _write(tmp_path, "projects/demo/notes.md", original)

    conflicts = detect(
        "UPDATE", "projects/demo/notes.md", "A new body entirely.\n", tmp_path
    )

    sup = [c for c in conflicts if c.kind == "supersedes"]
    assert len(sup) == 1
    assert sup[0].page == "projects/demo/notes.md"
    assert sup[0].write_id == prov.write_id


# --- 5. supersedes: ADD to fresh path → none --------------------------------


def test_add_to_fresh_path_yields_no_supersedes(tmp_path):
    conflicts = detect("ADD", "projects/demo/brand-new.md", "Fresh content.\n", tmp_path)
    assert [c for c in conflicts if c.kind == "supersedes"] == []


# --- 6. contradicts: negated proposal vs affirmative existing ---------------


def test_negated_proposal_contradicts_affirmative_existing_line(tmp_path):
    existing = "Always use spaces for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "Do not use spaces for indentation in Python files.\n"
    conflicts = detect("UPDATE", "projects/demo/style.md", proposed, tmp_path)

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert len(con) == 1
    assert con[0].evidence == "always use spaces for indentation in python files."
    assert con[0].page == "projects/demo/style.md"


# --- 7. contradicts: symmetric direction (existing negated, proposal affirms) ---


def test_negated_existing_contradicts_affirmative_proposal(tmp_path):
    existing = "Do not use tabs for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "Use tabs for indentation in Python files.\n"
    conflicts = detect("UPDATE", "projects/demo/style.md", proposed, tmp_path)

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert len(con) == 1
    assert con[0].evidence == "do not use tabs for indentation in python files."


# --- 8. negation with <3 shared tokens → no contradicts (negative test) -----


def test_negation_with_fewer_than_three_shared_tokens_does_not_contradict(tmp_path):
    _write(tmp_path, "projects/demo/style.md", "Use tabs here.\n")

    proposed = "Do not use tabs there.\n"
    conflicts = detect("UPDATE", "projects/demo/style.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


# --- 8b. negation marker must match a whole word, not a substring (bug fix) -


def test_whenever_is_not_treated_as_never(tmp_path):
    # Regression for the exact false-positive found on fresh installs:
    # index.md.tmpl's "...whenever a session promotes... You can also edit it
    # by hand." shares >=3 tokens (file/edit/hand) with identity.md.tmpl's
    # "...or edit any field by hand." "whenever" contains "never " as a
    # substring, but is not a negation of anything — this must not fire.
    existing = (
        "This file is filled in by /ren:interview during onboarding. "
        "You can re-run the interview anytime, or edit any field by hand.\n"
    )
    _write(tmp_path, "projects/demo/notes.md", existing)

    proposed = (
        "This file is updated by the session-wrap flow whenever a session "
        "promotes content to the wiki. You can also edit it by hand.\n"
    )
    conflicts = detect("ADD", "projects/demo/fresh.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_nonstop_is_not_treated_as_stop(tmp_path):
    existing = "Always use spaces for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "This nonstop use of spaces for indentation in Python files works.\n"
    conflicts = detect("UPDATE", "projects/demo/style.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_cannot_is_not_treated_as_not(tmp_path):
    existing = "Use tabs for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "You cannot use tabs for indentation in Python files.\n"
    conflicts = detect("UPDATE", "projects/demo/style.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_standalone_never_still_contradicts(tmp_path):
    # The word-boundary fix must not weaken real "never" detection.
    existing = "Always use spaces for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "Never use spaces for indentation in Python files.\n"
    conflicts = detect("UPDATE", "projects/demo/style.md", proposed, tmp_path)

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert len(con) == 1
    assert con[0].evidence == "always use spaces for indentation in python files."


# --- 9. unstamped existing page → supersedes with write_id=None ------------


def test_unstamped_existing_page_yields_supersedes_with_none_write_id(tmp_path):
    _write(tmp_path, "projects/demo/notes.md", "No frontmatter at all here.\n")

    conflicts = detect("UPDATE", "projects/demo/notes.md", "New content.\n", tmp_path)

    sup = [c for c in conflicts if c.kind == "supersedes"]
    assert len(sup) == 1
    assert sup[0].write_id is None


# --- 10. all three kinds can co-occur ---------------------------------------


def test_all_three_conflict_kinds_can_co_occur(tmp_path):
    prov = new_provenance("human", "sess-1", "ADD", "projects/combo/target.md")
    target_lines = _numbered_lines(11) + ["Line number 12 describes topic 12."]
    target_text = stamp_frontmatter("\n".join(target_lines) + "\n", prov)
    _write(tmp_path, "projects/combo/target.md", target_text)

    sibling_text = (
        "Always use tabs for indentation in Python files.\n"
        "Some other unrelated sibling sentence here.\n"
    )
    _write(tmp_path, "projects/combo/sibling.md", sibling_text)

    proposed_lines = _numbered_lines(11) + [
        "Do not use tabs for indentation in Python files."
    ]
    proposed_text = "\n".join(proposed_lines) + "\n"

    conflicts = detect("UPDATE", "projects/combo/target.md", proposed_text, tmp_path)
    kinds = {c.kind for c in conflicts}

    assert kinds == {"duplicate", "supersedes", "contradicts"}

    dup = [c for c in conflicts if c.kind == "duplicate"]
    assert any(c.page == "projects/combo/target.md" for c in dup)

    sup = [c for c in conflicts if c.kind == "supersedes"]
    assert sup[0].write_id == prov.write_id

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert any(c.page == "projects/combo/sibling.md" for c in con)


# --- Conflict shape ----------------------------------------------------------


def test_conflict_is_frozen_dataclass_with_expected_fields():
    c = Conflict(kind="duplicate", page="p.md", write_id=None, evidence="line")
    assert c.kind == "duplicate"
    assert c.page == "p.md"
    assert c.write_id is None
    assert c.evidence == "line"
    with pytest.raises(Exception):
        c.page = "other.md"  # type: ignore[misc]


# --- contradiction_evidence: direct pairwise check (no wiki_root, no globbing) --


def test_contradiction_evidence_finds_direct_contradiction():
    a = "The pricing model always uses monthly billing cycles.\n"
    b = "The pricing model never uses monthly billing cycles.\n"
    assert contradiction_evidence(a, b) is not None


def test_contradiction_evidence_none_when_no_contradiction():
    a = "Use tabs here.\n"
    b = "Use spaces there.\n"
    assert contradiction_evidence(a, b) is None


# --- duplicate_evidence: direct pairwise duplicate check ----------------------


class TestDuplicateEvidence:
    def test_near_identical_bodies_are_duplicates(self):
        a = "## Knowledge\n- uses postgres for storage\n- deploys to vercel\n- api lives in src/api\n"
        b = "## Knowledge\n- uses postgres for storage\n- deploys to vercel\n- api lives in src/api\n"
        assert duplicate_evidence(a, b) is not None

    def test_disjoint_bodies_are_not_duplicates(self):
        a = "## Knowledge\n- uses postgres for storage\n- runs on linux servers\n- scales horizontally\n"
        b = "## Knowledge\n- frontend built with react\n- uses typescript strictly\n- deploys to vercel\n"
        assert duplicate_evidence(a, b) is None

    def test_frontmatter_is_ignored(self):
        a = "---\ntype: fact\n---\n- uses postgres for storage\n- deploys to vercel\n- api lives in src/api\n"
        b = "---\ntype: note\n---\n- uses postgres for storage\n- deploys to vercel\n- api lives in src/api\n"
        assert duplicate_evidence(a, b) is not None


# --- numeric_drift_evidence: cheap numeric-drift screen ----------------------


class TestNumericDriftEvidence:
    def test_port_drift_is_detected(self):
        a = "## Knowledge\n- the dev server uses port 8080 for local runs\n"
        b = "## Knowledge\n- the dev server uses port 9090 for local runs\n"
        drift = numeric_drift_evidence(a, b)
        assert drift is not None
        assert "8080" in drift[0] and "9090" in drift[1]

    def test_identical_numbers_do_not_drift(self):
        a = "- the dev server uses port 8080 for local runs\n"
        b = "- the dev server uses port 8080 for local runs\n"
        assert numeric_drift_evidence(a, b) is None

    def test_short_lines_are_ignored(self):
        # fewer than 3 significant tokens after masking the number: no signal
        assert numeric_drift_evidence("- port 8080\n", "- port 9090\n") is None

    def test_within_page_drift_via_self_comparison(self):
        page = (
            "## Knowledge\n"
            "- the dev server uses port 8080 for local runs\n"
            "- some other unrelated fact line here\n"
            "- the dev server uses port 9090 for local runs\n"
        )
        drift = numeric_drift_evidence(page, page)
        assert drift is not None
        assert drift[0] != drift[1]

    def test_lines_without_numbers_never_drift(self):
        a = "- uses postgres for storage backend\n"
        b = "- uses sqlite for storage backend\n"
        assert numeric_drift_evidence(a, b) is None  # backend swaps are 0.5-ladder work


# --- duplicate_evidence: minimum content floor (near-empty templated pages) --


def test_near_empty_templated_pages_are_not_duplicates():
    a = "---\ntype: note\n---\n# Untitled\n- created from template\n"
    b = "---\ntype: note\n---\n# Untitled\n- created from template\n"
    assert duplicate_evidence(a, b) is None


# --- shortlist_pairs: candidate-pair generator for the LLM judge (Task 11) --


def test_paraphrased_pair_with_no_shared_lines_is_near_similar(tmp_path):
    # No shared lines at all (different wording/order), but high
    # significant-token overlap: exactly the class the heuristics miss and
    # the judge exists to catch.
    _write(
        tmp_path,
        "notes/a.md",
        "Redis caches user sessions for fast lookup.\n",
    )
    _write(
        tmp_path,
        "notes/b.md",
        "Fast lookup of user sessions is cached using Redis.\n",
    )

    pairs = shortlist_pairs(tmp_path)

    assert {"page": "notes/a.md", "with": "notes/b.md", "reason": "near-similar"} in pairs


def test_heuristic_contradiction_pair_appears_with_its_reason(tmp_path):
    _write(tmp_path, "notes/a.md", "We use Postgres for storage backend now.\n")
    _write(tmp_path, "notes/b.md", "We do not use Postgres for storage backend now.\n")

    pairs = shortlist_pairs(tmp_path)

    assert {"page": "notes/a.md", "with": "notes/b.md", "reason": "heuristic-contradiction"} in pairs


def test_unrelated_pages_are_absent(tmp_path):
    _write(tmp_path, "notes/a.md", "Redis caches user sessions for fast lookup.\n")
    _write(tmp_path, "notes/b.md", "Fast lookup of user sessions is cached using Redis.\n")
    _write(tmp_path, "notes/c.md", "The espresso machine needs quarterly descaling maintenance.\n")

    pairs = shortlist_pairs(tmp_path)

    involving_c = [p for p in pairs if p["page"] == "notes/c.md" or p["with"] == "notes/c.md"]
    assert involving_c == []


def test_dot_ren_and_quarantined_and_foreign_pages_are_excluded(tmp_path):
    _write(tmp_path, "notes/a.md", "We use Postgres for storage backend now.\n")
    _write(
        tmp_path,
        ".ren/metrics/a.md",
        "We do not use Postgres for storage backend now.\n",
    )
    quarantined = quarantine_mark("We do not use Postgres for storage backend now.\n")
    _write(tmp_path, "notes/quarantined.md", quarantined)

    foreign_prov = new_provenance("llm-auto", "sess-1", "ADD", "notes/foreign.md", trust="foreign")
    foreign = stamp_frontmatter("We do not use Postgres for storage backend now.\n", foreign_prov)
    _write(tmp_path, "notes/foreign.md", foreign)

    pairs = shortlist_pairs(tmp_path)

    involved_pages = {p["page"] for p in pairs} | {p["with"] for p in pairs}
    assert ".ren/metrics/a.md" not in involved_pages
    assert "notes/quarantined.md" not in involved_pages
    assert "notes/foreign.md" not in involved_pages


def test_cap_respects_heuristic_first_then_near_similar_by_descending_jaccard(tmp_path):
    # Two heuristic-contradiction pairs (should sort ahead of near-similar,
    # in candidate order) plus several near-similar pairs of decreasing
    # token overlap with a fixed anchor page.
    _write(tmp_path, "h1/a.md", "We use Postgres for storage backend now.\n")
    _write(tmp_path, "h1/b.md", "We do not use Postgres for storage backend now.\n")
    _write(tmp_path, "h2/a.md", "The team deploys nightly builds automatically.\n")
    _write(tmp_path, "h2/b.md", "The team does not deploy nightly builds automatically.\n")

    _write(
        tmp_path,
        "anchor.md",
        "alpha bravo charlie delta echo foxtrot golf hotel india juliet.\n",
    )
    # Decreasing overlap with anchor: near1 shares the most tokens, near3 the
    # fewest (still >= 0.5 jaccard).
    _write(
        tmp_path,
        "near1.md",
        "alpha bravo charlie delta echo foxtrot golf hotel india kilo.\n",
    )
    _write(
        tmp_path,
        "near2.md",
        "alpha bravo charlie delta echo foxtrot golf kilo lima mike.\n",
    )
    _write(
        tmp_path,
        "near3.md",
        "alpha bravo charlie delta echo foxtrot kilo lima.\n",
    )

    pairs = shortlist_pairs(tmp_path, cap=SHORTLIST_CAP)

    reasons = [p["reason"] for p in pairs]
    heuristic_count = sum(1 for r in reasons if r != "near-similar")
    assert heuristic_count == 2
    assert reasons[:2] == ["heuristic-contradiction", "heuristic-contradiction"]

    near_similar = [p for p in pairs if p["reason"] == "near-similar" and "anchor.md" in (p["page"], p["with"])]
    near_similar_others = [p["with"] if p["page"] == "anchor.md" else p["page"] for p in near_similar]
    assert near_similar_others == ["near1.md", "near2.md", "near3.md"]

    # Cap respected even when raised low.
    capped = shortlist_pairs(tmp_path, cap=3)
    assert len(capped) == 3
    assert [p["reason"] for p in capped] == ["heuristic-contradiction", "heuristic-contradiction", "near-similar"]


def test_focus_pages_restricts_one_side_of_every_pair(tmp_path):
    _write(tmp_path, "notes/a.md", "Redis caches user sessions for fast lookup.\n")
    _write(tmp_path, "notes/b.md", "Fast lookup of user sessions is cached using Redis.\n")
    _write(tmp_path, "notes/c.md", "Redis stores session data efficiently for lookups.\n")

    pairs = shortlist_pairs(tmp_path, focus_pages=["notes/c.md"])

    for p in pairs:
        assert "notes/c.md" in (p["page"], p["with"])

    unrestricted = shortlist_pairs(tmp_path)
    assert len(unrestricted) >= len(pairs)


def test_real_duplicates_still_flag():
    body = "# Deploy notes\n- use port 8080\n- restart nginx after deploy\n- check logs in /var/log\n"
    assert duplicate_evidence(body, body) is not None
