"""
Tests for lib.instrument.estimator — calibrated token estimator (Task 3.2).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/instrument/test_estimator.py -v
"""

from __future__ import annotations

import json
import math

import pytest

from lib.instrument import estimator
from lib.ren_paths import state_dir, wiki_root


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def isolated_state(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    wiki_root().mkdir(parents=True, exist_ok=True)
    return tmp_path


def _estimator_path():
    return state_dir() / "metrics" / "estimator.json"


# ------------------------------------------------------------- estimate_tokens


def test_default_ratio_when_no_file(isolated_state):
    text = "a" * 40
    assert estimator.estimate_tokens(text) == math.ceil(40 / estimator.DEFAULT_CHARS_PER_TOKEN)


def test_estimate_uses_stored_ratio(isolated_state):
    path = _estimator_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"chars_per_token": 2.0, "samples": 5, "updated": "2026-01-01T00:00:00Z"}), encoding="utf-8")

    assert estimator.estimate_tokens("aaaa") == math.ceil(4 / 2.0)


def test_corrupt_estimator_file_falls_back_to_default_no_raise(isolated_state):
    path = _estimator_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json at all {{{", encoding="utf-8")

    result = estimator.estimate_tokens("aaaa")
    assert result == math.ceil(4 / estimator.DEFAULT_CHARS_PER_TOKEN)


def test_malformed_estimator_shape_falls_back_to_default(isolated_state):
    path = _estimator_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")

    result = estimator.estimate_tokens("aaaa")
    assert result == math.ceil(4 / estimator.DEFAULT_CHARS_PER_TOKEN)


def test_non_positive_stored_ratio_falls_back_to_default(isolated_state):
    path = _estimator_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"chars_per_token": 0.0, "samples": 3, "updated": "x"}), encoding="utf-8")

    result = estimator.estimate_tokens("aaaa")
    assert result == math.ceil(4 / estimator.DEFAULT_CHARS_PER_TOKEN)


# ---------------------------------------------------------------- calibrate


def test_calibrate_first_batch_matches_batch_ratio(isolated_state):
    samples = [("a" * 400, 100)]
    ratio = estimator.calibrate(samples)

    assert ratio == pytest.approx(4.0)

    on_disk = json.loads(_estimator_path().read_text(encoding="utf-8"))
    assert on_disk["chars_per_token"] == pytest.approx(4.0)
    assert on_disk["samples"] == 1


def test_calibrate_second_batch_blends_by_sample_count(isolated_state):
    estimator.calibrate([("a" * 400, 100)])  # ratio 4.0, samples=1

    ratio = estimator.calibrate([("b" * 600, 300)])  # batch ratio 2.0, weight 1

    # blended = (4.0*1 + 2.0*1) / (1+1) = 3.0
    assert ratio == pytest.approx(3.0)

    on_disk = json.loads(_estimator_path().read_text(encoding="utf-8"))
    assert on_disk["chars_per_token"] == pytest.approx(3.0)
    assert on_disk["samples"] == 2


def test_calibrate_persistence_round_trip_feeds_estimate_tokens(isolated_state):
    estimator.calibrate([("a" * 800, 200)])  # ratio 4.0

    estimator.calibrate([("b" * 100, 50)])  # batch ratio 2.0, weight 1
    # blended = (4.0*1 + 2.0*1)/2 = 3.0
    assert estimator.estimate_tokens("c" * 30) == math.ceil(30 / 3.0)


def test_calibrate_rejects_empty_samples(isolated_state):
    with pytest.raises(ValueError):
        estimator.calibrate([])


@pytest.mark.parametrize("bad_tokens", [0, -1, -100])
def test_calibrate_rejects_non_positive_reported_tokens(isolated_state, bad_tokens):
    with pytest.raises(ValueError):
        estimator.calibrate([("some text", bad_tokens)])


def test_calibrate_multi_pair_batch_uses_combined_totals(isolated_state):
    # total_chars = 100 + 200 = 300; total_tokens = 50 + 50 = 100 -> batch_ratio = 3.0
    ratio = estimator.calibrate([("x" * 100, 50), ("y" * 200, 50)])
    assert ratio == pytest.approx(3.0)

    on_disk = json.loads(_estimator_path().read_text(encoding="utf-8"))
    assert on_disk["samples"] == 2  # two pairs in this batch, weight = len(samples)
