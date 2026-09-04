"""Spec 2026-09-04 §4 — `_orphan_pages` refactored onto `build_link_index`
must stay byte-identical. These are the shapes the #55 fixtures cover, plus
the new-convention shapes the refactor introduces."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from lib.memory.links import build_link_index

wiki_health = importlib.import_module("skills.wiki-health.lib")


@pytest.fixture
def graph_wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    (root / "projects/demo/knowledge/architecture").mkdir(parents=True)
    (root / "projects/demo/knowledge/lessons").mkdir(parents=True)
    (root / "projects/demo/raw").mkdir(parents=True)
    (root / "archive").mkdir(parents=True)
    (root / "index.md").write_text("# Index\n\n- [demo](projects/demo/map.md)\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    (root / "projects/demo/map.md").write_text(
        "# Demo\n\n- [architecture](knowledge/architecture/architecture.md)\n", encoding="utf-8"
    )
    (root / "projects/demo/knowledge/architecture/architecture.md").write_text(
        "# Architecture\n\n- [write-door](write-door.md)\n", encoding="utf-8"
    )
    (root / "projects/demo/knowledge/architecture/write-door.md").write_text(
        "# Write Door\n\nParent: [[architecture]]\n\n## Related\n"
        "- [[journal]] — lineage\n",
        encoding="utf-8",
    )
    # Reached ONLY by a `## Related` wikilink — the new convention must save it.
    (root / "projects/demo/knowledge/architecture/journal.md").write_text(
        "# Journal\n\nParent: [[architecture]]\n\n## Related\n", encoding="utf-8"
    )
    # Nothing links to this one — a genuine orphan.
    (root / "projects/demo/knowledge/lessons/stray.md").write_text(
        "# Stray\n\nnobody points here.\n", encoding="utf-8"
    )
    # Exempt shapes: raw/ and archive/ are never orphan candidates.
    (root / "projects/demo/raw/dump.md").write_text("# Dump\n", encoding="utf-8")
    (root / "archive/old.md").write_text("# Old\n", encoding="utf-8")
    return root


def test_related_wikilink_saves_a_page_from_orphanhood(graph_wiki):
    orphans = wiki_health._orphan_pages(graph_wiki)
    assert "projects/demo/knowledge/architecture/journal.md" not in orphans


def test_genuine_orphan_still_found(graph_wiki):
    assert wiki_health._orphan_pages(graph_wiki) == [
        "projects/demo/knowledge/lessons/stray.md"
    ]


def test_raw_and_archive_stay_exempt(graph_wiki):
    orphans = wiki_health._orphan_pages(graph_wiki)
    assert "projects/demo/raw/dump.md" not in orphans
    assert "archive/old.md" not in orphans


def test_accepts_a_prebuilt_index_and_agrees_with_building_its_own(graph_wiki):
    index = build_link_index(graph_wiki)
    assert wiki_health._orphan_pages(graph_wiki, index) == wiki_health._orphan_pages(graph_wiki)
