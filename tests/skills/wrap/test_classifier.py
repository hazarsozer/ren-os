"""
Tests for skills.wrap.lib.classifier — the durable-item classifier gate
(Task 4.1).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos (classifier_event metrics get
written there via lib.instrument.collect).

Run with: uv run pytest tests/skills/wrap/test_classifier.py -v
"""

from __future__ import annotations

import json

import pytest

from lib.instrument import collect
from lib.memory.taxonomy import parse_taxonomy
from lib.ren_paths import wiki_root
from skills.wrap.lib.classifier import (
    ClassifierError,
    ConceptPlacementError,
    Decision,
    PlacementError,
    classify_deterministic,
    classify_llm,
    decision_from_data,
    gate,
)


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _json_llm(verdict: str, reason: str = "test reason"):
    def llm_call(prompt: str) -> str:
        return json.dumps({"verdict": verdict, "reason": reason})
    return llm_call


# --- classify_llm: strict parse ---------------------------------------------


@pytest.mark.parametrize("verdict", ["durable", "session-only", "discard"])
def test_classify_llm_valid_verdicts_round_trip(wiki, verdict):
    decision = classify_llm("some item", _json_llm(verdict, reason="because reasons"))
    assert isinstance(decision, Decision)
    assert decision.verdict == verdict
    assert decision.reason == "because reasons"


def test_classify_llm_malformed_json_raises_classifier_error(wiki):
    def llm_call(prompt: str) -> str:
        return "not json at all {{{"
    with pytest.raises(ClassifierError):
        classify_llm("some item", llm_call)


def test_classify_llm_unknown_verdict_raises_classifier_error(wiki):
    def llm_call(prompt: str) -> str:
        return json.dumps({"verdict": "maybe-durable", "reason": "x"})
    with pytest.raises(ClassifierError):
        classify_llm("some item", llm_call)


def test_classify_llm_non_object_json_raises_classifier_error(wiki):
    def llm_call(prompt: str) -> str:
        return json.dumps(["durable"])
    with pytest.raises(ClassifierError):
        classify_llm("some item", llm_call)


def test_classify_llm_recovers_fenced_json(wiki):
    def llm_call(prompt: str) -> str:
        return '```json\n{"verdict": "discard", "reason": "noise"}\n```'
    decision = classify_llm("some item", llm_call)
    assert decision.verdict == "discard"


def test_classify_llm_recovers_trailing_prose_and_still_returns_durable(wiki):
    """Regression: a chatty sign-off after valid JSON must not degrade the
    gate to the never-durable deterministic fallback."""
    def llm_call(prompt: str) -> str:
        return '{"verdict": "durable", "reason": "genuine lesson"}\nHope this helps!'
    decision = classify_llm("some item", llm_call)
    assert decision.verdict == "durable"


def test_gate_recovers_trailing_prose_and_still_returns_durable(wiki):
    def llm_call(prompt: str) -> str:
        return '{"verdict": "durable", "reason": "genuine lesson"}\nHope this helps!'
    decision = gate("some item", llm_call)
    assert decision.verdict == "durable"


# --- classify_deterministic: never raises, never durable -------------------


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "   \n\t  ",
        "x" * 200_000,
        "!@#$%^&*()_+ 日本語 emoji 🎉🎉🎉" * 500,
    ],
)
def test_classify_deterministic_never_raises_and_never_durable(garbage):
    decision = classify_deterministic(garbage)
    assert isinstance(decision, Decision)
    assert decision.verdict in ("session-only", "discard")
    assert decision.verdict != "durable"


def test_classify_deterministic_non_str_input_never_raises():
    decision = classify_deterministic(None)  # type: ignore[arg-type]
    assert decision.verdict == "discard"


# --- gate: happy path + fail-closed ------------------------------------------


def test_gate_happy_path_returns_llm_decision(wiki):
    decision = gate("a genuine durable lesson", _json_llm("durable", "clearly reusable"))
    assert decision.verdict == "durable"
    assert decision.reason == "clearly reusable"


def test_gate_fail_closed_on_crashing_llm_call_records_event_and_falls_back(wiki):
    def crashing_llm(prompt: str) -> str:
        raise RuntimeError("llm backend unavailable")

    before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    decision = gate("some item", crashing_llm)
    after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    assert decision.verdict in ("session-only", "discard")
    new_events = after[len(before):]
    assert any(e.get("event") == "fail_closed" for e in new_events)


def test_gate_fail_closed_on_malformed_llm_output_records_event_and_falls_back(wiki):
    def bad_llm(prompt: str) -> str:
        return "garbage, not json"

    before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    decision = gate("some item", bad_llm)
    after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    assert decision.verdict != "durable"
    new_events = after[len(before):]
    assert any(e.get("event") == "fail_closed" for e in new_events)


def test_gate_with_no_llm_call_goes_deterministic_and_records_event(wiki):
    before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    decision = gate("some item", None)
    after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    assert decision.verdict != "durable"
    new_events = after[len(before):]
    assert len(new_events) == 1
    assert new_events[0]["event"] == "no_llm"


def test_classifier_event_preview_redacts_secret_shaped_content(wiki):
    """Defense-in-depth: a secret in a gated item must never reach the
    metrics JSONL, even truncated (an 80-char preview fits a whole AWS key)."""
    from lib.instrument import collect

    secret_item = 'aws creds: AKIAIOSFODNN7EXAMPLE should never leak'

    def crashing_llm(prompt):
        raise RuntimeError("boom")

    gate(secret_item, llm_call=crashing_llm)
    events = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    assert events, "expected a fail_closed event"
    preview = events[-1]["item_preview"]
    assert "AKIAIOSFODNN7EXAMPLE" not in preview
    assert preview == "<redacted: secret-shaped content>"


# --- v2: scope / action / target_page -------------------------------------------


def _llm(payload: dict):
    return lambda prompt: json.dumps(payload)


def test_decision_v2_defaults_are_create_global():
    d = Decision(verdict="durable", reason="r")
    assert d.scope == "global" and d.action == "create" and d.target_page is None


def test_classify_llm_accepts_update_to_eligible_target(wiki):
    from skills.wrap.lib.classifier import VALID_SCOPES, VALID_ACTIONS
    d = classify_llm(
        "we learned X about the damage formula",
        _llm({"verdict": "durable", "reason": "reusable", "scope": "project",
              "action": "update", "target_page": "projects/p/knowledge/a.md"}),
        eligible_targets=("projects/p/knowledge/a.md",), project="p",
    )
    assert d.action == "update" and d.target_page == "projects/p/knowledge/a.md"


def test_classify_llm_rejects_target_outside_eligibility_set(wiki):
    with pytest.raises(ClassifierError):
        classify_llm(
            "item", _llm({"verdict": "durable", "reason": "r", "scope": "project",
                          "action": "update", "target_page": "projects/p/knowledge/other.md"}),
            eligible_targets=("projects/p/knowledge/a.md",), project="p",
        )


def test_classify_llm_rejects_update_with_null_target(wiki):
    with pytest.raises(ClassifierError):
        classify_llm(
            "item", _llm({"verdict": "durable", "reason": "r", "scope": "global",
                          "action": "update", "target_page": None}),
            eligible_targets=("a.md",),
        )


def test_classify_llm_rejects_create_with_target(wiki):
    with pytest.raises(ClassifierError):
        classify_llm(
            "item", _llm({"verdict": "durable", "reason": "r", "scope": "global",
                          "action": "create", "target_page": "a.md"}),
            eligible_targets=("a.md",),
        )


def test_classify_llm_rejects_unknown_scope_or_action(wiki):
    with pytest.raises(ClassifierError):
        classify_llm("item", _llm({"verdict": "durable", "reason": "r",
                                   "scope": "universe", "action": "create",
                                   "target_page": None}))


def test_classify_llm_missing_v2_fields_defaults_create_global(wiki):
    # Back-compat: a bare {"verdict","reason"} answer still parses.
    d = classify_llm("item", _llm({"verdict": "session-only", "reason": "r"}))
    assert d.action == "create" and d.scope == "global" and d.target_page is None


def test_gate_propagates_placement_error_instead_of_discarding(wiki):
    """M5+M7 fix: `gate()` used to swallow a `PlacementError` into the
    deterministic fallback, which silently DISCARDED a durable item
    (`classify_deterministic` can only return "session-only"/"discard",
    never "durable") instead of keeping it — spec §4 says the fact is
    kept, routing failed, not durability. `gate()` now PROPAGATES
    `PlacementError` (mirroring `gate_precomputed`) so the caller routes it
    to `unplaced`/suggestions instead of losing it."""
    with pytest.raises(PlacementError):
        gate("item", _llm({"verdict": "durable", "reason": "r", "scope": "global",
                           "action": "update", "target_page": "not-eligible.md"}),
             eligible_targets=("a.md",))


# --- v3: kind / placement / title (concept-tree routing) --------------------


TAX = parse_taxonomy("```taxonomy\narchitecture/\n  memory-plane/\n```\n")


def _durable(**kw):
    return {"verdict": "durable", "reason": "r", "scope": "project",
            "action": "create", "target_page": None, **kw}


def test_kind_defaults_to_lesson():
    d = decision_from_data(_durable(), taxonomy=TAX)
    assert d.kind == "lesson" and d.placement is None


def test_concept_existing_node():
    d = decision_from_data(
        _durable(kind="concept", placement="architecture/memory-plane"),
        taxonomy=TAX)
    assert d.kind == "concept" and d.placement == "architecture/memory-plane"


def test_concept_new_leaf_needs_title():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(
            _durable(kind="concept", placement="architecture/write-door"),
            taxonomy=TAX)
    d = decision_from_data(
        _durable(kind="concept", placement="architecture/write-door",
                 title="Write Door"),
        taxonomy=TAX)
    assert d.title == "Write Door"


def test_concept_without_taxonomy_routes_to_fallback():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(_durable(kind="concept",
                                    placement="architecture"), taxonomy=None)


def test_concept_bad_placement():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(
            _durable(kind="concept", placement="missing/child"), taxonomy=TAX)


def test_global_concept_rejected():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(
            _durable(kind="concept", placement="architecture",
                     scope="global"), taxonomy=TAX)


def test_lesson_with_placement_rejected():
    with pytest.raises(Exception):
        decision_from_data(_durable(kind="lesson", placement="architecture"),
                           taxonomy=TAX)


def test_gate_propagates_concept_placement_error(wiki):
    """M5+M7 fix: an invalid CONCEPT placement (here: a global-scope
    concept, disallowed — no global taxonomy) must PROPAGATE out of
    `gate()` as `ConceptPlacementError`, not get swallowed into the
    deterministic fallback (which would discard the item as
    "session-only" instead of keeping it as a lesson, per spec §4)."""
    with pytest.raises(ConceptPlacementError):
        gate(
            "item",
            _llm({"verdict": "durable", "reason": "r", "scope": "global",
                  "action": "create", "target_page": None,
                  "kind": "concept", "placement": "architecture", "title": None}),
            taxonomy=TAX,
        )


# --- C2: taxonomy_block actually reaches the prompt -------------------------


def test_build_classifier_prompt_substitutes_taxonomy_block_when_given():
    from skills.wrap.lib.classifier import _NO_TAXONOMY_BLOCK, build_classifier_prompt

    prompt = build_classifier_prompt(
        "an item", taxonomy_block="architecture/\n  memory-plane/\n",
    )
    assert "architecture/" in prompt
    assert "memory-plane/" in prompt
    assert _NO_TAXONOMY_BLOCK not in prompt


def test_build_classifier_prompt_falls_back_to_no_taxonomy_block_when_omitted():
    from skills.wrap.lib.classifier import _NO_TAXONOMY_BLOCK, build_classifier_prompt

    prompt = build_classifier_prompt("an item")
    assert _NO_TAXONOMY_BLOCK in prompt
