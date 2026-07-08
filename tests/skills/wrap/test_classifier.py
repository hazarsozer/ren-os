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
from lib.ren_paths import wiki_root
from skills.wrap.lib.classifier import (
    ClassifierError,
    Decision,
    classify_deterministic,
    classify_llm,
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
