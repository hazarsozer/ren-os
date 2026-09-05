"""Spec 2026-09-04 §8 — recall ranks with the graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from skills.recall.lib import (
    INBOUND_BOOST_CAP,
    INBOUND_BOOST_PER_LINK,
    _inbound_counts,
    rank,
)


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge/architecture"
    kn.mkdir(parents=True)
    body = ("---\ntype: project-knowledge\n---\n# {t}\n\n"
            "Parent: [[architecture]]\n\nThe write door queues every proposal.\n\n"
            "## Related\n")
    (kn / "linked.md").write_text(body.format(t="Linked"), encoding="utf-8")
    (kn / "twin.md").write_text(body.format(t="Twin"), encoding="utf-8")
    (kn / "architecture.md").write_text(
        "---\ntype: hub\n---\n# Architecture\n\n"
        "The write door queues every proposal.\n\n"
        "## Related\n- [[linked]] — hub link\n",
        encoding="utf-8",
    )
    for i in range(3):
        (kn / f"src{i}.md").write_text(
            f"# Src{i}\n\nParent: [[architecture]]\n\n"
            "## Related\n- [[linked]] — points at linked\n",
            encoding="utf-8",
        )
    return root


def test_well_linked_page_outranks_its_unlinked_twin(wiki):
    ranked = rank("write door queues proposal", [
        "projects/demo/knowledge/architecture/twin.md",
        "projects/demo/knowledge/architecture/linked.md",
    ], wiki)
    assert ranked[0] == "projects/demo/knowledge/architecture/linked.md"


def test_hub_is_excluded_from_the_boost(wiki):
    counts = _inbound_counts(wiki)
    assert counts.get("projects/demo/knowledge/architecture/architecture.md", 0) == 0
    assert counts["projects/demo/knowledge/architecture/linked.md"] >= 3


def test_boost_is_capped(wiki):
    kn = wiki / "projects/demo/knowledge/architecture"
    for i in range(3, 12):
        (kn / f"src{i}.md").write_text(
            f"# Src{i}\n\n## Related\n- [[linked]] — more\n", encoding="utf-8"
        )
    counts = _inbound_counts(wiki)
    assert min(counts["projects/demo/knowledge/architecture/linked.md"],
               INBOUND_BOOST_CAP) == INBOUND_BOOST_CAP
    assert INBOUND_BOOST_PER_LINK == 0.1


def test_rank_signature_is_unchanged(wiki):
    ranked = rank("write door", ["projects/demo/knowledge/architecture/linked.md"], wiki)
    assert ranked == ["projects/demo/knowledge/architecture/linked.md"]


def test_index_is_memoised_on_wiki_root_mtime(wiki, monkeypatch):
    calls: list[Path] = []
    import lib.memory.links as links_mod
    real = links_mod.build_link_index

    def counting(root, **kw):
        calls.append(Path(root))
        return real(root, **kw)

    monkeypatch.setattr("skills.recall.lib.build_link_index", counting)
    _inbound_counts.cache_clear()
    _inbound_counts(wiki)
    _inbound_counts(wiki)
    assert len(calls) == 1


def test_unreadable_wiki_root_scores_zero_boost_not_a_crash(tmp_path):
    missing = tmp_path / "nope"
    assert rank("anything", [], missing) == []
    assert _inbound_counts(missing) == {}


@pytest.mark.parametrize(
    "rel, is_hub",
    [
        ("projects/demo/knowledge/architecture/architecture.md", True),
        ("knowledge/architecture/architecture.md", True),
        ("projects/demo/knowledge/architecture/linked.md", False),
    ],
)
def test_boost_skips_exactly_the_pages_the_kind_multiplier_calls_hubs(
    tmp_path: Path, rel: str, is_hub: bool
) -> None:
    """One hub predicate: the boost's exclusion must agree with
    `_classify_kind`'s (spec 2026-09-04 §8)."""
    from skills.recall.lib import DEFAULT_KIND_MULTIPLIER, _classify_kind, _is_hub_path

    root = tmp_path / "wiki"
    page = root / rel
    page.parent.mkdir(parents=True)
    page.write_text("# P\n\n## Related\n", encoding="utf-8")
    (root / "src.md").write_text(
        f"# Src\n\n## Related\n- [[{Path(rel).stem}]] — points at it\n", encoding="utf-8"
    )

    assert _is_hub_path(rel) is is_hub
    kind_says_hub = "/knowledge/" in f"/{rel}/" and _classify_kind(rel) == DEFAULT_KIND_MULTIPLIER
    assert _is_hub_path(rel) is kind_says_hub

    _inbound_counts.cache_clear()
    counts = _inbound_counts(root)
    assert (counts.get(rel, 0) == 0) is is_hub


def test_root_lessons_hub_is_excluded_from_the_inbound_boost(tmp_path):
    """I2: `lessons/lessons.md` is a folder-note hub outside any
    `knowledge/` tree — every wrap lesson points at it via
    `Parent: [[lessons]]`, so its inbound count is structural, not earned
    (spec 2026-09-04 §8: hubs are excluded)."""
    root = tmp_path / "wiki"
    hub = root / "lessons" / "lessons.md"
    hub.parent.mkdir(parents=True)
    hub.write_text("# Lessons\n\n## Related\n", encoding="utf-8")
    for i in range(5):
        (root / "lessons" / f"l{i}.md").write_text(
            f"# L{i}\n\nParent: [[lessons]]\n\n## Related\n- [[lessons]] — hub\n",
            encoding="utf-8",
        )

    _inbound_counts.cache_clear()
    assert _inbound_counts(root).get("lessons/lessons.md", 0) == 0
