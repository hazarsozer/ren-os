"""Spec 2026-09-04 §7 — distill emits the convention and pays for fan-out
edits out of WRITE_CAP."""

from __future__ import annotations

import importlib

from lib.memory.fanout import FanoutResult
from lib.memory.links import parse_page_links

distill = importlib.import_module("skills.distill.lib")


def test_seed_tree_marker_is_a_parent_line_not_a_see_line():
    body = "---\ntype: lesson\n---\n# A Lesson\n\nSomething happened.\n"
    annotated = distill._annotate_lesson(body, "memory-plane")
    assert parse_page_links(annotated).parent == "memory-plane"
    assert "See: [[memory-plane]]" not in annotated


def test_annotate_lesson_is_idempotent():
    body = "---\ntype: lesson\n---\n# A Lesson\n\nSomething happened.\n"
    once = distill._annotate_lesson(body, "memory-plane")
    assert distill._annotate_lesson(once, "memory-plane") == once


def test_annotate_lesson_adds_an_empty_related_section():
    out = distill._annotate_lesson("# L\n\nbody.\n", "memory-plane")
    assert "## Related" in out
    assert parse_page_links(out).related == ()


def test_fanout_edits_count_against_write_cap(monkeypatch):
    """A capped run must land FEWER items, not MORE writes (spec §5 budget)."""
    monkeypatch.setattr(
        distill, "fan_out",
        lambda *a, **k: FanoutResult(applied=[{"page": "x.md"}, {"page": "y.md"}]),
    )
    counted = distill._fanout_write_count(FanoutResult(applied=[{"page": "x"}, {"page": "y"}]))
    assert counted == 2


def test_fanout_write_count_ignores_held_and_suggested():
    assert distill._fanout_write_count(
        FanoutResult(applied=[{"page": "x"}], held=[{"page": "y"}], suggested=[{"page": "z"}])
    ) == 1


def test_seed_tree_batch_excludes_legacy_see_marker(tmp_path, monkeypatch):
    root = tmp_path
    lessons_dir = root / "projects" / "p" / "knowledge" / "lessons"
    lessons_dir.mkdir(parents=True)
    (lessons_dir / "a.md").write_text(
        "---\nren_ts: '2026-01-01T00:00:00Z'\n---\n# A\n\nbody.\n\nSee: [[node]]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(distill.ren_paths, "wiki_root", lambda: root)
    result = distill.seed_tree_batch("p", None)
    assert result == []


def test_seed_tree_batch_excludes_parent_marker(tmp_path, monkeypatch):
    root = tmp_path
    lessons_dir = root / "projects" / "p" / "knowledge" / "lessons"
    lessons_dir.mkdir(parents=True)
    (lessons_dir / "a.md").write_text(
        "---\nren_ts: '2026-01-01T00:00:00Z'\n---\n# A\n\nParent: [[node]]\n\nbody.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(distill.ren_paths, "wiki_root", lambda: root)
    result = distill.seed_tree_batch("p", None)
    assert result == []
