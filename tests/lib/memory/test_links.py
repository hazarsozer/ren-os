"""Spec 2026-09-04 §3-§4 — the link convention and the shared link index."""

from __future__ import annotations

from pathlib import Path

from lib.memory.links import (
    LinkIndex,
    PageLinks,
    build_link_index,
    parse_page_links,
    render_related,
    upsert_parent,
    upsert_related,
)

PAGE = """---
type: project-knowledge
---
# Write Door

Parent: [[memory-plane]]

The queue is the only write door. See also [[provenance]] in passing.

## Related
- [[queue-holds]] — the hold rules live next door
- [[journal]] — every applied write lands here

## Facts

- one fact
"""


def test_parse_extracts_parent_related_and_other():
    links = parse_page_links(PAGE)
    assert links.parent == "memory-plane"
    assert links.related == (
        ("queue-holds", "the hold rules live next door"),
        ("journal", "every applied write lands here"),
    )
    assert "provenance" in links.other
    # Related stems are NOT repeated in `other`.
    assert "queue-holds" not in links.other


def test_parse_no_parent_line_is_not_an_error():
    links = parse_page_links("# Bare\n\nnothing here.\n")
    assert links.parent is None
    assert links.related == ()
    assert links.other == ()


def test_parse_empty_related_section_is_empty_not_missing():
    links = parse_page_links("# T\n\nParent: [[h]]\n\n## Related\n")
    assert links.parent == "h"
    assert links.related == ()


def test_parse_markdown_links_land_in_other():
    links = parse_page_links("# T\n\nsee [the map](projects/x/map.md) for more.\n")
    assert links.other == ("projects/x/map.md",)


def test_render_related_shape():
    assert render_related([("a", "because a"), ("b", "because b")]) == (
        "## Related\n- [[a]] — because a\n- [[b]] — because b\n"
    )


def test_render_related_empty_keeps_the_heading():
    assert render_related([]) == "## Related\n"


def test_upsert_related_appends_then_is_idempotent():
    once = upsert_related(PAGE, "provenance", "stamps every applied page")
    assert "- [[provenance]] — stamps every applied page" in once
    twice = upsert_related(once, "provenance", "a different reason entirely")
    assert twice == once
    assert once.count("[[provenance]] —") == 1


def test_upsert_related_creates_the_section_when_absent():
    out = upsert_related("# T\n\nParent: [[h]]\n\nbody.\n", "x", "why")
    assert out.endswith("## Related\n- [[x]] — why\n")


def test_upsert_related_inserts_before_facts_not_after():
    out = upsert_related(PAGE, "provenance", "stamps pages")
    assert out.index("[[provenance]]") < out.index("## Facts")


def test_upsert_parent_adds_then_is_idempotent():
    once = upsert_parent("---\ntype: lesson\n---\n# T\n\nbody.\n", "memory-plane")
    assert "# T\n\nParent: [[memory-plane]]\n\nbody.\n" in once
    assert upsert_parent(once, "memory-plane") == once


def test_upsert_parent_replaces_an_existing_parent():
    out = upsert_parent(PAGE, "instrumentation")
    assert "Parent: [[instrumentation]]" in out
    assert "Parent: [[memory-plane]]" not in out
    assert out.count("Parent: ") == 1


def _wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    (root / "projects/demo/knowledge/architecture").mkdir(parents=True)
    (root / "projects/demo/knowledge/architecture/architecture.md").write_text(
        "# Architecture\n\n- [write-door](write-door.md)\n", encoding="utf-8"
    )
    (root / "projects/demo/knowledge/architecture/write-door.md").write_text(
        "# Write Door\n\nParent: [[architecture]]\n\n"
        "## Related\n- [[journal]] — lineage\n",
        encoding="utf-8",
    )
    (root / "projects/demo/knowledge/architecture/journal.md").write_text(
        "# Journal\n\nParent: [[architecture]]\n\n## Related\n", encoding="utf-8"
    )
    (root / ".ren").mkdir()
    (root / ".ren/hidden.md").write_text("# Hidden\n\n[[write-door]]\n", encoding="utf-8")
    return root


def test_build_link_index_resolves_stems_to_paths(tmp_path):
    idx = build_link_index(_wiki(tmp_path))
    assert isinstance(idx, LinkIndex)
    wd = "projects/demo/knowledge/architecture/write-door.md"
    jr = "projects/demo/knowledge/architecture/journal.md"
    hub = "projects/demo/knowledge/architecture/architecture.md"
    assert idx.outbound[wd] == {hub, jr}
    assert idx.inbound[jr] == {wd}
    assert idx.inbound[wd] == {hub}
    assert idx.parent[wd] == "architecture"
    assert idx.related[wd] == [("journal", "lineage")]


def test_build_link_index_skips_dot_dirs(tmp_path):
    idx = build_link_index(_wiki(tmp_path))
    assert not any(p.startswith(".ren/") for p in idx.pages)


def test_build_link_index_project_narrows_the_walk(tmp_path):
    root = _wiki(tmp_path)
    (root / "projects/other").mkdir(parents=True)
    (root / "projects/other/map.md").write_text("# Other\n", encoding="utf-8")
    idx = build_link_index(root, project="demo")
    assert "projects/other/map.md" not in idx.pages
    assert "projects/demo/knowledge/architecture/write-door.md" in idx.pages
