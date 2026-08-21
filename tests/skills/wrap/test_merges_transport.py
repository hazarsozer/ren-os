"""
Tests for the merges= transport (spec 2026-08-21 §5).

Under the standard verdicts= path there is no live llm_call, so every
update-action durable verdict used to die in the merge step and land in
gated_out. These pin the three-way: pre-computed merge, live llm_call, and
neither (route to suggestions, never gated_out).

Run with: uv run pytest tests/skills/wrap/test_merges_transport.py -v
"""

from __future__ import annotations

import pytest

from skills.wrap.lib.merge import MergeError, validate_merged


class TestValidateMerged:
    def test_accepts_a_well_formed_merge(self):
        current = "---\ntype: lesson\n---\n# A\nold\n"
        merged = "---\ntype: lesson\n---\n# A\nold\nnew\n"
        assert validate_merged(current, merged) == merged

    def test_rejects_altered_frontmatter(self):
        current = "---\ntype: lesson\n---\n# A\n"
        merged = "---\ntype: hub\n---\n# A\nnew\n"
        with pytest.raises(MergeError, match="frontmatter"):
            validate_merged(current, merged)

    def test_rejects_a_no_op_merge(self):
        current = "---\ntype: lesson\n---\n# A\n"
        with pytest.raises(MergeError, match="byte-identical"):
            validate_merged(current, current)

    def test_rejects_empty_or_non_string(self):
        current = "---\ntype: lesson\n---\n# A\n"
        with pytest.raises(MergeError, match="empty or not a string"):
            validate_merged(current, "   ")
        with pytest.raises(MergeError, match="empty or not a string"):
            validate_merged(current, None)


from lib import suggestions
from lib.instrument import collect
from skills.wrap.lib import wrap_session


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    (tmp_path / "wiki").mkdir()
    return tmp_path / "wiki"


_TARGET = "lessons/existing.md"
_CURRENT = "---\ntype: lesson\n---\n# Existing\n\nold line\n"
_MERGED = "---\ntype: lesson\n---\n# Existing\n\nold line\nnew line\n"


def _eligible_target(wiki, session):
    """Put the target on disk AND in this session's eligibility set."""
    path = wiki / "lessons" / "existing.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CURRENT, encoding="utf-8")
    collect.record(collect.KIND_L3_FETCH, {"session": session, "page": _TARGET})
    return path


def _durable_update():
    return {"verdict": "durable", "reason": "amends the lesson",
            "scope": "global", "action": "update", "target_page": _TARGET}


def test_precomputed_merge_applies(wiki):
    """A merge supplied via merges= reaches the write door with no llm_call."""
    path = _eligible_target(wiki, "s-merge-1")

    result = wrap_session("# n", ["the learning"], "s-merge-1",
                          verdicts=[_durable_update()], merges=[_MERGED])

    assert result["gated_out"] == []
    assert result["unplaced"] == []
    assert [u["page"] for u in result["updated"]] == [_TARGET]
    assert "new line" in path.read_text(encoding="utf-8")


def test_missing_merge_routes_to_suggestions_not_gated_out(wiki):
    """The #75 fix. This previously landed in gated_out with
    "merge llm call failed: 'NoneType' object is not callable"."""
    _eligible_target(wiki, "s-merge-2")

    result = wrap_session("# n", ["the learning"], "s-merge-2",
                          verdicts=[_durable_update()])

    assert result["gated_out"] == []
    assert result["updated"] == []
    assert len(result["unplaced"]) == 1
    assert any(
        s["payload"].get("action") == "place_durable_item"
        and s["fingerprint"].startswith("wrap-unmerged:")
        for s in suggestions.pending_suggestions()
    )


def test_invalid_merge_routes_to_suggestions(wiki):
    """A merge that altered the frontmatter is unplaced, never silently gated."""
    _eligible_target(wiki, "s-merge-3")
    tampered = "---\ntype: hub\n---\n# Existing\n\nold line\nnew line\n"

    result = wrap_session("# n", ["the learning"], "s-merge-3",
                          verdicts=[_durable_update()], merges=[tampered])

    assert result["gated_out"] == []
    assert result["updated"] == []
    assert len(result["unplaced"]) == 1


def test_live_llm_call_path_is_unchanged(wiki):
    """A caller holding a live callable behaves exactly as before."""
    path = _eligible_target(wiki, "s-merge-4")

    result = wrap_session("# n", ["the learning"], "s-merge-4",
                          verdicts=[_durable_update()],
                          llm_call=lambda prompt: _MERGED)

    assert [u["page"] for u in result["updated"]] == [_TARGET]
    assert "new line" in path.read_text(encoding="utf-8")


def test_supplied_merge_wins_over_llm_call(wiki):
    """When both are available the pre-computed merge is used — no LLM call."""
    calls = []

    def spy(prompt):
        calls.append(prompt)
        return _MERGED

    _eligible_target(wiki, "s-merge-5")
    wrap_session("# n", ["the learning"], "s-merge-5",
                 verdicts=[_durable_update()], merges=[_MERGED], llm_call=spy)

    assert calls == []


def test_merges_length_mismatch_raises(wiki):
    with pytest.raises(ValueError, match="merges must match durable_items"):
        wrap_session("# n", ["a", "b"], "s-merge-6",
                     verdicts=[_durable_update(), _durable_update()],
                     merges=["only-one"])
