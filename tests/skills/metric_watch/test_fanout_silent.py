"""Spec 2026-09-04 §5.5/§9 — items landing with zero candidates for a week
means the scorer or the walk is broken, not that nothing was related."""

from __future__ import annotations

import importlib
import time

import pytest

from lib.instrument import collect

mw = importlib.import_module("skills.metric-watch.lib")


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    (tmp_path / "wiki").mkdir()


def _event(candidates: int, days_ago: int) -> None:
    collect.record(collect.KIND_FANOUT_EVENT, {
        "item": "p.md", "candidates": candidates,
        "verdicts": {"relate": 0, "fact": 0, "none": 0},
        "applied": 0, "held": 0, "unknown_reason": None,
    })


def test_all_zero_candidate_events_fire_the_signal():
    for _ in range(3):
        _event(0, 1)
    assert mw._check_fanout_silent({}) == {"kind": "fan-out-silent", "count": 3, "days": 7}


def test_any_nonzero_candidate_event_silences_it():
    _event(0, 1)
    _event(4, 1)
    assert mw._check_fanout_silent({}) is None


def test_no_events_at_all_is_not_a_finding():
    assert mw._check_fanout_silent({}) is None


def test_watch_includes_the_check():
    for _ in range(2):
        _event(0, 1)
    findings = mw.watch("s1")
    assert any(f["kind"] == "fan-out-silent" for f in findings)


def test_same_silent_window_fires_once_across_runs():
    for _ in range(3):
        _event(0, 1)
    state: dict = {}
    first = mw._check_fanout_silent(state)
    assert first == {"kind": "fan-out-silent", "count": 3, "days": 7}
    assert state.get("last_fanout_ts")
    second = mw._check_fanout_silent(state)
    assert second is None


def test_new_silent_events_after_watermark_fire_again():
    _event(0, 1)
    state: dict = {}
    assert mw._check_fanout_silent(state) is not None
    time.sleep(1.1)
    _event(0, 1)
    assert mw._check_fanout_silent(state) is not None
