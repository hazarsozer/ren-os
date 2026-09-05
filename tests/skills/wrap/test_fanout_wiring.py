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


# --- C1: every durable landing under projects/<slug>/knowledge/ fans out -----


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    """A project whose knowledge tree already holds one page, so the real
    `fan_out` has a candidate to rank and actually calls its classifier."""
    root = tmp_path / "wiki"
    (root / "projects" / "demo" / "knowledge" / "lessons").mkdir(parents=True)
    arch = root / "projects" / "demo" / "knowledge" / "architecture"
    arch.mkdir(parents=True)
    (arch / "journal.md").write_text(
        "---\ntype: project-knowledge\nren_trust: \"model\"\n---\n# Journal\n\n"
        "Parent: [[architecture]]\n\nThe queue is the single write door.\n\n"
        "## Related\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    return root


_FANOUT_MARK = "EXISTING PAGES:"


def _durable_lesson_verdict(scope):
    return {"verdict": "durable", "reason": "r", "scope": scope,
            "action": "create", "target_page": None}


def _llm(prompts):
    """Records every prompt; answers a fan-out prompt with all-`none`."""
    def call(p):
        prompts.append(p)
        return '{"verdicts": [{"page": "journal", "edge": "none"}]}'
    return call


def test_project_lesson_landing_fans_out(wiki):
    """C1 (a): spec §5 — EVERY durable landing under
    `projects/<slug>/knowledge/` fans out, not just concept creates."""
    from lib.instrument import collect

    prompts: list[str] = []
    before = len(collect.read(kind=collect.KIND_FANOUT_EVENT))

    result = wrap.wrap_session(
        "---\n---\n\n# S\n\nnarrative.\n",
        ["the queue is the single write door"],
        "s-fan-lesson",
        llm_call=_llm(prompts),
        project="demo",
        verdicts=[_durable_lesson_verdict("project")],
    )

    assert [a["page"] for a in result["applied"]][0].startswith(
        "projects/demo/knowledge/lessons/")
    assert any(_FANOUT_MARK in p for p in prompts)
    events = collect.read(kind=collect.KIND_FANOUT_EVENT)
    assert len(events) == before + 1
    assert events[-1]["item"].startswith("projects/demo/knowledge/lessons/")


def test_global_lesson_landing_does_not_fan_out(wiki):
    """C1 (b): a global-scope lesson lives outside any project knowledge
    tree — there is nothing to fan it out across."""
    from lib.instrument import collect

    prompts: list[str] = []
    before = len(collect.read(kind=collect.KIND_FANOUT_EVENT))

    result = wrap.wrap_session(
        "---\n---\n\n# S\n\nnarrative.\n",
        ["a global habit worth keeping"],
        "s-fan-global",
        llm_call=_llm(prompts),
        project="demo",
        verdicts=[_durable_lesson_verdict("global")],
    )

    assert result["applied"][0]["page"].startswith("lessons/")
    assert not any(_FANOUT_MARK in p for p in prompts)
    assert len(collect.read(kind=collect.KIND_FANOUT_EVENT)) == before


def test_accretion_onto_an_existing_page_fans_out(wiki):
    """C1 (c): an `action == "update"` landing on a project knowledge page
    is an accretion — spec §5 counts it as a durable landing."""
    from lib.instrument import collect

    target = "projects/demo/knowledge/architecture/write-door.md"
    page = wiki / target
    page.write_text(
        "---\ntype: project-knowledge\nren_trust: \"model\"\n---\n# Write Door\n\n"
        "Parent: [[architecture]]\n\n## Related\n\n## Facts\n\n- the queue is the door\n",
        encoding="utf-8",
    )
    # `update` targets must be in this session's eligibility set (§1).
    collect.record(collect.KIND_L3_FETCH, {"session": "s-fan-accrete", "page": target})

    prompts: list[str] = []
    before = len(collect.read(kind=collect.KIND_FANOUT_EVENT))

    result = wrap.wrap_session(
        "---\n---\n\n# S\n\nnarrative.\n",
        ["holds are reported with their conflicts"],
        "s-fan-accrete",
        llm_call=_llm(prompts),
        project="demo",
        verdicts=[{"verdict": "durable", "reason": "r", "scope": "project",
                   "action": "update", "target_page": target}],
        merges=[page.read_text(encoding="utf-8").replace(
            "- the queue is the door",
            "- the queue is the door\n- holds are reported with their conflicts")],
    )

    assert [u["page"] for u in result["updated"]] == [target], repr(result)
    assert any(_FANOUT_MARK in p for p in prompts)
    events = collect.read(kind=collect.KIND_FANOUT_EVENT)
    assert len(events) == before + 1
    assert events[-1]["item"] == target
