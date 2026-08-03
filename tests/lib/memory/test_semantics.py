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
from lib.memory.quarantine import release as quarantine_release
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
    # issue #42: an UPDATE never self-conflicts with its own target, so this
    # now exercises a genuine cross-page duplicate (sibling), not self.
    body = "\n".join(_numbered_lines(12)) + "\n"
    _write(tmp_path, "projects/demo/existing.md", body)

    conflicts = detect("ADD", "projects/demo/notes.md", body, tmp_path)

    dup = [c for c in conflicts if c.kind == "duplicate"]
    assert len(dup) == 1
    assert dup[0].page == "projects/demo/existing.md"
    assert dup[0].evidence == "line number 1 describes topic 1."


# --- 2. duplicate: near-identical (1 line changed out of 12) ---------------


def test_near_identical_one_line_changed_is_duplicate(tmp_path):
    # issue #42: sibling, not self — self-duplicate is exempt for UPDATE.
    existing_lines = _numbered_lines(11) + ["Line number 12 describes topic 12."]
    proposed_lines = _numbered_lines(11) + ["A completely rewritten final line."]
    _write(tmp_path, "projects/demo/existing.md", "\n".join(existing_lines) + "\n")

    conflicts = detect(
        "ADD", "projects/demo/notes.md", "\n".join(proposed_lines) + "\n", tmp_path
    )

    dup = [c for c in conflicts if c.kind == "duplicate" and c.page == "projects/demo/existing.md"]
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
    # issue #42: sibling, not self — self-contradicts is exempt for UPDATE.
    existing = "Always use spaces for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "Do not use spaces for indentation in Python files.\n"
    conflicts = detect("ADD", "projects/demo/new-style.md", proposed, tmp_path)

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert len(con) == 1
    assert con[0].evidence == "always use spaces for indentation in python files."
    assert con[0].page == "projects/demo/style.md"


# --- 7. contradicts: symmetric direction (existing negated, proposal affirms) ---


def test_negated_existing_contradicts_affirmative_proposal(tmp_path):
    # issue #42: sibling, not self — self-contradicts is exempt for UPDATE.
    existing = "Do not use tabs for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "Use tabs for indentation in Python files.\n"
    conflicts = detect("ADD", "projects/demo/new-style.md", proposed, tmp_path)

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
    # issue #42: sibling, not self — self-contradicts is exempt for UPDATE.
    existing = "Always use spaces for indentation in Python files.\n"
    _write(tmp_path, "projects/demo/style.md", existing)

    proposed = "Never use spaces for indentation in Python files.\n"
    conflicts = detect("ADD", "projects/demo/new-style.md", proposed, tmp_path)

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
    # issue #42: the duplicate signal now comes from a sibling, not the
    # UPDATE's own target — self-duplicate/self-contradicts are exempt, but
    # supersedes (target-only) is unaffected and still fires alongside them.
    prov = new_provenance("human", "sess-1", "ADD", "projects/combo/target.md")
    target_text = stamp_frontmatter("Original target body, unrelated to duplicate check.\n", prov)
    _write(tmp_path, "projects/combo/target.md", target_text)

    dup_sibling_lines = _numbered_lines(11) + ["Line number 12 describes topic 12."]
    _write(tmp_path, "projects/combo/dup-sibling.md", "\n".join(dup_sibling_lines) + "\n")

    contradiction_sibling_text = (
        "Always use tabs for indentation in Python files.\n"
        "Some other unrelated sibling sentence here.\n"
    )
    _write(tmp_path, "projects/combo/sibling.md", contradiction_sibling_text)

    proposed_lines = _numbered_lines(11) + [
        "Do not use tabs for indentation in Python files."
    ]
    proposed_text = "\n".join(proposed_lines) + "\n"

    conflicts = detect("UPDATE", "projects/combo/target.md", proposed_text, tmp_path)
    kinds = {c.kind for c in conflicts}

    assert kinds == {"duplicate", "supersedes", "contradicts"}

    dup = [c for c in conflicts if c.kind == "duplicate"]
    assert any(c.page == "projects/combo/dup-sibling.md" for c in dup)

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


def test_project_raw_pages_are_excluded_from_shortlist(tmp_path):
    # M1 (0.6.2 review): raw/ is immutable source material — a source and the
    # knowledge page distilling it are SUPPOSED to overlap heavily. Pairing
    # them for the judge would violate the "coherence scans skip raw/"
    # invariant `skills.wiki-health` already enforces.
    _write(
        tmp_path,
        "projects/flux/raw/design-notes.md",
        "Redis caches user sessions for fast lookup.\n",
    )
    _write(
        tmp_path,
        "projects/flux/knowledge/caching.md",
        "Fast lookup of user sessions is cached using Redis.\n",
    )

    pairs = shortlist_pairs(tmp_path)

    involved_pages = {p["page"] for p in pairs} | {p["with"] for p in pairs}
    assert "projects/flux/raw/design-notes.md" not in involved_pages


def test_focus_pages_restricts_one_side_of_every_pair(tmp_path):
    _write(tmp_path, "notes/a.md", "Redis caches user sessions for fast lookup.\n")
    _write(tmp_path, "notes/b.md", "Fast lookup of user sessions is cached using Redis.\n")
    _write(tmp_path, "notes/c.md", "Redis stores session data efficiently for lookups.\n")

    pairs = shortlist_pairs(tmp_path, focus_pages=["notes/c.md"])

    for p in pairs:
        assert "notes/c.md" in (p["page"], p["with"])

    unrestricted = shortlist_pairs(tmp_path)
    assert len(unrestricted) >= len(pairs)


def test_focus_pages_bypasses_quarantine_skip_for_focus_page(tmp_path):
    # A quarantine-bannered page IS a model-class write awaiting judgment —
    # when it's the session's own write (in focus_pages), it must still be
    # eligible for pairing so the judge actually sees it.
    quarantined = quarantine_mark("We do not use Postgres for storage backend now.\n")
    _write(tmp_path, "notes/quarantined.md", quarantined)
    _write(tmp_path, "notes/clean.md", "We use Postgres for storage backend now.\n")

    pairs = shortlist_pairs(tmp_path, focus_pages=["notes/quarantined.md"])

    involved_pages = {p["page"] for p in pairs} | {p["with"] for p in pairs}
    assert "notes/quarantined.md" in involved_pages


def test_quarantined_page_not_in_focus_pages_still_skipped(tmp_path):
    quarantined = quarantine_mark("We do not use Postgres for storage backend now.\n")
    _write(tmp_path, "notes/quarantined.md", quarantined)
    _write(tmp_path, "notes/clean.md", "We use Postgres for storage backend now.\n")
    _write(tmp_path, "notes/other.md", "We use Postgres for storage backend now.\n")

    # focus_pages targets a different page entirely; the quarantined page
    # should remain excluded since it isn't the session's own write here.
    pairs = shortlist_pairs(tmp_path, focus_pages=["notes/other.md"])

    involved_pages = {p["page"] for p in pairs} | {p["with"] for p in pairs}
    assert "notes/quarantined.md" not in involved_pages


def test_foreign_page_in_focus_pages_still_excluded(tmp_path):
    # Foreign provenance is untrusted regardless of focus — it must never
    # enter the judge's consolidation pipeline, focus or not.
    foreign_prov = new_provenance("llm-auto", "sess-1", "ADD", "notes/foreign.md", trust="foreign")
    foreign = stamp_frontmatter("We use Postgres for storage backend now.\n", foreign_prov)
    _write(tmp_path, "notes/foreign.md", foreign)
    _write(tmp_path, "notes/clean.md", "We use Postgres for storage backend now.\n")

    pairs = shortlist_pairs(tmp_path, focus_pages=["notes/foreign.md"])

    involved_pages = {p["page"] for p in pairs} | {p["with"] for p in pairs}
    assert "notes/foreign.md" not in involved_pages


def test_real_duplicates_still_flag():
    body = "# Deploy notes\n- use port 8080\n- restart nginx after deploy\n- check logs in /var/log\n"
    assert duplicate_evidence(body, body) is not None


# --- issue #16: batch-ingest false-positive contradictions -------------------
#
# Batch-ingesting one repo produces a fan of sibling pages (distilled pages +
# an L2 map) that restate each other's topics by construction. Before the fix,
# the first page to land turned into a contradiction wall for the rest of its
# own batch: ~40 spans held, every one a same-topic restatement.


_INGEST_PAGES = {
    "projects/acme/architecture.md": (
        "The service layer owns all database access for the acme platform.\n"
        "Avoid calling the ORM directly from route handlers in the acme platform.\n"
        "Background jobs run through the queue worker pool.\n"
    ),
    "projects/acme/conventions.md": (
        "Route handlers in the acme platform delegate database access to the "
        "service layer, which owns it.\n"
        "The queue worker pool is where background jobs run.\n"
        "Tests live beside the module they cover.\n"
    ),
    "projects/acme/testing.md": (
        "Tests for the acme platform live beside the module they cover.\n"
        "Do not stub the service layer in integration tests for the platform.\n"
        "The queue worker pool has its own integration test suite.\n"
    ),
}

_INGEST_MAP = (
    "---\n"
    "type: l2-map\n"
    "---\n"
    "The service layer owns all database access for the acme platform.\n"
    "Background jobs run through the queue worker pool.\n"
    "Tests live beside the module they cover.\n"
)


def test_batch_of_sibling_pages_yields_no_contradicts_holds(tmp_path):
    """The reproduction: land the batch page by page, each new page exempting
    the siblings its own session already wrote. Zero contradicts."""
    written: list[str] = []
    for page, content in _INGEST_PAGES.items():
        conflicts = detect("ADD", page, content, tmp_path, exempt_pages=set(written))
        assert [c for c in conflicts if c.kind == "contradicts"] == [], page
        _write(tmp_path, page, content)
        written.append(page)


def test_same_batch_exemption_does_not_suppress_duplicate_detection(tmp_path):
    body = "\n".join(_numbered_lines(12)) + "\n"
    _write(tmp_path, "projects/acme/one.md", body)

    conflicts = detect(
        "ADD", "projects/acme/two.md", body, tmp_path,
        exempt_pages={"projects/acme/one.md"},
    )

    assert [c.kind for c in conflicts if c.kind == "duplicate"] == ["duplicate"]


def test_exemption_is_scoped_to_the_named_pages(tmp_path):
    _write(tmp_path, "projects/acme/style.md", "Always use spaces for indentation in Python files.\n")

    conflicts = detect(
        "ADD", "projects/acme/new.md",
        "Do not use spaces for indentation in Python files.\n",
        tmp_path, exempt_pages={"projects/acme/unrelated.md"},
    )

    assert [c.kind for c in conflicts if c.kind == "contradicts"] == ["contradicts"]


# --- issue #16: L2 map never contradicts its own subtree --------------------


def test_l2_map_does_not_contradict_pages_in_its_own_subtree(tmp_path):
    for page, content in _INGEST_PAGES.items():
        _write(tmp_path, page, content)

    conflicts = detect("ADD", "projects/acme/map.md", _INGEST_MAP, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_page_does_not_contradict_the_map_of_its_own_subtree(tmp_path):
    _write(tmp_path, "projects/acme/map.md", _INGEST_MAP)

    proposed = "Do not run background jobs through the queue worker pool.\n"
    conflicts = detect("ADD", "projects/acme/jobs.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_proposed_frontmatter_l2_map_no_longer_self_exempts(tmp_path):
    # 0.6.2 review finding H1: the PROPOSED side is detected as a map by
    # PATH ONLY — declaring `type: l2-map` in the proposal's own frontmatter
    # must not exempt it from contradiction checks.
    _write(tmp_path, "projects/acme/style.md", "Always use spaces for indentation in Python files.\n")

    proposed = "---\ntype: l2-map\n---\nDo not use spaces for indentation in Python files.\n"
    conflicts = detect("ADD", "projects/acme/overview.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] != []


def test_existing_map_by_frontmatter_type_still_exempt(tmp_path):
    # The EXISTING candidate side keeps frontmatter-based map detection: its
    # content is already on disk, not attacker-suppliable at propose time.
    _write(
        tmp_path, "projects/acme/legacy-map.md",
        "---\ntype: l2-map\n---\nAlways use spaces for indentation in Python files.\n",
    )

    proposed = "Do not use spaces for indentation in Python files.\n"
    conflicts = detect("ADD", "projects/acme/overview.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_map_exemption_does_not_cross_project_subtrees(tmp_path):
    _write(tmp_path, "projects/acme/style.md", "Always use spaces for indentation in Python files.\n")
    _write(
        tmp_path, "projects/acme/other-map.md",
        "---\ntype: l2-map\n---\nDo not use spaces for indentation in Python files.\n",
    )

    # A map in a DIFFERENT project's subtree gets no exemption here: the
    # candidate glob is sibling-scoped, so assert via the subtree helper that
    # the two sides are not treated as one project.
    from lib.memory.semantics import project_subtree

    assert project_subtree("projects/acme/map.md") == "projects/acme"
    assert project_subtree("projects/other/map.md") == "projects/other"
    assert project_subtree("decisions/adr-001.md") is None


# --- issue #16: a signal is required, topic overlap is not enough -----------


def test_restatement_sharing_topic_tokens_is_not_a_contradiction(tmp_path):
    existing = (
        "Background jobs run through the queue worker pool, which the service "
        "layer enqueues into during request handling.\n"
    )
    _write(tmp_path, "projects/demo/jobs.md", existing)

    # Negation marker present, same topic, but a DIFFERENT claim — the old
    # >=3-shared-token rule fired here; it must not now.
    proposed = "Do not enqueue jobs from the acme platform CLI entrypoint scripts.\n"
    conflicts = detect("ADD", "projects/demo/cli.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_genuine_negation_of_the_same_claim_is_still_held(tmp_path):
    existing = "Background jobs run through the queue worker pool.\n"
    _write(tmp_path, "projects/demo/jobs.md", existing)

    proposed = "Background jobs do not run through the queue worker pool.\n"
    conflicts = detect("ADD", "projects/demo/jobs2.md", proposed, tmp_path)

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert len(con) == 1
    assert con[0].evidence == "background jobs run through the queue worker pool."


def test_numeric_divergence_of_the_same_fact_is_held(tmp_path):
    _write(tmp_path, "projects/demo/config.md", "The request timeout is 30 seconds by default.\n")

    proposed = "The request timeout is 60 seconds by default.\n"
    conflicts = detect("ADD", "projects/demo/config2.md", proposed, tmp_path)

    con = [c for c in conflicts if c.kind == "contradicts"]
    assert len(con) == 1
    assert con[0].evidence == "the request timeout is 30 seconds by default."


def test_enumerated_lines_are_not_numeric_divergence(tmp_path):
    _write(tmp_path, "projects/demo/list.md", "\n".join(_numbered_lines(4)) + "\n")

    proposed = "Line number 9 describes topic 9.\n"
    conflicts = detect("ADD", "projects/demo/list2.md", proposed, tmp_path)

    assert [c for c in conflicts if c.kind == "contradicts"] == []


def test_numeric_divergence_is_exempt_within_a_batch(tmp_path):
    _write(tmp_path, "projects/acme/config.md", "The request timeout is 30 seconds by default.\n")

    conflicts = detect(
        "ADD", "projects/acme/config2.md",
        "The request timeout is 60 seconds by default.\n",
        tmp_path, exempt_pages={"projects/acme/config.md"},
    )

    assert [c for c in conflicts if c.kind == "contradicts"] == []


# --- issue #42: an UPDATE never self-conflicts with its own target ----------


def test_update_target_page_never_self_conflicts(tmp_path):
    # release-shaped UPDATE: a quarantine-review release proposes content
    # identical to the target save for the stripped quarantine banner. This
    # must never fire as a duplicate-of-self or contradicts-self — only the
    # supersedes provenance chain (queue.approve_and_apply reads it) survives.
    prov = new_provenance("human", "sess-1", "ADD", "projects/p/knowledge/a.md")
    body = "\n".join(f"- fact line {i}: the system holds {i} widgets" for i in range(10)) + "\n"
    existing = quarantine_mark(stamp_frontmatter(body, prov))
    _write(tmp_path, "projects/p/knowledge/a.md", existing)

    proposed = quarantine_release(existing)

    conflicts = detect(
        "UPDATE", "projects/p/knowledge/a.md", proposed, tmp_path, exempt_pages=set()
    )

    self_kinds = {c.kind for c in conflicts if c.page == "projects/p/knowledge/a.md"}
    assert "duplicate" not in self_kinds
    assert "contradicts" not in self_kinds
    assert "supersedes" in self_kinds  # provenance chain must survive


def test_update_cross_page_conflicts_still_detected(tmp_path):
    _write(tmp_path, "projects/p/knowledge/a.md", "---\ntitle: \"A\"\n---\n\n# A\n\n- old\n")
    sibling_body = "\n".join(f"- shared fact line {i}: value {i}" for i in range(10))
    _write(
        tmp_path, "projects/p/knowledge/b.md",
        f"---\ntitle: \"B\"\nren_write_id: \"w-B\"\n---\n\n# B\n\n{sibling_body}\n",
    )

    # propose A's UPDATE to be a near-copy of sibling B → duplicate vs B must still fire
    conflicts = detect(
        "UPDATE", "projects/p/knowledge/a.md",
        f"---\ntitle: \"A\"\n---\n\n# B\n\n{sibling_body}\n",
        tmp_path, exempt_pages=set(),
    )

    assert any(c.kind == "duplicate" and c.page == "projects/p/knowledge/b.md" for c in conflicts)
