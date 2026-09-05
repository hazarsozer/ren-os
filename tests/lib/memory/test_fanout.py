"""Spec 2026-09-04 §5 — write-time fan-out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.instrument import collect
from lib.memory.fanout import FANOUT_CANDIDATES, LandedItem, fan_out
from lib.memory.links import parse_page_links


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge"
    (kn / "architecture").mkdir(parents=True)
    (kn / "lessons").mkdir(parents=True)
    (kn / "architecture/architecture.md").write_text(
        "---\ntype: hub\n---\n# Architecture\n", encoding="utf-8"
    )
    (kn / "architecture/write-door.md").write_text(
        "---\ntype: project-knowledge\n---\n# Write Door\n\n"
        "Parent: [[architecture]]\n\nThe queue is the write door.\n\n"
        "## Related\n\n## Facts\n\n- the queue holds contradictions\n",
        encoding="utf-8",
    )
    (kn / "architecture/journal.md").write_text(
        "---\ntype: project-knowledge\n---\n# Journal\n\n"
        "Parent: [[architecture]]\n\nThe journal records every applied write.\n\n"
        "## Related\n",
        encoding="utf-8",
    )
    (kn / "lessons/queue-lesson.md").write_text(
        "---\ntype: lesson\n---\n# Queue Lesson\n\nThe queue surprised us once.\n\n"
        "## Related\n",
        encoding="utf-8",
    )
    (kn / "architecture/human-owned.md").write_text(
        "---\ntype: project-knowledge\nren_trust: \"user\"\n---\n# Human Owned\n\n"
        "The queue is described here by a human.\n\n## Related\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    return root


ITEM = LandedItem(
    page="projects/demo/knowledge/architecture/queue-holds.md",
    title="Queue Holds",
    text="A contradicts conflict holds the write for the live session to reason about.",
    write_id="w-TEST01",
)


def _llm(verdicts):
    def call(prompt: str) -> str:
        return json.dumps({"verdicts": verdicts})
    return call


def test_relate_verdict_edits_both_pages(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\n"
        "Parent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "holds precede applies"},
    ]))
    assert result.unknown_reason is None
    assert result.verdicts["relate"] == 1
    item_links = parse_page_links((wiki / ITEM.page).read_text(encoding="utf-8"))
    other = parse_page_links(
        (wiki / "projects/demo/knowledge/architecture/journal.md").read_text(encoding="utf-8")
    )
    assert ("journal", "holds precede applies") in item_links.related
    assert ("queue-holds", "holds precede applies") in other.related


def test_fact_verdict_appends_a_facts_bullet_on_a_concept_page(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "write-door", "edge": "fact",
         "reason": "the door is where holds happen",
         "fact": "A contradicts conflict holds the write."},
    ]))
    target = (wiki / "projects/demo/knowledge/architecture/write-door.md").read_text(encoding="utf-8")
    assert "- A contradicts conflict holds the write." in target
    assert "[[queue-holds]]" in target  # fact implies the relate edge too


def test_fact_on_a_lesson_downgrades_to_relate(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "queue-lesson", "edge": "fact", "reason": "same queue",
         "fact": "should never land"},
    ]))
    lesson = (wiki / "projects/demo/knowledge/lessons/queue-lesson.md").read_text(encoding="utf-8")
    assert "should never land" not in lesson
    assert "[[queue-holds]]" in lesson
    assert result.verdicts["relate"] == 1
    assert result.verdicts["fact"] == 0


def test_human_owned_candidate_becomes_a_suggestion_not_an_edit(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "human-owned", "edge": "relate", "reason": "same subject"},
    ]))
    page = (wiki / "projects/demo/knowledge/architecture/human-owned.md").read_text(encoding="utf-8")
    assert "[[queue-holds]]" not in page
    assert len(result.suggested) == 1
    assert result.suggested[0]["page"] == "projects/demo/knowledge/architecture/human-owned.md"


def test_unparseable_output_is_unknown_with_zero_writes(wiki):
    before = (wiki / "projects/demo/knowledge/architecture/journal.md").read_text(encoding="utf-8")
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", lambda p: "not json at all")
    assert result.unknown_reason is not None
    assert result.applied == []
    assert (wiki / "projects/demo/knowledge/architecture/journal.md").read_text(encoding="utf-8") == before


def test_missing_field_is_unknown_not_a_partial_apply(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "fine"},
        {"page": "write-door", "edge": "fact", "reason": "no fact field given"},
    ]))
    assert result.unknown_reason is not None
    assert result.applied == []


def test_hubs_and_self_are_excluded_from_candidates(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps({"verdicts": []})

    fan_out(ITEM, "demo", "s1", call)
    assert "architecture/architecture.md" not in seen[0]
    assert "queue-holds.md" not in seen[0]


def test_already_related_candidate_is_excluded(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n"
        "## Related\n- [[journal]] — already linked\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps({"verdicts": []})

    fan_out(ITEM, "demo", "s1", call)
    assert "journal.md" not in seen[0]


def test_zero_candidates_makes_no_llm_call_and_records_the_event(wiki, monkeypatch):
    (wiki / ITEM.page).write_text("# Queue Holds\n\n## Related\n", encoding="utf-8")
    monkeypatch.setattr("lib.memory.fanout.FANOUT_CANDIDATES", 0)

    def boom(prompt: str) -> str:
        raise AssertionError("llm_call must not run with zero candidates")

    result = fan_out(ITEM, "demo", "s1", boom, candidates=0)
    assert result.candidates == []
    events = collect.read(kind=collect.KIND_FANOUT_EVENT)
    assert events and events[-1]["candidates"] == 0


def test_fanout_event_shape(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "r"},
    ]))
    event = collect.read(kind=collect.KIND_FANOUT_EVENT)[-1]
    assert event["item"] == ITEM.page
    assert event["verdicts"] == {"relate": 1, "fact": 0, "none": 0}
    assert event["applied"] >= 1
    assert event["unknown_reason"] is None


def test_candidate_count_bounds_the_edits(wiki):
    assert FANOUT_CANDIDATES == 12


def _fatten(page: Path, bullets: int) -> None:
    """Give a page exactly `bullets` Facts bullets."""
    body = page.read_text(encoding="utf-8").split("## Facts")[0]
    facts = "\n".join(f"- existing fact {i}" for i in range(bullets))
    page.write_text(body + "## Facts\n\n" + facts + "\n", encoding="utf-8")


def test_fact_verdict_past_the_split_threshold_raises_one_suggestion(wiki):
    """Spec §5.3 — 'the 40-bullet split suggestion fires exactly as it does
    today'. Today's rule is `> CONCEPT_SPLIT_BULLETS` AFTER the append, so a
    page at exactly 40 crosses to 41 and fires."""
    from lib.memory.links import CONCEPT_SPLIT_BULLETS
    from lib import suggestions

    target = wiki / "projects/demo/knowledge/architecture/write-door.md"
    _fatten(target, CONCEPT_SPLIT_BULLETS)
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "write-door", "edge": "fact", "reason": "holds happen at the door",
         "fact": "A contradicts conflict holds the write."},
    ]))
    splits = [
        s for s in suggestions.pending_suggestions()
        if s["fingerprint"] == f"wrap-split:{target.relative_to(wiki).as_posix()}"
    ]
    assert len(splits) == 1


def test_split_suggestion_is_not_duplicated_on_a_second_run(wiki):
    from lib.memory.links import CONCEPT_SPLIT_BULLETS
    from lib import suggestions

    target = wiki / "projects/demo/knowledge/architecture/write-door.md"
    _fatten(target, CONCEPT_SPLIT_BULLETS)
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    verdict = [{"page": "write-door", "edge": "fact", "reason": "holds happen at the door",
                "fact": "A contradicts conflict holds the write."}]
    fan_out(ITEM, "demo", "s1", _llm(verdict))
    fan_out(ITEM, "demo", "s2", _llm(verdict))
    fp = f"wrap-split:{target.relative_to(wiki).as_posix()}"
    assert len([s for s in suggestions.pending_suggestions() if s["fingerprint"] == fp]) == 1


def test_fact_verdict_under_the_threshold_raises_no_split(wiki):
    from lib import suggestions

    target = wiki / "projects/demo/knowledge/architecture/write-door.md"
    _fatten(target, 3)
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "write-door", "edge": "fact", "reason": "r", "fact": "one more"},
    ]))
    assert not [s for s in suggestions.pending_suggestions() if s["fingerprint"].startswith("wrap-split:")]


def test_apply_failure_is_unknown_with_prior_edits_still_applied(wiki, monkeypatch):
    """Fix round 1: the apply phase (item-page read, each write-door call)
    must be fail-closed too — a raise partway through must not propagate
    into wrap/distill, and edits already applied stay listed."""
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    from lib.memory import fanout as fanout_mod

    real_propose_and_apply = fanout_mod.propose_and_apply
    calls = {"n": 0}

    def flaky(proposal):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real_propose_and_apply(proposal)

    monkeypatch.setattr(fanout_mod, "propose_and_apply", flaky)

    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "r1"},
        {"page": "write-door", "edge": "relate", "reason": "r2"},
    ]))
    assert result.unknown_reason is not None
    assert "boom" in result.unknown_reason
    assert len(result.applied) == 1
    events = collect.read(kind=collect.KIND_FANOUT_EVENT)
    assert len(events) == 1
    assert events[-1]["unknown_reason"] is not None


def test_item_page_unreadable_during_apply_is_unknown_with_zero_edits(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    # Candidate selection succeeds (it scores against item.title/item.text,
    # not the on-disk file), but the item's own page vanishes before the
    # apply phase's read.
    (wiki / ITEM.page).unlink()

    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "r"},
    ]))
    assert result.unknown_reason is not None
    assert result.applied == []
    events = collect.read(kind=collect.KIND_FANOUT_EVENT)
    assert len(events) == 1
    assert events[-1]["unknown_reason"] is not None
