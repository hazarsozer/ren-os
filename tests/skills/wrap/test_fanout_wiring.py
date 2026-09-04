"""Spec 2026-09-04 §7 — wrap renders Parent:/## Related and fans out."""

from __future__ import annotations

import importlib

import pytest

from lib.memory.fanout import FanoutResult
from lib.memory.links import parse_page_links

wrap = importlib.import_module("skills.wrap.lib")


def test_concept_page_content_carries_parent_and_empty_related():
    body = wrap._concept_page_content(
        "The queue holds contradictions.", "Queue Holds", "demo", "architecture"
    )
    links = parse_page_links(body)
    assert links.parent == "architecture"
    assert "## Related\n" in body
    assert links.related == ()
    assert "## Facts" in body
    # convention order: H1, Parent, body, Related — Related before Facts
    assert body.index("## Related") < body.index("## Facts")


def test_parent_stem_for_uses_the_leaf_hub():
    assert wrap._parent_stem_for("architecture/memory-plane", "demo") == "memory-plane"
    assert wrap._parent_stem_for("architecture", "demo") == "architecture"


def test_render_wrap_screen_reports_fanout_unknown():
    screen = wrap.render_wrap_screen(
        {"fanout": {"unknown": ["classifier output rejected: bad edge"],
                    "applied": 0, "suggested": 0}},
        "s1",
    )
    assert "fan-out unknown: classifier output rejected: bad edge" in screen


def test_render_wrap_screen_omits_the_line_when_nothing_unknown():
    screen = wrap.render_wrap_screen({"fanout": {"unknown": [], "applied": 2, "suggested": 0}}, "s1")
    assert "fan-out unknown" not in screen


def test_route_concept_result_runs_fanout_after_an_applied_create(monkeypatch):
    calls: list[tuple] = []

    def fake_fan_out(item, project, session, llm_call, *, producer="wrap", candidates=12):
        calls.append((item.page, project, producer))
        return FanoutResult(applied=[{"page": "other.md"}])

    monkeypatch.setattr(wrap, "fan_out", fake_fan_out)
    applied, unchanged, held, suggested = [], [], [], []
    fanout_acc = {"unknown": [], "applied": 0, "suggested": 0}
    created = wrap._route_concept_result(
        {"status": "applied", "qid": "q1", "write_id": "w1",
         "page": "projects/demo/knowledge/architecture/x.md", "op": "ADD",
         "schema_suggestion": None},
        applied, unchanged, held, suggested,
        item="the item text", title="X", project="demo", session="s1",
        llm_call=lambda p: "{}", fanout=fanout_acc,
    )
    assert created == 1
    assert calls == [("projects/demo/knowledge/architecture/x.md", "demo", "wrap")]
    assert fanout_acc["applied"] == 1


def test_route_concept_result_skips_fanout_for_a_held_create(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("fan-out must not run for a held write")

    monkeypatch.setattr(wrap, "fan_out", boom)
    fanout_acc = {"unknown": [], "applied": 0, "suggested": 0}
    created = wrap._route_concept_result(
        {"status": "held", "qid": "q1", "page": "p.md", "conflicts": ["contradicts"],
         "schema_suggestion": None},
        [], [], [], [],
        item="i", title="T", project="demo", session="s1",
        llm_call=lambda p: "{}", fanout=fanout_acc,
    )
    assert created == 0


def test_route_concept_result_collects_the_unknown_reason(monkeypatch):
    monkeypatch.setattr(
        wrap, "fan_out",
        lambda *a, **k: FanoutResult(unknown_reason="classifier output rejected: nope"),
    )
    fanout_acc = {"unknown": [], "applied": 0, "suggested": 0}
    wrap._route_concept_result(
        {"status": "applied", "qid": "q", "write_id": "w",
         "page": "projects/demo/knowledge/a/x.md", "op": "ADD", "schema_suggestion": None},
        [], [], [], [],
        item="i", title="T", project="demo", session="s1",
        llm_call=lambda p: "x", fanout=fanout_acc,
    )
    assert fanout_acc["unknown"] == ["classifier output rejected: nope"]
