"""
Tests for lib.memory.judge — the LLM pair-judge contract (Task 4, RenOS
0.5.2 prep). No consumers exist yet; this is the contract only.

Every test that touches `collect.record` redirects ren_paths' framework root
to tmp_path via REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/memory/test_judge.py -v
"""

from __future__ import annotations

import pytest

from lib.instrument import collect
from lib.memory.judge import JudgeError, judge_pair, judge_pairs
from lib.ren_paths import wiki_root


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _good_llm(prompt):
    return '{"verdict": "duplicate", "confidence": 0.9, "reason": "same fact reworded"}'


def test_judge_pair_parses_valid_verdict():
    v = judge_pair("Postgres is the db.", "We use Postgres.", _good_llm)
    assert v.kind == "duplicate" and v.confidence == 0.9


def test_judge_pair_rejects_unknown_verdict():
    with pytest.raises(JudgeError):
        judge_pair("a", "b", lambda p: '{"verdict": "maybe", "confidence": 0.5, "reason": "x"}')


def test_judge_pairs_none_llm_is_fail_closed(wiki):  # wiki fixture: collect writes under state_dir
    out = judge_pairs([("a", "b")], None)
    assert out == [None]
    events = collect.read(kind="judge_event")
    assert events[-1]["event"] == "no_llm"


def test_judge_pairs_raising_llm_degrades_per_pair(wiki):
    def boom(prompt):
        raise RuntimeError("api down")

    assert judge_pairs([("a", "b"), ("c", "d")], boom) == [None, None]


def test_judge_pairs_caps_and_records_dropped(wiki):
    pairs = [("a", str(i)) for i in range(12)]
    out = judge_pairs(pairs, _good_llm, cap=10)
    assert len(out) == 12 and out[10] is None and out[11] is None
