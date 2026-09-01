"""Tests for `seed_tree` — the `--seed-tree` backfill mode (spec 2026-08-31
§3, Task 7): manual-trigger-only batch mining of EXISTING project lessons
into the concept tree, via Task 3's shared `_apply_concept_create` machinery.

Reuses test_lib.py's REN_WIKI_ROOT isolation pattern.
"""

from __future__ import annotations

import json

import pytest

from lib.instrument import collect
from lib.ren_paths import PathTraversalError
from skills.distill.lib import (
    read_seed_tree_watermark,
    seed_tree,
    seed_tree_batch,
    seed_tree_watermark_path,
    write_seed_tree_watermark,
)

SCHEMA_MD = """---
type: schema
schema_version: 1
project: alpha
---

# Taxonomy

```taxonomy
architecture/
```
"""

LESSON_TEMPLATE = """---
type: lesson
ren_ts: "{ts}"
ren_trust: "model"
---
{body}
"""

CONCEPT_MARK = "the event loop dispatches callbacks in FIFO order"
EPISODIC_MARK = "we spent an hour chasing a flaky CI runner"


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    (root / "projects" / "alpha" / "knowledge" / "lessons").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    (root / "projects" / "alpha" / "schema.md").write_text(SCHEMA_MD, encoding="utf-8")
    return root


def _lesson(root, name, ts, body):
    path = root / "projects" / "alpha" / "knowledge" / "lessons" / name
    path.write_text(LESSON_TEMPLATE.format(ts=ts, body=body), encoding="utf-8")
    return path


def _fake_llm(prompt: str) -> str:
    if CONCEPT_MARK in prompt:
        return json.dumps({
            "verdict": "durable", "reason": "structural fact",
            "scope": "project", "action": "create", "target_page": None,
            "kind": "concept", "placement": "architecture/event-loop",
            "title": "Async Event Loop",
        })
    return json.dumps({
        "verdict": "session-only", "reason": "already a lesson, nothing new",
        "scope": "global", "action": "create", "target_page": None,
        "kind": "lesson", "placement": None, "title": None,
    })


def test_seed_tree_no_schema_refuses_with_zero_writes(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    (root / "projects" / "alpha" / "knowledge" / "lessons").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    _lesson(root, "concept-one.md", "2026-08-01T00:00:00Z", CONCEPT_MARK + ".")
    # No schema.md written for this project.

    result = seed_tree("alpha", _fake_llm)

    assert result["blind"] == "no taxonomy — run ingest's taxonomy draft first"
    assert result["applied"] == [] and result["annotated"] == []
    assert result["held"] == [] and result["suggested"] == []
    assert result["gated_out"] == [] and result["refused"] == []
    assert result["duplicates"] == [] and result["capped_remainder"] == 0
    assert result["watermark_after"] is None
    assert read_seed_tree_watermark("alpha") is None
    # No knowledge/ file besides the pre-existing lesson was ever written.
    knowledge_files = sorted(
        p.relative_to(root) for p in (root / "projects" / "alpha" / "knowledge").rglob("*.md")
    )
    assert [str(p) for p in knowledge_files] == ["projects/alpha/knowledge/lessons/concept-one.md"]


def test_seed_tree_places_concept_annotates_lesson_leaves_episodic_untouched(wiki):
    _lesson(wiki, "concept-one.md", "2026-08-01T00:00:00Z", CONCEPT_MARK + ".")
    _lesson(wiki, "episodic-one.md", "2026-08-02T00:00:00Z", EPISODIC_MARK + ".")

    result = seed_tree("alpha", _fake_llm)

    assert result["blind"] is None
    assert len(result["applied"]) == 1
    concept_page = result["applied"][0]["page"]
    assert concept_page == "projects/alpha/knowledge/architecture/event-loop/async-event-loop.md"
    assert (wiki / concept_page).is_file()

    # Leaf + parent hubs (Task 3's `_apply_concept_create` maintains these
    # internally — behavior 7 needs no extra call here).
    assert (wiki / "projects/alpha/knowledge/architecture/event-loop/event-loop.md").is_file()
    assert (wiki / "projects/alpha/knowledge/architecture/architecture.md").is_file()

    assert len(result["annotated"]) == 1
    assert result["annotated"][0]["page"] == "projects/alpha/knowledge/lessons/concept-one.md"
    assert result["annotated"][0]["target"] == "architecture/event-loop"

    concept_lesson_text = (
        wiki / "projects/alpha/knowledge/lessons/concept-one.md"
    ).read_text(encoding="utf-8")
    assert "See: [[event-loop]]" in concept_lesson_text
    assert CONCEPT_MARK in concept_lesson_text  # original body survives

    episodic_text = (
        wiki / "projects/alpha/knowledge/lessons/episodic-one.md"
    ).read_text(encoding="utf-8")
    assert "See:" not in episodic_text

    assert result["gated_out"] == [
        {"page": "projects/alpha/knowledge/lessons/episodic-one.md",
         "kind": "lesson", "verdict": "session-only"}
    ]
    assert result["refused"] == [] and result["held"] == []

    assert result["watermark_after"] == "2026-08-02T00:00:00Z"
    assert read_seed_tree_watermark("alpha") == "2026-08-02T00:00:00Z"

    run_event = collect.read(kind=collect.KIND_DISTILLER_RUN)[-1]
    assert run_event["mode"] == "seed_tree"
    assert run_event["applied"] == 1
    assert run_event["annotated"] == 1
    assert run_event["created_concept"] == 1


def test_seed_tree_cap_stops_run_with_resumable_watermark(wiki):
    _lesson(wiki, "concept-a.md", "2026-08-01T00:00:00Z",
            "the scheduler drains the ready queue before polling I/O.")
    _lesson(wiki, "concept-b.md", "2026-08-02T00:00:00Z",
            "the event loop dispatches callbacks in FIFO order.")
    _lesson(wiki, "concept-c.md", "2026-08-03T00:00:00Z",
            "the reactor pattern demultiplexes events onto handlers.")

    calls = {"n": 0}

    def llm_call(prompt: str) -> str:
        calls["n"] += 1
        # First lesson mined -> a new leaf under architecture/; the other two
        # are irrelevant once the cap stops the run before they're reached.
        return json.dumps({
            "verdict": "durable", "reason": "structural fact",
            "scope": "project", "action": "create", "target_page": None,
            "kind": "concept", "placement": "architecture/scheduler",
            "title": "Task Scheduler",
        })

    # cap=2: exactly one lesson's worth of writes (concept create + See:
    # annotation) — the second lesson must never be reached.
    result = seed_tree("alpha", llm_call, cap=2)

    assert len(result["applied"]) == 1
    assert len(result["annotated"]) == 1
    assert result["capped_remainder"] == 2
    assert result["watermark_after"] == "2026-08-01T00:00:00Z"
    assert calls["n"] == 1

    run_event = collect.read(kind=collect.KIND_DISTILLER_RUN)[-1]
    assert run_event["capped_remainder"] == 2


def test_seed_tree_rerun_after_completion_is_idempotent(wiki):
    _lesson(wiki, "concept-one.md", "2026-08-01T00:00:00Z", CONCEPT_MARK + ".")

    first = seed_tree("alpha", _fake_llm)
    assert len(first["applied"]) == 1 and len(first["annotated"]) == 1

    # Natural re-run: the annotation UPDATE re-stamps the lesson's own
    # `ren_ts` (the write door restamps `ren_*` provenance on EVERY write,
    # not just creation) — so the watermark comparison alone can't be relied
    # on to exclude it; the batch-level `See:`-marker guard is what actually
    # keeps it out. Nothing is written this run.
    second = seed_tree("alpha", _fake_llm)
    assert second["applied"] == [] and second["annotated"] == []
    assert second["watermark_after"] == first["watermark_after"]

    # Belt-and-suspenders: force the watermark all the way back too. Even
    # with a watermark that would otherwise re-admit it, the marker guard
    # still excludes the already-annotated lesson from the batch entirely —
    # no candidate is even offered to the classifier, let alone written.
    write_seed_tree_watermark("alpha", "2026-01-01T00:00:00Z")
    rebatched = seed_tree_batch("alpha", "2026-01-01T00:00:00Z")
    assert rebatched == []

    third = seed_tree("alpha", _fake_llm)
    assert third["applied"] == [] and third["annotated"] == []
    assert third["duplicates"] == [] and third["gated_out"] == []

    concept_lesson_text = (
        wiki / "projects/alpha/knowledge/lessons/concept-one.md"
    ).read_text(encoding="utf-8")
    assert concept_lesson_text.count("See: [[event-loop]]") == 1


def test_seed_tree_existing_node_placement_is_skipped_not_rejected(wiki):
    """Controller ruling (review fix round 1 IMPORTANT #2): a concept
    placement that resolves to an EXISTING taxonomy node is a valid
    classifier decision, not rejected noise — seed_tree just doesn't gain
    accretion onto existing nodes in this task. Must be counted under its
    own `existing_node_skipped` key, distinct from `placement_rejected`
    (spec §8: that counter is classifier noise), and left un-annotated."""
    _lesson(wiki, "concept-existing.md", "2026-08-01T00:00:00Z",
            "architecture as a whole handles every cross-cutting concern.")

    def llm_call(prompt: str) -> str:
        return json.dumps({
            "verdict": "durable", "reason": "structural fact",
            "scope": "project", "action": "create", "target_page": None,
            "kind": "concept", "placement": "architecture", "title": None,
        })

    result = seed_tree("alpha", llm_call)

    assert result["applied"] == [] and result["annotated"] == []
    assert result["existing_node_skipped"] == 1
    assert len(result["gated_out"]) == 1
    entry = result["gated_out"][0]
    assert entry["page"] == "projects/alpha/knowledge/lessons/concept-existing.md"
    assert entry["kind"] == "concept"
    assert "existing" in entry["reason"]

    run_event = collect.read(kind=collect.KIND_DISTILLER_RUN)[-1]
    assert run_event["existing_node_skipped"] == 1
    assert run_event["placement_rejected"] == 0

    lesson_text = (
        wiki / "projects/alpha/knowledge/lessons/concept-existing.md"
    ).read_text(encoding="utf-8")
    assert "See:" not in lesson_text
    # Nothing new landed under knowledge/ besides the pre-existing lesson.
    knowledge_files = sorted(
        p.relative_to(wiki) for p in (wiki / "projects/alpha/knowledge").rglob("*.md")
    )
    assert [str(p) for p in knowledge_files] == [
        "projects/alpha/knowledge/lessons/concept-existing.md"
    ]


def test_seed_tree_watermark_path_rejects_path_traversal(wiki):
    """Review fix round 1 CRITICAL #1: a traversal-shaped `project` string
    must never resolve outside the state dir."""
    with pytest.raises(PathTraversalError):
        seed_tree_watermark_path("../../../../../../../../tmp/pwned-marker")


def test_read_seed_tree_watermark_refuses_traversal_project(wiki):
    """The read side degrades gracefully (`None`) rather than raising —
    `seed_tree`'s own `load_taxonomy(project)` call, immediately after,
    independently refuses the same malicious project via its own
    `safe_join` guard."""
    assert read_seed_tree_watermark("../../../../../../../../tmp/pwned-marker") is None


def test_seed_tree_batch_refuses_path_traversal_project(wiki):
    """Same guard applied to the lessons-dir construction (review fix round
    1 CRITICAL #1) — a traversal-shaped `project` returns an empty batch
    rather than reading outside the wiki."""
    assert seed_tree_batch("../../../../../../../../tmp", None) == []


def test_seed_tree_refuses_path_traversal_project_end_to_end(wiki):
    """`seed_tree` itself, given a malicious `project`, must never touch
    anything outside the wiki: `load_taxonomy` fails closed on the same
    string (no `projects/<traversal>/schema.md` can exist), so the whole
    run refuses exactly like the missing-schema.md case — zero writes."""
    result = seed_tree("../../../../../../../../tmp/pwned", _fake_llm)
    assert result["blind"] == "no taxonomy — run ingest's taxonomy draft first"
    assert result["applied"] == [] and result["annotated"] == []
