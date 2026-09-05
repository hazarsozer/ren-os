"""Spec 2026-09-04 §10 — land a concept in a fixture project; assert the
item page, two related pages, and the event."""

from __future__ import annotations

import json

import pytest

from lib.instrument import collect
from lib.memory.fanout import LandedItem, fan_out
from lib.memory.links import parse_page_links


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge/architecture"
    kn.mkdir(parents=True)
    (kn / "architecture.md").write_text("---\ntype: hub\n---\n# Architecture\n", encoding="utf-8")
    for stem, body in (
        ("write-door", "The queue is the only write door for durable pages."),
        ("journal", "The journal records every applied write and its lineage."),
    ):
        (kn / f"{stem}.md").write_text(
            f"---\ntype: project-knowledge\n---\n# {stem}\n\n"
            f"Parent: [[architecture]]\n\n{body}\n\n## Related\n",
            encoding="utf-8",
        )
    (kn / "queue-holds.md").write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n"
        "A contradicts conflict holds the write door's proposal.\n\n## Related\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    return root


def test_landing_a_concept_relates_two_pages_and_records_the_event(wiki):
    def llm(prompt: str) -> str:
        return json.dumps({"verdicts": [
            {"page": "write-door", "edge": "relate", "reason": "holds happen at the door"},
            {"page": "journal", "edge": "relate", "reason": "an applied write follows a hold"},
        ]})

    item = LandedItem(
        page="projects/demo/knowledge/architecture/queue-holds.md",
        title="Queue Holds",
        text="A contradicts conflict holds the write door's proposal.",
        write_id="w-E2E01",
    )
    result = fan_out(item, "demo", "s-e2e", llm)

    assert result.unknown_reason is None
    assert result.verdicts["relate"] == 2

    kn = wiki / "projects/demo/knowledge/architecture"
    item_related = dict(parse_page_links((kn / "queue-holds.md").read_text(encoding="utf-8")).related)
    assert set(item_related) == {"write-door", "journal"}
    for stem in ("write-door", "journal"):
        back = dict(parse_page_links((kn / f"{stem}.md").read_text(encoding="utf-8")).related)
        assert "queue-holds" in back

    event = collect.read(kind=collect.KIND_FANOUT_EVENT)[-1]
    assert event["item"] == item.page
    assert event["applied"] == 3  # two candidates + the item's own page
