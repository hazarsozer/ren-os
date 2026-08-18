import pytest

from lib import suggestions
from lib.instrument import collect
from skills.wrap.lib import wrap_session


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    (tmp_path / "wiki").mkdir()
    return tmp_path / "wiki"


def _durable_create(scope="global"):
    return {"verdict": "durable", "reason": "r", "scope": scope,
            "action": "create", "target_page": None}


def test_verdicts_length_mismatch_raises(wiki):
    with pytest.raises(ValueError):
        wrap_session("# n", ["one item"], "s1", verdicts=[])


def test_index_keyed_verdicts_apply(wiki):
    result = wrap_session(
        "# n", ["keep me", "drop me"], "s2",
        verdicts=[_durable_create(),
                  {"verdict": "discard", "reason": "noise", "scope": "global",
                   "action": "create", "target_page": None}],
    )
    assert len(result["applied"]) == 1
    assert [g["item"] for g in result["gated_out"]] == ["drop me"]
    outcome = collect.read(kind=collect.KIND_DURABLE_OUTCOME)[-1]
    assert outcome["producer"] == "wrap"


def test_placement_error_routes_to_suggestions_not_discard(wiki):
    bad = {"verdict": "durable", "reason": "r", "scope": None,
           "action": "create", "target_page": None}
    result = wrap_session("# n", ["orphan learning"], "s3", verdicts=[bad])
    assert result["gated_out"] == []
    assert len(result["unplaced"]) == 1
    assert result["unplaced"][0]["item"] == "orphan learning"
    pending = suggestions.pending_suggestions()
    assert any(s["payload"].get("action") == "place_durable_item" for s in pending)


def test_no_classifier_routes_candidates_to_suggestions(wiki):
    # durable_items present, no verdicts, no llm_call: die loudly.
    result = wrap_session("# n", ["a learning"], "s4")
    assert result["gated_out"] == []          # not silently discarded
    assert result["applied"] == []            # and not auto-written
    assert len(result["unplaced"]) == 1
    events = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    assert events[-1]["event"] == "no_llm"    # defect signal preserved


def test_no_items_no_side_effects(wiki):
    result = wrap_session("# n", [], "s5")
    assert result["unplaced"] == []
