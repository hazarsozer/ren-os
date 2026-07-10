"""
Tests for skills.wrap.lib.harvest_suggestions (Task 20, RenOS 0.4.2).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/wrap/test_harvest_suggestions.py -v
"""

from __future__ import annotations

import pytest

from lib.ren_paths import wiki_root
from lib.suggestions import SuggestionSpec, _persist, get_suggestion, pending_suggestions, record
from skills.wrap.lib import harvest_suggestions


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


def _spec(producer: str, n: int) -> SuggestionSpec:
    return SuggestionSpec(
        producer=producer,
        title=f"{producer} suggestion {n}",
        rationale="test",
        evidence={},
        kind="structured_action",
        payload={"action": "noop"},
        fingerprint=f"{producer}:{n}",
    )


def test_harvest_records_all_three_producers(wiki, monkeypatch):
    import skills.wrap.lib as wrap_lib

    monkeypatch.setattr(wrap_lib, "promotion_candidates", lambda: [_spec("promotion", 1)])
    monkeypatch.setattr(wrap_lib, "doctrine_shaping", lambda: [_spec("doctrine", 1)])
    monkeypatch.setattr(wrap_lib, "wiki_health_critical", lambda sweep_result: [_spec("wiki-health", 1)])
    monkeypatch.setattr(wrap_lib, "_run_wiki_health_sweep", lambda: {})

    count = harvest_suggestions(session="sess-1")

    assert count == 3


def test_harvest_one_producer_raising_does_not_starve_others(wiki, monkeypatch):
    import skills.wrap.lib as wrap_lib

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(wrap_lib, "promotion_candidates", _boom)
    monkeypatch.setattr(wrap_lib, "doctrine_shaping", lambda: [_spec("doctrine", 1)])
    monkeypatch.setattr(wrap_lib, "wiki_health_critical", lambda sweep_result: [_spec("wiki-health", 1)])
    monkeypatch.setattr(wrap_lib, "_run_wiki_health_sweep", lambda: {})

    count = harvest_suggestions(session="sess-1")

    assert count == 2


def test_harvest_never_raises_when_sweep_itself_fails(wiki, monkeypatch):
    import skills.wrap.lib as wrap_lib

    monkeypatch.setattr(wrap_lib, "promotion_candidates", lambda: [_spec("promotion", 1)])
    monkeypatch.setattr(wrap_lib, "doctrine_shaping", lambda: [_spec("doctrine", 1)])
    monkeypatch.setattr(wrap_lib, "wiki_health_critical", lambda sweep_result: [_spec("wiki-health", 1)])

    def _sweep_boom():
        raise RuntimeError("sweep boom")

    monkeypatch.setattr(wrap_lib, "_run_wiki_health_sweep", _sweep_boom)

    count = harvest_suggestions(session="sess-1")

    # promotion + doctrine still recorded; wiki-health producer never even called
    assert count == 2


def test_harvest_returns_count_of_non_none_records_only(wiki, monkeypatch):
    """A duplicate fingerprint's record() call returns None (never re-nag) —
    that must not count toward the returned total."""
    import skills.wrap.lib as wrap_lib

    spec = _spec("promotion", 1)
    monkeypatch.setattr(wrap_lib, "promotion_candidates", lambda: [spec, spec])
    monkeypatch.setattr(wrap_lib, "doctrine_shaping", lambda: [])
    monkeypatch.setattr(wrap_lib, "wiki_health_critical", lambda sweep_result: [])
    monkeypatch.setattr(wrap_lib, "_run_wiki_health_sweep", lambda: {})

    count = harvest_suggestions(session="sess-1")

    assert count == 1


def test_harvest_expires_stale_pending_suggestions(wiki, monkeypatch):
    import skills.wrap.lib as wrap_lib

    monkeypatch.setattr(wrap_lib, "promotion_candidates", lambda: [])
    monkeypatch.setattr(wrap_lib, "doctrine_shaping", lambda: [])
    monkeypatch.setattr(wrap_lib, "wiki_health_critical", lambda sweep_result: [])
    monkeypatch.setattr(wrap_lib, "_run_wiki_health_sweep", lambda: {})

    stale = record(_spec("promotion", 99))
    stored = get_suggestion(stale["sid"])
    stored["ts"] = "2020-01-01T00:00:00Z"
    _persist(stored)

    harvest_suggestions(session="sess-1")

    assert pending_suggestions() == []
