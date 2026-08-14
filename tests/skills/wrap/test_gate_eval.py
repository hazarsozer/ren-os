"""
Wires skills.wrap.lib.classifier.gate into lib.evalkit.runner.run_gate_eval
over skills/wrap/eval_cases.json (Task 4.1). This is exit criterion 4's CI
demonstration: "the wrap classifier's eval passes and demonstrably gates —
including fail-closed behavior — before it ships as the write gate."

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/wrap/test_gate_eval.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.evalkit.runner import run_gate_eval
from lib.ren_paths import wiki_root
from skills.wrap.lib.classifier import gate

EVAL_CASES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "wrap" / "eval_cases.json"


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


def _load_cases() -> list[dict]:
    data = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))
    return data["cases"]


def _gate_fn(llm_call):
    """Adapt classifier.gate's 3-way Decision into evalkit's accept/refuse
    vocabulary: only "durable" is an "accept"; "session-only"/"discard" both
    refuse (durable memory is the thing being gated)."""
    def _fn(input_text: str) -> str:
        decision = gate(input_text, llm_call)
        return "accept" if decision.verdict == "durable" else "refuse"
    return _fn


def test_eval_cases_file_has_at_least_ten_cases():
    cases = _load_cases()
    assert len(cases) >= 10
    for case in cases:
        assert case["expect"] in ("accept", "refuse")


def test_gate_eval_passes_with_a_correct_llm_stub(wiki):
    cases = _load_cases()

    def correct_llm(prompt: str) -> str:
        for case in cases:
            if case["input"] in prompt:
                verdict = "durable" if case["expect"] == "accept" else "discard"
                return json.dumps({"verdict": verdict, "reason": "stub"})
        return json.dumps({"verdict": "discard", "reason": "unmatched"})

    report = run_gate_eval(_gate_fn(correct_llm), cases)

    assert report.total == len(cases)
    assert report.hits == len(cases)
    assert report.hit_rate == 1.0
    assert report.failures == []


def test_gate_eval_with_crashing_llm_accept_cases_fail_refuse_cases_pass(wiki):
    cases = _load_cases()

    def crashing_llm(prompt: str) -> str:
        raise RuntimeError("llm backend unavailable")

    report = run_gate_eval(_gate_fn(crashing_llm), cases)

    accept_cases = [c for c in cases if c["expect"] == "accept"]
    refuse_cases = [c for c in cases if c["expect"] == "refuse"]
    assert accept_cases and refuse_cases  # sanity: fixture actually has both

    # Fail-closed contract: every accept-case fails (fallback never returns
    # durable), every refuse-case passes.
    assert report.hits == len(refuse_cases)
    assert len(report.failures) == len(accept_cases)
    for failure in report.failures:
        assert failure["expected"] == "accept"


def test_v2_cases_assert_verdict_scope_action_and_target(wiki):
    """Cases carrying "expect_verdict" (Task 8) exercise Task 1's v2 Decision
    fields (scope/action/target_page), which `run_gate_eval`'s generic
    accept/refuse scoring (lib.evalkit.runner) deliberately can't see — that
    runner stays a plain accept/refuse gate scorer shared by every LLM-gated
    path, not just wrap's. So this test calls `gate()` directly, per case,
    with a stub LLM that returns exactly that case's expected v2 fields, and
    asserts the full Decision — not just the accept/refuse collapse.
    """
    cases = [c for c in _load_cases() if "expect_verdict" in c]
    assert cases  # sanity: fixture actually carries v2 cases

    for case in cases:
        expected_verdict = case["expect_verdict"]
        expected_scope = case.get("expect_scope", "global")
        expected_action = case.get("expect_action", "create")
        expected_target = case.get("expect_target")
        eligible_targets = tuple(case.get("eligible_targets", ()))
        project = case.get("project")

        def stub_llm(prompt: str, _case=case, _v=expected_verdict,
                      _s=expected_scope, _a=expected_action, _t=expected_target) -> str:
            payload = {"verdict": _v, "reason": "stub"}
            if _v == "durable":
                payload.update({"scope": _s, "action": _a, "target_page": _t})
            return json.dumps(payload)

        decision = gate(case["input"], stub_llm, eligible_targets=eligible_targets, project=project)

        assert decision.verdict == expected_verdict, case
        if expected_verdict == "durable":
            assert decision.scope == expected_scope, case
            assert decision.action == expected_action, case
            assert decision.target_page == expected_target, case


def test_gate_eval_crashing_llm_records_fail_closed_events(wiki):
    from lib.instrument import collect

    cases = _load_cases()

    def crashing_llm(prompt: str) -> str:
        raise RuntimeError("llm backend unavailable")

    before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    run_gate_eval(_gate_fn(crashing_llm), cases)
    after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    new_events = after[len(before):]
    fail_closed_events = [e for e in new_events if e.get("event") == "fail_closed"]
    assert len(fail_closed_events) == len(cases)
