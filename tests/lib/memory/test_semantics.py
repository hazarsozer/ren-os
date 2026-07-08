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
from lib.memory.semantics import Conflict, detect


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
